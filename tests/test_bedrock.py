"""The Bedrock guardrail: settings, reading ApplyGuardrail's answer, and errors in plain words."""


import pytest

from veil.bedrock import BedrockGuardrail, GuardrailError, normalize_guardrail

NONE = {"action": "NONE", "outputs": [], "assessments": [{}]}


def pii(*matches, kind="US_SOCIAL_SECURITY_NUMBER", action="ANONYMIZED"):
    """ApplyGuardrail's answer when its sensitive information filter finds ``matches``."""
    return {"action": "GUARDRAIL_INTERVENED", "outputs": [], "assessments": [{"sensitiveInformationPolicy": {
        "piiEntities": [{"type": kind, "match": m, "action": action, "detected": True} for m in matches],
        "regexes": []}}]}


class FakeGuardrailAPI:
    """Bedrock's ApplyGuardrail: answers with ``answer(source, texts)``, or raises it if it's an exception."""

    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def apply_guardrail(self, **request):
        texts = [block["text"]["text"] for block in request["content"]]
        self.calls.append({**request, "texts": texts})
        result = self.answer(request["source"], texts)
        if isinstance(result, Exception):
            raise result
        return result


def _guardrail(answer):
    return BedrockGuardrail("a1b2c3d4e5f6", "2", "us-east-1", "team-profile", client=FakeGuardrailAPI(answer))


def test_guardrail_settings():
    assert normalize_guardrail("", " ") == ("", "")
    assert normalize_guardrail(" a1b2c3d4e5f6 ", " 3 ") == ("a1b2c3d4e5f6", "3")
    assert normalize_guardrail("a1b2c3d4e5f6", "draft") == ("a1b2c3d4e5f6", "DRAFT")
    arn = "arn:aws:bedrock:us-east-1:123456789012:guardrail/a1b2c3d4e5f6"
    assert normalize_guardrail(arn, "1") == (arn, "1")
    for identifier, version, problem in (("a1b2c3d4e5f6", "", "version"), ("", "1", "ID too"),
                                         ("My Guardrail", "1", "isn't a guardrail ID"),
                                         ("a1b2c3d4e5f6", "v1", "isn't a guardrail version"),
                                         ("a1b2c3d4e5f6", "0", "isn't a guardrail version")):
        with pytest.raises(ValueError, match=problem):
            normalize_guardrail(identifier, version)


def test_what_it_finds_is_returned_as_written_with_its_kind():
    api = FakeGuardrailAPI(lambda source, texts: {
        "action": "GUARDRAIL_INTERVENED", "outputs": [], "assessments": [{"sensitiveInformationPolicy": {
            "piiEntities": [{"type": "US_SOCIAL_SECURITY_NUMBER", "match": "555443333", "action": "ANONYMIZED"},
                            {"type": "US_INDIVIDUAL_TAX_IDENTIFICATION_NUMBER", "match": "900-70-1234",
                             "action": "NONE", "detected": True}],
            "regexes": [{"name": "EIN", "regex": r"\d{2}-\d{7}", "match": "12 3456789", "action": "ANONYMIZED"},
                        {"name": "EIN", "regex": r"\d{2}-\d{7}", "match": "555443333", "action": "ANONYMIZED"}]}}]})
    guardrail = BedrockGuardrail("a1b2c3d4e5f6", "2", "us-east-1", client=api)
    found = guardrail.check(["ref 555443333", "", "ITIN 900-70-1234, EIN 12 3456789"], "INPUT")
    assert found.tax_ids == ["555443333", "900-70-1234", "12 3456789"] and found.other == []
    assert found.hidden == [("SSN", "555443333"), ("TIN", "900-70-1234"), ("TIN", "12 3456789")]
    # Blank texts aren't sent; the guardrail, version and source are.
    assert api.calls[0]["texts"] == ["ref 555443333", "ITIN 900-70-1234, EIN 12 3456789"]
    assert (api.calls[0]["guardrailIdentifier"], api.calls[0]["guardrailVersion"], api.calls[0]["source"]) == \
        ("a1b2c3d4e5f6", "2", "INPUT")
    assert _guardrail(lambda source, texts: NONE).check(["Fund III, LP"], "OUTPUT").tax_ids == []
    assert _guardrail(lambda source, texts: 1 / 0).check(["", "  "], "INPUT").tax_ids == []   # nothing to check


