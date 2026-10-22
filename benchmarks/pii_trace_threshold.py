"""A tagger checkpoint's threshold on PII-TRACE's dev half, chosen by the rule of judged/PROTOCOL.md: the threshold that
hides the most details in full, hiding no more other words than deerpark-PII-edge at 0.35 does on the same documents.

    python benchmarks/pii_trace_threshold.py MODEL [--reference Deerpark/veil-tagger-edge] [--drop private_date,private_url]

Each of the four ways pii_trace.py reads a conversation is chosen for on its own: the tagger alone or with veil's rules,
one message at a time or the whole conversation in one pass.  The spans come from pii_trace.py's cache (kept from a
score of 0.3), so a run of pii_trace.py --split dev with the same systems must come first, or this one reads them."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pii_trace as pt  # noqa: E402

from veil import tagged  # noqa: E402

THRESHOLDS = [round(0.3 + 0.05 * k, 2) for k in range(14)]   # 0.3 to 0.95
MODES = ["tagger", "tagger-conv", "union", "union-conv"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model")
    ap.add_argument("--reference", default=tagged.MODEL)
    ap.add_argument("--drop", default="private_date,private_url")
    a = ap.parse_args()
    drop = set(filter(None, a.drop.split(",")))
    convs = [c for c in pt.load() if pt.half(c["id"]) == "dev"]
    for c in convs:
        c["gold"] = [g for g in c["gold"] if g[3] not in drop]

    def scored(name):
        pred, _ = pt.run(name, convs)
        return pt.score(convs, [[p for p in ps if p[3] not in drop] for ps in pred], False)

    print(f"dev half: {len(convs)} conversations, {sum(len(c['gold']) for c in convs)} spans"
          + (f", leaving out {', '.join(sorted(drop))}" if drop else ""))
    for mode in MODES:
        ref = scored(f"{mode}:{a.reference}@{tagged.THRESHOLD}")
        budget = ref["other_hidden"]
        print(f"\n{mode}: {a.reference} at {tagged.THRESHOLD} hides {ref['contained']:.1%} in full, "
              f"{budget:.2%} of other words")
        print("  threshold  contained  consistent 2+  char F1  other words hidden")
        best = None
        for th in THRESHOLDS:
            r = scored(f"{mode}:{a.model}@{th}")
            ok = r["other_hidden"] <= budget
            print(f"  {th:<9}  {r['contained']:9.1%}  {r['consistent']['2+']['share']:13.1%}  {r['char']['f1']:7.3f}  "
                  f"{r['other_hidden']:.2%}{'' if ok else '  (over)'}")
            if ok and (best is None or r["contained"] > best[1]["contained"]):
                best = (th, r)
        print(f"  chosen: {best[0]} ({best[1]['contained']:.1%} in full, {best[1]['other_hidden']:.2%} other words)"
              if best else "  chosen: none within the reference's other words")


if __name__ == "__main__":
    main()
