"""OpenAI's Chat Completions through placeholders: the request's personal information is swapped for placeholders
before it's sent, and the reply comes back with the real values.

    from veil import Redactor, FINANCE
    from veil.openai import ChatSession

    session = ChatSession(Redactor(FINANCE), restore={"add_member": "all"})   # one per conversation
    sent = session.redact_request(request)            # a Chat Completions request body, as a dict
    reply = session.restore_response(response_json)   # the API's reply, as a dict

``veil.gateway`` uses this for ``POST /v1/chat/completions``, so any client of the Chat Completions API (OpenAI's
own, or another provider's compatible one) can go through it.

What's redacted: every message's text (``content`` as a string or as text parts, a ``refusal``), a message's
``name``, the arguments of earlier tool calls (``tool_calls`` and the older ``function_call``), the tools' and
``response_format``'s descriptions, ``prediction``, ``metadata`` and the ``user`` / ``safety_identifier`` fields.
Web search's ``user_location`` goes with its country and timezone only, as with ``veil.anthropic``.

In the reply, each choice's text and ``refusal`` come back with real values (outside URLs), and a tool call's
arguments get real values only for the tools ``restore`` names, as with ``veil.anthropic.wrap``.

Images, audio and files are refused (``FileError``) unless ``files`` says otherwise: ``"read"`` reads an inline
(``data:``) image or file's text on this machine and sends that, redacted, in its place; ``"send"`` sends them as
they are.  A content part of a kind veil doesn't know raises ``BlockError``.  Streaming isn't supported: a request
with ``stream: true`` raises ``NotImplementedError``.
"""

from __future__ import annotations

import base64
import binascii
import copy
import json
from typing import Any, Callable, Collection, Mapping

from veil.anthropic import BlockError, FileError
from veil.redactor import Redactor

_FILE_PARTS = {"image_url", "input_audio", "file"}


