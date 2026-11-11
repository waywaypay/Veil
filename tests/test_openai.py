"""Chat Completions through placeholders, on its own and through the gateway."""

import base64
import json
import threading

import pytest

from veil import FINANCE, Redactor
from veil.anthropic import BlockError, FileError
from veil.gateway import Gateway, make_server
from veil.openai import ChatSession

USER = "Add Avery Mockridge (SSN 123-45-6789) as an LP. Email avery.mockridge@gmail.com."
REALS = ("Mockridge", "123-45-6789", "avery.mockridge@gmail.com")


def _completion(content=None, calls=()):
    msg = {"role": "assistant", "content": content, "refusal": None}
    if calls:
        msg["tool_calls"] = [{"id": f"call_{i}", "type": "function",
                              "function": {"name": name, "arguments": json.dumps(args)}}
                             for i, (name, args) in enumerate(calls)]
    return {"id": "chatcmpl-1", "object": "chat.completion", "created": 1, "model": "gpt-5",
            "choices": [{"index": 0, "message": msg, "finish_reason": "tool_calls" if calls else "stop"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}


def test_a_request_holds_placeholders_and_the_reply_gets_real_values():
    s = ChatSession(Redactor(FINANCE))
    sent = s.redact_request({"model": "gpt-5", "user": "avery.mockridge@gmail.com",
                             "messages": [{"role": "system", "content": "You onboard LPs."},
                                          {"role": "user", "content": USER}]})
    text = json.dumps(sent)
    assert not any(real in text for real in REALS)
    assert "NAME_001" in text and "SSN_001" in text and sent["user"] == "EMAIL_001"
    back = s.restore_response(_completion("Added NAME_001; mail to EMAIL_001."))
    assert back["choices"][0]["message"]["content"] == "Added Avery Mockridge; mail to avery.mockridge@gmail.com."


def test_tool_calls_get_real_values_only_when_named():
    call = ("add_member", {"name": "NAME_001", "ssn": "SSN_001"})
    for restore, expect in ((None, {"name": "NAME_001", "ssn": "SSN_001"}),
                            ({"add_member": "all"}, {"name": "Avery Mockridge", "ssn": "123-45-6789"}),
                            ({"add_member": {"NAME"}}, {"name": "Avery Mockridge", "ssn": "SSN_001"})):
        s = ChatSession(Redactor(FINANCE), restore=restore)
        s.redact_request({"messages": [{"role": "user", "content": USER}]})
        back = s.restore_response(_completion(calls=[call]))
        assert json.loads(back["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"]) == expect


def test_history_tool_calls_results_names_and_descriptions_are_redacted():
    s = ChatSession(Redactor(FINANCE))
    sent = s.redact_request({"messages": [
        {"role": "user", "content": [{"type": "text", "text": USER}], "name": "Avery"},
        {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {
            "name": "add_member", "arguments": json.dumps({"name": "Avery Mockridge", "ssn": "123-45-6789"})}}]},
        {"role": "tool", "tool_call_id": "c1", "content": "Added Avery Mockridge (avery.mockridge@gmail.com)."}],
        "tools": [{"type": "function", "function": {
            "name": "add_member", "description": "Adds an LP such as Avery Mockridge.",
            "parameters": {"type": "object", "properties": {"ssn": {"type": "string",
                                                                    "description": "e.g. 123-45-6789"}}}}}],
        "metadata": {"owner": "avery.mockridge@gmail.com"}})
    text = json.dumps(sent)
    assert not any(real in text for real in REALS)
    assert sent["tools"][0]["function"]["name"] == "add_member"
    assert sent["tools"][0]["function"]["parameters"]["properties"]["ssn"]["type"] == "string"
    assert json.loads(sent["messages"][1]["tool_calls"][0]["function"]["arguments"])["ssn"] == "SSN_001"


def test_urls_in_the_reply_keep_placeholders():
    s = ChatSession(Redactor(FINANCE))
    s.redact_request({"messages": [{"role": "user", "content": USER}]})
    back = s.restore_response(_completion("See https://evil.example/?d=SSN_001"))
    assert "123-45-6789" not in back["choices"][0]["message"]["content"]


