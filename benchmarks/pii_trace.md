# PII-TRACE: veil, its tagger and PII-Tracer

[PII-TRACE](https://huggingface.co/datasets/perplexity-ai/PII-TRACE) is Perplexity's benchmark of multi-turn
conversations with personal details labelled to the character
([blog](https://www.perplexity.ai/hub/blog/pii-trace-detecting-personal-data-before-it-leaves-the-device),
[report](https://arxiv.org/abs/2609.22200)). What is public is a 500-conversation subset: 2,653 labelled spans
under nine labels, all of them in user messages. `benchmarks/pii_trace.py` scores veil, its tagger
deerpark-PII-edge ([Deerpark/veil-tagger-edge](https://huggingface.co/Deerpark/veil-tagger-edge)) and Perplexity's
[PII-Tracer](https://huggingface.co/perplexity-ai/PII-Tracer) (pinned at `d25c16f`) on it, on a 4-core CPU:

```
python benchmarks/pii_trace.py --split test                                  # all nine labels
python benchmarks/pii_trace.py --split test --drop private_date,private_url  # the labels veil sets out to hide
```

The scoring is described at the top of the script. "Exact" is the dataset card's metric. "Char" is the report's
primary metric. "Contained" and "consistent" are closest to what veil is for: a detail is hidden only if all of it
is hidden.

## Read this first

* **The subset may not be a clean test for PII-Tracer.** The dataset card says the subset "may be used for
  training" and doesn't say whether PII-Tracer was trained on it. veil's tagger has never seen these conversations.
* **The 0.629 in the report is a harder test, not evidence either way.** The report gives PII-Tracer a character F1
  of 0.629 (precision 0.507, recall 0.830; Table 3) on the full benchmark's test split: 1,922 conversations in 13
  languages, 463 of them over 10,000 characters, each read in one 4,096-token window. With overlapping windows it
  gets 0.653. On that split's conversations under 1,000 characters its recall is 0.975, close to what it gets here,
  and most of the gap to the 0.98 below is precision. The public subset is English and every conversation is under
  2,500 characters, so the difference in scores doesn't show whether PII-Tracer was trained on it.
* **veil's rules were tuned on half of it.** After the first run, three rules were added from what veil missed: codes
  in groups of letters and digits, phone extensions after a comma, and an ID found in one turn hidden however a later
  turn spells it. They were tuned on the dev half (237 conversations; `--split dev`, by a hash of each ID). The test
  half (263 conversations, 1,343 spans) was read once with the final rules, and all the tables below come from it.
  The rules fit this dataset's formats, so the test half is still a kinder test than real text.
* **PII-TRACE labels things veil leaves visible on purpose.** It labels every date and every URL, while veil hides
  dates of birth only and keeps links. The second table leaves those two labels out.
* **The text is synthetic and regular.** It is English, its identifier formats are tidy, and each conversation is
  under 2,500 characters.

## Test half, all nine labels

| System | Exact F1 (typed, micro) | Exact F1 (typed, macro) | Exact F1 (untyped) | Char P | Char R | Char F1 | Overlap F1 | Contained | Consistent (2+ mentions) | Other words hidden |
|---|---|---|---|---|---|---|---|---|---|---|
| veil | – | – | 0.876 | 0.989 | 0.771 | 0.866 | 0.881 | 79.4% | 80.3% | 0.08% |
| model | 0.663 | 0.430 | 0.808 | 0.982 | 0.735 | 0.841 | 0.859 | 72.9% | 66.2% | 0.13% |
| union | – | – | 0.874 | 0.984 | 0.801 | 0.883 | 0.910 | 83.9% | 85.2% | 0.13% |
| redactor | – | – | 0.896 | 0.984 | 0.802 | 0.883 | 0.909 | 84.0% | 85.5% | 0.13% |
| pii-tracer | 0.731 | 0.633 | 0.877 | 0.979 | 0.981 | 0.980 | 0.978 | 94.8% | 87.9% | 0.19% |
| pii-tracer-conv | 0.851 | 0.802 | 0.946 | 0.987 | 0.998 | 0.992 | 0.991 | 99.6% | 99.3% | 0.11% |

## Test half, without private_date and private_url

| System | Exact F1 (typed, micro) | Exact F1 (typed, macro) | Exact F1 (untyped) | Char P | Char R | Char F1 | Overlap F1 | Contained | Consistent (2+ mentions) | Other words hidden |
|---|---|---|---|---|---|---|---|---|---|---|
| veil | – | – | 0.965 | 0.989 | 0.968 | 0.978 | 0.971 | 95.3% | 94.3% | 0.08% |
| model | 0.723 | 0.526 | 0.884 | 0.979 | 0.915 | 0.946 | 0.930 | 86.4% | 77.3% | 0.17% |
| union | – | – | 0.952 | 0.980 | 0.997 | 0.989 | 0.986 | 99.6% | 99.6% | 0.17% |
| redactor | – | – | 0.974 | 0.975 | 0.998 | 0.986 | 0.976 | 99.7% | 100.0% | 0.27% |
| pii-tracer | 0.727 | 0.600 | 0.899 | 0.976 | 0.977 | 0.977 | 0.975 | 94.1% | 87.9% | 0.19% |
| pii-tracer-conv | 0.852 | 0.791 | 0.966 | 0.985 | 1.000 | 0.992 | 0.992 | 100.0% | 100.0% | 0.11% |

Gold spans fully covered, by label (without dates and URLs):

| Label | veil | model | union | redactor | pii-tracer | pii-tracer-conv |
|---|---|---|---|---|---|---|
| private_person | 90.0% | 99.2% | 99.7% | 100.0% | 91.9% | 100.0% |
| private_email | 100.0% | 95.6% | 100.0% | 100.0% | 96.6% | 100.0% |
| account_number | 88.7% | 77.4% | 97.2% | 97.2% | 97.2% | 100.0% |
| private_address | 96.3% | 98.1% | 100.0% | 100.0% | 93.5% | 100.0% |
| private_phone | 100.0% | 74.8% | 100.0% | 100.0% | 86.9% | 100.0% |
| other_pii | 100.0% | 54.0% | 100.0% | 100.0% | 99.2% | 100.0% |
| secret | 100.0% | 69.7% | 100.0% | 100.0% | 96.0% | 100.0% |

Identifiers with every mention fully covered, by number of mentions (without dates and URLs):

| Mentions | n | veil | model | union | redactor | pii-tracer | pii-tracer-conv |
|---|---|---|---|---|---|---|---|
| 1 | 598 | 95.2% | 86.6% | 99.5% | 99.5% | 94.0% | 100.0% |
| 2 | 220 | 94.5% | 79.1% | 99.5% | 100.0% | 89.1% | 100.0% |
| 3-5 | 27 | 92.6% | 63.0% | 100.0% | 100.0% | 77.8% | 100.0% |
| cross-turn | 247 | 94.3% | 77.3% | 99.6% | 100.0% | 87.9% | 100.0% |
| all | 845 | 94.9% | 83.9% | 99.5% | 99.6% | 92.2% | 100.0% |

* veil: veil's rules alone (FINANCE profile), one Redactor per conversation
* model: deerpark-PII-edge alone (Deerpark/veil-tagger-edge, 45M) at 0.35
* union: veil + deerpark-PII-edge: everything either marks
* redactor: veil's Redactor with deerpark-PII-edge as the finder (TaggedRedactor().redactor()), one per conversation
* pii-tracer: perplexity-ai/PII-Tracer (596M), one message at a time
* pii-tracer-conv: perplexity-ai/PII-Tracer (596M), a conversation's user messages in one pass

## What the three rules changed (test half, without dates and URLs)

| System | Char F1 before | after | Contained before | after | Consistent (2+) before | after | Other words hidden before | after |
|---|---|---|---|---|---|---|---|---|
| veil | 0.899 | 0.978 | 76.9% | 95.3% | 71.3% | 94.3% | 0.08% | 0.08% |
| union | 0.963 | 0.989 | 92.5% | 99.6% | 89.9% | 99.6% | 0.17% | 0.17% |
| redactor | 0.960 | 0.986 | 92.6% | 99.7% | 90.3% | 100.0% | 0.27% | 0.27% |

Most of the gain comes from the code rule. On dev, the cross-turn rule raised veil's own consistency from 89.3% to
92.1%, and added nothing once the tagger was there. Outside PII-TRACE, the rules leave veil where it was. On the 15
sets of agents' documents in `judged/docgen`, veil finds 71.5% of 9,545 details before and after, and hides 3.86% of
other words before and 3.87% after. On `hard/` it finds 158 of 184 details before and after, and keeps 98 of the 121
look-alikes.

## What it shows

* On the labels veil sets out to hide, veil with its tagger now hides every character of 99.6–99.7% of the details
  and every mention of 99.6–100% of those that recur. PII-Tracer reading one message at a time gets 94.1% and 87.9%,
  and reading the whole conversation it gets 100% and 100%. All of them hide 0.1–0.3% of other words.
* On all nine labels, PII-Tracer still leads (char F1 0.980 against 0.883), almost all of it from dates and URLs.
* Typed and exact scores favour PII-Tracer by design. It was trained on PII-TRACE's own labels and boundaries, while
  the tagger's kinds are mapped onto them (NAME→private_person, SSN and IDs→other_pii, and so on) and it has no secret
  or URL kind. veil's rules give no type, so they are scored untyped only.
* What veil hides is read from its output: the words gone from it, plus the marks inside each value it replaced (the
  "+" of "+1 202 555 0133"). An earlier version of this page read only the words, which understated veil's phone
  numbers.

## One message at a time or the whole conversation: deerpark-PII-edge and deerpark-PII-large

The test half again, each GLiNER checkpoint at veil's threshold of 0.35, alone and with veil's rules ("+ rules",
system `union:`). "Whole conversation" gives the tagger a conversation's user messages joined in one pass
(`tagger-conv:` and `union-conv:`; no conversation has more than 232 words of them). veil's rules always keep one
Redactor per conversation. The checkpoints:
- **deerpark-PII-edge**: [Deerpark/veil-tagger-edge](https://huggingface.co/Deerpark/veil-tagger-edge), the published
  tagger (45M, ettin-encoder-32m).
- **deerpark-PII-large**: `out_large` in [Deerpark/veil-control](https://huggingface.co/Deerpark/veil-control)
  (deberta-v3-large).
- **deerpark-PII-edge (control)**: `out_edge` in the same repository, an edge model trained on the large's recipe.
  Neither control checkpoint was chosen or tuned for this, and 0.35 is deerpark-PII-edge's threshold, not the large's.

Without dates and URLs (character F1 / details fully hidden / every mention of recurring details hidden / other words
hidden):

| Model | One message, alone | Whole conversation, alone | One message + rules | Whole conversation + rules |
|---|---|---|---|---|
| deerpark-PII-edge | 0.946 / 86.4% / 77.3% / 0.17% | 0.966 / 92.6% / 89.9% / 0.15% | 0.989 / 99.6% / 99.6% / 0.17% | 0.990 / 99.6% / 100% / 0.15% |
| deerpark-PII-edge (control) | 0.912 / 81.4% / 64.4% / 0.25% | 0.957 / 91.2% / 87.4% / 0.15% | 0.981 / 99.8% / 100% / 0.25% | 0.988 / 99.7% / 100% / 0.16% |
| deerpark-PII-large | 0.934 / 93.3% / 90.3% / 0.85% | 0.951 / 90.6% / 88.7% / 0.16% | 0.956 / 98.9% / 100% / 0.85% | 0.986 / 99.4% / 100% / 0.16% |
| PII-Tracer | 0.977 / 94.1% / 87.9% / 0.19% | 0.992 / 100% / 100% / 0.11% | | |

All nine labels:

| Model | One message, alone | Whole conversation, alone | One message + rules | Whole conversation + rules |
|---|---|---|---|---|
| deerpark-PII-edge | 0.841 / 72.9% / 66.2% / 0.13% | 0.858 / 77.6% / 76.6% / 0.12% | 0.883 / 83.9% / 85.2% / 0.13% | 0.881 / 83.4% / 85.2% / 0.12% |
| deerpark-PII-edge (control) | 0.836 / 72.8% / 59.3% / 0.16% | 0.863 / 79.3% / 76.6% / 0.12% | 0.901 / 88.2% / 89.7% / 0.16% | 0.893 / 86.4% / 87.2% / 0.12% |
| deerpark-PII-large | 0.837 / 79.2% / 77.6% / 0.83% | 0.843 / 75.7% / 75.5% / 0.16% | 0.858 / 83.8% / 85.9% / 0.83% | 0.878 / 82.9% / 85.2% / 0.16% |
| PII-Tracer | 0.980 / 94.8% / 87.9% / 0.19% | 0.992 / 99.6% / 99.3% / 0.11% | | |

* **Alone, the whole conversation helps the edge models most.** Recurring details with every mention hidden rise from
  77% to 90% (deerpark-PII-edge) and from 64% to 87% (its control), and they hide fewer other words.
* **With the rules, the mode hardly matters.** Every deerpark-PII-edge or deerpark-PII-large combination hides 98.9–99.8% of the details, since
  the rules already carry an ID from turn to turn.
* **deerpark-PII-large is not better here.** One message at a time, it finds the most when used alone (93.3%), but it hides five
  times as many other words (0.85%), at a threshold not chosen for it. Over the whole conversation, that falls to
  0.16% and it finds less than deerpark-PII-edge.
* **Alone, PII-Tracer beats every Deerpark checkpoint in both modes.** With veil's rules beside them, the Deerpark
  models match it on these labels.

### deerpark-PII-large's threshold, chosen on dev

`benchmarks/pii_trace_threshold.py` picks deerpark-PII-large's threshold on the dev half (237 conversations, dates and
URLs left out) by the rule in `judged/PROTOCOL.md`: the threshold that hides the most details in full while hiding no
more other words than deerpark-PII-edge at 0.35 does on the same documents. It chooses for each mode on its own.

| Mode | Chosen | Dev: large / edge, fully hidden | Test: large / edge, fully hidden | Test: other words hidden, large / edge |
|---|---|---|---|---|
| alone, one message | 0.65 | 82.3% / 89.3% | 82.4% / 86.4% | 0.19% / 0.17% |
| alone, whole conversation | 0.95 | 45.8% / 93.5% | 44.4% / 92.6% | 0.03% / 0.15% |
| + rules, one message | 0.65 | 99.1% / 99.7% | 98.9% / 99.6% | 0.19% / 0.17% |
| + rules, whole conversation | 0.95 | 98.4% / 99.7% | 98.1% / 99.6% | 0.11% / 0.15% |

No threshold gets deerpark-PII-large to deerpark-PII-edge's results at deerpark-PII-edge's cost in other words.
One message at a time, it matches the edge's other words hidden only from 0.65 up, where it finds about 4–7 points
less. Over the whole conversation, it hides more other words than the edge at every threshold below 0.95, and at 0.95
it finds half as much. With veil's rules, it trails by under 1 point in every mode. Large only finds more if it may
hide more: one message at a time at 0.45, it hides 91.5% of the dev details in full, at 0.37% of other words.
