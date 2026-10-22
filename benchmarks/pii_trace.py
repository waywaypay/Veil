"""veil, its tagger and Perplexity's PII-Tracer on PII-TRACE, Perplexity's multi-turn PII benchmark.

    python benchmarks/pii_trace.py [--systems veil,model,union,pii-tracer,pii-tracer-conv] [--out pii_trace_report/]

The data is the public 500-conversation subset of perplexity-ai/PII-TRACE (2,653 labelled spans, nine labels, every one
in a user message), fetched once into $VEIL_BENCH_DATA.  Only user messages are read and scored, as the dataset card
says the labels cover.  Each system reads one message at a time, except:

* "veil" and "union" keep one Redactor for the whole conversation, as veil is meant to be used, so a name found in
  one turn is hidden in the next;
* "pii-tracer-conv" reads a conversation's user messages joined by blank lines in one pass (they fit in its 4,096
  tokens), so it sees every turn at once.

Scores, every one over (conversation, turn, start, end) in user messages:

* exact: the dataset card's metric, a span counts only with the same start and end (and, typed, the same label);
  micro and macro over the nine labels.  Systems whose labels map onto PII-TRACE's are scored typed as well.
* char: precision, recall and F1 over characters, labels ignored (the blog's headline metric).
* overlap: a gold span is found if any predicted span touches it; a predicted span is right if it touches any gold one.
* contained: share of gold spans every character of which some predicted span covers.
* consistent: an identifier (one value, compared by its letters and digits, in one conversation) counts only if every
  character of every mention is covered; by number of mentions.
* other words hidden: of the words no gold span touches, the share a system's spans touch (veilbench's cost measure).

--split dev or test scores one half of the conversations (by a hash of their ID), so rules can be tuned on dev and
read once on test.  --drop private_date,private_url scores only the labels veil sets out to hide: those gold spans are left out, and so are
the spans a system labels as them (an untyped system's spans all stay).
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import veilbench as vb  # noqa: E402

from veil import FINANCE, Redactor, tagged  # noqa: E402

URL = "https://huggingface.co/datasets/perplexity-ai/PII-TRACE/resolve/main/data/train.parquet"
LABELS = ["private_person", "private_email", "account_number", "private_address", "private_date", "private_phone",
          "other_pii", "secret", "private_url"]
# the tagger's kinds -> PII-TRACE's labels (it has no URL or secret kind; SSNs and other IDs are PII-TRACE's other_pii)
FROM_TAGGER = {"NAME": "private_person", "ADDRESS": "private_address", "EMAIL": "private_email", "PHONE": "private_phone",
               "ACCOUNT": "account_number", "DOB": "private_date", "SSN": "other_pii", "ID": "other_pii"}
_WORD = re.compile(r"\w+")


def half(cid):
    """ "dev" or "test": a conversation's half, from a hash of its ID."""
    import hashlib
    return "dev" if hashlib.sha1(cid.encode()).digest()[0] % 2 == 0 else "test"


def load():
    import pandas as pd
    path = vb.DATA / "pii_trace.parquet"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(URL, path)
    convs = []
    for r in pd.read_parquet(path).itertuples():
        users = [t["user"] or "" for t in sorted(r.turns, key=lambda t: t["turn"])]
        gold = [(s["turn"], s["start"], s["end"], s["label"], s["text"]) for s in r.spans]
        for t, s, e, _, txt in gold:
            assert users[t][s:e] == txt, (r.id, t)
        convs.append({"id": r.id, "users": users, "gold": gold})
    return convs


# -- systems: each gives, per conversation, [(turn, start, end, label or None)] ---------------------------------------

def tagger_spans(name, convs, th):
    """The tagger's spans as TaggedRedactor joins them: adjacent ones of a kind merged, names with their initials."""
    texts = [u for c in convs for u in c["users"]]
    have = vb.system_spans(name, texts)
    out = []
    for c in convs:
        found = []
        for t, u in enumerate(c["users"]):
            found += [(t, s, e, FROM_TAGGER[k]) for s, e, k, _ in tagged.merged([x for x in have[vb._key(u)] if x[3] >= th], u)]
        out.append(found)
    return out


def veil_spans(convs):
    """veil's rules, one Redactor per conversation; each hidden run of words is one span."""
    out = []
    for c in convs:
        r, found = watched(), []
        for t, u in enumerate(c["users"]):
            for s, e in hidden(u, r):
                found.append((t, s, e, None))
        out.append(found)
    return out


