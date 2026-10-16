"""Score veil on the OCR text of documents (rebuilt from Tesseract's words by veil.files), and list what the plain
text caught but the OCR text leaks.  Make the OCR data first with make_ocr.py (needs Tesseract, Pillow and the
DejaVu fonts).

python benchmarks/make_ocr.py <gretel parquet> <n> <ocr json>
python benchmarks/gretel_ocr.py <gretel parquet> <ocr json> <clean|scanned> [n]"""

import json
import sys

import pandas as pd

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import gretel as bench

from veil import FINANCE, Redactor
from veil.files import reflow

path, ocr_path, mode = sys.argv[1], sys.argv[2], sys.argv[3]
n = int(sys.argv[4]) if len(sys.argv) > 4 else 100000
d = pd.read_parquet(path)
d = d[d.language == "English"].head(n)
docs = [(t, json.loads(s)) for t, s in zip(d.generated_text, d.pii_spans)]
raw = json.load(open(ocr_path))[mode][: len(docs)]
inputs = [reflow(x) if isinstance(x, dict) else x for x in raw]
fn = Redactor(FINANCE).redact_text
r = bench.score(docs, fn, inputs)


def p(x):
    return f"{x[0] / x[1]:.1%}" if x[1] else "-"


for g, x in r["recall"].items():
    print(f"  {g:28} {p(x):10} adjudicated {p(r['recall_clean_by'][g])} (n={r['recall_clean_by'][g][1]})")
a, c, f = r["recall_all"], r["recall_clean"], r["over_redact"]
print(f"ALL {p(a)}  adjudicated {p(c)}  over {f[0] / f[1]:.2%}")
with open(ocr_path + f".{mode}.miss.txt", "w") as fh:
    for k, ((text, spans), given) in enumerate(zip(docs, inputs)):
        out = fn(given)
        _, kg = bench.redacted_mask(given, out)
        a = bench.words(text)
        m = bench.word_map(text, given)
        _, kp = bench.redacted_mask(text, fn(text))
        gw = bench.words(given)
        for sp in spans:
            g = bench.LABEL_GROUP.get(sp["label"])
            if not g or bench.is_noise(text[sp["start"] : sp["end"]], sp["label"], text[sp["end"] : sp["end"] + 60]):
                continue
            idx = [i for i, (_, s, e) in enumerate(a) if s < sp["end"] and e > sp["start"]]
            if any(m[i] is not None and kg[m[i]] for i in idx) and not any(kp[i] for i in idx):
                js = [m[i] for i in idx if m[i] is not None]
                s0, e0 = gw[min(js)][1], gw[max(js)][2]
                fh.write(f"{g} | {text[sp['start'] : sp['end']]!r} | OCR: {given[max(0, s0 - 35) : e0 + 20]!r}\n")
