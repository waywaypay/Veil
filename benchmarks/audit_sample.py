"""A random sample of what veil misses and what it hides by mistake on the held-out set, for a person to judge
by hand: is each missed span really a personal detail, and is each over-redacted run really an ordinary word?
The Gretel labels are synthetic and noisy both ways ("Secondee" labelled a name; an unlabelled SSN), so the
audited rates (benchmarks/audit.md) say more than the raw ones.

python audit_sample.py <parquet> <n misses> <n over-redacted runs> <seed> > sample.jsonl"""

import json
import random
import sys

import gretel as bench
import pandas as pd

from veil import FINANCE, Redactor


def main(path, n_miss, n_fp, seed):
    d = pd.read_parquet(path)
    d = d[d.language == "English"]
    misses, runs = [], []
    for i, (text, spans) in enumerate(zip(d.generated_text, d.pii_spans)):
        spans = json.loads(spans)
        out = Redactor(FINANCE).redact_text(text)
        ws, kept = bench.redacted_mask(text, out)
        gold = [False] * len(ws)
        for sp in spans:
            idx = [j for j, (_, s, e) in enumerate(ws) if s < sp["end"] and e > sp["start"]]
            for j in idx:
                gold[j] = True
            idx = [j for j in idx if ws[j][0].lower() not in bench.TITLES]
            lab = sp["label"]
            if lab in bench.LABEL_GROUP and idx and any(kept[j] for j in idx) and \
                    not bench.is_noise(text[sp["start"]:sp["end"]], lab, text[sp["end"]:sp["end"] + 60]):
                misses.append({"doc": i, "kind": bench.LABEL_GROUP[lab], "span": text[sp["start"]:sp["end"]],
                               "context": text[max(0, sp["start"] - 80):sp["end"] + 40]})
        j = 0
        while j < len(ws):
            if not gold[j] and not kept[j] and ws[j][0].lower() not in bench.TITLES:
                k = j
                while k + 1 < len(ws) and not gold[k + 1] and not kept[k + 1]:
                    k += 1
                s, e = ws[j][1], ws[k][2]
                runs.append({"doc": i, "words": k - j + 1, "span": text[s:e],
                             "context": text[max(0, s - 80):e + 40]})
                j = k + 1
            else:
                j += 1
    rnd = random.Random(seed)
    for m in rnd.sample(misses, min(n_miss, len(misses))):
        print(json.dumps({"type": "miss", **m}, ensure_ascii=False))
    # weighted by words, as the over-redaction rate counts words
    for r in rnd.choices(runs, weights=[r["words"] for r in runs], k=n_fp):
        print(json.dumps({"type": "over", **r}, ensure_ascii=False))
    print(json.dumps({"type": "totals", "misses": len(misses), "runs": len(runs),
                      "words": sum(r["words"] for r in runs)}), file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]))