class Watched(Redactor):
    """A Redactor that notes what it hides, as written, so a hidden run can take in the marks no word holds."""
    def _placeholder(self, kind, key, written, dashed):
        self.written.append(written)
        return super()._placeholder(kind, key, written, dashed)


def watched(**kw):
    r = Watched(FINANCE, **kw)
    r.written = []
    return r


def hidden(text, r):
    """What Redactor ``r`` hides in ``text``, as runs: the words its output no longer has (tagged.veil_hidden), each
    taking in the marks at the edges of the value it hid ("+" of "+1 202 555 0133", which no word holds)."""
    r.written.clear()
    words = tagged.veil_hidden(text, r.redact_text(text))
    for w in r.written:
        for m in re.finditer(re.escape(w), text):
            if any(s < m.end() and m.start() < e for s, e in words):
                words += [(m.start() + k, m.start() + k + 1) for k, c in enumerate(w) if not (c.isalnum() or c.isspace())]
    return _runs(text, words)


def _runs(text, words):
    """Hidden words joined into runs where only spaces and punctuation lie between them on one line."""
    out = []
    for s, e in sorted(words):
        if out and re.fullmatch(r"[^\w\n]*", text[out[-1][1]:s]):
            out[-1][1] = e
        else:
            out.append([s, e])
    return [tuple(x) for x in out]


def tracer_spans(convs):
    texts = [u for c in convs for u in c["users"]]
    have = vb.system_spans("pii-tracer", texts)
    return [[(t, s, e, k) for t, u in enumerate(c["users"]) for s, e, k, _ in have[vb._key(u)]] for c in convs]


SEP = "\n\n"


def tracer_conv_spans(convs):
    """PII-Tracer on a conversation's user messages joined, its spans mapped back to each message."""
    joined = [SEP.join(c["users"]) for c in convs]
    have = vb.system_spans("pii-tracer", joined)
    out = []
    for c, j in zip(convs, joined):
        starts, pos = [], 0
        for u in c["users"]:
            starts.append(pos)
            pos += len(u) + len(SEP)
        found = []
        for s, e, k, _ in have[vb._key(j)]:
            for t, (a, u) in enumerate(zip(starts, c["users"])):
                if s < a + len(u) and e > a:
                    found.append((t, max(s, a) - a, min(e, a + len(u)) - a, k))
        out.append(found)
    return out


def redactor_spans(convs):
    """veil's Redactor with the tagger as its finder (TaggedRedactor().redactor()), one per conversation: what an app
    gets from veil.tagged.  Each hidden run of words is one span."""
    texts = [u for c in convs for u in c["users"]]
    have = vb.system_spans("model", texts)
    out = []
    for c in convs:
        def finder(u):
            return [(s, e, k) for s, e, k, _ in tagged.merged([x for x in have[vb._key(u)] if x[3] >= tagged.THRESHOLD], u)]
        r, found = watched(finder=finder), []
        for t, u in enumerate(c["users"]):
            found += [(t, s, e, None) for s, e in hidden(u, r)]
        out.append(found)
    return out


def union(a, b):
    return [x + [(t, s, e, None) for t, s, e, _ in y] for x, y in zip(a, b)]


# -- scoring ----------------------------------------------------------------------------------------------------------

def prf(tp, npred, ngold):
    p, r = tp / max(1, npred), tp / max(1, ngold)
    return {"p": p, "r": r, "f1": 2 * p * r / max(1e-9, p + r)}


