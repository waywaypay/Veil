# veil

Reversible placeholders for personal information in what you send an LLM.

The model sees `NAME_001`, `SSN_001` and `EMAIL_001`. Your tools get the real
values back. The same person keeps the same placeholder for the whole
conversation, so the model can still reason about who is who.

```
you send   →  "Add Avery Mockridge (SSN 123-45-6789) as an LP"
model sees →  "Add NAME_001 (SSN SSN_001) as an LP"
model calls   add_member({"name": "NAME_001", "ssn": "SSN_001"})
your tool  ←  add_member({"name": "Avery Mockridge", "ssn": "123-45-6789"})
```

The code was extracted from the K-1 assistant in Snowman, where it keeps
partners' taxpayer IDs, names and addresses away from the model while the
assistant reads K-1 PDFs and fills in records. It has no dependencies.

## Where it runs

veil is a library, not a service. It runs inside your app's own process, on
the device where the data is, with nothing to host:

- The redactor imports only Python's standard library and makes no network
  calls.
- The table of placeholders and real values exists only in memory, in the
  `Redactor` object. It isn't written anywhere unless you save it yourself
  (`r.mapping`).
- The model receives only text that has already been redacted, and replies
  are restored on the device.

Two optional pieces send text off the device, so leave them out if
everything must stay local:

- **`veil.bedrock`** sends text to AWS before it has been redacted. That is
  how a second check works.
- **`name_finder`** runs wherever its code runs: a spaCy model loaded in the
  same process stays local, but a cloud NER API does not.

## Install

```
pip install "git+https://github.com/waywaypay/veil"              # the redactor only
pip install "veil[anthropic,bedrock] @ git+https://github.com/waywaypay/veil"
```

## Use it with the Anthropic SDK

```python
import anthropic
from veil import Redactor, FINANCE
from veil.anthropic import wrap

client = wrap(anthropic.Anthropic(), Redactor(FINANCE))     # one per conversation
client.redactor.add_person("Avery K. Mockridge")            # people you already know of
client.redactor.add_business("Marlow Vane Growth Fund, LP") # names the model should keep seeing

reply = client.messages.create(model="claude-opus-5-5", max_tokens=1024, tools=TOOLS, messages=messages)
```

You keep the conversation with the real values in it, as you would without
veil. Each request goes out as a copy with placeholders in place of the real
values. That covers what the user typed, tool results, the system prompt and
the model's earlier turns. In the reply, text and tool-call inputs come back
with the real values. Thinking blocks go back unchanged. Streaming isn't
supported yet: `stream=True` raises an error.

## Use it with anything else

```python
from veil import Redactor

r = Redactor()
safe = r.redact_text("Call Priya Patel at 415-555-0134")      # "Call NAME_001 at PHONE_001"
r.restore_text("NAME_001 confirmed.")                          # "Priya Patel confirmed."
r.redact({"rows": [...], "note": "..."})                       # dicts and lists, keys included
r.redact_text(user_message, typed=True)                        # read more eagerly: see below
r.mapping                                                      # {"NAME_001": "Priya Patel", ...}
```

`typed=True` is for what a person typed. In that mode, any two or three
capitalized words that aren't in the profile's vocabulary are taken for a
name, and so are a lower-case first name and surname ("add jane smith").

## What it finds

| Placeholder | What |
|---|---|
| `SSN`, `EIN`, `TIN` | US taxpayer IDs, in any format: odd dashes and spaces, one digit per box, split across lines, HTML or %-escaped, Unicode digits, OCR misreads (`l23-45-6789`). Amounts, dates and phone numbers are left alone. |
| `NAME` | People you name with `add_person`, in every way they get written (`MOCKRIDGE, AVERY K`, `A. Mockridge`, `Mr. Mockridge`). Also names it finds: common first names and surnames, after Mr./Dr., after labels like `Name:`, `Attn:`, `c/o` and `Sincerely,`, in "Last, First" order, and inside trust and joint-account names. |
| `ADDRESS` | Street addresses with city, state and ZIP; PO and rural boxes; military addresses; UK and Canadian postcodes; some European formats. |
| `EMAIL`, `PHONE` | Including obfuscated forms like `jane at example dot com`, and international numbers. |
| `ACCOUNT` | Bank, routing, card (checked with the Luhn algorithm), IBAN (checksum-validated) and SWIFT numbers. |
| `ID`, `DOB` | Passport, driver's license and member ID numbers, and birth dates, when a label says what they are. Also any other run of 11 to 19 digits. |

Business names stay visible, because the model usually needs them. A name
followed by Fund, Capital, Partners, LLC, L.P. and similar is treated as a
business, as is anything you pass to `add_business`.

A placeholder always comes back as the exact text it replaced. So when veil
hides something that wasn't personal (a false positive), the model sees a
placeholder, but nothing wrong is ever invented.

## Profiles

A profile tells veil which words in a kind of document look like names but
aren't (a K-1's "Guaranteed Payments", a fund report's "Capital Account").

| Profile | Adds |
|---|---|
| `GENERIC` (default) | Nothing: everyday English, months, places, job titles. |
| `FINANCE` | Fund, investing and accounting vocabulary. In typed text, "as an LP" or "Jane's share" after words marks them as a person's name. |
| `US_TAX_K1` | Schedule K-1 vocabulary. A box number before an amount ("20 1250000") isn't taken for an EIN. |

You can build your own profile:

```python
from veil import FINANCE
CLINIC = FINANCE.extend("clinic", stop_words="Triage Discharge Intake", cues=[r"referring\s+physician"],
                        cue_ends="physician")
```

## Choosing what to look for, and adding your own

```python
Redactor(detect={"SSN", "EIN", "TIN", "EMAIL"})        # only these kinds
Redactor(patterns={"MRN": r"\bMRN[- ]?\d{6,8}\b"})     # MRN_001, MRN_002 ...
r.add("Project Nightingale", "CODENAME")               # one value, by hand
Redactor(name_finder=my_ner)                           # names from spaCy, Presidio, a cloud API ...
```

Names are found with word lists and rules, not a statistical model. That
works well on forms, statements and messages. In free-flowing prose, though,
it misses an unusual name that has no title or label before it ("CEO Satya
Nadella"). Pass a `name_finder` (any function from text to a list of names)
to close that gap. Each name it returns gets every variant spelling covered,
like names given to `add_person`.

## A second check: Amazon Bedrock Guardrails

```python
from veil.bedrock import BedrockGuardrail, RECOMMENDED_PII_TYPES, EIN_REGEX

guardrail = BedrockGuardrail("a1b2c3d4e5f6", "1", aws_region="us-east-1", aws_profile="team")
client = wrap(anthropic.Anthropic(), Redactor(FINANCE), guardrail=guardrail)
```

With a guardrail set, each new text in a request is checked before it's
sent:

- Anything the guardrail finds that veil missed becomes a placeholder too.
- If the guardrail objects to anything else, or can't be reached, the call
  raises `GuardrailError` and nothing is sent.

Replies are checked too. A taxpayer ID in a reply is taken out, because the
model only ever saw placeholders and shouldn't have written one. Anything
with the same `check(texts, source)` method can stand in for the Bedrock
guardrail.

## Development

```
pip install -e ".[dev]"
pytest
ruff check .
```

The tests include Snowman's original suite, run under the `US_TAX_K1`
profile. Among them are ten fictional K-1 specimens (their text is stored in
`tests/fixtures/`) and stress tests of taxpayer-ID formats.
