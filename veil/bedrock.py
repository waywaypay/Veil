"""An Amazon Bedrock Guardrail as a second check that no personal information reaches the model.

The placeholders (``veil.Redactor``) are the main control.  A guardrail
looks again at what each request adds before it goes out, and at each reply,
through Bedrock's ApplyGuardrail API, which checks text apart from any model
call, so it works whichever endpoint or provider the model is called through.

The guardrail is meant to have a sensitive information filter for SSNs,
ITINs, names, addresses, email addresses, phone numbers and bank and card
numbers (``RECOMMENDED_PII_TYPES``), and a regex for EINs (``EIN_REGEX``).
Each one it finds that the placeholders missed becomes a placeholder too, of
the matching kind (``veil.anthropic`` does this for you).  Anything else it
objects to (a denied topic, a content or word filter) should stop the request,
and so should a guardrail that can't be reached: ``check`` raises
GuardrailError then.

Any object with the same ``check(texts, source) -> Findings`` method can
stand in for it: a wrapper around Presidio, Google's DLP or your own rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from veil.tax_ids import TAX_ID_KINDS

# The placeholder kind for each of the guardrail's PII types; any other type is an "ID".  A regex's match is a
# "TIN": the one AWS admins are asked to add is for EINs.
_KIND = {"US_SOCIAL_SECURITY_NUMBER": "SSN", "US_INDIVIDUAL_TAX_IDENTIFICATION_NUMBER": "TIN", "NAME": "NAME",
         "ADDRESS": "ADDRESS", "EMAIL": "EMAIL", "PHONE": "PHONE", "US_BANK_ACCOUNT_NUMBER": "ACCOUNT",
         "US_BANK_ROUTING_NUMBER": "ACCOUNT", "INTERNATIONAL_BANK_ACCOUNT_NUMBER": "ACCOUNT",
         "SWIFT_CODE": "ACCOUNT", "CREDIT_DEBIT_CARD_NUMBER": "ACCOUNT", "CREDIT_DEBIT_CARD_CVV": "ACCOUNT",
         "CREDIT_DEBIT_CARD_EXPIRY": "ACCOUNT", "PIN": "ACCOUNT"}
# What a guardrail should look for (set these up in the Bedrock console): each of these PII types,
# masked, and EINs by this regex.
RECOMMENDED_PII_TYPES = ("US_SOCIAL_SECURITY_NUMBER", "US_INDIVIDUAL_TAX_IDENTIFICATION_NUMBER", "NAME", "ADDRESS",
                         "EMAIL", "PHONE", "US_BANK_ACCOUNT_NUMBER", "US_BANK_ROUTING_NUMBER",
                         "INTERNATIONAL_BANK_ACCOUNT_NUMBER", "SWIFT_CODE", "CREDIT_DEBIT_CARD_NUMBER")
EIN_REGEX = r"\b\d{2}-\d{7}\b"
_WHAT = {"SSN": "a taxpayer ID", "EIN": "a taxpayer ID", "TIN": "a taxpayer ID", "NAME": "a name",
         "ADDRESS": "an address", "EMAIL": "an email address", "PHONE": "a phone number",
         "ACCOUNT": "an account number", "DOB": "a birth date", "ID": "personal information"}
# AWS's formats for a guardrail's ID (or ARN) and version.
_GUARDRAIL_ID = re.compile(r"^(?:[a-z0-9]+|arn:aws(?:-[^:]+)?:bedrock:[a-z0-9-]{1,20}:\d{12}:guardrail/[a-z0-9]+)$")
_GUARDRAIL_VERSION = re.compile(r"^(?:[1-9]\d{0,7}|DRAFT)$")


class GuardrailError(Exception):
    """The guardrail stopped a request, or couldn't check it.  The message is for the user."""


def what(kind: str) -> str:
    """A placeholder kind in words: "a taxpayer ID", "a name" ..."""
    return _WHAT.get(kind, "personal information")


@dataclass
class Findings:
    hidden: list[tuple[str, str]] = field(default_factory=list)   # (placeholder kind, as written) for each find
    other: list[str] = field(default_factory=list)     # anything else it objected to, in words

    @property
    def tax_ids(self) -> list[str]:
        return [text for kind, text in self.hidden if kind in TAX_ID_KINDS]


def normalize_guardrail(identifier: str, version: str) -> tuple[str, str]:
    """A guardrail's ID and version as typed, or ("", "") for none.  Raises ValueError saying what's wrong."""
    identifier, version = (identifier or "").strip(), (version or "").strip().upper()
    if not identifier and not version:
        return "", ""
    if not identifier:
        raise ValueError("Enter the guardrail's ID too, or clear its version.")
    if not _GUARDRAIL_ID.match(identifier):
        raise ValueError(f"{identifier!r} isn't a guardrail ID. Use the ID from the Bedrock console, "
                         "e.g. a1b2c3d4e5f6, or the guardrail's ARN.")
    if not version:
        raise ValueError("Enter the guardrail's version, e.g. 1.")
    if not _GUARDRAIL_VERSION.match(version):
        raise ValueError(f"{version!r} isn't a guardrail version. Use its number, e.g. 1, or DRAFT.")
    return identifier, version


