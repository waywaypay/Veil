"""What deerpark-PII-edge misses on PII-TRACE's dev half, alone, and why: an error analysis to aim its next round at.

    python benchmarks/pii_trace_errors.py                       # the tagger, one message at a time and whole conversation
    python benchmarks/pii_trace_errors.py --gold-only           # the gold spans' formats and veil's rules, no model

Only the dev half (pii_trace.half) is read, without private_date and private_url, so the test half stays read once.
Each gold span is put in one outcome, for the tagger alone at its threshold (0.35):

* hidden: every character covered by some span of the tagger's (any kind; the scores in pii_trace.md are untyped);
* partial: some characters covered, not all (a boundary miss);
* lower threshold: not hidden at 0.35, but hidden by what the tagger marks at some threshold down to the floor
  (0.1), the highest such threshold given, so a threshold for its kind could reach it;
* missed: not hidden even at the floor.

Each span is also given a format (its letters, digits and marks with runs collapsed: "AB12-77XQ" -> "A9-9A") and a
format family, and whether veil's rules hide it (one Redactor per conversation, as pii_trace.py runs them).  The
report goes to stdout and the spans to --out as JSONL."""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pii_trace as P  # noqa: E402

from veil import tagged  # noqa: E402

KEEP = [lab for lab in P.LABELS if lab not in ("private_date", "private_url")]
FLOOR = 0.1
STEPS = [0.3, 0.25, 0.2, 0.15, 0.1]


def shape(text):
    """Letters, digits and marks with runs collapsed: upper "A", lower "a", digit "9", space " "."""
    out = []
    for c in text:
        k = "A" if c.isupper() else "a" if c.islower() else "9" if c.isdigit() else " " if c.isspace() else c
        if not out or out[-1] != k:
            out.append(k)
    return "".join(out)


def family(label, text):
    """A coarse format family, to group the misses by."""
    t = text.strip()
    if label == "private_phone":
        if re.search(r"(?i)\b(ext|x)\.?\s*\d", t) or "," in t:
            return "phone with extension"
        if t.startswith("+") and not t.startswith("+1"):
            return "phone, international"
        if re.search(r"[A-Za-z]", t):
            return "phone with letters"
        return "phone, North American" if len(re.sub(r"\D", "", t)) in (10, 11) else "phone, other length"
    if label == "private_email":
        return "email"
    if label == "private_person":
        n = len(t.split())
        return "name, one word" if n == 1 else "name, two words" if n == 2 else "name, 3+ words"
    if label == "private_address":
        return "address with digits" if re.search(r"\d", t) else "address, words only"
    if re.fullmatch(r"\d[\d\s-]*", t):
        return "digits" + (", grouped" if re.search(r"[\s-]", t) else "")
    if re.search(r"(?i)^(sk|pk|rk|ghp|gho|xox[abp]|AKIA|AIza|eyJ)[-_]?", t) or len(t) >= 24 and re.fullmatch(r"[\w\-+/=.]+", t):
        return "key or token"
    if " " in t and len(re.findall(r"[A-Za-z]{3,}", t)) >= 2:
        return "words (phrase or password)"
    if re.search(r"[A-Za-z]", t) and re.search(r"\d", t):
        return "letters and digits" + (", grouped" if re.search(r"[\s\-_./]", t) else "")
    return "letters only" if re.fullmatch(r"[A-Za-z]+", t) else "other"


def covered(s, e, spans):
    """How many of the characters s..e (spaces aside) the spans cover, and how many there are."""
    chars = [i for i in range(s, e)]
    hit = sum(1 for i in chars if any(a <= i < b for a, b in spans))
    return hit, len(chars)


def tagger_found(convs, conv, model):
    """For each conversation, turn: [(start, end, kind, score)] at the floor, joined as TaggedRedactor joins them."""
    r = tagged.TaggedRedactor(model=model)
    if not conv:
        texts = [u for c in convs for u in c["users"]]
        got = dict(zip(texts, r.model_spans(texts, threshold=FLOOR)))
        return [[got[u] for u in c["users"]] for c in convs]
    joined = [P.SEP.join(c["users"]) for c in convs]
    found = r.model_spans(joined, threshold=FLOOR)
    out = []
    for c, spans in zip(convs, found):
        per, pos = [], 0
        for u in c["users"]:
            per.append([(max(s, pos) - pos, min(e, pos + len(u)) - pos, k, sc) for s, e, k, sc in spans
                        if s < pos + len(u) and e > pos])
            pos += len(u) + len(P.SEP)
        out.append(per)
    return out


