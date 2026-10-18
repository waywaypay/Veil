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
