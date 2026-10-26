# How the next rounds of the tagger are chosen and tested

Written on 18 October 2026, before any round 6 result existed.

## Sets

* **Training**: everything in rounds 1 to 5, round 6's new agent-written documents, and generators run with training
  seeds only.
* **Dev**: the dev slices in `train_wider.py` (Gretel, Nemotron, Gretel's other languages, Gretel en-v1, TAB, tax
  forms, agent-written documents, synthetic forms, tweets, receipts, résumés) and the chat dev set. Every choice is
  made here.
* **Earlier tests, now development data**: the round 4 test sets (150 agent-written documents, 300 forms, 700 tweets,
  231 Enron emails), the 20 sets, the chat test set and veil's stress cases. They were looked at while rounds 5 and 6
  were designed, so they are reported, but as development results, not as the final test.
* **Locked tests**, built before the final model is chosen and scored once after it is:
  * 150 documents written by new agents who never see the training documents or the earlier tests;
  * synthetic forms from a seed no other set uses;
  * Enron emails from mailboxes and files the earlier sample didn't use;
  * tweets and posts not in any earlier sample;
  * chats from WildChat shards no set has used.

## Choosing

One rule, on dev only: among checkpoints and thresholds (and any change around the model, such as normalising its
input), take the one with the highest mean found over the dev slices whose mean share of other words hidden is no
higher than the current best's. Chats count as one slice, their ordinary and public words hidden together.

## Judging

Every run of words any system hides in a locked test set, and every detail a dataset labels, is judged in context to
the written rules, by reviewers who aren't told which system hid it. A second reviewer judges a random fifth again;
agreement is reported.

## Reporting

Found and other words hidden on each locked test set with 95% bootstrap intervals (over documents); differences
inside them are ties. The model alone and veil with the model, beside veil alone. Near-duplicates between training
and test text are checked and reported. Losses are reported with the wins.

## How the locked tests are scored

Written on 18 October 2026, after the locked sets were judged and before any system was scored on them
(`lockedtest.py score`, run once, after the final model is chosen).

* **Systems**: veil alone; rounds 2 to 5 and the chosen model, each alone and as veil with the model (its "checked"
  gate), at the thresholds chosen on dev (round 2 0.35, round 3 0.4, round 4 0.425, round 5 0.4). veil's profile is
  FINANCE, as in the earlier tests, and GENERIC with one redactor a conversation for chats.
* **Documents and forms** (150 documents by new agents; 300 forms from `formgen.docs(300, 96)`): a labelled detail is
  found when every word of it is hidden; other words hidden is the share of unlabelled words hidden.
* **Tweets, Enron emails and chats**: as round 4's test. Each span judged a private person's detail is a detail,
  found only when every word of it is hidden. Public names count as other words, so hiding them is a mistake; business
  details and unsure spans count neither way; a hidden word no verdict covers counts as another word hidden. A chat's
  filled-in details are details too. Chats report ordinary and public words hidden together, as on dev.
* **A check on span lengths**: the judged sets are scored a second time with every private-person span that holds a
  smaller one set aside (neither way), so a run that took in a name and its email counts as the two details in it.
  The first scoring is the result; the second is reported beside it.
* **Intervals**: 2,000 bootstrap resamples over texts (over conversations for chats), seed 0, percentile 95%.
  Differences between systems are paired (the same resamples); a difference whose interval holds zero is a tie.
  Reported: the chosen model alone and veil with it against veil, and the chosen model against each earlier round.
