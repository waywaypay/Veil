# Round 7: research scripts, as run

These are the scripts behind round 7 (W-2 and US tax-form data, segments 1-4, the W-2 field parser, the OCR and
verifier experiments, the fixed veil + tagger merge, the error review and the second locked test's scoring). They were
run from a scratch folder and still name its paths; they are kept here so the work can be read and re-run, not as a
library. `veilbench.py` one level up is the maintained way to benchmark.

* `INTEGRITY_LOG.md`: what was checked, when, and every convention adopted along the way.
* `round7.py`: building the training mix, training the segments, the dev slices.
* `w2gen.py`, `usgen.py`, `w2real.py`, `w2prov.py`: W-2 and other tax-form generators (the IRS fillable PDF, payroll
  provider layouts, OCR).
* `w2parse_*.py`, `parse_eval.py`, `combo_parse.py`, `html_eval.py`, `w2html/`: the W-2 field parser and its tests on
  independently written layouts (`templates_dev.py` for development, `templates_heldout.py` scored once).
* `merge_fix.py`: the veil + tagger merge that decides both on the original text (now `veil/tagged.py`).
* `dump_misses.py`, `errors/`: the error review (a stratified sample of misses and two reviewers' verdicts).
* `score_locked2.py`, `locked2_scores.json`: the second locked test, scored once with r7_3@0.35.
* `slope.html`, `breakdown.html`: the charts.