class ChatSession:
    """One conversation's redactor, and the Chat Completions request and reply handling."""

    def __init__(self, redactor: Redactor | None = None,
                 restore: Mapping[str, Collection[str] | str | None] | str | None = None,
                 files: str | Callable[[bytes, str], str] = "refuse", user_location: str = "country"):
        self.redactor = redactor if redactor is not None else Redactor()
        if isinstance(restore, str) and restore != "all":
            raise ValueError('restore must be "all" or {tool name: kinds}')
        # The kinds each tool's calls get back, by tool name ("*": any other tool); None: every kind.
        self.restore = {"*": None} if restore == "all" else {
            name: None if kinds is None or kinds == "all" else {kinds} if isinstance(kinds, str) else set(kinds)
            for name, kinds in (restore or {}).items()}
        if files == "read":
            from veil.files import read_text
            files = read_text
        elif files not in ("send", "refuse") and not callable(files):
            raise ValueError('files must be "send", "read", "refuse" or a function (data, media_type) -> text')
        self.files = files
        if user_location not in ("country", "send", "drop"):
            raise ValueError('user_location must be "country", "send" or "drop"')
        self.user_location = user_location

    # -- requests ----------------------------------------------------------------------------------------

    def redact_request(self, request: dict) -> dict:
        """A copy of a Chat Completions request with placeholders in it."""
        if request.get("stream"):
            raise NotImplementedError("veil doesn't redact streamed replies yet; send the request without "
                                      "stream: true.")
        r = self.redactor
        out = dict(request)
        out["messages"] = [self._message(m) for m in request.get("messages") or []]
        for key in ("tools", "functions", "response_format"):
            if key in request:
                out[key] = self._descriptions(request[key])
        if isinstance(request.get("prediction"), dict):
            p = request["prediction"]
            out["prediction"] = {**p, "content": self._content(p.get("content"), None)}
        if isinstance(request.get("metadata"), dict):
            out["metadata"] = r.redact(request["metadata"])
        for key in ("user", "safety_identifier"):
            if isinstance(request.get(key), str):
                out[key] = r.redact_text(request[key])
        if isinstance(request.get("web_search_options"), dict):
            out["web_search_options"] = self._located(request["web_search_options"])
        return out

    def _message(self, message: Any) -> dict:
        if not isinstance(message, dict):
            raise BlockError(f"veil can't redact a message given as {type(message).__name__}. Nothing was sent.")
        r = self.redactor
        role = message.get("role")
        m = dict(message)
        if "content" in m:
            m["content"] = self._content(m["content"], role)
        if isinstance(m.get("refusal"), str):
            m["refusal"] = r.redact_text(m["refusal"])
        if isinstance(m.get("name"), str):
            m["name"] = r.redact_text(m["name"])
        if isinstance(m.get("tool_calls"), list):
            m["tool_calls"] = [self._call(c) for c in m["tool_calls"]]
        if isinstance(m.get("function_call"), dict):
            m["function_call"] = self._function(m["function_call"])
        return m

    def _content(self, content: Any, role: str | None) -> Any:
        r = self.redactor
        if isinstance(content, str):
            return r.redact_text(content, typed=role == "user")
        if isinstance(content, list):
            return [self._part(p, role) for p in content]
        return content   # None, for an assistant turn that only calls tools

    def _part(self, part: Any, role: str | None) -> dict:
        if not isinstance(part, dict):
            raise BlockError(f"veil can't redact a content part given as {type(part).__name__}. Nothing was sent.")
        kind = part.get("type")
        if kind == "text":
            return {**part, "text": self.redactor.redact_text(part.get("text", ""), typed=role == "user")}
        if kind == "refusal":
            return {**part, "refusal": self.redactor.redact_text(part.get("refusal", ""))}
        if kind in _FILE_PARTS:
            return self._file(part)
        raise BlockError(f"veil doesn't know how to redact a {kind!r} content part, so it would have reached the "
                         "model as it is. Nothing was sent.")

    def _file(self, part: dict) -> dict:
        """An image, audio or file part, as ``files`` says: as it is, or its text redacted in its place."""
        if self.files == "send":
            return part
        kind = part["type"]
        if self.files == "refuse":
            raise FileError(f"This request has {'an image' if kind == 'image_url' else 'a file' if kind == 'file' else 'audio'} "
                            "in it, which would reach the model with whatever is in it. Nothing was sent. Read its "
                            "text first (files=\"read\"), or send it as it is (files=\"send\").")
        url = (part.get("image_url") or {}).get("url") if kind == "image_url" else \
            (part.get("file") or {}).get("file_data") if kind == "file" else None
        data, media_type = _data_url(url) if isinstance(url, str) else (None, None)
        if data is None:
            raise FileError("This request has audio, a file given by ID, or an image given by a web address, which "
                            "veil can't read here. Nothing was sent. Send its bytes inline as a data: URL, or send "
                            "it as it is (files=\"send\").")
        return {"type": "text", "text": self.redactor.redact_text(self.files(data, media_type))}

    def _call(self, call: Any) -> Any:
        if isinstance(call, dict) and isinstance(call.get("function"), dict):
            return {**call, "function": self._function(call["function"])}
        return call

    def _function(self, fn: dict) -> dict:
        args = fn.get("arguments")
        if not isinstance(args, str):
            return fn
        try:
            return {**fn, "arguments": json.dumps(self.redactor.redact(json.loads(args)))}
        except ValueError:
            return {**fn, "arguments": self.redactor.redact_text(args)}

    def _descriptions(self, value: Any) -> Any:
        """``value`` with each ``description`` in it redacted (a tool's, or one in a JSON schema)."""
        if isinstance(value, dict):
            return {k: self.redactor.redact_text(v) if k == "description" and isinstance(v, str)
                    else self._descriptions(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._descriptions(v) for v in value]
        return value

    def _located(self, options: dict) -> dict:
        loc = options.get("user_location")
        if not isinstance(loc, dict) or self.user_location == "send":
            return options
        if self.user_location == "drop":
            return {k: v for k, v in options.items() if k != "user_location"}
        approx = loc.get("approximate") if isinstance(loc.get("approximate"), dict) else {}
        return {**options, "user_location": {**loc, "approximate": {k: v for k, v in approx.items()
                                                                    if k in ("country", "timezone")}}}

    # -- replies -----------------------------------------------------------------------------------------

    def restore_response(self, response: dict) -> dict:
        """A copy of a Chat Completions reply with the real values back in its text and named tools' calls."""
        response = copy.deepcopy(response)
        r = self.redactor
        for choice in response.get("choices") or []:
            msg = choice.get("message") if isinstance(choice, dict) else None
            if not isinstance(msg, dict):
                continue
            for key in ("content", "refusal"):
                if isinstance(msg.get(key), str):
                    msg[key] = r.restore_text(msg[key], urls=False)
            for call in msg.get("tool_calls") or []:
                if isinstance(call, dict) and isinstance(call.get("function"), dict):
                    call["function"] = self._restored(call["function"])
            if isinstance(msg.get("function_call"), dict):
                msg["function_call"] = self._restored(msg["function_call"])
        return response

    def _restored(self, fn: dict) -> dict:
        kinds = self.restore.get(fn.get("name"), self.restore.get("*", set()))
        args = fn.get("arguments")
        if not isinstance(args, str):
            return fn
        try:
            return {**fn, "arguments": json.dumps(self.redactor.restore(json.loads(args), kinds, urls=False))}
        except ValueError:
            return {**fn, "arguments": self.redactor.restore_text(args, kinds, urls=False)}


def _data_url(url: str) -> tuple[bytes | None, str | None]:
    """The bytes and media type of a ``data:...;base64,...`` URL; ``(None, None)`` for anything else."""
    if not url.startswith("data:") or ";base64," not in url:
        return None, None
    head, _, body = url.partition(";base64,")
    try:
        return base64.b64decode(body, validate=True), head[5:] or "application/octet-stream"
    except (binascii.Error, ValueError):
        return None, None
