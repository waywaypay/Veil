"""The gateway: what reaches the API holds placeholders, and what reaches the client has the real values."""

import json
import threading

import pytest

from veil.gateway import Gateway, make_server

anthropic = pytest.importorskip("anthropic")

USER = "Add Avery Mockridge (SSN 123-45-6789) as an LP. Email avery.mockridge@gmail.com."


class Upstream:
    """Stands in for the API: keeps each request and plays back scripted (status, reply) pairs."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def __call__(self, url, data, headers):
        self.calls.append((url, json.loads(data), headers))
        status, reply = self.script.pop(0)
        return status, json.dumps(reply).encode()


def _message(*content):
    return {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": list(content), "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 1}}


@pytest.fixture
def serve():
    servers = []

    def start(gateway):
        server = make_server(gateway, "127.0.0.1", 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return anthropic.Anthropic(base_url=f"http://127.0.0.1:{server.server_address[1]}", api_key="sk-test",
                                   max_retries=0)

    yield start
    for s in servers:
        s.shutdown()
        s.server_close()


def test_the_api_sees_placeholders_and_the_client_gets_real_values(serve):
    up = Upstream((200, _message({"type": "text", "text": "Added NAME_001; welcome mail to EMAIL_001."})))
    client = serve(Gateway("finance", send=up))
    reply = client.messages.create(model="claude-opus-5-5", max_tokens=100,
                                   messages=[{"role": "user", "content": USER}])
    url, sent, headers = up.calls[0]
    assert url == "https://api.anthropic.com/v1/messages"
    text = json.dumps(sent)
    for real in ("Mockridge", "123-45-6789", "avery.mockridge@gmail.com"):
        assert real not in text
    assert "NAME_001" in text and "SSN_001" in text and "EMAIL_001" in text
    assert reply.content[0].text == "Added Avery Mockridge; welcome mail to avery.mockridge@gmail.com."
    assert headers.get("x-api-key") == "sk-test" or headers.get("authorization") == "Bearer sk-test"


@pytest.mark.filterwarnings("ignore:veil gave the")
def test_a_tool_gets_placeholders_unless_it_is_named():
    call = {"type": "tool_use", "id": "t1", "name": "add_member", "input": {"name": "NAME_001", "ssn": "SSN_001"}}
    body = json.dumps({"model": "m", "max_tokens": 10, "messages": [{"role": "user", "content": USER}]}).encode()
    status, reply = Gateway(send=Upstream((200, _message(call)))).handle("/v1/messages", body, {})
    assert status == 200 and reply["content"][0]["input"] == {"name": "NAME_001", "ssn": "SSN_001"}
    status, reply = Gateway(restore=["add_member"], send=Upstream((200, _message(call)))).handle(
        "/v1/messages", body, {})
    assert reply["content"][0]["input"] == {"name": "Avery Mockridge", "ssn": "123-45-6789"}


def test_each_turn_numbers_the_conversation_the_same_way():
    up = Upstream((200, _message({"type": "text", "text": "ok"})), (200, _message({"type": "text", "text": "ok"})))
    g = Gateway(send=up)
    first = [{"role": "user", "content": USER}]
    g.handle("/v1/messages", json.dumps({"model": "m", "max_tokens": 5, "messages": first}).encode(), {})
    later = first + [{"role": "assistant", "content": "Done."},
                     {"role": "user", "content": "Now email Avery Mockridge again."}]
    g.handle("/v1/messages", json.dumps({"model": "m", "max_tokens": 5, "messages": later}).encode(), {})
    assert up.calls[1][1]["messages"][0] == up.calls[0][1]["messages"][0]
    assert "NAME_001" in up.calls[1][1]["messages"][2]["content"]


def test_streaming_is_refused_and_nothing_is_sent(serve):
    up = Upstream()
    client = serve(Gateway(send=up))
    with pytest.raises(anthropic.BadRequestError, match="streamed"):
        client.messages.create(model="m", max_tokens=5, stream=True, messages=[{"role": "user", "content": USER}])
    assert up.calls == []


def test_an_image_is_refused_by_default_and_nothing_is_sent():
    up = Upstream()
    image = {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "iVBORw0KGgo="}}
    body = json.dumps({"model": "m", "max_tokens": 5,
                       "messages": [{"role": "user", "content": [image, {"type": "text", "text": "Who?"}]}]})
    status, reply = Gateway(send=up).handle("/v1/messages", body.encode(), {})
    assert status == 400 and reply["error"]["type"] == "invalid_request_error"
    assert up.calls == []


def test_an_api_error_is_passed_on_as_it_is(serve):
    err = {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}
    client = serve(Gateway(send=Upstream((401, err))))
    with pytest.raises(anthropic.AuthenticationError, match="invalid x-api-key"):
        client.messages.create(model="m", max_tokens=5, messages=[{"role": "user", "content": USER}])


def test_count_tokens_is_redacted_too(serve):
    up = Upstream((200, {"input_tokens": 42}))
    client = serve(Gateway(send=up))
    count = client.messages.count_tokens(model="m", messages=[{"role": "user", "content": USER}])
    assert count.input_tokens == 42
    assert up.calls[0][0].endswith("/v1/messages/count_tokens")
    assert "123-45-6789" not in json.dumps(up.calls[0][1])


def test_only_the_api_paths_are_served():
    status, reply = Gateway(send=Upstream()).handle("/v1/files", b"{}", {})
    assert status == 404 and reply["error"]["type"] == "not_found_error"


def test_only_credentials_and_api_headers_are_passed_on():
    up = Upstream((200, _message({"type": "text", "text": "ok"})))
    body = json.dumps({"model": "m", "max_tokens": 5, "messages": [{"role": "user", "content": "hi"}]}).encode()
    Gateway(send=up).handle("/v1/messages", body, {"X-Api-Key": "k", "anthropic-version": "2023-06-01",
                                                   "Cookie": "session=1", "X-Forwarded-For": "10.0.0.1"})
    assert up.calls[0][2] == {"x-api-key": "k", "anthropic-version": "2023-06-01"}
