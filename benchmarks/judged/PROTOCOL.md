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
