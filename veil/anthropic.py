"""Claude through placeholders: wrap an Anthropic client and the model never sees personal information.

    import anthropic
    from veil import Redactor, FINANCE
    from veil.anthropic import wrap

    client = wrap(anthropic.Anthropic(), Redactor(FINANCE))
    client.redactor.add_person("Avery K. Mockridge")      # people you already know of
    reply = client.messages.create(model="claude-opus-5-5", max_tokens=1024, tools=TOOLS,
                                   messages=[{"role": "user", "content": "Add Avery Mockridge as an LP"}])

You keep the conversation with real values in it, as you would without veil.
On the way out, ``messages.create`` sends a copy with each one replaced by a
placeholder (NAME_001, SSN_001 ...): what the user typed, each tool result,
the system prompt, and the model's own earlier turns.  On the way back, the
reply's text and each tool call's input have the real values put back, so
the tools you run get "Avery K. Mockridge", not NAME_001.  The same value
keeps the same placeholder for as long as you use the same redactor, so use
one per conversation.

What's redacted: text, tool results (text and JSON), and tool calls.  Images
and PDFs sent as files are passed through as they are: send their text
instead.  Thinking blocks go back exactly as they came (the API checks
them), and they only ever held placeholders.

With a ``guardrail`` (``veil.bedrock.BedrockGuardrail`` or anything with the
same ``check`` method), each new text in a request is checked before it's
sent: what it finds that the placeholders missed becomes a placeholder too,
and anything else it objects to, or a guardrail that can't be reached, raises
GuardrailError and nothing is sent.  The reply is checked too: a taxpayer ID
in it is taken out (the model only saw placeholders, so it shouldn't have
written one), other personal information it finds stays for the user but is
hidden from then on, and a reply it objects to is replaced with a note.

Streaming isn't supported yet: ``stream=True`` raises.
"""

from __future__ import annotations

import copy
import hashlib
from typing import Any

from veil.bedrock import GuardrailError, what
from veil.redactor import Redactor
from veil.tax_ids import TAX_ID_KINDS

TAX_ID_REMOVED = "[taxpayer ID removed]"


def _as_dict(block: Any) -> Any:
    if isinstance(block, dict):
        return dict(block)
    if hasattr(block, "model_dump"):
        return block.model_dump(mode="json", exclude_none=True)
    return block


class Session:
    """One conversation's redactor and guardrail, and the request and reply handling ``wrap`` uses."""

    def __init__(self, redactor: Redactor | None = None, guardrail=None, redact_system: bool = True):
        self.redactor = redactor if redactor is not None else Redactor()
        self.guardrail = guardrail
        self.redact_system = redact_system
        self._checked: set[str] = set()   # digests of texts the guardrail has passed

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
        if kind == "document" and isinstance(b.get("source"), dict) and b["source"].get("type") == "text":
            return {**b, "source": {**b["source"], "data": r.redact_text(b["source"].get("data", ""))}}
        return b   # thinking, images, files: as they are

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


def wrap(client, redactor: Redactor | None = None, guardrail=None, redact_system: bool = True) -> VeiledClient:
    """``client`` (anthropic.Anthropic, AnthropicBedrock ...) with placeholders on the way out and real values
    on the way back.  Use one per conversation, or pass the conversation's ``redactor``."""
    return VeiledClient(client, Session(redactor, guardrail, redact_system))