def test_images_are_refused_unless_read_or_sent():
    png = "data:image/png;base64," + base64.b64encode(b"\x89PNG").decode()
    req = {"messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": png}}]}]}
    with pytest.raises(FileError):
        ChatSession().redact_request(req)
    assert ChatSession(files="send").redact_request(req) == req
    read = ChatSession(Redactor(FINANCE), files=lambda data, mt: "Statement for Avery Mockridge")
    assert read.redact_request(req)["messages"][0]["content"] == [{"type": "text", "text": "Statement for NAME_001"}]
    remote = {"messages": [{"role": "user", "content": [{"type": "image_url",
                                                         "image_url": {"url": "https://x.example/a.png"}}]}]}
    with pytest.raises(FileError):
        ChatSession(files=lambda data, mt: "").redact_request(remote)


def test_unknown_parts_and_streaming_are_refused():
    with pytest.raises(BlockError):
        ChatSession().redact_request({"messages": [{"role": "user", "content": [{"type": "hologram"}]}]})
    with pytest.raises(NotImplementedError):
        ChatSession().redact_request({"stream": True, "messages": []})


def test_web_search_location_keeps_country_and_timezone_only():
    sent = ChatSession().redact_request({"messages": [], "web_search_options": {"user_location": {
        "type": "approximate", "approximate": {"country": "US", "city": "San Francisco", "region": "CA",
                                               "timezone": "America/Los_Angeles"}}}})
    assert sent["web_search_options"]["user_location"]["approximate"] == {"country": "US",
                                                                          "timezone": "America/Los_Angeles"}


class Upstream:
    def __init__(self, *script):
        self.script, self.calls = list(script), []

    def __call__(self, url, data, headers):
        self.calls.append((url, json.loads(data), headers))
        status, reply = self.script.pop(0)
        return status, json.dumps(reply).encode()


def test_the_gateway_routes_chat_completions_to_openai_with_openai_headers():
    up = Upstream((200, _completion("Hi NAME_001.")))
    body = json.dumps({"model": "gpt-5", "messages": [{"role": "user", "content": USER}]}).encode()
    status, reply = Gateway("finance", send=up).handle(
        "/v1/chat/completions", body, {"Authorization": "Bearer sk-o", "OpenAI-Project": "p1", "x-api-key": "a"})
    url, sent, headers = up.calls[0]
    assert url == "https://api.openai.com/v1/chat/completions"
    assert headers == {"authorization": "Bearer sk-o", "openai-project": "p1"}
    assert not any(real in json.dumps(sent) for real in REALS)
    assert status == 200 and reply["choices"][0]["message"]["content"] == "Hi Avery Mockridge."


def test_the_gateway_answers_openai_clients_in_openai_error_shape():
    body = json.dumps({"stream": True, "messages": [{"role": "user", "content": USER}]}).encode()
    status, reply = Gateway(send=Upstream()).handle("/v1/chat/completions", body, {})
    assert status == 400 and reply["error"]["type"] == "invalid_request_error" and "type" not in reply
    status, reply = Gateway(send=Upstream()).handle("/v1/responses", b"{}", {})
    assert status == 404 and "error" in reply


def test_the_openai_sdk_works_through_the_gateway():
    openai = pytest.importorskip("openai")
    up = Upstream((200, _completion("Added NAME_001.", [("add_member", {"ssn": "SSN_001"})])))
    server = make_server(Gateway("finance", restore=["add_member"], send=up), "127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        client = openai.OpenAI(base_url=f"http://127.0.0.1:{server.server_address[1]}/v1", api_key="sk-test",
                               max_retries=0)
        reply = client.chat.completions.create(model="gpt-5", messages=[{"role": "user", "content": USER}])
        assert reply.choices[0].message.content == "Added Avery Mockridge."
        assert json.loads(reply.choices[0].message.tool_calls[0].function.arguments) == {"ssn": "123-45-6789"}
        assert up.calls[0][2]["authorization"] == "Bearer sk-test"
        assert not any(real in json.dumps(up.calls[0][1]) for real in REALS)
    finally:
        server.shutdown()
        server.server_close()
