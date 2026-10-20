"""Every labelled private detail that veil + model (union, r7_3@0.35) leaves at least partly visible on the dev slices,
with context; and a stratified sample for review.  -> errors/misses_all.jsonl, errors/sample.jsonl"""
import json, os, random, sys
sys.path.insert(0, "/tmp/claude-0/-home-user-Veil/190ab3d3-f9c1-50ad-a470-e321ea643401/scratchpad")
import breakdown  # noqa: F401  (specific data types)
import round4 as R, round7 as R7, merge_fix as M
from breakdown import cached
T = R.T
bench = T.bench
if os.environ.get("PYTHONHASHSEED") != "0":
    os.execve(sys.executable, [sys.executable, *sys.argv], {**os.environ, "PYTHONHASHSEED": "0"})
have = cached("/tmp/claude-0/-home-user-Veil/190ab3d3-f9c1-50ad-a470-e321ea643401/scratchpad/ft/r7_3")
misses, totals = [], {}
for name, rows in R7.dev_sets().items():
    if not all(T.key(t) in have for t, _ in rows):
        continue
    for di, (text, spans) in enumerate(rows):
        out = M.union(text, have[T.key(text)], 0.35)
        ws = bench.words(text)
        _, kept = bench.redacted_mask(text, out)
        for s, e, g in spans:
            if g in ("ordinary", "outside"):
                continue
            idx = [j for j, (_, a, b) in enumerate(ws) if a < e and b > s and ws[j][0].lower() not in bench.TITLES]
            if not idx:
                continue
            totals[(name, g)] = totals.get((name, g), 0) + 1
            vis = [ws[j][0] for j in idx if kept[j]]
            if vis:
                a, b = max(0, s - 220), min(len(text), e + 220)
                misses.append({"slice": name, "doc": di, "type": g, "detail": text[s:e], "visible": vis,
                               "context": text[a:s] + "[[" + text[s:e] + "]]" + text[e:b]})
os.makedirs("errors", exist_ok=True)
with open("errors/misses_all.jsonl", "w") as f:
    for m in misses:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")
tot = sum(totals.values())
print(f"{len(misses)} misses of {tot} details ({1 - len(misses) / tot:.2%} found)")
by_t = {}
for m in misses:
    by_t[m["type"]] = by_t.get(m["type"], 0) + 1
tt = {}
for (n, g), c in totals.items():
    tt[g] = tt.get(g, 0) + c
for g, c in sorted(by_t.items(), key=lambda x: -x[1]):
    print(f"  {g:20} {c:5} missed of {tt[g]:6}  ({c / tt[g]:.1%} missed)")
# stratified sample: 400, proportional to misses by type, at least 12 per type (or all), spread over slices
rng = random.Random(11)
sample = []
for g, c in by_t.items():
    pool = [m for m in misses if m["type"] == g]
    k = min(len(pool), max(12, round(400 * c / len(misses))))
    sample += rng.sample(pool, k)
rng.shuffle(sample)
with open("errors/sample.jsonl", "w") as f:
    for i, m in enumerate(sample):
        f.write(json.dumps({"id": i, **m}, ensure_ascii=False) + "\n")
print(len(sample), "sampled")
