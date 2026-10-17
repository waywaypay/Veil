# A span tagger beside veil

veil finds names with word lists and rules. These are tests of a small statistical model beside it: a GLiNER span
tagger, which reads a text and marks the stretches that are a name, an address, a phone number and so on, giving
their exact positions (it writes nothing). It runs on a CPU. veil runs first; the tagger can only add to what veil
hides, and a name it adds is added with `add_person`, so all its spellings are covered and it's put back as written.

Scripts: `tagger.py` (shared), `tagger_sets.py` (20 test sets), `chats.py` (real AI chats), `train_tagger.py`
(fine-tuning). Data and caches go to `benchmarks/data` (`$VEIL_BENCH_DATA`). Figures are found / other words hidden,
on each dataset's own labels, not adjudicated (the hand audit in `audit.md` found that raw labels overstate veil's
mistakes about four times on Gretel).

## The models

| Model | Built on | Parameters | Smallest file kept | Licence |
|---|---|---|---|---|
| `knowledgator/gliner-pii-edge-v1.0` ("edge") | `jhu-clsp/ettin-encoder-32m` | about 45M | 46 MB (its int8) | Apache-2.0 |
| `knowledgator/gliner-pii-base-v1.0` ("base") | `microsoft/deberta-v3-small` | about 166M | 197 MB (its int8) | Apache-2.0 |
| `nvidia/gliner-PII` ("large") | `microsoft/deberta-v3-large` | 570M | 1.8 GB (PyTorch) | NVIDIA Open Model Licence |
| edge, fine-tuned on Gretel (round 1) | edge | about 45M | | |
| edge, fine-tuned on the mix (round 2) | round 1 | about 45M | 91 MB (weights stored in 16 bits, below) | |

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
