import json, os, sys
sys.path.insert(0, ".")
import breakdown  # noqa
import round4 as R, round7 as R7, merge_fix as M, fieldpass as F
from breakdown import cached
T = R.T; bench = T.bench
if os.environ.get("PYTHONHASHSEED") != "0":
    os.execve(sys.executable, [sys.executable, *sys.argv], {**os.environ, "PYTHONHASHSEED": "0"})
have = cached(os.path.abspath("ft/r7_3"))
sets = {k: v for k, v in R7.dev_sets().items() if all(T.key(t) in have for t, _ in v)}
res = {}
for name, rows in sets.items():
    ins = [t for t, _ in rows]
    a = T.score(rows, ins, [M.union(t, have[T.key(t)], 0.35) for t in ins])
    b = T.score(rows, ins, [M.union(t, have[T.key(t)], 0.35, F.ranges(t)) for t in ins])
    res[name] = (a["found"], a["over"], b["found"], b["over"])
    print(f"{name[:34]:34} union {a['found']:.1%}/{a['over']:.2%}   + field pass {b['found']:.1%}/{b['over']:.2%}", flush=True)
n = len(res)
print(f"MEAN union {sum(r[0] for r in res.values()) / n:.2%}/{sum(r[1] for r in res.values()) / n:.2%}   + field pass {sum(r[2] for r in res.values()) / n:.2%}/{sum(r[3] for r in res.values()) / n:.2%}")
# the reviewed sample: which true misses does the field pass now catch?
items = {json.loads(l)["id"]: json.loads(l) for l in open("errors/sample.jsonl")}
v = {}
for f in ("errors/rev1/verdicts.jsonl", "errors/rev2/verdicts.jsonl"):
    for l in open(f):
        r = json.loads(l); v.setdefault(r["id"], r)
fixed = {}
for i, it in items.items():
    rows = sets[it["slice"]]; text, spans = rows[it["doc"]]
    out = M.union(text, have[T.key(text)], 0.35, F.ranges(text))
    ws = bench.words(text); _, kept = bench.redacted_mask(text, out)
    s = text.find(it["detail"]) if it["detail"] in text else -1
    idx = [j for j, (_, a, b) in enumerate(ws) if s >= 0 and a < s + len(it["detail"]) and b > s and ws[j][0].lower() not in bench.TITLES]
    now = bool(idx) and not any(kept[j] for j in idx)
    c = v[i]["category"]
    fixed.setdefault(c, [0, 0]); fixed[c][1] += 1; fixed[c][0] += now
print("reviewed sample, now fully hidden by category:", {c: f"{a}/{b}" for c, (a, b) in fixed.items()})
