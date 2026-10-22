# PII-TRACE: veil, its tagger and PII-Tracer

[PII-TRACE](https://huggingface.co/datasets/perplexity-ai/PII-TRACE) is Perplexity's benchmark of multi-turn
conversations with personal details labelled to the character
([blog](https://www.perplexity.ai/hub/blog/pii-trace-detecting-personal-data-before-it-leaves-the-device),
[report](https://arxiv.org/abs/2609.22200)). What is public is a 500-conversation subset: 2,653 labelled spans
under nine labels, all of them in user messages. `benchmarks/pii_trace.py` scores veil, its tagger
([Deerpark/veil-tagger-edge](https://huggingface.co/Deerpark/veil-tagger-edge)) and Perplexity's
[PII-Tracer](https://huggingface.co/perplexity-ai/PII-Tracer) (pinned at `d25c16f`) on it, on a 4-core CPU:

```
python benchmarks/pii_trace.py --split test                                  # all nine labels
python benchmarks/pii_trace.py --split test --drop private_date,private_url  # the labels veil sets out to hide
```

The scoring is described at the top of the script. "Exact" is the dataset card's metric. "Char" is the blog's
headline metric. "Contained" and "consistent" are closest to what veil is for: a detail is hidden only if all of it
is hidden.

## Read this first

* **The subset is not a clean test for PII-Tracer.** The dataset card says the subset "may be used for training"
  and doesn't say whether PII-Tracer was trained on it. On its own 1,922-conversation test split, the blog gives
  PII-Tracer a character F1 of 0.629. Here it scores about 0.98. Its numbers below are best read as an upper bound.
  veil's tagger has never seen these conversations.
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
* model: veil's tagger alone (Deerpark/veil-tagger-edge, 45M) at 0.35
* union: veil + its tagger: everything either marks
* redactor: veil's Redactor with its tagger as the finder (TaggedRedactor().redactor()), one per conversation
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
