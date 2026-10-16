"""Claude through placeholders: what's sent holds none of it, and what comes back has it again."""

import json

import pytest

from veil import FINANCE, Redactor
from veil.anthropic import TAX_ID_REMOVED, Session, wrap
from veil.bedrock import BedrockGuardrail, GuardrailError

anthropic = pytest.importorskip("anthropic")
from anthropic.types import Message  # noqa: E402
from test_bedrock import NONE, FakeGuardrailAPI, pii  # noqa: E402


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
    client = wrap(fake, Redactor(FINANCE))
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


def test_other_attributes_pass_through():
    fake = FakeClient([_message("ok")])
    client = wrap(fake)
    assert client.api_key == "k"
    client.beta.messages.create(model="m", max_tokens=1, messages=[{"role": "user", "content": "jane@example.com"}])
    assert "jane@" not in _sent(fake)


# -- with a guardrail --------------------------------------------------------------------------------------

def _guarded(answer, script, redactor=None):
    api = FakeGuardrailAPI(answer)
    fake = FakeClient(script)
    client = wrap(fake, redactor or Redactor(FINANCE),
                  guardrail=BedrockGuardrail("a1b2c3d4e5f6", "2", "us-east-1", client=api))
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
    blocked = {"action": "GUARDRAIL_INTERVENED", "outputs": [], "assessments": [
        {"topicPolicy": {"topics": [{"name": "Investment advice", "type": "DENY", "action": "BLOCKED"}]}}]}
    answers = [blocked]
    client, fake, api = _guarded(lambda source, texts: answers[-1], [_message("Fine.")])
    messages = [{"role": "user", "content": "Should I buy more of Fund III?"}]
    with pytest.raises(GuardrailError, match="flagged the denied topic 'Investment advice'. Nothing was sent."):
        client.messages.create(model="m", max_tokens=10, messages=messages)
    answers.append(RuntimeError("boom"))
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
    answers["OUTPUT"] = {"action": "GUARDRAIL_INTERVENED", "outputs": [], "assessments": [
        {"contentPolicy": {"filters": [{"type": "INSULTS", "action": "BLOCKED"}]}}]}
    assert client.messages.create(model="m", max_tokens=10, messages=ask).content[0].text == \
        "(The guardrail held back this reply: it flagged insults content.)"
    answers["OUTPUT"] = RuntimeError("boom")
    assert client.messages.create(model="m", max_tokens=10, messages=ask).content[0].text.startswith(
        "(This reply isn't shown, because the guardrail couldn't check it.")


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