def score(convs, pred, typed):
    G = [(i, t, s, e, k) for i, c in enumerate(convs) for t, s, e, k, _ in c["gold"]]
    P = [(i, t, s, e, k) for i, ps in enumerate(pred) for t, s, e, k in ps if e > s]
    res = {"gold": len(G), "predicted": len(P)}

    gu, pu = {g[:4] for g in G}, {p[:4] for p in P}
    res["exact"] = prf(len(gu & pu), len(pu), len(gu))
    if typed:
        gt, pt = {tuple(g) for g in G}, {tuple(p) for p in P}
        res["exact_typed"] = prf(len(gt & pt), len(pt), len(gt))
        per = {lab: prf(len({x for x in gt & pt if x[4] == lab}), len({x for x in pt if x[4] == lab}),
                        len({x for x in gt if x[4] == lab})) for lab in LABELS}
        res["exact_typed_macro_f1"] = sum(v["f1"] for v in per.values()) / len(per)
        res["exact_typed_by_label"] = per

    # character masks per message
    gm, pm = defaultdict(set), defaultdict(set)
    for i, t, s, e, _ in G:
        gm[i, t].update(range(s, e))
    for i, t, s, e, _ in P:
        pm[i, t].update(range(s, e))
    keys = set(gm) | set(pm)
    tp = sum(len(gm[k] & pm[k]) for k in keys)
    res["char"] = prf(tp, sum(len(pm[k]) for k in keys), sum(len(gm[k]) for k in keys))

    by_msg = defaultdict(list)
    for i, t, s, e, _ in P:
        by_msg[i, t].append((s, e))
    gby = defaultdict(list)
    for i, t, s, e, _ in G:
        gby[i, t].append((s, e))
    g_hit = sum(any(a < e and b > s for a, b in by_msg[i, t]) for i, t, s, e, _ in G)
    p_hit = sum(any(a < e and b > s for a, b in gby[i, t]) for i, t, s, e, _ in P)
    rr, pp = g_hit / max(1, len(G)), p_hit / max(1, len(P))
    res["overlap"] = {"p": pp, "r": rr, "f1": 2 * pp * rr / max(1e-9, pp + rr)}
    covered = lambda i, t, s, e: set(range(s, e)) <= pm[i, t]   # noqa: E731
    res["contained"] = sum(covered(i, t, s, e) for i, t, s, e, _ in G) / max(1, len(G))
    by_label = defaultdict(lambda: [0, 0])
    for i, t, s, e, k in G:
        by_label[k][0] += covered(i, t, s, e)
        by_label[k][1] += 1
    res["contained_by_label"] = {k: v[0] / v[1] for k, v in by_label.items()}

    ids = defaultdict(list)
    for i, c in enumerate(convs):
        for t, s, e, k, txt in c["gold"]:
            ids[i, re.sub(r"[\W_]", "", txt).lower()].append((t, s, e))
    buckets = defaultdict(lambda: [0, 0])
    for (i, _), ms in ids.items():
        n = len(ms)
        b = "1" if n == 1 else "2" if n == 2 else "3-5" if n <= 5 else "6+"
        ok = all(covered(i, t, s, e) for t, s, e in ms)
        for key in (b, "all") + (("2+",) if n > 1 else ()) + (("cross-turn",) if len({t for t, _, _ in ms}) > 1 else ()):
            buckets[key][0] += ok
            buckets[key][1] += 1
    res["consistent"] = {k: {"share": v[0] / v[1], "n": v[1]} for k, v in sorted(buckets.items())}

    fp = tot = 0
    for i, c in enumerate(convs):
        for t, u in enumerate(c["users"]):
            for m in _WORD.finditer(u):
                if any(s < m.end() and e > m.start() for s, e in gby[i, t]):
                    continue
                tot += 1
                fp += any(s < m.end() and e > m.start() for s, e in by_msg[i, t])
    res["other_hidden"] = fp / max(1, tot)
    return res


ABOUT = {"veil": "veil's rules alone (FINANCE profile), one Redactor per conversation",
         "model": f"veil's tagger alone ({vb.TAGGER}, 45M) at {tagged.THRESHOLD}",
         "union": "veil + its tagger: everything either marks",
         "redactor": "veil's Redactor with its tagger as the finder (TaggedRedactor().redactor()), one per conversation",
         "pii-tracer": "perplexity-ai/PII-Tracer (596M), one message at a time",
         "pii-tracer-conv": "perplexity-ai/PII-Tracer (596M), a conversation's user messages in one pass"}


def run(name, convs):
    if name == "veil":
        return veil_spans(convs), False
    if name == "model":
        return tagger_spans("model", convs, tagged.THRESHOLD), True
    if name == "union":
        return union(tagger_spans("model", convs, tagged.THRESHOLD), veil_spans(convs)), False
    if name == "redactor":
        return redactor_spans(convs), False
    if name == "pii-tracer":
        return tracer_spans(convs), True
    if name == "pii-tracer-conv":
        return tracer_conv_spans(convs), True
    if name.startswith("tagger:"):   # another GLiNER checkpoint of the tagger: tagger:<dir or repo>[@threshold]
        model, _, th = name[7:].partition("@")
        key = "tagger-" + re.sub(r"\W+", "_", model)
        vb.SYSTEMS.setdefault(key, (lambda m=model: vb.Tagger(m), model, tagged.THRESHOLD))
        ABOUT.setdefault(name, f"veil's tagger, checkpoint {model}")
        return tagger_spans(key, convs, float(th) if th else tagged.THRESHOLD), True
    raise SystemExit(f"unknown system {name}")