def test_other_personal_information_is_returned_with_its_kind_and_anything_else_is_named():
    answer = {"action": "GUARDRAIL_INTERVENED", "outputs": [{"text": "Sorry."}], "assessments": [{
        "topicPolicy": {"topics": [{"name": "Investment advice", "type": "DENY", "action": "BLOCKED"}]},
        "contentPolicy": {"filters": [{"type": "PROMPT_ATTACK", "confidence": "HIGH", "action": "BLOCKED"}]},
        "wordPolicy": {"customWords": [{"match": "secret", "action": "BLOCKED"}]},
        "sensitiveInformationPolicy": {"piiEntities": [
            {"type": "NAME", "match": "Rowan N. Exemplar", "action": "ANONYMIZED"},
            {"type": "ADDRESS", "match": "1 Main St", "action": "NONE", "detected": True},   # detect-only too
            {"type": "US_BANK_ACCOUNT_NUMBER", "match": "000123456789", "action": "BLOCKED"},
            {"type": "EMAIL", "match": "rowan@example.com", "action": "ANONYMIZED", "detected": False},  # not found
            {"type": "DRIVER_ID", "match": "D1234567", "action": "ANONYMIZED"},
            {"type": "US_SOCIAL_SECURITY_NUMBER", "action": "BLOCKED"},
            {"type": "PHONE", "action": "BLOCKED"}]}}]}
    found = _guardrail(lambda source, texts: answer).check(["..."], "INPUT")
    assert found.tax_ids == []
    assert found.hidden == [("NAME", "Rowan N. Exemplar"), ("ADDRESS", "1 Main St"), ("ACCOUNT", "000123456789"),
                            ("ID", "D1234567")]
    assert found.other == ["a taxpayer ID it didn't quote", "a phone number it didn't quote",
                           "the denied topic 'Investment advice'", "prompt_attack content", "a blocked word"]
    # It stepped in and didn't say why: that still counts.
    vague = {"action": "GUARDRAIL_INTERVENED", "actionReason": "Guardrail blocked.", "outputs": [],
             "assessments": [{}]}
    assert _guardrail(lambda source, texts: vague).check(["..."], "INPUT").other == ["Guardrail blocked."]


def test_errors_say_what_to_fix():
    from botocore.exceptions import ClientError, EndpointConnectionError, NoCredentialsError, ProfileNotFound

    def client_error(code):
        return ClientError({"Error": {"Code": code, "Message": "no"}}, "ApplyGuardrail")

    for exc, words in ((client_error("AccessDeniedException"), "allow bedrock:ApplyGuardrail"),
                       (client_error("ResourceNotFoundException"), "no guardrail a1b2c3d4e5f6 version 2 in us-east-1"),
                       (client_error("ExpiredTokenException"), "aws sso login --profile team-profile"),
                       (NoCredentialsError(), "aws sso login --profile team-profile"),
                       (ProfileNotFound(profile="team-profile"), "no AWS profile named 'team-profile'"),
                       (EndpointConnectionError(endpoint_url="https://bedrock-runtime.us-east-1.amazonaws.com"),
                        "Couldn't reach Amazon Bedrock's guardrail in us-east-1"),
                       (client_error("ThrottlingException"), "couldn't run")):
        with pytest.raises(GuardrailError, match=words.replace("(", r"\(")):
            _guardrail(lambda source, texts, exc=exc: exc).check(["text"], "INPUT")
