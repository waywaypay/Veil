# PII-TRACE: veil, its tagger and PII-Tracer

[PII-TRACE](https://huggingface.co/datasets/perplexity-ai/PII-TRACE) is Perplexity's benchmark of multi-turn
conversations with personal details labelled to the character
([blog](https://www.perplexity.ai/hub/blog/pii-trace-detecting-personal-data-before-it-leaves-the-device),
[report](https://arxiv.org/abs/2609.22200)). What is public is a 500-conversation subset: 2,653 labelled spans
under nine labels, all of them in user messages. These are the scores of veil, its tagger
([Deerpark/veil-tagger-edge](https://huggingface.co/Deerpark/veil-tagger-edge)) and Perplexity's
[PII-Tracer](https://huggingface.co/perplexity-ai/PII-Tracer) (pinned at `d25c16f`) on that subset, from
`benchmarks/pii_trace.py`, on a 4-core CPU:

```
python benchmarks/pii_trace.py                                       # all nine labels
python benchmarks/pii_trace.py --drop private_date,private_url       # the labels veil sets out to hide
```

The two runs took about 3 minutes for veil and the tagger and about 6 for PII-Tracer's two ways of reading. The
scoring is described at the top of the script. "Exact" is the dataset card's metric. "Char" is the blog's headline
metric. "Contained" and "consistent" are closest to what veil is for: a detail is hidden only if all of it is hidden.

## Read this first

* **The subset is not a clean test for PII-Tracer.** The dataset card says the subset "may be used for training"
  and doesn't say whether PII-Tracer was trained on it. On its own 1,922-conversation test split, the blog gives
  PII-Tracer a character F1 of 0.629. Here it scores 0.993. Its numbers below are best read as an upper bound.
  veil's tagger has never seen these conversations.
* **PII-TRACE labels things veil leaves visible on purpose.** It labels every date and every URL, while veil hides
  dates of birth only and keeps links. Those two labels are 428 of the 2,653 spans. The second table leaves them out.
* **The text is synthetic and regular.** It is English, its identifier formats are tidy, and each conversation is
  under 2,500 characters.

## All nine labels

| System | Exact F1 (typed, micro) | Exact F1 (typed, macro) | Exact F1 (untyped) | Char P | Char R | Char F1 | Overlap F1 | Contained | Consistent (2+ mentions) | Other words hidden |
|---|---|---|---|---|---|---|---|---|---|---|
| veil | – | – | 0.719 | 0.989 | 0.662 | 0.793 | 0.785 | 59.9% | 54.1% | 0.08% |
| model | 0.659 | 0.424 | 0.817 | 0.984 | 0.753 | 0.853 | 0.873 | 74.7% | 68.4% | 0.13% |
| union | – | – | 0.811 | 0.984 | 0.775 | 0.867 | 0.888 | 79.2% | 77.5% | 0.13% |
| pii-tracer | 0.739 | 0.638 | 0.877 | 0.981 | 0.981 | 0.981 | 0.979 | 94.6% | 88.2% | 0.18% |
| pii-tracer-conv | 0.848 | 0.796 | 0.947 | 0.988 | 0.998 | 0.993 | 0.992 | 99.6% | 99.7% | 0.09% |

## Without private_date and private_url (2,225 spans)

| System | Exact F1 (typed, micro) | Exact F1 (typed, macro) | Exact F1 (untyped) | Char P | Char R | Char F1 | Overlap F1 | Contained | Consistent (2+ mentions) | Other words hidden |
|---|---|---|---|---|---|---|---|---|---|---|
| veil | – | – | 0.796 | 0.989 | 0.823 | 0.898 | 0.870 | 71.4% | 64.0% | 0.07% |
| model | 0.715 | 0.515 | 0.890 | 0.979 | 0.926 | 0.951 | 0.936 | 87.9% | 80.6% | 0.18% |
| union | – | – | 0.879 | 0.979 | 0.953 | 0.966 | 0.956 | 93.2% | 91.4% | 0.18% |
| pii-tracer | 0.735 | 0.602 | 0.896 | 0.979 | 0.980 | 0.979 | 0.978 | 94.2% | 89.0% | 0.18% |
| pii-tracer-conv | 0.845 | 0.777 | 0.962 | 0.987 | 0.999 | 0.993 | 0.992 | 99.8% | 100.0% | 0.09% |

Gold spans fully covered, by label:

| Label | veil | model | union | pii-tracer | pii-tracer-conv |
|---|---|---|---|---|---|
| private_person | 88.9% | 99.5% | 99.9% | 92.6% | 100.0% |
| private_email | 100.0% | 96.2% | 100.0% | 95.7% | 100.0% |
| account_number | 0.0% | 78.1% | 78.1% | 98.2% | 100.0% |
| private_address | 96.8% | 98.6% | 100.0% | 94.1% | 99.5% |
| private_date | 0.0% | 11.8% | 11.8% | 91.4% | 97.3% |
| private_phone | 37.6% | 73.4% | 94.5% | 87.2% | 99.5% |
| other_pii | 11.8% | 56.9% | 57.8% | 98.6% | 100.0% |
| secret | 100.0% | 76.2% | 100.0% | 98.1% | 99.0% |
| private_url | 0.0% | 0.0% | 0.0% | 100.0% | 100.0% |

Identifiers with every mention fully covered, by number of mentions (all nine labels):

| Mentions | n | veil | model | union | pii-tracer | pii-tracer-conv |
|---|---|---|---|---|---|---|
| 1 | 1395 | 64.2% | 73.0% | 77.1% | 94.8% | 99.6% |
| 2 | 515 | 55.9% | 69.7% | 78.8% | 88.2% | 99.8% |
| 3-5 | 76 | 42.1% | 59.2% | 68.4% | 88.2% | 98.7% |
| cross-turn | 591 | 54.1% | 68.4% | 77.5% | 88.2% | 99.7% |
| all | 1986 | 61.2% | 71.6% | 77.2% | 92.8% | 99.6% |

* veil: veil's rules alone (FINANCE profile), one Redactor per conversation
* model: veil's tagger alone (Deerpark/veil-tagger-edge, 45M) at 0.35
* union: veil + its tagger: everything either marks
* pii-tracer: perplexity-ai/PII-Tracer (596M), one message at a time
* pii-tracer-conv: perplexity-ai/PII-Tracer (596M), a conversation's user messages in one pass

## What it shows

* On the labels veil sets out to hide, veil plus its tagger ("union") hides every character of 93.2% of the details,
  and every mention of 91.4% of the details that recur. PII-Tracer reading one message at a time gets 94.2% and 89.0%.
  Reading a whole conversation in one pass, it gets 99.8% and 100%. All three hide about the same share of other
  words (0.1–0.2%).
* Where the tagger falls short: account and reference numbers (78%), "other" identifiers (57%) and phone numbers on
  their own (73%; 94.5% with veil's rules).
* Typed and exact scores favour PII-Tracer by design. It was trained on PII-TRACE's own labels and boundaries, while
  the tagger's kinds are mapped onto them (NAME→private_person, SSN and IDs→other_pii, and so on) and it has no secret
  or URL kind. veil's rules give no type, so they are scored untyped only.