def markdown(rep):
    rows = list(rep["systems"].items())
    f = lambda x: f"{x:.3f}"   # noqa: E731
    out = [f"PII-TRACE public subset{'' if rep['split'] == 'all' else ', ' + rep['split'] + ' half'}: {rep['conversations']} conversations, {rep['gold']} labelled spans, user messages "
           "only" + (f", leaving out {', '.join(rep['dropped'])}" if rep["dropped"] else "") + ".", "",
           "| System | Exact F1 (typed, micro) | Exact F1 (typed, macro) | Exact F1 (untyped) | Char P | Char R | Char F1 | "
           "Overlap F1 | Contained | Consistent (2+ mentions) | Other words hidden |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for name, r in rows:
        ty = (f(r["exact_typed"]["f1"]), f(r["exact_typed_macro_f1"])) if "exact_typed" in r else ("–", "–")
        out.append(f"| {name} | {ty[0]} | {ty[1]} | {f(r['exact']['f1'])} | {f(r['char']['p'])} | {f(r['char']['r'])} | "
                   f"{f(r['char']['f1'])} | {f(r['overlap']['f1'])} | {r['contained']:.1%} | "
                   f"{r['consistent'].get('2+', {}).get('share', 0):.1%} | {r['other_hidden']:.2%} |")
    out += ["", "Gold spans fully covered, by label:", "", "| Label | " + " | ".join(n for n, _ in rows) + " |",
            "|---|" + "---|" * len(rows)]
    for lab in LABELS:
        out.append(f"| {lab} | " + " | ".join(f"{r['contained_by_label'].get(lab, 0):.1%}" for _, r in rows) + " |")
    out += ["", "Identifiers with every mention fully covered, by number of mentions:", "",
            "| Mentions | n | " + " | ".join(n for n, _ in rows) + " |", "|---|---|" + "---|" * len(rows)]
    for b in ["1", "2", "3-5", "6+", "cross-turn", "all"]:
        n = rows[0][1]["consistent"].get(b, {}).get("n", 0)
        if n:
            out.append(f"| {b} | {n} | " + " | ".join(f"{r['consistent'][b]['share']:.1%}" for _, r in rows) + " |")
    out += [""] + [f"* {n}: {ABOUT.get(n, n)}" for n, _ in rows]
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--systems", default="veil,model,union,pii-tracer,pii-tracer-conv")
    ap.add_argument("--out", default="pii_trace_report")
    ap.add_argument("--split", choices=("all", "dev", "test"), default="all")
    ap.add_argument("--drop", default="", help="labels to leave out of the gold spans and of typed predictions")
    a = ap.parse_args()
    drop = set(filter(None, a.drop.split(",")))
    LABELS[:] = [lab for lab in LABELS if lab not in drop]
    convs = [c for c in load() if a.split in ("all", half(c["id"]))]
    for c in convs:
        c["gold"] = [g for g in c["gold"] if g[3] not in drop]
    rep = {"split": a.split, "dropped": sorted(drop), "conversations": len(convs), "gold": sum(len(c["gold"]) for c in convs), "systems": {}}
    for name in a.systems.split(","):
        pred, typed = run(name, convs)
        pred = [[p for p in ps if p[3] not in drop] for ps in pred]
        r = rep["systems"][name] = score(convs, pred, typed)
        print(f"{name:18} exact F1 {r['exact']['f1']:.3f}  char F1 {r['char']['f1']:.3f}  contained {r['contained']:.1%}  "
              f"other words hidden {r['other_hidden']:.2%}", flush=True)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    json.dump(rep, open(out / "report.json", "w"), indent=1)
    (out / "report.md").write_text(markdown(rep), encoding="utf-8")
    print(f"wrote {out / 'report.json'} and {out / 'report.md'}")


if __name__ == "__main__":
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    main()
