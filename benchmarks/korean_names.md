# Korean: the names deerpark-PII-edge marks, checked

deerpark-PII-edge was never trained on Korean. In Hangul it marks ordinary words as names ("투어", "의도를", "참가자
명단에는"), so in `languages_trace.md` it hid 23% of the other words of Korean messages against 0.3–6.4% in the other
five languages. Its scores don't tell those words from names: on 800 Korean dev messages, 3,436 of the 4,044 Hangul
names it marked at 0.35 were false, and raising the threshold to 0.6 still kept 116 false names for every 71 true ones.

`veil.hangul` judges them by their words instead, and `veil.tagged.vetted` drops a name the model marks in Hangul if
every Hangul word in it is an everyday one: a verb or adjective form, a word `wordfreq` lists for Korean (Zipf 3.5 or
more) once a particle is off, a run of listed words, a listed word with a suffix, or a role with an honorific
("선생님"). The rules and their exceptions are in the module's docstring. The model and its other kinds of span are
unchanged; every path of `veil.tagged` (`TaggedRedactor.find`, `.redactor()`) goes through the check, and so do the
benchmarks' tagger systems. Text without Hangul is untouched: every figure in `languages.md`, and every language but
Korean in `languages_trace.md`, is the same as before.

```
python benchmarks/korean_names.py fetch
python benchmarks/korean_names.py --out korean_names_report/
```

## How it was made

* **Dev**, read as often as needed: ai4privacy pii-masking-openpii-1.5m's Korean validation messages 200–999 (in
  `languages_trace.py`'s order) and townboy/korean-pii-dataset's validation split. A first version with word lists
  mined from these sets' own generators held up poorly across them (a list from one removed 41–81% of the false names
  in the other), so the frequencies come from `wordfreq`, which counts general Korean text.
* **Held out**: `languages_trace.py`'s 200 Korean messages, townboy's test split, and
  [schift-io/korean-pii-benchmark-v3](https://huggingface.co/datasets/schift-io/korean-pii-benchmark-v3) (473 court,
  news and office texts with real-world name shapes, organisations and look-alikes).
* **The held-out sets were read twice.** The first reading showed losses the dev sets had hidden: a name followed by
  "is" ("주찬우이며"), a nickname with digits ("구름303"), a name in hanja beside Korean words ("외국인 피의자 田中太郎"),
  and names whose last syllable looks like a particle or a suffix ("지나은", "기지후"). The fixes (the copula, the
  particle's form, other scripts, digits, syllables that end given names) are rules of Korean, not of these sets, and
  were checked on dev before the second reading, which the table below gives. The first reading's names fully hidden
  were 75.8% (townboy test) and 35.8% (schift-io), edge alone.

## Results

Without dates and URLs, one message at a time; before → after:

| Set | Messages | Gold spans | System | Char F1 | Char precision | Details fully hidden | Names fully hidden | Other words hidden |
|---|---|---|---|---|---|---|---|---|
| dev: ai4privacy 200-999 | 800 | 4064 | edge | 0.690 → 0.808 | 0.584 → 0.787 | 69.9% → 67.4% | 47.9% → 44.0% | 21.17% → 5.44% |
| dev: ai4privacy 200-999 | 800 | 4064 | edge+rules | 0.702 → 0.820 | 0.587 → 0.782 | 74.9% → 72.5% | 53.1% → 49.3% | 21.37% → 5.67% |
| dev: townboy validation | 1510 | 3250 | edge | 0.642 → 0.746 | 0.499 → 0.696 | 78.4% → 59.8% | 48.9% → 48.9% | 27.75% → 7.25% |
| dev: townboy validation | 1510 | 3250 | edge+rules | 0.677 → 0.787 | 0.519 → 0.714 | 95.6% → 77.0% | 97.6% → 97.6% | 27.76% → 7.25% |
| held out: ai4privacy (languages_trace) | 200 | 994 | edge | 0.688 → 0.801 | 0.583 → 0.775 | 69.1% → 67.5% | 44.3% → 42.3% | 22.93% → 6.61% |
| held out: ai4privacy (languages_trace) | 200 | 994 | edge+rules | 0.701 → 0.814 | 0.588 → 0.774 | 73.6% → 72.0% | 51.5% → 49.5% | 23.04% → 6.76% |
| held out: townboy test | 995 | 1490 | edge | 0.671 → 0.808 | 0.518 → 0.720 | 89.2% → 82.2% | 80.7% → 80.7% | 27.03% → 7.24% |
| held out: townboy test | 995 | 1490 | edge+rules | 0.680 → 0.819 | 0.524 → 0.725 | 94.6% → 87.7% | 94.9% → 94.9% | 27.03% → 7.24% |
| held out: schift-io v3 | 473 | 621 | edge | 0.481 → 0.562 | 0.419 → 0.599 | 40.3% → 38.2% | 41.1% → 38.0% | 22.80% → 9.05% |
| held out: schift-io v3 | 473 | 621 | edge+rules | 0.621 → 0.735 | 0.504 → 0.684 | 57.3% → 55.4% | 47.2% → 44.8% | 22.85% → 9.12% |

* **Other words hidden fall from 21–28% to 5–9%** on every set, and character F1 rises by 0.08–0.14, by precision.
* **Names fully hidden are unchanged on townboy** (80.7%, 94.9% with the rules, on its test split) and fall 2 points on
  the held-out ai4privacy messages (4 on its dev ones) and 2–3 on schift-io. What's lost on ai4privacy is mostly a surname alone ("김", "곽") and that set's names made of words ("자연
  화", "여우"). Every name lost on schift-io is a public figure's that `wordfreq` lists: 노무현 (5 mentions), 김대중
  (4), 박근혜 (2), 안중근 and 이도.
* **Details fully hidden fall 7 points on townboy's test split** (19 on its validation split): every one a town alone ("여수시", "서울특별시") that the model had
  marked as a name. The labels here count a town as an address, as `languages_trace.py` maps ai4privacy's; veil
  leaves a town alone visible in a sentence by design, and none of these was next to a street or a postcode.

## What it doesn't do

* A given name that is also a common word ("서연", Zipf 3.6; "철수", "withdrawal") is taken for the word.
* Verb forms the rules don't list stay names ("끝난"), and so do rare words `wordfreq` doesn't have ("워크숍", Zipf
  3.3), so the edge model still hides 5–9% of other words in Korean, against 0.3–6.4% in the other languages.
* It fixes what veil does with the model's spans, not the model. Training it on Korean, with ordinary words left
  unlabelled, would fix the cause; Hindi and Telugu (`languages.md`) have the same problem and no check yet.
