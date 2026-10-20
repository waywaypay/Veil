import os, sys
sys.path.insert(0, ".")
import round4 as R, round7 as R7, merge_fix as M
from breakdown import cached
T = R.T
if os.environ.get("PYTHONHASHSEED") != "0":
    os.execve(sys.executable, [sys.executable, *sys.argv], {**os.environ, "PYTHONHASHSEED": "0"})
have = cached(os.path.abspath("ft/r7_3"))
sets = {k: v for k, v in R7.dev_sets().items() if all(T.key(t) in have for t, _ in v)}
for label, fn in [("model@0.30", lambda t: T.alone(t, have[T.key(t)], 0.30)),
                  ("model@0.35", lambda t: T.alone(t, have[T.key(t)], 0.35)),
                  ("union@0.40", lambda t: M.union(t, have[T.key(t)], 0.40)),
                  ("union@0.45", lambda t: M.union(t, have[T.key(t)], 0.45)),
                  ("union@0.50", lambda t: M.union(t, have[T.key(t)], 0.50))]:
    rs = [T.score(rows, [t for t, _ in rows], [fn(t) for t, _ in rows]) for rows in sets.values()]
    print(f"{label}  found {sum(r['found'] for r in rs) / len(rs):.2%}  over {sum(r['over'] for r in rs) / len(rs):.2%}  ({len(rs)} slices)", flush=True)
