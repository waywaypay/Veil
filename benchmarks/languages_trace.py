"""PII-TRACE's language comparison, run on public data: veil's rules, the deerpark-PII taggers and PII-Tracer in the six
languages of the PII-TRACE report's Figure 3 (English, German, French, Italian, Russian, Korean), scored as
pii_trace.py scores PII-TRACE.  Results in benchmarks/languages_trace.md.

    python benchmarks/languages_trace.py fetch
    python benchmarks/languages_trace.py [--per 200] [--systems veil,edge,edge+rules,large,large+rules,pii-tracer] [--out languages_trace_report/]

The report's per-language test documents aren't public (the released subset of PII-TRACE is 500 English
conversations), so each language is drawn from public data labelled in ai4privacy's format, --per messages at random:

* English, German, French, Italian: ai4privacy's pii-masking-openpii-1.5m, validation split, its "base" part;
* Korean: the same split's "asia-pacific" part;
* Russian: wolframko/russian-pii-66k (ai4privacy's format; only a train split).

They are single messages, not conversations, so each is read as a one-turn conversation; "consistent" then counts a
detail that recurs within a message.  Their labels are mapped onto PII-TRACE's nine (LABELS below); what PII-TRACE has
no label for (a title, an age, a gender, a time) is left unlabelled, as PII-TRACE leaves it.  Like pii_trace.py, the
report gives all labels, and the labels veil sets out to hide (without private_date and private_url).

Scores are pii_trace.py's: character precision, recall and F1, labels ignored (the report's per-language metric);
contained (gold spans every character of which is covered); consistent (details with 2+ mentions, each covered); and
other words hidden.  Systems:

* veil: veil's rules alone (FINANCE profile)
* edge, large: deerpark-PII-edge (Deerpark/veil-tagger-edge) or deerpark-PII-large (out_large in
  Deerpark/veil-control) alone, at veil's threshold (tagged.THRESHOLD)
* edge+rules, large+rules: the checkpoint and veil's rules, everything either marks
* pii-tracer: perplexity-ai/PII-Tracer, pinned as veilbench pins it"""
import argparse
import json
import random
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import languages  # noqa: E402
import pandas as pd  # noqa: E402
import pii_trace as pt  # noqa: E402
import veilbench as vb  # noqa: E402

HF = "https://huggingface.co/api/datasets"
FILES = {"openpii15_val_0.parquet": f"{HF}/ai4privacy/pii-masking-openpii-1.5m/parquet/default/validation/0.parquet",
         "openpii15_val_1.parquet": f"{HF}/ai4privacy/pii-masking-openpii-1.5m/parquet/default/validation/1.parquet",
         "russian_pii.parquet": f"{HF}/wolframko/russian-pii-66k/parquet/default/train/0.parquet"}
# ai4privacy's labels -> PII-TRACE's (a user name is a handle, which PII-TRACE counts as a person's name)
LABELS = {"GIVENNAME": "private_person", "SURNAME": "private_person", "USERNAME": "private_person",
          "STREET": "private_address", "BUILDINGNUM": "private_address", "CITY": "private_address",
          "ZIPCODE": "private_address", "EMAIL": "private_email", "TELEPHONENUM": "private_phone",
          "IDCARDNUM": "account_number", "SOCIALNUM": "account_number", "TAXNUM": "account_number",
          "DRIVERLICENSENUM": "account_number", "PASSPORTNUM": "account_number", "CREDITCARDNUMBER": "account_number",
          "ACCOUNTNUM": "account_number", "DATE": "private_date", "DATEOFBIRTH": "private_date", "PASSWORD": "secret",
          "URL": "private_url"}
LANGUAGES = {"en": "English", "de": "German", "fr": "French", "it": "Italian", "ru": "Russian", "ko": "Korean"}
DROP = {"private_date", "private_url"}


def fetch():
    vb.DATA.mkdir(parents=True, exist_ok=True)
    for name, url in FILES.items():
        if not (vb.DATA / name).exists():
            print("fetching", name, file=sys.stderr, flush=True)
            urllib.request.urlretrieve(url, vb.DATA / name)


def _conv(cid, text, mask):
    """A message as a one-turn conversation in pii_trace.py's form."""
    gold = [(0, m["start"], m["end"], LABELS[m["label"]], text[m["start"]:m["end"]])
            for m in mask if m["label"] in LABELS and m["end"] > m["start"]]
    return {"id": cid, "users": [text], "gold": gold}


def load(per, seed=0):
    """{language: [conversation]}, ``per`` messages of each language drawn at random."""
    cols = ["uid", "source_text", "privacy_mask", "language", "source_dataset"]
    d = pd.concat([pd.read_parquet(vb.DATA / f, columns=cols) for f in FILES if f.startswith("openpii15")])
    out = {}
    for lang in ("en", "de", "fr", "it", "ko"):
        part = d[(d.language == lang) & (d.source_dataset == ("asia-pacific" if lang == "ko" else "base"))]
        rows = list(zip(part.uid, part.source_text, part.privacy_mask))
        random.Random(seed).shuffle(rows)
        out[LANGUAGES[lang]] = [_conv(f"{lang}-{u}", t, m) for u, t, m in rows[:per]]
    r = pd.read_parquet(vb.DATA / "russian_pii.parquet", columns=["source_text", "privacy_mask"])
    rows = list(enumerate(zip(r.source_text, r.privacy_mask)))
    random.Random(seed).shuffle(rows)
    out[LANGUAGES["ru"]] = [_conv(f"ru-{i}", t, m) for i, (t, m) in rows[:per]]
    return {k: out[k] for k in ("English", "German", "French", "Italian", "Russian", "Korean")}


