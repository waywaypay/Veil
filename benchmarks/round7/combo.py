"""veil alone, model alone, and veil + model (tagger.with_veil, 'all kinds' and 'strict' gates) on the W-2 / tax / all dev slices, from cached spans."""
import os, sys, json
sys.path.insert(0, "/tmp/claude-0/-home-user-Veil/190ab3d3-f9c1-50ad-a470-e321ea643401/scratchpad")
import round4 as R, round7 as R7
from veil import FINANCE, Redactor
T = R.T
from breakdown import cached
sets = R7.dev_sets()
out = {}
for spec in sys.argv[1:]:
    model, _, th = spec.partition("@"); th = float(th)
    have = cached(model)
    for name, rows in sets.items():
        if not all(T.key(t) in have for t, _ in rows):
            continue
        ins = [t for t, _ in rows]
        res = {"veil": T.score(rows, ins, [Redactor(FINANCE).redact_text(t) for t in ins]),
               "model": T.score(rows, ins, [T.alone(t, have[T.key(t)], th) for t in ins])}
        for g in ("all kinds", "strict"):
            res["veil+model "+g] = T.score(rows, ins, [T.with_veil(t, have[T.key(t)], T.GATES[g], th) for t in ins])
        out.setdefault(os.path.basename(model)+f"@{th:g}", {})[name] = {k: [v["found"], v["over"], v["details"]] for k, v in res.items()}
json.dump(out, open("combo.json", "w"))
for m, d in out.items():
    print(m)
    for name, r in d.items():
        print(f"  {name[:34]:34}", "  ".join(f"{k[:16]} {v[0]:.1%}/{v[1]:.2%}" for k, v in r.items()))
    print("  MEAN", "  ".join(f"{k[:16]} {sum(r[k][0] for r in d.values())/len(d):.2%}/{sum(r[k][1] for r in d.values())/len(d):.2%}" for k in next(iter(d.values()))))
