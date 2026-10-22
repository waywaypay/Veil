"""A threshold for each kind of detail the tagger marks, and overlapping chunks, chosen on dev by PROTOCOL.md's rule:
the highest mean found over the dev slices whose mean share of other words hidden is no higher than the current
best's (veil + the tagger at 0.35 for every kind, 200-word chunks without overlap).

Dev slices, all development data under round 7's dev sets: judged/docgen/test, judged/docgen/locked (the first locked
test, development data since round 5), and the generators on round 7's dev seeds (forms 96, W-2s 42, US tax forms 44).
judged/docgen/locked2 is never read.

The model runs once per chunking at a score floor of 0.1 (cached in $VEIL_BENCH_DATA/cache), so every threshold is
scored without running it again: GLiNER keeps spans greedily by score, so what it keeps at 0.1 and then above t is what
it keeps at t.  Thresholds are tuned one kind at a time, a few passes over the kinds, then checked by tuning on one half
of each slice's documents and scoring the other half.

python kind_thresholds.py [--overlap 25] [--out kind_thresholds.json]"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

if os.environ.get("PYTHONHASHSEED") != "0":   # formgen's draws repeat only with a fixed hash seed
    os.execve(sys.executable, [sys.executable, *sys.argv], {**os.environ, "PYTHONHASHSEED": "0"})

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE / "round7"), str(HERE.parent)]

import formgen  # noqa: E402
import gretel as bench  # noqa: E402
import usgen  # noqa: E402
import veilbench as VB  # noqa: E402
import w2gen  # noqa: E402

from veil import tagged  # noqa: E402

KINDS = sorted(set(tagged.LABELS.values()))
GRID = [0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6]
FLOOR = 0.1
BASE = tagged.THRESHOLD


def _gen(docs):
    return [{"text": t, "spans": [(s, e, VB.TYPE.get(lab, "ordinary")) for s, e, lab in sp]} for t, sp in docs]


def slices():
    return {"documents (docgen/test)": VB.read(sorted(glob.glob(str(HERE / "judged/docgen/test/*.jsonl")))),
            "documents (locked 1)": VB.read(sorted(glob.glob(str(HERE / "judged/docgen/locked/*.jsonl")))),
            "forms (seed 96)": _gen(formgen.docs(300, 96)),
            "W-2s (seed 42)": _gen(w2gen.docs(200, 42)),
            "US tax forms (seed 44)": _gen(usgen.docs(280, 44))}


# -- the model, over plain or overlapping chunks ------------------------------------------------------------------------

def windows(text, overlap=0):
    """[(offset, piece, own_start, own_end)]: tagged.chunks()'s chunks, each widened by ``overlap`` words on either side;
    a chunk keeps the spans that start inside its own (unwidened) part."""
    cs = tagged.chunks(text)
    if not overlap:
        return [(o, p, o, o + len(p)) for o, p in cs]
    ws = [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]
    starts = [a for a, _ in ws]
    out = []
    for o, p in cs:
        e = o + len(p)
        i = next((k for k, a in enumerate(starts) if a >= o), len(ws))
        j = max((k for k, a in enumerate(starts) if a < e), default=i)
        a = ws[max(0, i - overlap)][0] if ws else o
        b = ws[min(len(ws) - 1, j + overlap)][1] if ws else e
        a, b = min(a, o), max(b, e)
        out.append((a, text[a:b], o, e))
    return out


def model_spans(texts, overlap=0, model=VB.TAGGER, batch=VB.BATCH):
    """{key(text): [(start, end, kind, score)]} at the score floor, cached."""
    VB.CACHE.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^\w.-]+", "_", model)
    path = VB.CACHE / f"kinds_{name}_ov{overlap}_f{FLOOR:g}.jsonl"
    have = {}
    if path.exists():
        for line in open(path):
            r = json.loads(line)
            have[r["k"]] = [tuple(x) for x in r["s"]]
    todo = list(dict.fromkeys(t for t in texts if VB._key(t) not in have))
    if todo:
        import torch
        from gliner import GLiNER
        m = GLiNER.from_pretrained(model)
        m.eval()
        t0 = time.perf_counter()
        for g in range(0, len(todo), VB.GROUP):
            group = todo[g:g + VB.GROUP]
            pieces = [(i, w) for i, t in enumerate(group) for w in windows(t, overlap)]
            found = [[] for _ in group]
            with torch.inference_mode():
                for b in range(0, len(pieces), batch):
                    part = pieces[b:b + batch]
                    ents = m.batch_predict_entities([w[1] for _, w in part], list(tagged.LABELS), threshold=FLOOR)
                    for (i, (off, _, lo, hi)), es in zip(part, ents):
                        found[i] += [(off + e["start"], off + e["end"], tagged.LABELS[e["label"]], round(e["score"], 3))
                                     for e in es if lo <= off + e["start"] < hi]
            with open(path, "a") as f:
                for t, s in zip(group, found):
                    have[VB._key(t)] = sorted(s)
                    f.write(json.dumps({"k": VB._key(t), "s": have[VB._key(t)]}) + "\n")
            print(f"  overlap {overlap}: {g + len(group)} of {len(todo)} texts in {time.perf_counter() - t0:.0f} s",
                  file=sys.stderr, flush=True)
    return have


# -- scoring ------------------------------------------------------------------------------------------------------------

class Doc:
    """One document with what it needs to be scored at any thresholds: its words, which are labelled, the veil words."""
    def __init__(self, d, found, veil):
        self.text, self.found = d["text"], found
        self.ws = bench.words(self.text)
        personal = [False] * len(self.ws)
        self.details = []   # (type, word indices)
        for s, e, g in d["spans"]:
            idx = [j for j, (_, a, b) in enumerate(self.ws) if a < e and b > s]
            if g != "ordinary":
                for j in idx:
                    personal[j] = True
            idx = [j for j in idx if self.ws[j][0].lower() not in bench.TITLES]
            if idx and g not in ("ordinary", "outside"):
                self.details.append((g, idx))
        self.other = [j for j, (w, _, _) in enumerate(self.ws) if not personal[j] and w.lower() not in bench.TITLES]
        self.veil = self._hidden(veil)

    def _hidden(self, spans):
        out, j = set(), 0
        for s, e in sorted(spans):
            while j < len(self.ws) and self.ws[j][2] <= s:
                j += 1
            k = j
            while k < len(self.ws) and self.ws[k][1] < e:
                out.add(k)
                k += 1
        return out

    def score(self, th):
        """(details found by type, details by type, other words hidden, other words) with ``th``: {kind: threshold}."""
        kept = [x for x in self.found if x[3] >= th[x[2]]]
        hidden = self.veil | self._hidden([(s, e) for s, e, _, _ in tagged.merged(kept, self.text)])
        hit, tot = {}, {}
        for g, idx in self.details:
            tot[g] = tot.get(g, 0) + 1
            hit[g] = hit.get(g, 0) + all(j in hidden for j in idx)
        return hit, tot, sum(j in hidden for j in self.other), len(self.other)


def evaluate(sets, th, half=None):
    """Mean found and mean other words hidden over the slices (and each slice's), on one half of each slice or all."""
    per = {}
    for name, docs in sets.items():
        H = N = fp = fpt = 0
        for d in docs:
            if half is not None and d.half != half:
                continue
            hit, tot, a, b = d.score(th)
            H, N, fp, fpt = H + sum(hit.values()), N + sum(tot.values()), fp + a, fpt + b
        per[name] = (H / max(1, N), fp / max(1, fpt))
    return sum(f for f, _ in per.values()) / len(per), sum(o for _, o in per.values()) / len(per), per


def by_type(sets, th):
    hit, tot = {}, {}
    for docs in sets.values():
        for d in docs:
            h, t, _, _ = d.score(th)
            for g in t:
                hit[g], tot[g] = hit.get(g, 0) + h.get(g, 0), tot.get(g, 0) + t[g]
    return {g: (hit[g], tot[g]) for g in sorted(tot)}


def tune(sets, half=None, passes=3):
    """Thresholds by kind, one kind at a time: the most found with other words hidden no higher than at 0.35."""
    base = {k: BASE for k in KINDS}
    _, budget, _ = evaluate(sets, base, half)
    th, (best_f, best_o, _) = dict(base), evaluate(sets, base, half)
    for _ in range(passes):
        moved = False
        for k in KINDS:
            for v in GRID:
                if v == th[k]:
                    continue
                f, o, _ = evaluate(sets, {**th, k: v}, half)
                closer = abs(v - BASE) < abs(th[k] - BASE)
                if o <= budget + 1e-12 and (f > best_f + 1e-12 or (abs(f - best_f) <= 1e-12 and (o < best_o or closer))):
                    th[k], best_f, best_o, moved = v, f, o, True
        if not moved:
            break
    return th


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--overlap", type=int, default=25, help="words of context each chunk takes on either side")
    ap.add_argument("--out", default=str(HERE / "kind_thresholds.json"))
    a = ap.parse_args()

    raw = slices()
    texts = list(dict.fromkeys(d["text"] for docs in raw.values() for d in docs))
    veil = VB.system_spans("veil", texts)
    report = {"slices": {k: len(v) for k, v in raw.items()}, "kinds": KINDS, "grid": GRID, "baseline": BASE, "runs": {}}
    for ov in sorted({0, a.overlap}):
        found = model_spans(texts, ov)
        sets = {name: [Doc(d, found[VB._key(d["text"])], [(s, e) for s, e, *_ in veil[VB._key(d["text"])]]) for d in docs]
                for name, docs in raw.items()}
        for docs in sets.values():
            for d in docs:
                d.half = int(hashlib.sha1(d.text.encode()).hexdigest()[:8], 16) % 2
        base = {k: BASE for k in KINDS}
        th = tune(sets)
        run = {"uniform": evaluate(sets, base), "tuned": evaluate(sets, th), "thresholds": th,
               "by_type_uniform": by_type(sets, base), "by_type_tuned": by_type(sets, th), "split_half": []}
        for h in (0, 1):   # tuned on one half, scored on the other
            t_h = tune(sets, half=h)
            run["split_half"].append({"tuned_on": h, "thresholds": t_h, "uniform": evaluate(sets, base, 1 - h)[:2],
                                      "tuned": evaluate(sets, t_h, 1 - h)[:2]})
        report["runs"][f"overlap {ov}"] = run
        print(f"\n== chunks overlapping by {ov} words")
        for label, (f, o, per) in (("all kinds at 0.35", run["uniform"]), ("tuned by kind", run["tuned"])):
            print(f"{label:18} mean found {f:.2%}   mean other words hidden {o:.2%}")
            for name, (pf, po) in per.items():
                print(f"    {name:26} found {pf:.2%}   other {po:.2%}")
        print("thresholds: " + ", ".join(f"{k} {v}" for k, v in th.items()))
        for g in run["by_type_tuned"]:
            (h0, n), (h1, _) = run["by_type_uniform"][g], run["by_type_tuned"][g]
            print(f"    {g:20} {h0}/{n} -> {h1}/{n}")
        for s in run["split_half"]:
            print(f"tuned on half {s['tuned_on']}, scored on the other: found {s['uniform'][0]:.2%} -> {s['tuned'][0]:.2%}, "
                  f"other {s['uniform'][1]:.2%} -> {s['tuned'][1]:.2%}   ({s['thresholds']})")
    json.dump(report, open(a.out, "w"), indent=1)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
