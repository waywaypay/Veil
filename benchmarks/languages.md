# Across languages: veil's rules and the deerpark-PII taggers

`benchmarks/languages.py` scores veil's rules, deerpark-PII-edge
([Deerpark/veil-tagger-edge](https://huggingface.co/Deerpark/veil-tagger-edge), 45M) and deerpark-PII-large (`out_large`
in [Deerpark/veil-control](https://huggingface.co/Deerpark/veil-control), deberta-v3-large), each checkpoint alone and
with the rules, language by language, on a 4-core CPU:

```
python benchmarks/languages.py fetch
python benchmarks/languages.py --per 200 --docs 60 --out languages_report/
```

The sets:

* **ai4privacy open-pii-masking-500k** (validation split): short messages in English, German, Spanish, French, Italian,
  Dutch, Hindi and Telugu, 200 drawn at random from each.
* **ai4privacy pii-masking-400k** (validation split): short messages in six European languages, 200 from each.
* **Gretel synthetic_pii_finance_multilingual** (test split): finance documents in seven languages, the first 60 of
  each. deerpark-PII-edge was trained on this set's training split in the six languages other than English (round 3).

Figures are found / other words hidden, as in veilbench: a detail is found only if every word of it is hidden; other
words hidden is the share of words no label covers that a system hid. Labels are the datasets' own, mapped onto veil's
kinds as `tagger_sets.py` maps them, not adjudicated. Both checkpoints run at veil's threshold, 0.35. "+rules" hides
every word either the checkpoint or veil's rules hide. Each language's 95% intervals (in `report.json`) are ±2–7
points on ai4privacy and ±3–16 on Gretel.

## Read this first

* **deerpark-PII-large may have seen ai4privacy.** It was trained from `knowledgator/gliner-pii-large-v1.0`, and
  Knowledgator doesn't say what its models were trained on. Finding 97–99% of ai4privacy's details in every language,
  far above anything else here, fits a model that saw this data or data made the same way. Read its ai4privacy figures
  as an upper bound. The same doubt applies, less sharply, to deerpark-PII-edge's base.
* **Gretel's names in other languages are noisy.** The benchmark's filter for spans labelled as names that are no
  name (`gretel.is_noise`) works from English word lists, so in the other languages it keeps labels such as "Uw
  gegevens", "Overige inkomsten", "Ihre Zahlung", "Saldo Iniziale" and "Detta dokument". Every one of the 49 Dutch names
  edge+rules misses is of this sort, and many of those in German and Italian; their names, and so their totals,
  are understated.
* **ai4privacy labels towns alone.** "city / postcode" counts a town on its own ("est née à Ruswil"), which veil
  leaves visible in a sentence by design. Towns and street addresses are most of what edge+rules misses there.
* **Hindi and Telugu: the models hide pieces of ordinary words.** Both checkpoints mark fragments of Devanagari and
  Telugu words (GLiNER splits a word at its vowel signs), hiding 48–51% (edge) and 80–88% (large) of other words.
  Neither was trained on these scripts. veil's rules hide almost nothing else there.

## Results

### ai4privacy open-pii-masking-500k

200 documents a language. Found / other words hidden:

| Language | Details | veil | edge | edge+rules | large | large+rules |
|---|---|---|---|---|---|---|
| English | 391 | 55.5% / 0.19% | 83.6% / 0.15% | 87.0% / 0.34% | 98.5% / 0.57% | 98.5% / 0.64% |
| German | 363 | 47.9% / 2.88% | 83.7% / 6.55% | 87.1% / 9.10% | 98.3% / 5.88% | 98.6% / 8.17% |
| Spanish | 357 | 48.5% / 0.91% | 87.4% / 1.57% | 89.6% / 2.18% | 99.2% / 3.20% | 99.2% / 3.91% |
| French | 366 | 48.4% / 0.85% | 84.7% / 0.55% | 87.2% / 1.37% | 98.4% / 2.04% | 98.6% / 2.80% |
| Hindi | 361 | 48.5% / 0.00% | 80.3% / 50.94% | 85.0% / 50.94% | 98.3% / 79.88% | 98.9% / 79.88% |
| Italian | 377 | 57.0% / 1.08% | 84.1% / 1.31% | 90.2% / 2.19% | 97.9% / 2.79% | 98.1% / 3.73% |
| Dutch | 405 | 51.4% / 2.32% | 83.2% / 5.49% | 87.4% / 7.03% | 97.3% / 4.07% | 97.5% / 6.21% |
| Telugu | 449 | 45.2% / 0.07% | 83.5% / 47.65% | 90.2% / 47.70% | 98.0% / 88.47% | 98.7% / 88.47% |

edge+rules, found by kind of detail (details in brackets):

| Kind | English | German | Spanish | French | Hindi | Italian | Dutch | Telugu |
|---|---|---|---|---|---|---|---|---|
| SSN / ID / license / tax | 87% (31) | 91% (46) | 98% (49) | 91% (35) | 97% (36) | 96% (27) | 98% (42) | 100% (44) |
| bank / card / account | 100% (3) | 100% (2) | 100% (3) | 100% (4) | 100% (2) | 100% (2) | 100% (10) | 100% (5) |
| city / postcode | 43% (28) | 35% (26) | 50% (32) | 66% (35) | 65% (34) | 64% (39) | 44% (34) | 89% (37) |
| email | 100% (22) | 100% (33) | 100% (29) | 100% (21) | 100% (26) | 100% (27) | 100% (19) | 100% (25) |
| name | 95% (242) | 93% (183) | 95% (183) | 92% (198) | 87% (193) | 95% (198) | 92% (243) | 87% (254) |
| phone / fax | 88% (34) | 93% (41) | 100% (35) | 92% (40) | 93% (27) | 96% (48) | 87% (31) | 95% (38) |
| street address | 52% (31) | 69% (32) | 62% (26) | 61% (33) | 70% (43) | 72% (36) | 69% (26) | 91% (46) |

large+rules, found by kind of detail (details in brackets):

| Kind | English | German | Spanish | French | Hindi | Italian | Dutch | Telugu |
|---|---|---|---|---|---|---|---|---|
| SSN / ID / license / tax | 97% (31) | 98% (46) | 98% (49) | 100% (35) | 100% (36) | 100% (27) | 98% (42) | 100% (44) |
| bank / card / account | 100% (3) | 100% (2) | 100% (3) | 100% (4) | 100% (2) | 100% (2) | 100% (10) | 100% (5) |
| city / postcode | 96% (28) | 100% (26) | 94% (32) | 94% (35) | 97% (34) | 97% (39) | 88% (34) | 100% (37) |
| email | 100% (22) | 100% (33) | 100% (29) | 100% (21) | 100% (26) | 100% (27) | 100% (19) | 100% (25) |
| name | 100% (242) | 100% (183) | 100% (183) | 99% (198) | 99% (193) | 99% (198) | 100% (243) | 98% (254) |
| phone / fax | 100% (34) | 100% (41) | 100% (35) | 100% (40) | 100% (27) | 100% (48) | 97% (31) | 100% (38) |
| street address | 87% (31) | 88% (32) | 100% (26) | 94% (33) | 98% (43) | 89% (36) | 85% (26) | 98% (46) |

### ai4privacy pii-masking-400k

200 documents a language. Found / other words hidden:

| Language | Details | veil | edge | edge+rules | large | large+rules |
|---|---|---|---|---|---|---|
| English | 262 | 51.5% / 2.20% | 82.4% / 2.34% | 87.0% / 3.40% | 97.3% / 6.59% | 97.3% / 7.12% |
| German | 200 | 46.0% / 4.56% | 83.5% / 9.52% | 84.5% / 11.94% | 97.5% / 14.53% | 97.5% / 16.37% |
| Spanish | 189 | 44.4% / 3.24% | 84.7% / 7.11% | 85.2% / 8.15% | 98.4% / 9.78% | 98.4% / 11.20% |
| French | 204 | 42.2% / 3.50% | 82.4% / 6.11% | 84.8% / 7.68% | 98.5% / 9.81% | 98.5% / 11.17% |
| Italian | 177 | 42.9% / 2.27% | 88.1% / 7.38% | 88.7% / 8.08% | 98.3% / 11.76% | 98.3% / 12.44% |
| Dutch | 201 | 48.8% / 2.89% | 83.1% / 9.88% | 84.1% / 11.00% | 98.0% / 10.75% | 98.0% / 12.31% |

edge+rules, found by kind of detail (details in brackets):

| Kind | English | German | Spanish | French | Italian | Dutch |
|---|---|---|---|---|---|---|
| SSN / ID / license / tax | 94% (36) | 85% (26) | 100% (27) | 89% (27) | 100% (33) | 100% (21) |
| bank / card / account | 100% (23) | 100% (17) | 100% (16) | 100% (14) | 100% (17) | 100% (17) |
| city / postcode | 57% (37) | 46% (24) | 79% (24) | 66% (32) | 60% (15) | 52% (27) |
| date of birth | 33% (6) | 57% (7) | 50% (8) | 33% (6) | 40% (5) | 60% (10) |
| email | 100% (16) | 100% (26) | 100% (15) | 100% (19) | 100% (15) | 100% (26) |
| name | 97% (71) | 97% (58) | 83% (41) | 95% (55) | 98% (46) | 96% (49) |
| phone / fax | 100% (18) | 100% (14) | 100% (13) | 100% (12) | 100% (19) | 100% (12) |
| street address | 64% (22) | 57% (7) | 61% (23) | 61% (23) | 58% (12) | 44% (18) |
| user name | 94% (33) | 71% (21) | 86% (22) | 94% (16) | 67% (15) | 86% (21) |

large+rules, found by kind of detail (details in brackets):

| Kind | English | German | Spanish | French | Italian | Dutch |
|---|---|---|---|---|---|---|
| SSN / ID / license / tax | 100% (36) | 100% (26) | 100% (27) | 100% (27) | 100% (33) | 100% (21) |
| bank / card / account | 100% (23) | 100% (17) | 100% (16) | 100% (14) | 100% (17) | 100% (17) |
| city / postcode | 97% (37) | 92% (24) | 100% (24) | 100% (32) | 100% (15) | 96% (27) |
| date of birth | 83% (6) | 86% (7) | 100% (8) | 100% (6) | 60% (5) | 90% (10) |
| email | 100% (16) | 100% (26) | 100% (15) | 100% (19) | 100% (15) | 100% (26) |
| name | 100% (71) | 100% (58) | 100% (41) | 100% (55) | 100% (46) | 100% (49) |
| phone / fax | 100% (18) | 100% (14) | 100% (13) | 100% (12) | 100% (19) | 100% (12) |
| street address | 77% (22) | 71% (7) | 87% (23) | 91% (23) | 92% (12) | 89% (18) |
| user name | 100% (33) | 100% (21) | 100% (22) | 94% (16) | 100% (15) | 100% (21) |

### Gretel finance (multilingual)

60 documents a language. Found / other words hidden:

| Language | Details | veil | edge | edge+rules | large | large+rules |
|---|---|---|---|---|---|---|
| English | 181 | 96.1% / 0.85% | 97.2% / 0.86% | 97.2% / 1.12% | 97.8% / 1.96% | 97.8% / 2.23% |
| Dutch | 210 | 49.0% / 1.54% | 63.3% / 3.10% | 68.6% / 4.03% | 85.7% / 8.99% | 87.6% / 9.61% |
| French | 172 | 83.7% / 3.71% | 87.8% / 2.29% | 92.4% / 4.63% | 95.9% / 6.53% | 96.5% / 8.52% |
| German | 213 | 70.0% / 3.01% | 73.2% / 2.27% | 82.6% / 4.60% | 85.0% / 4.60% | 87.8% / 6.88% |
| Italian | 252 | 69.4% / 3.53% | 76.6% / 1.73% | 84.9% / 4.66% | 87.7% / 4.65% | 90.5% / 6.93% |
| Spanish | 162 | 85.8% / 2.86% | 86.4% / 1.55% | 92.0% / 3.87% | 93.8% / 6.86% | 98.8% / 8.61% |
| Swedish | 192 | 78.1% / 1.82% | 88.0% / 2.66% | 90.6% / 3.63% | 91.1% / 7.82% | 92.7% / 8.75% |

edge+rules, found by kind of detail (details in brackets):

| Kind | English | Dutch | French | German | Italian | Spanish | Swedish |
|---|---|---|---|---|---|---|---|
| SSN / passport / license | 100% (3) | 100% (1) | 100% (6) | 100% (5) | 100% (3) | 100% (6) | 100% (8) |
| bank / card / IBAN / SWIFT | 100% (20) | 100% (10) | 100% (5) | 67% (6) | 100% (20) | 100% (11) | 100% (5) |
| customer / employee ID | 100% (8) | 100% (6) | 100% (2) | 100% (6) | 100% (4) | 100% (3) | 100% (4) |
| date of birth | 100% (2) | – | 100% (1) | 100% (6) | 100% (4) | 100% (3) | 100% (1) |
| email | 79% (14) | 100% (9) | 100% (15) | 100% (12) | 100% (10) | 100% (15) | 100% (22) |
| name | 100% (82) | 51% (134) | 85% (89) | 74% (134) | 76% (144) | 84% (81) | 81% (90) |
| phone | 100% (9) | 100% (10) | 100% (12) | 100% (1) | 100% (12) | 100% (8) | 100% (13) |
| street address | 95% (43) | 98% (40) | 100% (42) | 100% (43) | 95% (55) | 100% (35) | 98% (49) |

large+rules, found by kind of detail (details in brackets):

| Kind | English | Dutch | French | German | Italian | Spanish | Swedish |
|---|---|---|---|---|---|---|---|
| SSN / passport / license | 100% (3) | 100% (1) | 100% (6) | 100% (5) | 100% (3) | 100% (6) | 100% (8) |
| bank / card / IBAN / SWIFT | 100% (20) | 100% (10) | 100% (5) | 67% (6) | 100% (20) | 100% (11) | 100% (5) |
| customer / employee ID | 100% (8) | 100% (6) | 100% (2) | 100% (6) | 100% (4) | 100% (3) | 100% (4) |
| date of birth | 100% (2) | – | 100% (1) | 100% (6) | 100% (4) | 100% (3) | 100% (1) |
| email | 79% (14) | 100% (9) | 100% (15) | 100% (12) | 100% (10) | 100% (15) | 100% (22) |
| name | 100% (82) | 81% (134) | 93% (89) | 82% (134) | 83% (144) | 98% (81) | 84% (90) |
| phone | 100% (9) | 100% (10) | 100% (12) | 100% (1) | 100% (12) | 100% (8) | 100% (13) |
| street address | 98% (43) | 100% (40) | 100% (42) | 100% (43) | 100% (55) | 100% (35) | 100% (49) |

* veil: veil's rules alone (FINANCE profile)
* edge: deerpark-PII-edge (Deerpark/veil-tagger-edge) alone at 0.35
* edge+rules: veil + deerpark-PII-edge: every word either hides
* large: deerpark-PII-large (Deerpark/veil-control/out_large) alone at 0.35
* large+rules: veil + deerpark-PII-large: every word either hides

## What it shows

* **veil's rules are English rules.** On Gretel finance, the kind of document they were tuned on, they find 96% in
  English and 49–86% in the other six languages. On ai4privacy's short messages they find 42–57% in every language,
  English included: they miss names in running text, towns alone, user names, and IDs and phone numbers in formats
  they don't know.
* **The edge tagger carries most of the gain, and the rules still add.** edge+rules finds 84–90% on ai4privacy in every
  language and 69–92% on Gretel's other languages, against 42–86% for the rules. On Gretel the rules add 3–9 points to
  the tagger alone in every language but English; on ai4privacy, 0.5–7.
* **The large checkpoint finds more and mostly hides more.** large+rules finds 97–99% on ai4privacy (see above) and
  88–99% on Gretel's other languages, but hides 6.9–9.6% of other words on those against edge+rules' 3.6–4.7%, and
  7–16% against 3–12% on pii-masking-400k, at a threshold not chosen for it.
* **Other languages cost more in other words hidden.** edge+rules hides 0.3% and 3.4% of other words in English
  messages, and up to 9% (open-pii) and 12% (pii-masking-400k) in German and Dutch.
* **Hindi and Telugu are not usable with either tagger as it is.** edge+rules finds 85–90% of their details, but by hiding half
  the text or more. veil's rules alone hide almost nothing else, and find under half.
