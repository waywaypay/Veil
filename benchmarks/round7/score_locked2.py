"""The second locked test's 165 hand-written documents (M01-M11), scored once with the frozen round 7 model r7_3@0.35: model
alone, veil alone, veil + model.  Per document type and per type of data; found with a 95% bootstrap interval over documents.
python score_locked2.py"""
import json, os, random, sys, glob
sys.path.insert(0, "/tmp/claude-0/-home-user-Veil/190ab3d3-f9c1-50ad-a470-e321ea643401/scratchpad")
import breakdown  # noqa: F401  (patches the group maps to the specific types)
import round4 as R
from veil import FINANCE, Redactor
T = R.T
S = "/tmp/claude-0/-home-user-Veil/190ab3d3-f9c1-50ad-a470-e321ea643401/scratchpad"
MODEL, TH = f"{S}/ft/r7_3", 0.35
docs = []
for f in sorted(glob.glob(f"{S}/locked2/M*.jsonl")):
    for l in open(f):
        if l.strip():
            r = json.loads(l)
            docs.append((os.path.basename(f)[:3], r["type"], r["locale"], R.unmark(r["text"])))
rows = R.rows([d[3] for d in docs])
texts = [t for t, _ in rows]
found = T.spans(MODEL, texts)
sysout = {"model alone": [T.alone(t, found[T.key(t)], TH) for t in texts],
          "veil alone": [Redactor(FINANCE).redact_text(t) for t in texts],
          "veil + model": [T.with_veil(t, found[T.key(t)], T.GATES["all kinds"], TH) for t in texts]}
per = {}
for name, outs in sysout.items():
    per[name] = [T.score([rows[i]], [texts[i]], [outs[i]]) for i in range(len(rows))]


def agg(idx, name):
    hit = tot = 0
    by = {}
    over_num = over_den = 0.0
    for i in idx:
        r = per[name][i]
        for g, (h, t) in r["by"].items():
            hit += h; tot += t
            b = by.setdefault(g, [0, 0]); b[0] += h; b[1] += t
        w = len(texts[i].split())
        over_num += r["over"] * w; over_den += w
    return hit, tot, by, over_num / max(1, over_den)


def ci(idx, name, n=2000):
    rng = random.Random(7)
    vals = []
    for _ in range(n):
        s = [rng.choice(idx) for _ in idx]
        h, t, _, _ = agg(s, name)
        vals.append(h / max(1, t))
    vals.sort()
    return vals[int(.025 * n)], vals[int(.975 * n)]


out = {"overall": {}, "by_type": {}, "by_data": {}}
allidx = list(range(len(rows)))
print(f"{len(rows)} documents, model {os.path.basename(MODEL)}@{TH}")
for name in sysout:
    h, t, by, ov = agg(allidx, name)
    lo, hi = ci(allidx, name)
    out["overall"][name] = {"found": h / t, "lo": lo, "hi": hi, "over": ov, "details": t}
    print(f"{name:13} found {h / t:.1%} [{lo:.1%}, {hi:.1%}] of {t} details   other words hidden {ov:.2%}")
    out["by_data"][name] = {g: [a, b] for g, (a, b) in by.items()}
types = sorted({d[1] for d in docs})
print("\nby document type (found, other words hidden)         model alone      veil alone       veil + model")
for ty in types:
    idx = [i for i, d in enumerate(docs) if d[1] == ty]
    cells = []
    for name in sysout:
        h, t, _, ov = agg(idx, name)
        out["by_type"].setdefault(ty, {})[name] = {"found": h / max(1, t), "over": ov, "details": t, "docs": len(idx)}
        cells.append(f"{h / max(1, t):6.1%}/{ov:5.2%}")
    print(f"{ty[:44]:44} n={len(idx):2} d={out['by_type'][ty]['model alone']['details']:4}  " + "   ".join(cells))
print("\nby type of data (found: model alone / veil alone / veil + model)")
gs = sorted({g for r in per["model alone"] for g in r["by"]})
for g in gs:
    cells = []
    for name in sysout:
        h = sum(r["by"].get(g, [0, 0])[0] for r in per[name]); t = sum(r["by"].get(g, [0, 0])[1] for r in per[name])
        cells.append(f"{h / max(1, t):6.1%}")
    t = sum(r["by"].get(g, [0, 0])[1] for r in per["model alone"])
    print(f"{g:20} n={t:4}  " + "  ".join(cells))
json.dump(out, open(f"{S}/locked2_scores.json", "w"), indent=1)
