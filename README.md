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

Two optional hooks run your own code, so they stay local only if that code
does:

- **`guardrail`** sees text before it has been redacted. A check that calls a
  cloud service (Amazon Bedrock Guardrails, Google's DLP) sends it there.
- **`name_finder`** runs wherever its code runs: a spaCy model loaded in the
  same process stays local, but a cloud NER API does not.

## Install

```
pip install "git+https://github.com/waywaypay/veil"              # the redactor only
pip install "veil[anthropic] @ git+https://github.com/waywaypay/veil"
pip install "veil[anthropic,files] @ git+https://github.com/waywaypay/veil"  # also reads PDFs and images
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

## Images and PDFs

veil redacts text, and an image or PDF would reach the model with whatever
is written in it. So by default a request with one in it raises `FileError`
and nothing is sent. Say what should happen to them instead:

```python
client = wrap(anthropic.Anthropic(), Redactor(FINANCE), files="read")     # send their text, redacted
client = wrap(anthropic.Anthropic(), Redactor(FINANCE), files="send")     # send them as they are
client = wrap(anthropic.Anthropic(), Redactor(FINANCE), files=my_reader)  # (data, media_type) -> text
```

With `files="read"`, each image and PDF is read on this machine and its text,
with placeholders in it, is sent in its place. A PDF's own text is read with
pypdf; images and scanned pages are read with Tesseract OCR, which you install
yourself (`apt install tesseract-ocr`, `brew install tesseract`). The model
then sees the words, not the picture or the layout. Each file is read once a
conversation.

A file sent as a URL or a Files API ID can't be read first (Anthropic fetches
those, or already has them), so with `"read"` or `"refuse"` the request
raises `FileError` and nothing is sent. Send its bytes as base64 instead.
Only `files="send"` lets such a file through.

Outside the wrapper, `veil.files.read_text(data, media_type)` gives you the
text to pass to `redact_text` yourself.

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
| `SSN`, `EIN`, `TIN` | US taxpayer IDs, in any format: odd dashes and spaces, one digit per box, split across lines, HTML or %-escaped, Unicode digits, OCR misreads (`l23-45-6789`), and SSNs masked to their last four (`***-**-1234`). Amounts, dates, times, phone numbers and IP addresses are left alone. |
| `NAME` | People you name with `add_person`, in every way they get written (`MOCKRIDGE, AVERY K`, `A. Mockridge`, `Mr. Mockridge`). Also names it finds: first names and surnames from every country (lists drawn from Wikidata and the 2010 US Census), after Mr., Dr., Agent or Captain, after labels like `Name:`, `Attn:`, `Shipper:`, `c/o` and `Sincerely,`, a first name alone after "Hello" or before a comma, in "Last, First" order, as "First M. Last", in capitals in bank messages (`/MISTY LEE DEAN/`), after a greeting ("Thank you, Dean."), in JSON, XML and table fields whose key or column says they hold a name (`"last_name"`, `<FirstName>`, a CSV's "Customer" column), and inside trust and joint-account names. Places ("Ontario"), roles ("Policyholder") and a person's name inside a business's ("Taylor Healthcare Fund") stay. |
| `ADDRESS` | Street addresses (any USPS street suffix) with the city, postcode, country and the lines under them; PO and rural boxes; military addresses; UK and Canadian postcodes; European forms (`Bahnhofstrasse 45`, `5 Xaviweg`, `45, Baker Street`, `7, avenue Gérard Lecoq`). |
| `EMAIL`, `PHONE` | Including obfuscated forms like `jane at example dot com`, international numbers, and national ones with a trunk 0 (`0800 123 4567`). |
| `ACCOUNT` | Bank, routing, card (checked with the Luhn algorithm), IBAN (checksum-validated), BBAN and SWIFT numbers, the last also without a label when shaped like one (ISO 9362, with a valid country); a card or account number a few words after its label ("the card number on file is ..."). |
| `ID`, `DOB` | Passport, driver's license, customer, employee, user and member ID numbers, usernames and @handles, and birth dates, when a label, a field's key or a table's column says what they are (`driver_license_number`, `DateOfBirth`, `date of birth must be ...` count), or the words before them in the sentence ("the employee ID for Jo is Nq-92647"). Also UK National Insurance numbers, one to four capitals and six or more digits (`EMP286818`), and any other run of 11 to 24 digits. |

Business names stay visible, because the model usually needs them. A name
followed by Fund, Capital, Partners, LLC, L.P. and similar is treated as a
business, as is anything you pass to `add_business`.

A placeholder comes back as the text it replaced, except a person's name,
which comes back the way that person was first written (so a tool call that
adds `NAME_001` adds the person by their full name). So when veil hides
something that wasn't personal (a false positive), the model sees a
placeholder, but nothing wrong is ever invented.

## What the model can't do with a placeholder

The model can move a placeholder around: put `NAME_001` in a name field, pass
`SSN_001` to a tool, keep track of whose SSN is whose. All of that works,
because your tool gets the real values back.

What it can't do is look inside one. To the model, a placeholder is one
solid block, and it comes back as the whole value it replaced:

| You ask the model to | What your tool gets |
|---|---|
| Put the name in one field and the SSN in another | ✅ The full name and the full SSN |
| Fill First Name and Last Name separately | ❌ The full name in both fields |
| Enter the last 4 digits of the SSN | ❌ The full SSN, or a mangled field |
| Write the SSN without dashes | ❌ The SSN as it was written, dashes included |
| Fill City, State and ZIP | ❌ The whole address in every field |
| Check that an SSN is valid, or that two spellings of a name match | ❌ Nothing it can check: it sees only placeholders |

Splitting, reformatting and checking values belongs in your tool. Have the
model pass the whole placeholder and do the work in code, after the real
value is back:

```python
def fill_form(name: str, ssn: str, address: str):   # real values by the time this runs
    first, *_, last = name.split()
    ssn_last4 = ssn.replace("-", "")[-4:]
    ...
```

If the model really does need to read a kind of value, leave that kind out
of `detect` so it stays visible (see below).

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

Names are found with word lists and rules, not a statistical model: about
98,000 first names and 560,000 surnames from Wikidata and the 2010 US Census,
leaving out the ones that are everyday English words (by `wordfreq`
frequency) unless no dictionary has them ("Damien" and "Thompson" stay; the
ENABLE word list decides). That works well on forms, statements, messages and structured
data. In free-flowing prose, though, it misses a name that's on no list and
has no title or label before it. Pass a `name_finder` (any function from text
to a list of names) to close that gap. Each name it returns gets every variant spelling covered,
like names given to `add_person`.

## A second check: a guardrail

```python
from veil.anthropic import Findings, GuardrailError, wrap

class MyGuardrail:
    def check(self, texts: list[str], source: str) -> Findings:   # source: "INPUT" or "OUTPUT"
        ...   # e.g. call Amazon Bedrock's ApplyGuardrail, Presidio or your own rules
        return Findings(hidden=[("SSN", "555 4433 33")], other=[])

client = wrap(anthropic.Anthropic(), Redactor(FINANCE), guardrail=MyGuardrail())
```

With a guardrail set, each new text in a request is checked before it's
sent:

- Anything in `hidden` (a placeholder kind and the text as written) that
  veil missed becomes a placeholder too.
- If `other` names anything it objects to, or `check` raises
  `GuardrailError`, the call raises `GuardrailError` and nothing is sent.

Replies are checked too. A taxpayer ID in a reply is taken out, because the
model only ever saw placeholders and shouldn't have written one.

## Development

```
pip install -e ".[dev]"
pytest
ruff check .
```

The tests include Snowman's original suite, run under the `US_TAX_K1`
profile. Among them are ten fictional K-1 specimens (their text is stored in
`tests/fixtures/`) and stress tests of taxpayer-ID formats.
