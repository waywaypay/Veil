import sys, json
sys.path.insert(0, ".")
import round4 as R, round7 as R7
from breakdown import cached
T = R.T
sets = R7.dev_sets()
a, b = cached("ft/r7_3"), cached("ft/r7_4")
import os
a = cached(os.path.abspath("ft/r7_3")); b = cached(os.path.abspath("ft/r7_4"))
th = 0.35
rows_out = []
for name, rows in sets.items():
    if not all(T.key(t) in a and T.key(t) in b for t, _ in rows): continue
    ins = [t for t, _ in rows]
    r3 = T.score(rows, ins, [T.alone(t, a[T.key(t)], th) for t in ins])
    r4 = T.score(rows, ins, [T.alone(t, b[T.key(t)], th) for t in ins])
    un = T.score(rows, ins, [T.alone(t, a[T.key(t)] + b[T.key(t)], th) for t in ins])
    rows_out.append((name, r3, r4, un))
    print(f"{name[:36]:36} r7_3 {r3['found']:.1%}/{r3['over']:.2%}  r7_4 {r4['found']:.1%}/{r4['over']:.2%}  union {un['found']:.1%}/{un['over']:.2%}")
n = len(rows_out)
for i, k in ((1, "r7_3"), (2, "r7_4"), (3, "union")):
    print(f"MEAN {k:6} {sum(r[i]['found'] for r in rows_out)/n:.2%} / {sum(r[i]['over'] for r in rows_out)/n:.2%}")
