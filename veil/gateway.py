"""A gateway that speaks the Anthropic Messages API, with veil in between.

Run it on a machine you control and point any client of the Messages API at it
instead of at Anthropic:

    python -m veil.gateway --profile finance --port 8787

    client = anthropic.Anthropic(base_url="http://127.0.0.1:8787")   # the key goes through as usual

Each ``POST /v1/messages`` is redacted the way ``veil.anthropic.wrap`` redacts a
request (the same ``Session``), sent on to Anthropic, and the reply comes back
with the real values in its text.  ``POST /v1/messages/count_tokens`` is redacted
and sent on too.  Nothing else is served.

Every request carries the whole conversation, so each one gets its own
redactor: the same text gets the same placeholders on every turn, and nothing
from one request is kept for the next, or for anyone else's.

Tool calls come back with placeholders in their input unless the tool is named
with ``--restore-tool`` (or ``--restore-all-tools``), as with ``wrap``'s
``restore``: text that talks the model into calling ``send_email`` with
``SSN_001`` then sends the placeholder, not the number.

The client's own credentials (``x-api-key`` or ``Authorization``) and its
``anthropic-version`` and ``anthropic-beta`` headers are passed on; the gateway
holds no key of its own.  It listens on 127.0.0.1 unless told otherwise, and
logs each request's method, path and status, never a body.

Not supported yet, and refused with a 400 rather than sent without
placeholders: ``stream: true``, and what ``wrap`` refuses (images and PDFs
unless ``--files`` says otherwise, MCP servers, unknown content blocks, a web
tool's domains that name someone).

Standard library only.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
import warnings
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from veil.anthropic import BlockError, DomainError, FileError, McpError, Session
from veil.profiles import PROFILES
from veil.redactor import Redactor

DEFAULT_UPSTREAM = "https://api.anthropic.com"
MAX_BODY = 64 * 1024 * 1024   # bytes; the API's own limit for a Messages request is 32 MB
_PASSED_ON = ("x-api-key", "authorization", "anthropic-version", "anthropic-beta")
_REFUSED = (BlockError, DomainError, FileError, McpError, ValueError)


class Gateway:
    """What the server does with one request, apart from HTTP.  ``send`` makes the call upstream and returns
    ``(status, body bytes)``; tests pass their own."""

    def __init__(self, profile: str = "generic", restore: str | list[str] | None = None, files: str = "refuse",
                 upstream: str = DEFAULT_UPSTREAM, timeout: float = 600, send=None):
        if profile not in PROFILES:
            raise ValueError(f"profile must be one of {', '.join(PROFILES)}")
        if files not in ("refuse", "read", "send"):
            raise ValueError('files must be "refuse", "read" or "send"')
        self.profile = PROFILES[profile]
        self.restore = "all" if restore == "all" else {name: "all" for name in (restore or [])}
        self.files = files
        self.upstream = upstream.rstrip("/")
        self.timeout = timeout
        self.send = send or self._send

    def session(self) -> Session:
        # A request holds the whole conversation, so a fresh redactor per request numbers it the same way each
        # time; one_conversation guards a redactor shared across requests, which this never does.
        return Session(Redactor(self.profile), files=self.files, restore=self.restore, one_conversation=False)

    def handle(self, path: str, body: bytes, headers: dict[str, str]) -> tuple[int, dict]:
        """``(status, JSON reply)`` for one POST."""
        if path not in ("/v1/messages", "/v1/messages/count_tokens"):
            return _error(404, "not_found_error", f"veil's gateway serves /v1/messages and "
                                                  f"/v1/messages/count_tokens, not {path}.")
        try:
            request = json.loads(body or b"{}")
        except ValueError:
            return _error(400, "invalid_request_error", "The request body isn't JSON.")
        if not isinstance(request, dict):
            return _error(400, "invalid_request_error", "The request body must be a JSON object.")
        if request.get("stream"):
            return _error(400, "invalid_request_error",
                          "veil's gateway doesn't redact streamed replies yet, so nothing was sent. "
                          "Send the request without stream: true.")
        session = self.session()
        try:
            redacted = session.redact_request(request)
        except _REFUSED as exc:
            return _error(400, "invalid_request_error", str(exc))
        out_headers = {k.lower(): v for k, v in headers.items() if k.lower() in _PASSED_ON}
        status, raw = self.send(self.upstream + path, json.dumps(redacted).encode(), out_headers)
        try:
            reply = json.loads(raw or b"{}")
        except ValueError:
            return _error(502, "api_error", "The upstream API's reply wasn't JSON.")
        if status == 200 and path == "/v1/messages" and isinstance(reply, dict) and "content" in reply:
            reply = session.restore_response(reply)
        return status, reply

    def _send(self, url: str, data: bytes, headers: dict[str, str]) -> tuple[int, bytes]:
        req = urllib.request.Request(url, data=data, method="POST",
                                     headers={**headers, "content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:   # the API's own error, passed on as it is
            return exc.code, exc.read()


def _error(status: int, kind: str, message: str) -> tuple[int, dict]:
    return status, {"type": "error", "error": {"type": kind, "message": message}}


def make_server(gateway: Gateway, host: str = "127.0.0.1", port: int = 8787) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        server_version = "veil-gateway"

        def do_POST(self):   # noqa: N802
            length = int(self.headers.get("content-length") or 0)
            if length > MAX_BODY:
                self._reply(*_error(413, "request_too_large", "The request is larger than the gateway accepts."))
                return
            body = self.rfile.read(length)
            try:
                status, reply = gateway.handle(self.path.split("?", 1)[0], body, dict(self.headers.items()))
            except Exception as exc:   # noqa: BLE001 -- reported to the client, never with the request's text
                status, reply = _error(502, "api_error", f"veil's gateway couldn't complete the request "
                                                         f"({type(exc).__name__}).")
            self._reply(status, reply)

        def do_GET(self):   # noqa: N802
            if self.path == "/healthz":
                self._reply(200, {"ok": True})
            else:
                self._reply(*_error(404, "not_found_error", "Not found."))

        def _reply(self, status: int, reply: Any):
            data = json.dumps(reply).encode()
            self.send_response(status)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, fmt, *args):   # method, path and status only: never a body
            sys.stderr.write(f"{self.address_string()} {fmt % args}\n")

    return ThreadingHTTPServer((host, port), Handler)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m veil.gateway",
                                description="An Anthropic Messages API gateway that swaps personal information for "
                                            "placeholders on the way out and puts it back on the way in.")
    p.add_argument("--host", default="127.0.0.1", help="address to listen on (default 127.0.0.1)")
    p.add_argument("--port", type=int, default=8787, help="port to listen on (default 8787)")
    p.add_argument("--profile", default="generic", choices=sorted(PROFILES), help="veil profile (default generic)")
    p.add_argument("--restore-tool", action="append", default=[], metavar="NAME",
                   help="a tool whose calls get real values back; repeat for each")
    p.add_argument("--restore-all-tools", action="store_true", help="every tool's calls get real values back")
    p.add_argument("--files", default="refuse", choices=["refuse", "read", "send"],
                   help="images and PDFs: refuse them (default), read their text here and send it redacted "
                        "(needs veil[files]), or send them as they are")
    p.add_argument("--upstream", default=DEFAULT_UPSTREAM, help=f"where to send requests (default {DEFAULT_UPSTREAM})")
    args = p.parse_args(argv)
    # wrap's advice for a tool left out of restore names its Python argument; here the flag is --restore-tool.
    warnings.filterwarnings("ignore", message="veil gave the .* tool placeholders")
    gateway = Gateway(args.profile, "all" if args.restore_all_tools else args.restore_tool, args.files, args.upstream)
    server = make_server(gateway, args.host, args.port)
    print(f"veil gateway on http://{args.host}:{server.server_address[1]} -> {gateway.upstream}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