def outcome(s, e, text, found):
    """hidden / partial / lower threshold (with the threshold) / missed, for the tagger's spans at the floor."""
    def at(th):
        return [(a, b) for a, b, _, _ in tagged.merged([x for x in found if x[3] >= th], text)]
    hit, n = covered(s, e, at(tagged.THRESHOLD))
    if hit == n:
        return "hidden", tagged.THRESHOLD
    for th in STEPS:
        h, _ = covered(s, e, at(th))
        if h == n:
            return "lower threshold", th
    return ("partial" if hit else "missed"), None


def table(rows, key, cols):
    by = defaultdict(Counter)
    for r in rows:
        by[key(r)][r["outcome"]] += 1
    out = ["| " + " | ".join(["", "n"] + cols) + " |", "|" + "---|" * (len(cols) + 2)]
    for k, c in sorted(by.items(), key=lambda kv: -sum(kv[1].values())):
        n = sum(c.values())
        out.append(f"| {k} | {n} | " + " | ".join(f"{100 * c[o] / n:.1f}%" for o in cols) + " |")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gold-only", action="store_true", help="formats and veil's rules only; the model isn't run")
    ap.add_argument("--model", default=tagged.ONNX_MODEL, help="a TaggedRedactor model (default: deerpark-PII-edge)")
    ap.add_argument("--out", default="pii_trace_errors.jsonl")
    a = ap.parse_args()
    convs = [c for c in P.load() if P.half(c["id"]) == "dev"]
    veil = P.veil_spans(convs)
    modes = {} if a.gold_only else {"one message": tagger_found(convs, False, a.model),
                                         "whole conversation": tagger_found(convs, True, a.model)}
    rows = []
    for ci, c in enumerate(convs):
        vspans = defaultdict(list)
        for t, s, e, _ in veil[ci]:
            vspans[t].append((s, e))
        seen = Counter()
        for t, s, e, label, text in c["gold"]:
            if label not in KEEP:
                continue
            value = re.sub(r"\W", "", text).lower()
            seen[value] += 1
            h, n = covered(s, e, vspans[t])
            row = {"id": c["id"], "turn": t, "label": label, "text": text, "shape": shape(text),
                   "family": family(label, text), "mention": seen[value], "veil": h == n,
                   "context": c["users"][t][max(0, s - 40):e + 40]}
            for m, found in modes.items():
                o, th = outcome(s, e, c["users"][t], found[ci][t])
                row[m] = {"outcome": o, "threshold": th,
                          "kinds": sorted({k for a2, b2, k, sc in found[ci][t] if a2 < e and b2 > s and sc >= FLOOR})}
            rows.append(row)
    with open(a.out, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")

    print(f"PII-TRACE dev half: {len(convs)} conversations, {len(rows)} gold spans without dates and URLs\n")
    vr = [dict(r, outcome="veil hides" if r["veil"] else "veil misses") for r in rows]
    print("## Formats, and veil's rules\n")
    print(table(vr, lambda r: r["label"] + " / " + r["family"], ["veil hides"]) + "\n")
    print("Most common formats by label:\n")
    for lab in KEEP:
        c = Counter(r["shape"] for r in rows if r["label"] == lab)
        print(f"* {lab}: " + ", ".join(f"`{s}` {n}" for s, n in c.most_common(8)))
    cols = ["hidden", "partial", "lower threshold", "missed"]
    for m in modes:
        mr = [dict(r, outcome=r[m]["outcome"]) for r in rows]
        print(f"\n## The tagger alone, {m}\n")
        print(table(mr, lambda r: r["label"], cols) + "\n")
        print(table(mr, lambda r: r["label"] + " / " + r["family"], cols) + "\n")
        print(table(mr, lambda r: "first mention" if r["mention"] == 1 else "a later mention", cols) + "\n")
        th = Counter((r["label"], r[m]["threshold"]) for r in rows if r[m]["outcome"] == "lower threshold")
        print("Threshold that would reach each 'lower threshold' span: " +
              "; ".join(f"{lab} {t}: {n}" for (lab, t), n in sorted(th.items())) + "\n")
        print("Misses, a sample by label (kind the tagger gave nearby, if any):\n")
        for lab in KEEP:
            miss = [r for r in rows if r["label"] == lab and r[m]["outcome"] in ("missed", "partial")]
            for r in miss[:6]:
                ctx = r["context"].replace("\n", " ")
                print(f"* {lab}: `{r['text']}` ({r[m]['outcome']}, {','.join(r[m]['kinds']) or '-'}) … {ctx} …")


if __name__ == "__main__":
    main()