class BedrockGuardrail:
    """One guardrail in the user's AWS account, called with their AWS sign-in."""

    def __init__(self, identifier: str, version: str, aws_region: str, aws_profile: str = "", client=None):
        """``client``: a boto3 bedrock-runtime client to use; by default one is made from ``aws_profile``."""
        self.identifier, self.version = normalize_guardrail(identifier, version)
        if not self.identifier:
            raise ValueError("Enter the guardrail's ID and version.")
        self.aws_region = aws_region
        self.aws_profile = aws_profile
        self._client = client

    @property
    def client(self):
        if self._client is None:
            import boto3
            session = boto3.Session(profile_name=self.aws_profile or None)
            self._client = session.client("bedrock-runtime", region_name=self.aws_region)
        return self._client

    def check(self, texts: list[str], source: str) -> Findings:
        """What the guardrail finds in ``texts``; ``source`` is "INPUT" (a request) or "OUTPUT" (a reply)."""
        texts = [t for t in texts if t and t.strip()]
        if not texts:
            return Findings()
        try:
            response = self.client.apply_guardrail(
                guardrailIdentifier=self.identifier, guardrailVersion=self.version, source=source,
                content=[{"text": {"text": t}} for t in texts])
        except Exception as exc:
            raise GuardrailError(self._error_message(exc)) from exc
        found = Findings()
        for assessment in response.get("assessments") or []:
            sensitive = assessment.get("sensitiveInformationPolicy") or {}
            pii = [e for e in sensitive.get("piiEntities") or [] if e.get("detected") is not False]
            regexes = [r for r in sensitive.get("regexes") or [] if r.get("detected") is not False]
            # Whatever it detects is hidden, whether the guardrail is set to mask it, block it or only note it.
            for kind, entity in [*((_KIND.get(e.get("type"), "ID"), e) for e in pii), *(("TIN", r) for r in regexes)]:
                if entity.get("match"):
                    found.hidden.append((kind, entity["match"]))
                else:
                    found.other.append(f"{what(kind)} it didn't quote")
            for topic in (assessment.get("topicPolicy") or {}).get("topics") or []:
                if topic.get("action") == "BLOCKED":
                    found.other.append(f"the denied topic {topic.get('name')!r}")
            for content in (assessment.get("contentPolicy") or {}).get("filters") or []:
                if content.get("action") == "BLOCKED":
                    found.other.append(f"{str(content.get('type')).lower()} content")
            words = assessment.get("wordPolicy") or {}
            if any(w.get("action") == "BLOCKED"
                   for w in [*(words.get("customWords") or []), *(words.get("managedWordLists") or [])]):
                found.other.append("a blocked word")
        kinds: dict[str, str] = {}
        for kind, text in found.hidden:   # once each, as the first kind it was found as
            kinds.setdefault(text, kind)
        found.hidden = [(kind, text) for text, kind in kinds.items()]
        found.other = list(dict.fromkeys(found.other))
        if response.get("action") == "GUARDRAIL_INTERVENED" and not found.hidden and not found.other:
            found.other.append(response.get("actionReason") or "a policy it didn't name")
        return found

    def _error_message(self, exc: Exception) -> str:
        name = exc.__class__.__name__
        code = (getattr(exc, "response", None) or {}).get("Error", {}).get("Code", "")
        if isinstance(exc, ImportError):
            return "The guardrail needs the 'boto3' package: pip install 'veil[bedrock]'"
        if code == "AccessDeniedException":
            return (f"Your AWS role isn't allowed to use the guardrail {self.identifier}. Ask your AWS admin to "
                    "allow bedrock:ApplyGuardrail on it.")
        if code == "ResourceNotFoundException":
            return (f"There's no guardrail {self.identifier} version {self.version} in {self.aws_region}. Check "
                    "its ID, version and region.")
        if name == "ProfileNotFound":
            return (f"There's no AWS profile named {self.aws_profile!r} on this computer. Fix the name, or "
                    "create it with aws configure sso.")
        if name in ("NoCredentialsError", "UnauthorizedSSOTokenError", "TokenRetrievalError", "SSOTokenLoadError") \
                or code in ("ExpiredTokenException", "UnrecognizedClientException"):
            profile = self.aws_profile or "<your profile>"
            return ("Couldn't sign in to AWS to run the guardrail. Sign in on this computer (aws sso login "
                    f"--profile {profile}), then try again.")
        if name in ("EndpointConnectionError", "ConnectTimeoutError", "ReadTimeoutError"):
            return f"Couldn't reach Amazon Bedrock's guardrail in {self.aws_region}."
        return f"The guardrail couldn't run ({exc})."
