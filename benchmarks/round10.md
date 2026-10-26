# Round 10: conversations, codes and secrets (a draft recipe)

A draft, written on 26 October 2026 before any round 10 data or model exists. Once agreed, it goes into
`judged/PROTOCOL.md` as round 10's section, as rounds 8 and 9 did, and this file is removed.

## Why

On PII-TRACE's test half (`pii_trace.md`), without dates and URLs, deerpark-PII-edge alone, one message at a time,
hides 86.4% of the details in full and every mention of 77.3% of the recurring ones. PII-Tracer gets 94.1% and 87.9%.
Edge leads on names (99.2% against 91.9%) and addresses (98.1% against 93.5%). The gap is in four labels:

| Label | edge | PII-Tracer | What the dev half's spans look like (`pii_trace_errors.py --gold-only`) |
|---|---|---|---|
| other_pii | 54.0% | 99.2% | IDs of letters and digits in groups: `MB-3VX3-VP8FF7`, `MD 6DQ6 QJ7SM4`, `MB/…`, `MB7VX3QY3FZ6` |
| secret | 69.7% | 96.0% | codes of nine digits after "access code" or "comparison code": `549984606`, `131-716-284`, `906.419.528` |
| private_phone | 74.8% | 86.9% | 103 of 111 with an extension: `+1 202 555 0137 ext 11037`, `+1 (202) 555-0187, extension 12387` |
| account_number | 77.4% | 97.2% | references in four groups: `AC-3DS5-KQ5L-R9FL`, `PR 5NS2 BJ9B H8GR`, `AC/2CN7/VN5E/C6JN` |

Veil's rules hide nearly all of these, so with the rules beside it edge already matches PII-Tracer
(99.6–99.7% hidden in full). Round 10 is for the tagger alone: for anyone who uses it without veil's rules, and for
details whose format the rules don't know.

Some of this is still a hypothesis. That edge loses phones at the extension (a boundary miss) and codes for lack of
a kind (a recall miss) is inferred from the formats. The base model it was trained from splits 23% of the phones at
"ext". `pii_trace_errors.py` on edge itself settles it. Run it before building any data, and set the shares below by
what it finds:

* mostly **partial** (boundaries): weight the extension and separator variants, since that's what the data has to
  teach;
* mostly **lower threshold**: try thresholds per kind first (`kind_thresholds.py`); the data may then need less;
* mostly **missed**: the recipe as written.

## Starting point

Round 9's chosen model, if round 9 has been trained by then; otherwise round 7's published model. If round 9 hasn't
started, its protocol may instead take these sources in, as round 9 took round 8's. Four 500-step segments at most.

## New labels

The tagger has no kind for a secret. Add these labels to `veil.tagged.LABELS`:

* `password or access code`: passwords, PINs, passcodes, access, security, recovery and one-time codes, Wi-Fi keys;
* `api key`: API keys, tokens and private keys (`sk-…`, `ghp_…`, `AKIA…`, `xoxb-…`, `-----BEGIN … KEY-----`).

Both map to veil's `ID` placeholder for now. A `SECRET` kind of its own in veil is a separate change. In
`pii_trace.py`, they map to `secret`. The labelling rules (`judged/docgen/RULES.md`) gain both rows, and a line saying
that a phone number's extension is part of its span.

## The line between a private code and one that stays

`RULES.md` leaves order, invoice, case, tracking and version numbers visible. PII-TRACE marks a "reference number" or
an "ID" whatever it refers to. Round 10 keeps veil's line, and teaches it by the words around a value, not its shape:

* **marked**: a value that is a person's account, membership, policy, patient, customer or loan number, or their
  credential, by its label or sentence ("my member ID is…", "policy no.", "the access code for my account");
* **left unmarked**: the same shapes as order, invoice, ticket, tracking, case, booking, SKU, build and version numbers,
  commit hashes, UUIDs in code, hex colours, timestamps and amounts.

Every source below writes both, so the model can't learn "letters and digits in groups" as a detail. A PII-TRACE
"reference number" that names no account is scored as a miss on its test half, and the report says how many such
spans there are.

## Data

**A. `chatgen.py`, generated conversations: 4,000, a fifth dev.** User messages to an assistant, two to six turns,
under 300 words in all. Made-up people (Faker, the locales `r9gen.py` uses). English for 80%; German, French, Spanish,
Dutch and Italian share the rest. Each conversation plants three to eight details from:

* phone numbers with extensions in every common form (`ext 204`, `ext. 204`, `x204`, `, extension 204`, `#204`) and
  without; with country codes, parentheses, dots, dashes and spaces; numbers outside North America;
