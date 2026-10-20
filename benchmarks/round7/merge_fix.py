"""veil + model, merged before redacting: the model's finds (on the original text) are registered with the redactor first
(add_person for names, add for the rest), then veil redacts the original once, so its rules and the model's finds apply
together.  python merge_fix.py <model>@<th>   (dev slices; writes merge_fix.json)"""
import json, os, sys
sys.path.insert(0, "/tmp/claude-0/-home-user-Veil/190ab3d3-f9c1-50ad-a470-e321ea643401/scratchpad")
import round4 as R, round7 as R7
from breakdown import cached
from veil import FINANCE, Redactor
T = R.T


def merged_first(text, found, threshold, gate=None, redactor=None):
    r = redactor or Redactor(FINANCE)
    found = [x for x in found if x[3] >= threshold]
    cands = {(s, e, k) for s, e, k, _ in T.merged(found, text)} | {(s, e, k) for s, e, k, _ in found}
    for s, e, kind in sorted(cands, key=lambda x: x[0] - x[1]):     # longest first
        v = text[s:e]
        if len(v.strip()) < 3 or (gate and not gate(kind, v)):
            continue
        try:
            r.add_person(v) if kind == "NAME" else r.add(v, kind)
        except ValueError:
            pass
    return r.redact_text(text)


def union(text, found, threshold, extra=()):
    """Every word veil hides and every span the model marks, both decided on the original text, hidden together."""
    import gretel
    a, kept = gretel.redacted_mask(text, Redactor(FINANCE).redact_text(text))
    ranges = [(s, e) for (_, s, e), k in zip(a, kept) if not k]
    ranges += [(s, e) for s, e, _, _ in T.merged([x for x in found if x[3] >= threshold], text)]
    ranges += [(s, e) for s, e, *_ in extra]
    out, last = [], None
    for s, e in sorted(ranges):
        if last and s <= last[1]:
            last[1] = max(last[1], e)
        else:
            last = [s, e]
            out.append(last)
    t = text
    for s, e in reversed(out):
        t = t[:s] + "X_X" + t[e:]
    return t


if __name__ == "__main__":
    if os.environ.get("PYTHONHASHSEED") != "0":
        os.execve(sys.executable, [sys.executable, *sys.argv], {**os.environ, "PYTHONHASHSEED": "0"})
    spec = sys.argv[1]
    model, _, th = spec.partition("@"); th = float(th)
    have = cached(model)
    out = {}
    for name, rows in R7.dev_sets().items():
        if not all(T.key(t) in have for t, _ in rows):
            continue
        ins = [t for t, _ in rows]
        res = {"model": T.score(rows, ins, [T.alone(t, have[T.key(t)], th) for t in ins]),
                              "new veil+model": T.score(rows, ins, [merged_first(t, have[T.key(t)], th) for t in ins]),
               "union": T.score(rows, ins, [union(t, have[T.key(t)], th) for t in ins])}
        out[name] = {k: [v["found"], v["over"]] for k, v in res.items()}
        print(f"{name[:34]:34}", "  ".join(f"{k} {v['found']:.1%}/{v['over']:.2%}" for k, v in res.items()), flush=True)
    n = len(out)
    print("MEAN", "  ".join(f"{k} {sum(r[k][0] for r in out.values()) / n:.2%}/{sum(r[k][1] for r in out.values()) / n:.2%}" for k in next(iter(out.values()))))
    json.dump(out, open("merge_fix.json", "w"), indent=1)
