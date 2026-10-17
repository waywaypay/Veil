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
as they came.

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
finds is taken out, and a reply it objects to is replaced with a note.

Streaming isn't supported yet: ``stream=True`` raises.
"""

from __future__ import annotations

import base64
import copy
import hashlib
from dataclasses import dataclass, field
from typing import Any, Callable

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
                 files: str | Callable[[bytes, str], str] = "refuse"):
        self.redactor = redactor if redactor is not None else Redactor()
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
        return out

    def _message(self, message: dict) -> dict:
        role = message.get("role")
        content = message.get("content")
        if isinstance(content, str):
            return {**message, "content": self.redactor.redact_text(content, typed=role == "user")}
        return {**message, "content": [self._block(b, role) for b in content or []]}

    def _block(self, block: Any, role: str | None) -> Any:
        b = _as_dict(block)
        if not isinstance(b, dict):
            return block
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
        return b   # thinking and the like: as they are

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
            self._guard_reply(content)
        for i, block in enumerate(content):
            kind = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
            if kind == "text":
                self._set(content, i, block, "text", self.redactor.restore_text(self._get(block, "text")))
            elif kind == "tool_use":
                self._set(content, i, block, "input", self.redactor.restore(self._get(block, "input")))
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

    @staticmethod
    def _get(block: Any, key: str) -> Any:
        return block.get(key) if isinstance(block, dict) else getattr(block, key, None)

    @staticmethod
    def _set(content: list, i: int, block: Any, key: str, value: Any) -> None:
        if isinstance(block, dict):
            content[i] = {**block, key: value}
        else:
            setattr(block, key, value)


class _Messages:
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

    def __getattr__(self, name):
        return getattr(self._messages, name)


class _Beta:
    def __init__(self, beta, session: Session):
        self._beta = beta
        self.messages = _Messages(beta.messages, session)

    def __getattr__(self, name):
        return getattr(self._beta, name)


class VeiledClient:
    """An Anthropic client whose ``messages.create`` (and ``beta.messages.create``) go through placeholders."""

    def __init__(self, client, session: Session):
        self._client = client
        self.session = session
        self.messages = _Messages(client.messages, session)
        if hasattr(client, "beta"):
            self.beta = _Beta(client.beta, session)

    @property
    def redactor(self) -> Redactor:
        return self.session.redactor

    def __getattr__(self, name):
        return getattr(self._client, name)


def wrap(client, redactor: Redactor | None = None, guardrail=None, redact_system: bool = True,
         files: str | Callable[[bytes, str], str] = "refuse") -> VeiledClient:
    """``client`` (anthropic.Anthropic, AnthropicBedrock ...) with placeholders on the way out and real values
    on the way back.  Use one per conversation, or pass the conversation's ``redactor``.

    ``files`` says what happens to images and PDFs: "refuse" the request (the default), "read" their text
    here and send it redacted instead, "send" them as they are, or a function ``(data, media_type) -> text`` to read them."""
    return VeiledClient(client, Session(redactor, guardrail, redact_system, files))