def systems():
    """Our name -> pii_trace.run's name."""
    large = languages.checkpoint(languages.MODELS["large"])
    return {"veil": "veil", "edge": "model", "edge+rules": "union", "large": f"tagger:{large}",
            "large+rules": f"union:{large}", "pii-tracer": "pii-tracer"}


ABOUT = {"veil": "veil's rules alone (FINANCE profile)",
         "edge": f"deerpark-PII-edge ({languages.MODELS['edge']}) alone at {pt.tagged.THRESHOLD}",
         "edge+rules": "veil + deerpark-PII-edge: everything either marks",
         "large": f"deerpark-PII-large ({languages.MODELS['large']}) alone at {pt.tagged.THRESHOLD}",
         "large+rules": "veil + deerpark-PII-large: everything either marks",
         "pii-tracer": "perplexity-ai/PII-Tracer (596M)"}


def run(names, per):
    data = load(per)
    convs = [c for cs in data.values() for c in cs]
    where = {c["id"]: lang for lang, cs in data.items() for c in cs}
    rep = {"per": per, "about": {n: ABOUT[n] for n in names}, "all labels": {}, "without dates and URLs": {}}
    run_as = systems()
    for name in names:
        pred, _ = pt.run(run_as[name], convs)
        for view, drop in (("all labels", set()), ("without dates and URLs", DROP)):
            for lang, cs in data.items():
                idx = [i for i, c in enumerate(convs) if where[c["id"]] == lang]
                gold = [{**convs[i], "gold": [g for g in convs[i]["gold"] if g[3] not in drop]} for i in idx]
                p = [[x for x in pred[i] if x[3] not in drop] for i in idx]
                r = pt.score(gold, p, False)
                rep[view].setdefault(lang, {"messages": len(cs), "gold": r["gold"], "systems": {}})["systems"][name] = {
                    "char": r["char"], "contained": r["contained"], "contained_by_label": r["contained_by_label"],
                    "consistent": r["consistent"].get("2+", {}), "other_hidden": r["other_hidden"]}
        a = rep["all labels"]
        print(f"{name:12} " + "  ".join(f"{lang} {a[lang]['systems'][name]['char']['f1']:.3f}" for lang in data), flush=True)
    return rep


def markdown(rep):
    names = list(rep["about"])
    out = []
    for view in ("all labels", "without dates and URLs"):
        langs = rep[view]
        out += [f"### Character F1, {view}", "", "| System | " + " | ".join(langs) + " |", "|---|" + "---|" * len(langs)]
        for n in names:
            out.append(f"| {n} | " + " | ".join(f"{langs[lang]['systems'][n]['char']['f1']:.3f}" for lang in langs) + " |")
        out += ["", f"Character precision / recall / details fully hidden / other words hidden, {view}:", "",
                "| Language | Gold spans | " + " | ".join(names) + " |", "|---|---|" + "---|" * len(names)]
        for lang, r in langs.items():
            out.append(f"| {lang} | {r['gold']} | " + " | ".join(
                f"{s['char']['p']:.3f} / {s['char']['r']:.3f} / {s['contained']:.1%} / {s['other_hidden']:.2%}"
                for s in (r["systems"][n] for n in names)) + " |")
        out.append("")
    langs = rep["without dates and URLs"]
    if any(r["systems"][names[0]]["consistent"].get("n") for r in langs.values()):   # few messages repeat a detail
        out += ["Details with 2+ mentions in a message, every mention fully hidden (without dates and URLs):", "",
                "| Language | n | " + " | ".join(names) + " |", "|---|---|" + "---|" * len(names)]
        for lang, r in langs.items():
            n = r["systems"][names[0]]["consistent"].get("n", 0)
            out.append(f"| {lang} | {n} | " + " | ".join(f"{r['systems'][x]['consistent'].get('share', 0):.1%}" for x in names) + " |")
        out.append("")
    out += [f"* {n}: {a}" for n, a in rep["about"].items()]
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["fetch", "score"], default="score")
    ap.add_argument("--systems", default=",".join(ABOUT))
    ap.add_argument("--per", type=int, default=200, help="messages a language")
    ap.add_argument("--out", default="languages_trace_report")
    a = ap.parse_args()
    fetch()
    if a.cmd == "fetch":
        return
    names = [x.strip() for x in a.systems.split(",") if x.strip()]
    for n in names:
        if n not in ABOUT:
            raise SystemExit(f"unknown system {n}: one of {', '.join(ABOUT)}")
    rep = run(names, a.per)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    json.dump(rep, open(out / "report.json", "w"), indent=1, ensure_ascii=False)
    (out / "report.md").write_text(markdown(rep), encoding="utf-8")
    print(f"wrote {out / 'report.json'} and {out / 'report.md'}")


if __name__ == "__main__":
    main()
