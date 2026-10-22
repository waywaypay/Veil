"""deerpark-PII-edge in Korean, with and without veil.hangul's check on the names it marks.  Results in
benchmarks/korean_names.md.

    python benchmarks/korean_names.py fetch
    python benchmarks/korean_names.py [--out korean_names_report/]

The check was written on two dev sets and read once on three held-out ones:

* dev: ai4privacy pii-masking-openpii-1.5m's Korean validation messages 200 to 999 (in languages_trace.py's order;
  the first 200 are its test messages) and townboy/korean-pii-dataset's validation split (CC-BY-4.0);
* held out: languages_trace.py's 200 Korean messages, townboy's test split, and schift-io/korean-pii-benchmark-v3
  (CC-BY-SA-4.0: court, news and office text with real-world name shapes, organisations and look-alikes).

Labels are mapped onto PII-TRACE's, and scores are pii_trace.py's, without dates and URLs (as languages_trace.md's
second tables): character precision, recall and F1, details fully hidden, names fully hidden, and other words hidden.
Each system is read one message at a time: "edge" is the tagger alone, "edge+rules" the tagger and veil's rules.
"before" turns the check off (tagged.vetted lets every span through)."""
import argparse
import json
import random
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import languages_trace as lt  # noqa: E402
import pandas as pd  # noqa: E402
import pii_trace as pt  # noqa: E402
import veilbench as vb  # noqa: E402

from veil import tagged  # noqa: E402

FILES = {"ko/schift.jsonl": "https://huggingface.co/datasets/schift-io/korean-pii-benchmark-v3/resolve/main/benchmark_v3.jsonl",
         "ko/townboy_raw_validation.jsonl": "https://huggingface.co/datasets/townboy/korean-pii-dataset/resolve/main/data/validation.jsonl",
         "ko/townboy_raw_test.jsonl": "https://huggingface.co/datasets/townboy/korean-pii-dataset/resolve/main/data/test.jsonl"}
TOWNBOY = {"NAME": "private_person", "NICKNAME": "private_person", "PHONE": "private_phone", "EMAIL": "private_email",
           "ADDRESS": "private_address", "ZIPCODE": "private_address", "CITY": "private_address",
           "BIRTHDATE": "private_date", "PASSPORTNUM": "account_number", "ALIEN_NUMBER": "account_number",
           "DRIVER_LICENSE": "account_number", "CARD_NUMBER": "account_number", "ACCOUNT_NUMBER": "account_number",
           "MEMBER_ID": "other_pii", "USER_ID": "other_pii", "EMPLOYEE_ID": "other_pii", "PARTICIPANT_ID": "other_pii",
           "VEHICLE_NUMBER": "other_pii", "URL": "private_url", "IP_ADDRESS": "private_url"}
SCHIFT = {"private_person": "private_person", "private_address": "private_address", "private_phone": "private_phone",
          "private_email": "private_email", "resident_id": "account_number"}   # its organisations are left unlabelled


def fetch():
    lt.fetch()
    for name, url in FILES.items():
        if not (vb.DATA / name).exists():
            (vb.DATA / name).parent.mkdir(parents=True, exist_ok=True)
            print("fetching", name, file=sys.stderr, flush=True)
            urllib.request.urlretrieve(url, vb.DATA / name)


def _conv(cid, text, spans, labels):
    gold = [(0, s, e, labels[lab], text[s:e]) for s, e, lab in spans if lab in labels and e > s]
    return {"id": cid, "users": [text], "gold": [g for g in gold if g[3] not in lt.DROP]}


def ai4privacy(lo, hi):
    """languages_trace.py's Korean messages, in its order."""
    cols = ["uid", "source_text", "privacy_mask", "language", "source_dataset"]
    d = pd.concat([pd.read_parquet(vb.DATA / f, columns=cols) for f in lt.FILES if f.startswith("openpii15")])
    part = d[(d.language == "ko") & (d.source_dataset == "asia-pacific")]
    rows = list(zip(part.uid, part.source_text, part.privacy_mask))
    random.Random(0).shuffle(rows)
    return [_conv(f"ko-{u}", t, [(m["start"], m["end"], m["label"]) for m in mask], lt.LABELS) for u, t, mask in rows[lo:hi]]


def townboy(split):
    rows = [json.loads(line) for line in open(vb.DATA / f"ko/townboy_raw_{split}.jsonl", encoding="utf-8")]
    return [_conv(f"townboy-{r['id']}", r["source_text"], [(m["start"], m["end"], m["label"]) for m in r["privacy_mask"]],
                  TOWNBOY) for r in rows]


def schift():
    rows = [json.loads(line) for line in open(vb.DATA / "ko/schift.jsonl", encoding="utf-8")]
    return [_conv(f"schift-{i}", r["text"], [tuple(s) for s in r["spans"]], SCHIFT) for i, r in enumerate(rows)]


def sets():
    return {"dev: ai4privacy 200-999": ai4privacy(200, 1000), "dev: townboy validation": townboy("validation"),
            "held out: ai4privacy (languages_trace)": ai4privacy(0, 200), "held out: townboy test": townboy("test"),
            "held out: schift-io v3": schift()}


def run():
    rep = {}
    data = sets()
    checked = tagged.vetted
    for mode, vet in (("before", lambda found, text: found), ("after", checked)):
        tagged.vetted = vet
        for name, convs in data.items():
            for system, run_as in (("edge", "model"), ("edge+rules", "union")):
                pred, _ = pt.run(run_as, convs)
                pred = [[x for x in p if x[3] not in lt.DROP] for p in pred]
                r = pt.score(convs, pred, False)
                rep.setdefault(name, {"messages": len(convs), "gold": r["gold"]}).setdefault(system, {})[mode] = {
                    "char": r["char"], "contained": r["contained"],
                    "names": r["contained_by_label"].get("private_person", 0), "other_hidden": r["other_hidden"]}
                print(f"{mode:6} {name:40} {system:10} char F1 {r['char']['f1']:.3f}  names "
                      f"{r['contained_by_label'].get('private_person', 0):.1%}  other words {r['other_hidden']:.2%}", flush=True)
    tagged.vetted = checked
    return rep


def markdown(rep):
    out = ["| Set | Messages | Gold spans | System | Char F1 | Char precision | Details fully hidden | Names fully hidden | "
           "Other words hidden |", "|---|---|---|---|---|---|---|---|---|"]
    for name, r in rep.items():
        for system in ("edge", "edge+rules"):
            b, a = r[system]["before"], r[system]["after"]
            out.append(f"| {name} | {r['messages']} | {r['gold']} | {system} | {b['char']['f1']:.3f} → {a['char']['f1']:.3f} | "
                       f"{b['char']['p']:.3f} → {a['char']['p']:.3f} | {b['contained']:.1%} → {a['contained']:.1%} | "
                       f"{b['names']:.1%} → {a['names']:.1%} | {b['other_hidden']:.2%} → {a['other_hidden']:.2%} |")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["fetch", "score"], default="score")
    ap.add_argument("--out", default="korean_names_report")
    a = ap.parse_args()
    fetch()
    if a.cmd == "fetch":
        return
    rep = run()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    json.dump(rep, open(out / "report.json", "w"), indent=1, ensure_ascii=False)
    (out / "report.md").write_text(markdown(rep), encoding="utf-8")
    print(f"wrote {out / 'report.json'} and {out / 'report.md'}")


if __name__ == "__main__":
    main()