* IDs and references of letters and digits: two to five groups, separated by `-`, a space, `/`, `.` or nothing, in
  upper and mixed case, after a cue from the marked list above;
* access codes and secrets: four to twelve digits in groups of three or four (`-`, space, `.`), passwords, PINs, API
  keys in their providers' formats, recovery and one-time codes;
* emails written plain, obfuscated (`at … dot …`, `[at]`, `(dot)`) and with spaces around the `@`;
* names, addresses and dates of birth, at a smaller share. Edge is already strong on these, and they are there so it
  stays that way.

And for what repeats across turns:

* the same value again in a later turn, half the time written differently (spaces for dashes, lower case, without the
  country code);
* corrections and supersessions ("the old code was 549984606; the new one is 113821102"): both are marked;
* two people with one surname, and a first name alone in a later turn after the full name in an earlier one.

Every conversation also holds two or more look-alikes from the left-unmarked list.

**B. Agent-written chats: 300, a fifth dev.** As `judged/docgen`, by agents writing to `RULES.md` with the two new
labels. Families: support and account recovery, banking and insurance, travel and bookings, IT helpdesk, a developer
pasting config, logs or `.env` files (keys among harmless settings), help filling in a form, and chats with nothing
personal in them. These agents never see PII-TRACE or `chatgen.py`'s output. This source exists so the round isn't
learning one generator's templates.

**C. Replayed, so nothing learned is lost:** 6,000 chunks of round 9's mix (round 7's, if round 9 wasn't trained), and
round 2's judged WildChat turns.

**D. Whole conversations.** Half of A's and B's conversations are trained with their user messages joined by blank
lines (`pii_trace.SEP`) as one example, and half as one message each. Edge alone gains the most from reading a
conversation whole (86.4% to 92.6% hidden in full; 77.3% to 89.9% of recurring details), and it has never been trained
that way. Inference chunks at 200 words (`tagged.chunks`), and PII-TRACE's longest conversation has 232 words of user
text, so 300-word chunks with overlap are tried on dev too.

Shares, before the error analysis changes them: A 45%, B 15%, C 40%. Example lengths are cut as in rounds 6 to 9
(over 2,048 tokens, to the first 1,024).

**Never used for training or choosing:** PII-TRACE in any form. Its dev half is reported at each dev check as a
readout but is not in the choosing mean, so its test half stays a readout of a model not chosen for it.

## Choosing

`PROTOCOL.md`'s rule, on dev only: the segment and threshold with the highest mean found over the dev slices, with a
mean share of other words hidden no higher than the starting model's at its threshold on the same slices. Dev is
round 9's dev slices, plus A's and B's fifths. A's dev fifth counts its look-alikes as other words, so a model that
hides order numbers pays for it.

## Testing, once, after the choice

* PII-TRACE's test half: the chosen model beside the starting model and PII-Tracer, alone and with veil's rules, one
  message at a time and whole conversation, all nine labels and without dates and URLs.
* A locked chat test, built before any round 10 training data and kept from those who make it: 150 conversations by
  new agents, judged blind, and 300 WildChat conversations from shards 8 and 9 that the second locked test didn't use.
  This is the clean readout. PII-TRACE's formats are what the data was aimed at, so its test half is a kinder test.
* The second locked test, as a second look (not clean), to show nothing was lost on documents, forms, tweets and
  emails.

## Targets

The model alone, one message at a time, on PII-TRACE's test half without dates and URLs:

* at least 95% of each of other_pii, secret, private_phone and account_number hidden in full;
* at least 94.1% of all details hidden in full and 87.9% of recurring ones with every mention hidden, PII-Tracer's one-message
  figures;
* at most 0.17% of other words hidden, edge's figure now;
* on the locked chat test and the second locked test, no fall in found and no rise in other words hidden beyond their
  intervals.

The result is reported whichever way it falls.

## Work this needs

* `benchmarks/round7/chatgen.py` and `round10.py` (build, train and dev, as `round9.py`), the B agents' brief, and the
  locked chat test's brief;
* the two labels in `veil/tagged.py`, `pii_trace.py`'s mapping, and their rows in `RULES.md`;
* `pii_trace_errors.py` run on the starting model first, and its numbers added under "Why".

## To decide

1. Whether the new labels map to `ID` or to a new `SECRET` kind in veil.
2. Whether round 10 starts from round 9 or from round 7, or is folded into round 9.
3. Whether "booking reference" is marked (a person's trip) or left visible (like an order number). This draft leaves
   it visible.
