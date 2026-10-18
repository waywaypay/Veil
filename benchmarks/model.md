# A span tagger beside veil

veil finds names with word lists and rules. These are tests of a small statistical model beside it: a GLiNER span
tagger, which reads a text and marks the stretches that are a name, an address, a phone number and so on, giving
their exact positions (it writes nothing). It runs on a CPU. veil runs first; the tagger can only add to what veil
hides, and a name it adds is added with `add_person`, so all its spellings are covered and it's put back as written.

Scripts: `tagger.py` (shared), `tagger_sets.py` (20 test sets), `chats.py` (real AI chats), `train_tagger.py`
(fine-tuning, rounds 1 and 2), `train_wider.py` (rounds 3 to 6), `locked.py` (the locked test). Data and caches go
to `benchmarks/data` (`$VEIL_BENCH_DATA`). Figures are found / other words hidden, on each dataset's own labels, not
adjudicated (the hand audit in `audit.md` found that raw labels overstate veil's mistakes about four times on
Gretel), except where a section says its spans were judged.

## The models

| Model | Built on | Parameters | Smallest file kept | Licence |
|---|---|---|---|---|
| `knowledgator/gliner-pii-edge-v1.0` ("edge") | `jhu-clsp/ettin-encoder-32m` | about 45M | 46 MB (its int8) | Apache-2.0 |
| `knowledgator/gliner-pii-base-v1.0` ("base") | `microsoft/deberta-v3-small` | about 166M | 197 MB (its int8) | Apache-2.0 |
| `nvidia/gliner-PII` ("large") | `microsoft/deberta-v3-large` | 570M | 1.8 GB (PyTorch) | NVIDIA Open Model Licence |
| edge, fine-tuned on Gretel (round 1) | edge | about 45M | | |
| edge, fine-tuned on the mix (round 2) | round 1 | about 45M | 91 MB (weights stored in 16 bits, below) | |
| edge, rounds 3 to 6 (below) | the round before | about 45M | 91 MB (16 bits; round 6 gives PyTorch's spans on 498 of 500 texts, two names scored at the threshold falling the other way) | |

NVIDIA's model was trained on Nemotron-PII, so its Nemotron figures are in distribution, as are round 2's (trained
on Nemotron's training split; tested on its test split). Knowledgator doesn't say what its models were trained on.

Seconds a page (1,400 characters), in PyTorch on 4 cores held to AVX2 as a 2018 laptop's: edge 0.43, base 0.54, large
2.1; veil alone 0.013.

## Off the shelf, with veil

Thresholds 0.4. "Names" adds only the tagger's names to what veil hides; "alone" is the tagger without veil.

| Set | veil | edge, names | large, names | edge alone | large alone |
|---|---|---|---|---|---|
| Gretel finance (veil's held-out) | 95.6 / 1.09 | 95.8 / 1.10 | 95.7 / 1.13 | 82.0 / 4.31 | 76.3 / 1.68 |
| Nemotron, plain | 91.5 / 0.09 | 94.5 / 0.09 | 93.5 / 0.09 | 94.0 / 1.44 | 96.3 / 1.15 |
| Nemotron, lower case | 76.3 / 0.21 | 85.3 / 0.21 | 85.3 / 0.21 | 92.8 / 2.07 | 96.5 / 1.12 |
| Nemotron, fax | 80.0 / 0.26 | 83.8 / 0.33 | 82.8 / 0.35 | 93.8 / 2.53 | 96.5 / 1.18 |
| Gretel en-v1 | 82.8 / 1.10 | 83.6 / 1.14 | 83.7 / 1.19 | 93.7 / 3.59 | 93.1 / 5.27 |
| ai4privacy, English | 49.8 / 2.11 | 56.9 / 2.24 | 58.5 / 2.46 | 90.8 / 10.79 | 93.3 / 8.74 |
| ai4privacy, 5 other languages | 42–49 / 2.2–4.4 | 48–58 | 52–59 | 90–95 / 14–26 | 92–95 / 7–10 |
| TAB court judgments (real) | 84.7 / 0.43 | 90.9 / 0.46 | 91.4 / 0.45 | 70.2 / 2.79 | 81.8 / 0.91 |
| CoNLL-2003 news (real) | 78.1 / 1.22 | 81.7 / 1.33 | 92.0 / 1.31 | 50.0 / 21.77 | 97.5 / 10.07 |
| OntoNotes (real) | 75.7 / 0.67 | 79.8 / 0.68 | 87.9 / 0.74 | 49.1 / 4.86 | 90.2 / 1.65 |

Adding names costs almost nothing in other words hidden and finds 3–16 points more in prose, lower case and chats.
Adding every kind finds more again but hides towns (which veil leaves visible in a sentence), sports teams, dates
and amounts taken for account numbers: 7–14% of other words in news and other languages. On veil's own kind of
document the models add little; there the larger model ties the smaller ones, and in people's prose it finds 6–10
points more names.

The tables add what a model returns after veil. Through `name_finder` a model's names are looked for after veil's
own too, only where nothing else is, so one that marks a first name and a surname apart ("Luigi", "Togliatti") no
longer makes veil miss the whole name.

## Trained for veil

The edge model, fine-tuned on CPU (bf16), in 500-step segments, with every choice made on dev sets and each test
set scored once at the end (`train_tagger.py` has the recipe):

* round 1: 2,500 steps on Gretel finance's English training split, the split veil's rules were tuned on (noise
  spans the benchmark adjudicates away left unlabelled);
* round 2: 1,500 steps more on Gretel chunks, Nemotron-PII's training split (a town or postcode labelled only as
  part of a street address, as veil hides them) and 1,800 chunks of WildChat turns from shards the chat tests don't
  use, judged: 1,019 private people's details labelled, 4,440 public and fictional names and ordinary words left
  unlabelled.

Round 1 on Gretel's dev documents (threshold 0.4): 79.0 / 4.56 untrained, 96.2 / 1.07 after 1,000 steps, 96.3 / 0.85
after 2,500 (veil: 95.9 / 1.29). The threshold chosen on dev is 0.35.

The tagger alone, on the test sets:

| Set | veil | edge | round 1 | round 2 |
|---|---|---|---|---|
| Gretel finance (veil's held-out) | 95.6 / 1.09 | 82.0 / 4.31 | 95.8 / 0.88 | 95.6 / 0.78 |
| Nemotron, plain | 91.5 / 0.09 | 94.0 / 1.44 | 95.8 / 0.34 | 96.3 / 0.30 |
| Nemotron, lower case | 76.3 / 0.21 | 92.8 / 2.07 | 92.3 / 0.33 | 93.8 / 0.24 |
| Nemotron, fax | 80.0 / 0.26 | 93.8 / 2.53 | 93.3 / 0.86 | 93.5 / 0.54 |
| Gretel en-v1 | 82.8 / 1.10 | 93.7 / 3.59 | 94.6 / 1.45 | 96.9 / 2.29 |
| ai4privacy, English | 49.8 / 2.11 | 90.8 / 10.79 | 83.5 / 4.61 | 85.7 / 4.46 |
| TAB court judgments (real) | 84.7 / 0.43 | 70.2 / 2.79 | 93.6 / 1.09 | 97.5 / 0.57 |
| CoNLL-2003 news (real) | 78.1 / 1.22 | 50.0 / 21.77 | 92.6 / 7.21 | 90.5 / 6.01 |
| OntoNotes (real) | 75.7 / 0.67 | 49.1 / 4.86 | 93.1 / 1.60 | 91.6 / 0.86 |

On Gretel the trained tagger finds as much as veil's rules and hides a fifth (round 1) to a quarter (round 2) fewer
other words; the lead dev showed in finding (1.4 points) didn't carry to test. It learned what Gretel never labels (a
town alone, a date, an amount, "Lender") and names in prose, so it improved on text it never saw too: in OntoNotes it
finds more than the model thirteen times its size. It's still a different trade from veil's off Gretel: more found,
more other words hidden.

## Real AI chats

`chats.py`: English messages people sent ChatGPT (WildChat-1M), user turns in order through one Redactor a
conversation, profile GENERIC. 316 conversations Presidio found something in, its markers filled with made-up
names, emails and phone numbers, and 400 it found nothing in. Every run of words a system hid that wasn't put there
was judged in context: 931 details in all, 446 put back and 485 real ones Presidio left; and "public" names, a
public figure's or a fictional character's, which hiding protects no one by.

| | Found | Other words hidden: chats with details / without | Public names hidden |
|---|---|---|---|
| veil | 83.2 | 0.46 / 0.32 | 1.94 |
| veil, `typed=True` | 87.4 | 1.31 / 1.33 | 2.41 |
| veil + edge's names | 86.4 | 0.47 / 0.36 | 2.24 |
| veil + large's names | 89.0 | 0.51 / 0.44 | 2.66 |
| veil + round 2's names | 87.4 | 0.61 / 0.48 | 2.68 |
| round 1 alone | 92.7 | 1.40 / 1.66 | 2.95 |
| round 2 alone | 93.7 | 0.90 / 0.63 | 2.56 |

In chats, the largest cost isn't what's missed but the names of public figures and fictional characters hidden
with the private ones (Frodo Baggins, Hermione Granger, a visual novel's cast): 1.9% of every word in ordinary
chats with veil alone, six times its other mistakes, and an assistant asked for a story about NAME_001 and NAME_002
doesn't know who they are. Most of it is veil's word lists, which a tagger added after veil can't take back; and the
tagger, trained with such names left unlabelled, hides them only a little less (2.95% to 2.56%). Telling a private
person from a character takes knowing who's famous.

What's still missed in chats: a phone number written bare in a sentence, a name after "I'm" or with "san", address
lines from outside Europe and North America, usernames and `@Author` tags in pasted code.

## Rounds 3 to 6

`train_wider.py`, each round from the last one's model, in 500-step segments, every checkpoint and threshold chosen
on dev sets:

* round 3: Gretel finance's other languages, Gretel pii-masking-en-v1, TAB's training split, Privy's API payloads,
  `taxgen.py`'s tax-form snippets, and round 2's mix replayed;
* round 4: 400 documents of ten families written by Claude agents (`judged/docgen`: letters, forms, logs, chats,
  invoices, records in many locales), `formgen.py`'s forms in 38 locales, tweets and posts (Broad Twitter Corpus,
  WNUT-17) with each person and handle judged private or public, receipts and résumés with a made-up person written
  in, press releases and EU court texts with nothing personal in them, and round 3's mix replayed;
* round 5: half of round 4's mix, more of round 3's, round 2's judged chats, fresh tax-form snippets, the tweets again
  (one segment);
* round 6: from round 5, aimed at what round 4 missed on dev: 320 documents by eight more agents
  (`judged/docgen/round6`: health and insurance numbers, bank lines and payment files, staff and customer numbers,
  German, Dutch, Nordic and Romance-language prose, Asian, African and Middle Eastern names, taxpayer IDs in markup,
  chats with nothing personal in them), round 4's documents again, round 5's mix, fresh forms and tax snippets.

From round 6 on the choice followed a rule written down before its results (`judged/PROTOCOL.md`): among
checkpoints and thresholds, the highest mean found over the 13 dev slices whose mean share of other words hidden is
no higher than the best so far's. Round 6's third segment at 0.4 won (94.0 / 2.72, against round 5's 93.4 / 3.18 and
round 4's 93.3 / 3.26); `PROTOCOL.md` has each step and the model's hash. A normaliser that decodes HTML entities,
%-escapes and Unicode digits before the tagger reads lost on dev and isn't used.

## The locked test

Five test sets made for the last round, before its model was chosen, and scored once after (`locked.py`; keys and
verdicts in `judged/locked.json`):

* 150 documents written by ten new agents, who never saw the training documents or the earlier tests, labelled by
  their writers (`judged/docgen/locked`);
* 300 forms from a `formgen.py` seed no other set uses;
* 700 tweets and posts from the corpora's test splits that no earlier sample took;
* 197 Enron emails from mailboxes in a file the earlier sample didn't draw on;
* 720 WildChat conversations from four shards no other set uses (320 with Presidio's markers filled in, 400 without).

In the tweets, emails and chats, every run of words any system hid (veil, rounds 2 to 6) and every person and handle
the tweet corpora label was judged in context to `judged/wider_rules.md` by Claude reviewers not told which system hid
it: 2,257 spans in tweets, 4,017 in emails, 4,673 in chats. A detail counts as found when every word of it is hidden;
public figures' names count against a system that hides them; a business's own contact details count neither way.

Found / other words hidden; the model at the threshold chosen on dev, veil with it through the "checked" gate:

| Set | veil | round 2 | round 3 | round 4 | round 5 | **round 6** | veil + round 6 |
|---|---|---|---|---|---|---|---|
| 150 documents by new agents | 65.1 / 3.91 | 76.2 / 4.52 | 74.3 / 4.16 | 87.9 / 4.49 | 88.0 / 4.58 | **91.0 / 3.95** | 85.1 / 6.22 |
| 300 forms (seed 96) | 73.9 / 2.53 | 80.8 / 4.90 | 78.5 / 3.53 | 97.3 / 2.15 | 97.1 / 2.36 | **97.8 / 1.52** | 87.3 / 3.60 |
| 700 tweets and posts | 85.6 / 3.81 | 82.4 / 7.94 | 78.3 / 7.07 | 83.8 / 7.33 | 80.3 / 7.44 | **92.5 / 5.79** | 87.0 / 5.16 |
| 197 Enron emails | 86.4 / 1.23 | 80.8 / 0.96 | 88.8 / 1.09 | 83.7 / 1.22 | 84.0 / 1.18 | **86.9 / 0.94** | 91.8 / 1.87 |
| 720 chats | 87.4 / 1.32 | 94.1 / 1.46 | 94.0 / 1.58 | 94.8 / 1.65 | 94.0 / 1.61 | **95.0 / 1.61** | 92.5 / 1.78 |

Paired 95% bootstrap intervals over texts (conversations for chats), found; other words hidden. An interval holding
zero is a tie:

| Set | round 6 alone − veil | veil + round 6 − veil | round 6 − round 4 | round 6 − round 5 |
|---|---|---|---|---|
| documents | +23.0 to +28.7; −0.38 to +0.52 | +17.4 to +22.6; +1.88 to +2.79 | +2.0 to +4.3; −0.79 to −0.30 | +2.1 to +4.0; −0.91 to −0.37 |
| forms | +21.1 to +26.8; −1.58 to −0.47 | +11.4 to +15.6; +0.79 to +1.37 | −0.2 to +1.1; −0.89 to −0.38 | +0.0 to +1.3; −1.09 to −0.60 |
| tweets and posts | +2.1 to +11.5; +1.50 to +2.51 | +0.2 to +3.0; +1.09 to +1.66 | +3.5 to +14.5; −1.86 to −1.23 | +5.8 to +19.1; −1.99 to −1.33 |
| Enron emails | −6.6 to +7.2; −0.68 to +0.01 | +4.1 to +6.8; +0.33 to +1.11 | +1.4 to +4.9; −0.41 to −0.16 | +0.9 to +4.9; −0.41 to −0.08 |
| chats | +5.7 to +9.5; +0.12 to +0.47 | +4.0 to +6.3; +0.32 to +0.64 | −0.8 to +1.2; −0.11 to +0.01 | +0.1 to +2.0; −0.07 to +0.08 |

What it shows:

* Alone, round 6 finds more than veil on documents, forms, tweets and chats, and ties it on Enron. It hides other words
  as often as veil on documents and Enron, less on forms, and more on tweets (+2 points) and chats (+0.3).
* Against rounds 4 and 5 it finds as much or more on every set and hides fewer other words on documents, forms,
  tweets and Enron; on chats it ties round 4 and finds a little more than round 5.
* veil with round 6 finds 91.8% in Enron, more than either alone, but in documents and forms it finds less than
  round 6 alone and hides more: veil's own placeholders cut into the spans the tagger would have hidden whole, and
  the gate keeps out what it can't check.
* None reaches 99%. The closest are forms (97.8%) and, counting a run that took in two details as the two details,
  chats (97.6%).

The losses:

* **Enron's distribution lists.** Three emails with long "Surname, First; Surname, First" lists hold 233 of the 395
  details round 6 misses in Enron: it hides the first names and leaves the surnames. veil misses 51 of them. Its
  interval (80.2 to 93.4) is so wide because of them.
* **Tweets.** It hides a tweet's other words half again as often as veil (5.79% against 3.81%). Both hide public
  figures' names and handles about as often (386 words and 362); the difference is link codes, hashtags and URL
  slugs (245 words against veil's 49).
* **Chats.** Public figures' and characters' names, which hiding protects no one by, are still about 1% of every word
  for every system; the tagger hides them a little more often than veil (0.97% against 0.83%).

Checks:

* **The same verdicts, a second time.** A second reviewer judged a random fifth of the items again without the first
  verdicts: chats 900 spans, 98.2% the same (kappa 0.97); Enron 680, 96.6% (0.93); tweets 434, 97.0% (0.95). Two
  other agents labelled 30 of the documents from scratch: 650 of the writers' 653 spans exactly the same, and round 6
  scores 89.7% on the writers' labels, 89.6% on theirs. The reviewers are the same model as the writers, working to
  the same rules, so this measures how consistently the rules are applied, not how far people would agree.
* **Long spans.** A judged span that took in two details (a name and its email) counts as one detail found only if
  both are hidden; counted as the details inside it, round 6 alone is 94.9% in tweets, 88.8% in Enron (veil 88.8%)
  and 97.6% in chats, the ranking unchanged.
* **Overlap with training.** The share of a locked text's 8-word runs found anywhere in training: a median of 0% in
  every set; the highest are four US tax forms (up to 35%, the IRS's own form text) and one stock tweet ("I posted a
  new photo to Facebook", 75%).
* **Coverage.** Every run of words any model alone hid is judged. veil and veil with a model leave a few runs no
  reviewer saw (up to 32 in chats, from a conversation's redactor hiding a name again in a later turn); each counts
  as a mistake.
* What happened along the way is in `judged/INTEGRITY.md` (who opened what, conflicting verdicts, a scorer fix made
  before scoring) and `judged/PROTOCOL.md` (each choice, and a training segment that ran out of memory and was run
  again).

### Earlier tests, now development data

Round 4's test sets, the 20 sets, the chat test and veil's taxpayer-ID stress cases were looked at while rounds 5
and 6 were designed, so they are development results here, not a test. Round 5's and round 6's spans in round 4's
tweets and emails weren't judged; each such run counts as a mistake. The tagger alone:

| Set | veil | round 2 | round 4 | round 5 | round 6 |
|---|---|---|---|---|---|
| 150 held-out agent documents | 65.4 / 3.96 | 78.4 / 4.45 | 87.6 / 4.40 | 88.3 / 4.46 | 91.1 / 3.86 |
| 300 held-out forms (seed 97) | 75.0 / 2.33 | 81.1 / 5.11 | 97.6 / 2.13 | 97.1 / 2.30 | 98.0 / 1.54 |
| 700 tweets and posts | 90.5 / 3.55 | 88.5 / 7.30 | 86.2 / 6.54 | 90.0 / 6.83 | 91.6 / 4.95 |
| 231 Enron emails | 87.2 / 0.86 | 90.1 / 0.91 | 92.7 / 0.88 | 93.3 / 1.01 | 94.7 / 0.86 |
| Gretel finance (veil's held-out) | 95.8 / 1.09 | 95.6 / 0.78 | 94.7 / 1.05 | 94.7 / 1.03 | 94.7 / 0.98 |
| Nemotron, plain | 92.8 / 0.07 | 96.3 / 0.30 | 97.0 / 0.14 | 97.0 / 0.16 | 97.0 / 0.11 |
| Nemotron, lower case | 77.3 / 0.21 | 93.8 / 0.24 | 95.0 / 0.22 | 95.5 / 0.20 | 95.0 / 0.21 |
| Nemotron, UPPER CASE | 86.8 / 0.40 | 86.0 / 0.47 | 93.0 / 0.51 | 91.8 / 0.41 | 89.0 / 0.30 |
| Nemotron, fax | 81.3 / 0.26 | 93.5 / 0.54 | 95.3 / 0.52 | 94.3 / 0.46 | 95.8 / 0.43 |
| Gretel en-v1 | 82.8 / 1.10 | 96.9 / 2.29 | 95.5 / 1.60 | 95.8 / 1.62 | 94.2 / 1.30 |
| ai4privacy, English | 49.8 / 2.11 | 85.7 / 4.46 | 78.4 / 3.31 | 80.8 / 3.65 | 78.0 / 2.94 |
| TAB court judgments (real) | 84.7 / 0.43 | 97.5 / 0.57 | 97.8 / 0.28 | 97.8 / 0.28 | 97.5 / 0.30 |
| CoNLL-2003 news (real) | 78.1 / 1.23 | 90.5 / 6.01 | 90.0 / 5.68 | 90.3 / 6.99 | 91.1 / 4.18 |
| OntoNotes (real) | 76.9 / 0.67 | 91.6 / 0.86 | 86.1 / 0.45 | 85.3 / 0.46 | 84.1 / 0.32 |
| chats (found; ordinary words hidden, with details / without; public names) | 84.5; 0.46 / 0.32; 1.94 | 93.6; 0.90 / 0.63; 2.56 | 93.7; 0.87 / 1.16; 2.60 | 93.2; 0.79 / 1.07; 2.65 | 93.3; 0.84 / 0.92; 2.43 |

Of veil's 74 taxpayer-ID formats that once leaked, round 6 alone still leaks 5 (round 2: 17, round 4: 11, round 5:
6); of 20 K-1 specimens, 1. The losses since round 2 are in news prose and labels it never trained on: OntoNotes
(91.6 to 84.1, though with fewer other words hidden), ai4privacy's fragments (85.7 to 78.0) and Gretel en-v1 (96.9
to 94.2), and against round 4, UPPER CASE text (93.0 to 89.0). The forms here differ slightly from round 4's report,
which drew them before `formgen.py` was made repeatable.

## Running it small

`train_tagger.py export` writes the model as ONNX, which gives the same spans as PyTorch on every text tried, and
`model_f16.onnx`, the same with its weights stored in 16 bits and cast back to 32 bits as ONNX Runtime loads it. Made
smaller, against full precision on 150 texts (Gretel, Nemotron, OntoNotes), and timed on 60 Gretel documents (4
threads, ONNX Runtime):

| File | Size | Spans as at full precision | Seconds a page |
|---|---|---|---|
| full precision | 181 MB | all | 0.57 |
| **weights stored in 16 bits** (`model_f16.onnx`) | **91 MB** | **all** | **0.56** |
| weights in 8 bits (`MatMulNBits`, blocks of 32), arithmetic in float | 117 MB | 99.4% | 0.64 |
| the same, the embedding table in 4 bits | 52 MB | 95.3% | |
| ONNX Runtime's usual int8 (`quantize_dynamic`, activations too) | 46 MB | 67.5% | 0.47 |

The usual int8 doesn't suit this model: many of its scores sit just over the threshold, and quantizing the
activations moves them under it, so the tagger alone found 73.0% on Gretel instead of 95.6%, and 80.3% of TAB's names
instead of 97.5% (Knowledgator's own models are trained for it). Storing the weights in 16 bits halves the file and
changes nothing else.

## Caveats

* Synthetic test sets come from generators the round 2 tagger (Nemotron) or veil and both rounds (Gretel) learned
  from; TAB, CoNLL-2003, OntoNotes, ai4privacy and the chats are the tests of what generalises.
* The chat details are found by pooling: a detail every system missed isn't counted, so every system's "found" is
  high by an unknown amount. Verdicts were by Claude reviewers working to written rules; spot checks agreed on 57 of
  60.
* 100–500 documents a set: differences under about two points are noise.
