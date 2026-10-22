# PII-TRACE's language comparison: veil, the deerpark-PII taggers and PII-Tracer

The PII-TRACE report ([arXiv 2609.22200](https://arxiv.org/abs/2609.22200), §4.6 and Figure 3) compares detectors
language by language: character F1 on its test split in English, German, French, Italian, Russian and Korean (Latin,
Cyrillic and Hangul scripts). `benchmarks/languages_trace.py` runs that comparison for veil's rules, deerpark-PII-edge
and deerpark-PII-large, alone and with the rules, and for PII-Tracer itself, scored with `pii_trace.py`'s code, on a
4-core CPU:

```
python benchmarks/languages_trace.py fetch
python benchmarks/languages_trace.py --per 200 --out languages_trace_report/
```

## Read this first

* **These are not the report's test documents.** Its per-language test split isn't public: the released PII-TRACE
  subset is 500 English conversations, and the report says per-language results "will be available upon release".
  So each language is 200 messages drawn at random from public data in ai4privacy's format: pii-masking-openpii-1.5m's
  validation split for English, German, French and Italian (its "base" part) and Korean (its "asia-pacific" part), and
  wolframko/russian-pii-66k for Russian (it has no licence on its card and only a train split). Same languages, same
  metric and same scoring code; different, easier documents.
* **Single messages, not conversations.** The messages run 130–360 characters on average, and no detail is mentioned
  twice in one, so the report's consistency metrics (a detail hidden in every mention, across turns) can't be measured
  here. Its long-conversation difficulties don't arise either.
* **PII-Tracer was trained on ai4privacy.** The report (§3.7) trains it on 714k samples "including ... samples from the
  ai4privacy corpus". It scores 0.62–0.74 character F1 per language on PII-TRACE's test split (Figure 3) and 0.93–0.96
  here. deerpark-PII-large's base (`knowledgator/gliner-pii-large-v1.0`) doesn't say what it was trained on and may
  have seen ai4privacy too. Read both as upper bounds on this data.
* **Labels are ai4privacy's, mapped onto PII-TRACE's nine**: names and user names to private_person; street, building
  number, town and postcode to private_address; IDs, tax and social numbers, licences, passports, cards and accounts to
  account_number; dates to private_date; passwords to secret. A title, an age, a gender or a time is left unlabelled,
  as PII-TRACE leaves it. ai4privacy labels every date and every town alone; veil hides dates of birth only and keeps a
  town alone visible, so, as in `pii_trace.md`, the second set of tables leaves out dates and URLs.

## Results

### Character F1, all labels

| System | English | German | French | Italian | Russian | Korean |
|---|---|---|---|---|---|---|
| veil | 0.751 | 0.600 | 0.632 | 0.627 | 0.678 | 0.471 |
| edge | 0.854 | 0.832 | 0.874 | 0.872 | 0.897 | 0.788 |
| edge+rules | 0.873 | 0.801 | 0.867 | 0.865 | 0.898 | 0.800 |
| large | 0.917 | 0.895 | 0.914 | 0.917 | 0.972 | 0.888 |
| large+rules | 0.917 | 0.854 | 0.902 | 0.897 | 0.972 | 0.888 |
| pii-tracer | 0.935 | 0.932 | 0.932 | 0.938 | 0.962 | 0.939 |

Character precision / recall / details fully hidden / other words hidden, all labels:

| Language | Gold spans | veil | edge | edge+rules | large | large+rules | pii-tracer |
|---|---|---|---|---|---|---|---|
| English | 1196 | 0.947 / 0.622 / 59.9% / 0.45% | 0.961 / 0.769 / 77.6% / 0.30% | 0.948 / 0.809 / 81.4% / 0.63% | 0.956 / 0.881 / 89.2% / 0.49% | 0.942 / 0.892 / 90.2% / 0.85% | 0.886 / 0.991 / 98.7% / 3.27% |
| German | 1104 | 0.803 / 0.479 / 43.8% / 3.08% | 0.871 / 0.795 / 80.3% / 2.75% | 0.788 / 0.814 / 82.6% / 5.68% | 0.912 / 0.878 / 88.5% / 2.13% | 0.827 / 0.883 / 89.1% / 5.03% | 0.883 / 0.986 / 98.8% / 3.09% |
| French | 1154 | 0.907 / 0.485 / 44.2% / 1.05% | 0.941 / 0.816 / 82.1% / 0.81% | 0.907 / 0.830 / 83.1% / 1.78% | 0.940 / 0.889 / 89.5% / 0.95% | 0.910 / 0.895 / 89.9% / 1.89% | 0.882 / 0.988 / 98.3% / 2.99% |
| Italian | 1256 | 0.875 / 0.489 / 45.5% / 1.69% | 0.920 / 0.828 / 81.9% / 1.63% | 0.879 / 0.851 / 84.8% / 2.87% | 0.937 / 0.898 / 91.1% / 1.39% | 0.892 / 0.903 / 91.7% / 2.75% | 0.888 / 0.993 / 98.6% / 3.56% |
| Russian | 654 | 1.000 / 0.513 / 30.1% / 0.00% | 0.870 / 0.926 / 87.0% / 6.69% | 0.870 / 0.928 / 87.5% / 6.69% | 0.958 / 0.986 / 97.4% / 1.99% | 0.958 / 0.986 / 97.4% / 1.99% | 0.934 / 0.993 / 97.6% / 3.69% |
| Korean | 1154 | 0.929 / 0.316 / 25.6% / 0.14% | 0.793 / 0.783 / 66.2% / 7.04% | 0.791 / 0.808 / 70.0% / 7.16% | 0.868 / 0.908 / 88.6% / 2.42% | 0.865 / 0.911 / 89.0% / 2.56% | 0.910 / 0.970 / 91.9% / 4.52% |

### Character F1, without dates and URLs

| System | English | German | French | Italian | Russian | Korean |
|---|---|---|---|---|---|---|
| veil | 0.802 | 0.669 | 0.702 | 0.707 | 0.695 | 0.539 |
| edge | 0.921 | 0.879 | 0.930 | 0.906 | 0.893 | 0.801 |
| edge+rules | 0.924 | 0.836 | 0.918 | 0.897 | 0.894 | 0.814 |
| large | 0.964 | 0.942 | 0.959 | 0.957 | 0.971 | 0.916 |
| large+rules | 0.950 | 0.888 | 0.943 | 0.933 | 0.971 | 0.915 |
| pii-tracer | 0.926 | 0.924 | 0.923 | 0.931 | 0.962 | 0.935 |

Character precision / recall / details fully hidden / other words hidden, without dates and URLs:

| Language | Gold spans | veil | edge | edge+rules | large | large+rules | pii-tracer |
|---|---|---|---|---|---|---|---|
| English | 1029 | 0.913 / 0.715 / 68.0% / 1.24% | 0.960 / 0.885 / 87.3% / 0.26% | 0.921 / 0.927 / 91.7% / 1.38% | 0.953 / 0.976 / 97.3% / 0.46% | 0.915 / 0.989 / 98.4% / 1.61% | 0.871 / 0.989 / 98.5% / 2.69% |
| German | 930 | 0.792 / 0.578 / 51.8% / 3.09% | 0.862 / 0.897 / 88.2% / 2.56% | 0.769 / 0.916 / 91.0% / 5.51% | 0.906 / 0.981 / 97.1% / 1.93% | 0.809 / 0.984 / 97.8% / 4.86% | 0.871 / 0.983 / 98.6% / 2.35% |
| French | 997 | 0.904 / 0.574 / 51.2% / 1.05% | 0.939 / 0.922 / 91.0% / 0.76% | 0.901 / 0.936 / 92.2% / 1.74% | 0.936 / 0.983 / 97.4% / 0.90% | 0.902 / 0.988 / 97.9% / 1.84% | 0.868 / 0.984 / 98.1% / 2.52% |
| Italian | 1076 | 0.875 / 0.592 / 53.1% / 1.58% | 0.913 / 0.900 / 87.7% / 1.47% | 0.868 / 0.928 / 91.1% / 2.64% | 0.931 / 0.985 / 97.8% / 1.30% | 0.882 / 0.991 / 98.5% / 2.58% | 0.877 / 0.992 / 98.4% / 2.78% |
| Russian | 624 | 1.000 / 0.533 / 31.6% / 0.00% | 0.865 / 0.923 / 86.1% / 6.42% | 0.866 / 0.925 / 86.5% / 6.42% | 0.957 / 0.986 / 97.3% / 1.92% | 0.957 / 0.986 / 97.3% / 1.92% | 0.934 / 0.992 / 97.4% / 3.25% |
| Korean | 994 | 0.928 / 0.380 / 29.7% / 0.16% | 0.775 / 0.828 / 67.5% / 6.61% | 0.774 / 0.859 / 72.0% / 6.76% | 0.862 / 0.977 / 93.7% / 2.17% | 0.859 / 0.980 / 94.2% / 2.33% | 0.906 / 0.965 / 90.7% / 3.24% |

* veil: veil's rules alone (FINANCE profile)
* edge: deerpark-PII-edge (Deerpark/veil-tagger-edge) alone at 0.35
* edge+rules: veil + deerpark-PII-edge: everything either marks
* large: deerpark-PII-large (Deerpark/veil-control/out_large) alone at 0.35
* large+rules: veil + deerpark-PII-large: everything either marks
* pii-tracer: perplexity-ai/PII-Tracer (596M)

## What it shows

* **On all labels, PII-Tracer leads in five of the six languages** (character F1 0.93–0.94, and 0.96 in Russian,
  where deerpark-PII-large reaches 0.97). It finds the most (character recall 0.97–0.99) and hides the most other
  words (3.0–4.5%).
* **Without dates and URLs, deerpark-PII-large alone leads in five of the six** (0.94–0.97; Korean 0.92 against
  PII-Tracer's 0.94), with fewer other words hidden than PII-Tracer in every language (0.5–2.2% against 2.4–3.3%).
* **deerpark-PII-edge holds up in the European languages and Russian, and less well in Korean.** Without dates and URLs
  it scores 0.88–0.93 in the five, hiding 0.3–6.4% of other words (the most in Russian), and 0.80 in Korean, hiding
  6.6%. It marks ordinary Hangul words as names ("투어", "의도를", "참가자 명단에는"); veil now drops a Korean "name"
  made of everyday words (`veil.hangul`, `korean_names.md`). Before that, edge scored 0.69 in Korean and hid 23% of
  other words.
* **veil's rules add whole details and cost precision.** With the rules beside it, edge hides 0.4–4.5 points more details
  fully, but in German, French and Italian its character F1 drops (by 0.01–0.04), as the rules hide words the labels
  leave out. With the large checkpoint, F1 drops in all four Latin-script languages, by up to 0.05.
* **The rules alone are English-first.** Without dates and URLs they score 0.80 in English, 0.67–0.71 in the other
  European languages and Russian, and 0.54 in Korean, hiding 30–68% of details fully. They hide almost nothing they
  shouldn't in Russian and Korean (0.00% and 0.16%), and miss most of what's there.