* **Agreement**: a second reviewer judges a random fifth of each judged set's items without the first verdicts;
  reported as raw agreement and Cohen's kappa over the five verdicts (`personal` of any label, `public`, `ordinary`,
  `business`, `unsure`) and over what scoring uses (private person's detail or not). A second labeller marks 30 of
  the locked documents (3 a family) from scratch; reported as span agreement and Cohen's kappa over words, and the
  models are scored on both labellings of those 30.

## Chosen

Frozen on 18 October 2026 at 09:02 UTC, before any system was scored on the locked sets: round 6's third segment at
a threshold of 0.4 (`pytorch_model.bin` sha256 `dcf0cb9a291d28dd90f4cde0b36c9c8574c9b17a5637cd4186e4a6b2f29f45a4`).
Means over the 13 dev slices, found / other words hidden, each step's bound the last best's other words hidden:

| | found | other words hidden | |
|---|---|---|---|
| round 4 at 0.425 | 93.33 | 3.26 | |
| round 5, segment 1 at 0.4 | 93.40 | 3.18 | the best before round 6 |
| round 6, segment 1 at 0.375 | 94.38 | 3.19 | over the bound |
| round 6, segment 1 at 0.4 | 93.53 | 2.81 | best |
| round 6, segment 2 at 0.35 | 94.82 | 3.16 | over the bound |
| round 6, segment 2 at 0.375 | 93.88 | 2.75 | best |
| round 6, segment 3 at 0.375 | 94.68 | 3.02 | over the bound |
| **round 6, segment 3 at 0.4** | **94.02** | **2.72** | **chosen** |
| round 6, segment 3 at 0.425 | 93.41 | 2.44 | |

Segment 2's first run ran out of memory at step 387 on one 7,897-token bank file; that example was cut to 1,024
tokens and the segment run again from segment 1 (`train_wider.py`'s `examples`). The three planned segments take
the mix once; no fourth was trained.

## Round 7 on: towards 99% found and under 1% other words hidden

Written on 18 October 2026, after round 6's locked test was scored and before any round 7 data existed.

* **Target**: the model alone, at one threshold chosen on dev, finding at least 99.0% of private people's details
  while hiding at most 1.00% of other words, on each of a second locked test's five sets.
* **The first locked test is development data now.** Its sets, and every earlier test, may be studied to decide what
  data to make. New model spans in its judged sets are judged before they're counted.
* **A second locked test**, made before round 7's training data and kept from everyone who makes that data: 150
  documents by ten new agents and 15 forms of many kinds (school, government, insurance, housing, tax outside the US,
  web submissions) by an eleventh, added before any round 7 model existed, forms from `formgen.py` seed 95, 200 Enron emails from the corpus's third file in
  mailboxes neither earlier sample used, tweets and posts 1,400 to 2,099 of the test splits' shuffle, and 720 chats
  from WildChat shards 8 and 9 (WildChat-1M has 14 shards; 0 to 7 and 10 to 13 are taken, 8 and 9 never used). It is judged blind and scored once, at the end, as the first was.
* **Choosing**: the rule above, on dev only. Dev is the earlier dev slices, the first locked test's five sets and a
  held-out fifth of each new source.
* **Stopping**: when the dev means reach the target, or when two rounds in a row add less than 0.3 points of mean
  dev found at no more other words hidden; then the second locked test is scored once either way, and the result
  reported as it falls.
* **Measurement ceiling**: on the first locked test, a second reviewer agreed on whether a span is a private
  person's detail 97.8% (Enron) to 98.8% (tweets) of the time, so a 99% found on the judged sets is near what the
  judging itself can tell apart. This is reported beside the result.

## Round 8: real public records

Written on 21 October 2026, after round 7 was published and before any round 8 model existed.

* **Data**: 320 real public documents (SEC Form 4, Form D and employment, separation and consulting agreements; IRS 990
  returns; CORD receipts; fetched by `r8_fetch.py`), labelled by agents under `r8/LABEL.md`. 40 more are held out of
  everything for a human-labelled real-document test. A fifth of the 320 is dev. Training mix: the 256 training
  documents three times over, plus 6,000 chunks of round 7's mix replayed.
* **Starting point**: round 7's published model. Four 500-step segments at most, no more whatever the dev scores say.
* **Choosing**: the rule above, on dev only: the segment and threshold that find the most, hiding no more other words
  than round 7's model at 0.35 does on the same dev sets. Dev is round 7's dev plus the public-record fifth.
* **The second locked test is no longer untouched.** Round 7's model was scored on it, and its misses were studied for
  the hide-by-default experiments. Round 8 is scored on it and reported, but as a second look and not a clean test.
  The clean readouts are the 40 held-out public records, scored once, and, when people have labelled them, the real
  documents.
* **Reported whichever way it falls**, with round 7's number beside it on the same sets. A gain on public records that
  costs found or other words hidden elsewhere is reported as that.

## Round 9: targeted synthetic documents with round 8's public records

Written on 21 October 2026, before any round 9 model existed. Round 8 was never trained (the CPU runs were cut off),
so its public records are folded in here.

* **Data**: round 8's public-record training documents (three times over); 3,000 documents from `r9gen.py`, aimed at
  what veil's rules and round 7's model still miss on practice data: addresses as other countries and scripts write them
  (Arabic, Persian, Cyrillic, Thai, Korean, Japanese, Chinese, Greek, Hebrew, Turkish, Irish house names, Argentine,
  Italian and German forms), forms with one box or space per letter, scanned copies with misread characters, names in
  parts (particles, initials, suffixes, nicknames, surnames first in capitals), Japanese, Chinese, Korean and Arabic
  names with honorifics and readings, a first name alone after a role, and staff numbers in payroll registers and
  timesheets; 800 chunks of W-2 layouts (the real IRS form and payroll providers, the training shards only); and 6,000
  chunks of round 7's mix replayed. 11,131 chunks in all. A fifth of `r9gen.py`'s documents is dev.
* **Starting point**: round 7's published model. Four 500-step segments at most.
* **Choosing**: the rule above, on dev only (round 7's dev, the public-record fifth and the `r9gen.py` fifth): the
  segment and threshold that find the most, hiding no more other words than round 7's model at 0.35 does on the same
  dev sets.
* **Testing**: the second locked test once with the chosen model, through veil's redactor and as two layers, reported
  beside round 7's model on the same documents. As for round 8, that test has been looked at (its misses guided the
  hide-by-default experiment, and the rules added since were checked on it once each), so it is a second look, not a
  clean test; the clean readouts are the 40 held-out public records and, once people label them, the real documents.
* **Reported whichever way it falls.**

## Round 10: conversations, codes and secrets

Written on 26 October 2026, before any round 10 data or model existed. Decided then: round 10 starts from round 7's
published model and is not folded into round 9; the two new labels for secrets map to veil's `ID` placeholder, and
veil gets no `SECRET` kind; booking references and reservation codes stay visible, like order numbers.

### Why

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

### Starting point

Round 7's published model, whether or not round 9 is trained by then. Round 10 is not folded into round 9, and it
doesn't take in round 9's data. Each round is measured against round 7 on its own, and either can be merged later.
Four 500-step segments at most.

### New labels

The tagger has no kind for a secret. Add these labels to `veil.tagged.LABELS`:

* `password or access code`: passwords, PINs, passcodes, access, security, recovery and one-time codes, Wi-Fi keys;
* `api key`: API keys, tokens and private keys (`sk-…`, `ghp_…`, `AKIA…`, `xoxb-…`, `-----BEGIN … KEY-----`).

Both map to veil's `ID` placeholder; veil gets no `SECRET` kind of its own. In `pii_trace.py`, they map to `secret`.
The labelling rules (`judged/docgen/RULES.md`) gain both rows, and a line saying that a phone number's extension is
part of its span.

### The line between a private code and one that stays

`RULES.md` leaves order, invoice, case, tracking and version numbers visible. PII-TRACE marks a "reference number" or
an "ID" whatever it refers to. Round 10 keeps veil's line, and teaches it by the words around a value, not its shape:

* **marked**: a value that is a person's account, membership, policy, patient, customer or loan number, or their
  credential, by its label or sentence ("my member ID is…", "policy no.", "the access code for my account");
* **left unmarked**: the same shapes as order, invoice, ticket, tracking, case, SKU, build and version numbers,
  commit hashes, UUIDs in code, hex colours, timestamps and amounts. Booking references and reservation codes stay
  visible too, like an order number: they point to a trip, not to a person's account.

Every source below writes both, so the model can't learn "letters and digits in groups" as a detail. A PII-TRACE
"reference number" that names no account, or a booking reference, is scored as a miss on its test half, and the
report says how many such spans there are.

### Data

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

**C. Replayed, so nothing learned is lost:** 6,000 chunks of round 7's mix (`round7_examples_seg3.json`, as rounds
8 and 9 replay it), and round 2's judged WildChat turns.

**D. Whole conversations.** Half of A's and B's conversations are trained with their user messages joined by blank
lines (`pii_trace.SEP`) as one example, and half as one message each. Edge alone gains the most from reading a
conversation whole (86.4% to 92.6% hidden in full; 77.3% to 89.9% of recurring details), and it has never been trained
that way. Inference chunks at 200 words (`tagged.chunks`), and PII-TRACE's longest conversation has 232 words of user
text, so 300-word chunks with overlap are tried on dev too.

Shares, before the error analysis changes them: A 45%, B 15%, C 40%. Example lengths are cut as in rounds 6 to 9
(over 2,048 tokens, to the first 1,024).

**Never used for training or choosing:** PII-TRACE in any form. Its dev half is reported at each dev check as a
readout but is not in the choosing mean, so its test half stays a readout of a model not chosen for it.

### Choosing

The rule above, on dev only: the segment and threshold with the highest mean found over the dev slices, with a
mean share of other words hidden no higher than round 7's model's at 0.35 on the same slices. Dev is round 9's dev
slices (round 7's, the public-record fifth and `r9gen.py`'s fifth, none of them trained on here), plus A's and B's
fifths. A's dev fifth counts its look-alikes as other words, so a model that hides order numbers pays for it.

### Testing, once, after the choice

* PII-TRACE's test half: the chosen model beside round 7's model and PII-Tracer, alone and with veil's rules, one
  message at a time and whole conversation, all nine labels and without dates and URLs.
* A locked chat test, built before any round 10 training data and kept from those who make it: 150 conversations by
  new agents, judged blind, and 300 WildChat conversations from shards 8 and 9 that the second locked test didn't use.
  This is the clean readout. PII-TRACE's formats are what the data was aimed at, so its test half is a kinder test.
* The second locked test, as a second look (not clean), to show nothing was lost on documents, forms, tweets and
  emails.

### Targets

The model alone, one message at a time, on PII-TRACE's test half without dates and URLs:

* at least 95% of each of other_pii, secret, private_phone and account_number hidden in full;
* at least 94.1% of all details hidden in full and 87.9% of recurring ones with every mention hidden, PII-Tracer's
  one-message figures;
* at most 0.17% of other words hidden, edge's figure now;
* on the locked chat test and the second locked test, no fall in found and no rise in other words hidden beyond their
  intervals.

The result is reported whichever way it falls.

### Work this needs

* `round7/chatgen.py` and `round10.py` (build, train and dev, as `round9.py`), the B agents' brief, and the
  locked chat test's brief;
* the two labels in `veil/tagged.py`, `pii_trace.py`'s mapping, and their rows in `RULES.md`;
* `pii_trace_errors.py` run on round 7's model first, and its numbers added under "Why".
