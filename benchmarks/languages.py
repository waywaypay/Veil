"""veil's rules, the deerpark-PII taggers and both together, language by language.  Results in benchmarks/languages.md.

    python benchmarks/languages.py fetch
    python benchmarks/languages.py [--systems veil,edge,edge+rules,large,large+rules] [--per 200] [--out languages_report/]

Three sets, each scored in every language it has:

* ai4privacy's open-pii-masking-500k, its validation split: short messages in eight languages (Hindi and Telugu among
  them), --per drawn from each at random;
* ai4privacy's pii-masking-400k, its validation split: short messages in six European languages, --per from each;
* Gretel's synthetic_pii_finance_multilingual, its test split: finance documents in seven languages, --docs of each.
  The edge tagger was trained on the six other languages of its training split, never on this one.

Labels are each dataset's own, mapped onto veil's kinds as tagger_sets.py and external.py map them; what veil doesn't
look for (a date, an age, a password) is "outside", neither scored nor counted against a system.  Scoring is
veilbench's: found is the share of labelled details every word of which is hidden, with a 95% interval from resampling
documents; other words hidden is the share of the unlabelled words a system hid.

Systems:
* veil: veil's rules alone (FINANCE profile);
* edge, large: a deerpark-PII checkpoint alone at veil's threshold (tagged.THRESHOLD);
* edge+rules, large+rules: veil and the checkpoint, every word either hides (veilbench's "union").

Words are runs of letters and digits (\\w+), so in Hindi and Telugu a word's vowel signs split it into pieces, each
scored as a word.

What a model marks in a text is cached under $VEIL_BENCH_DATA/cache (veilbench's cache), so a model reads a text once."""
import argparse
import json
import random
import re
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import tagger_sets  # noqa: E402
import veilbench as vb  # noqa: E402

from veil import tagged  # noqa: E402

HF = tagger_sets.HF
FILES = {"openpii_val.parquet": f"{HF}/ai4privacy/open-pii-masking-500k-ai4privacy/parquet/default/validation/0.parquet",
         "ai4p_val.parquet": f"{HF}/ai4privacy/pii-masking-400k/parquet/default/validation/0.parquet",
         "gretel_test.parquet": f"{HF}/gretelai/synthetic_pii_finance_multilingual/parquet/default/test/0.parquet"}
# a checkpoint: a Hugging Face repository, with a folder inside it after a second slash
MODELS = {"edge": tagged.MODEL, "large": "Deerpark/veil-control/out_large"}
LANGUAGES = {"en": "English", "de": "German", "fr": "French", "es": "Spanish", "it": "Italian", "nl": "Dutch",
             "hi": "Hindi", "te": "Telugu", "France": "French", "Swedish": "Swedish"}
EXTRA = {"PASSPORTNUM": "SSN / ID / license / tax"}   # open-pii's label for what external.py calls passport_number


def fetch():
    vb.DATA.mkdir(parents=True, exist_ok=True)
    for name, url in FILES.items():
        if not (vb.DATA / name).exists():
            print("fetching", name, file=sys.stderr, flush=True)
            urllib.request.urlretrieve(url, vb.DATA / name)


def checkpoint(spec):
    """A local directory or a repository name for "owner/repo" or "owner/repo/folder"."""
    parts = spec.split("/")
    if len(parts) <= 2 or Path(spec).exists():
        return spec
    from huggingface_hub import snapshot_download
    folder = "/".join(parts[2:])
    return str(Path(snapshot_download("/".join(parts[:2]), allow_patterns=[f"{folder}/*"])) / folder)


# -- the sets: name -> {language: [(text, [(start, end, group)])]} -------------------------------------------------

def _group(label):
    return EXTRA.get(label) or tagger_sets._group(label)


def ai4privacy(file, per, seed=0):
    d = pd.read_parquet(vb.DATA / file, columns=["source_text", "privacy_mask", "language"])
    out = {}
    for lang in sorted(d.language.unique(), key=lambda x: (x != "en", x)):
        rows = [(t, [(m["start"], m["end"], _group(m["label"])) for m in mask])
                for t, mask in zip(d.source_text[d.language == lang], d.privacy_mask[d.language == lang])]
        random.Random(seed).shuffle(rows)
        out[LANGUAGES.get(lang, lang)] = rows[:per]
    return out


def gretel(docs):
    d = pd.read_parquet(vb.DATA / "gretel_test.parquet", columns=["generated_text", "pii_spans", "language"])
    return {LANGUAGES.get(lang, lang): tagger_sets.gretel_rows(zip(g.generated_text.head(docs), g.pii_spans.head(docs)))
            for lang, g in sorted(d.groupby("language"), key=lambda x: (x[0] != "English", x[0]))}


def sets(per, docs):
    return {"ai4privacy open-pii-masking-500k": ai4privacy("openpii_val.parquet", per),
            "ai4privacy pii-masking-400k": ai4privacy("ai4p_val.parquet", per),
            "Gretel finance (multilingual)": gretel(docs)}


# -- systems ----------------------------------------------------------------------------------------------------------

def _key(model):
    """veilbench's cache name for a checkpoint: its own "model" for the published tagger, so the caches are shared."""
    if model == vb.TAGGER:
        return "model"
    key = "tagger-" + re.sub(r"\W+", "_", model)
    vb.SYSTEMS.setdefault(key, (lambda: vb.Tagger(checkpoint(model)), model, tagged.THRESHOLD))
    return key


def hidden(spec, texts):
    """Each text with what system ``spec`` hides replaced, as veilbench.outputs does."""
    model, rules = spec.partition("+")[0], spec.endswith("+rules")
    found = {} if model == "veil" else vb.system_spans(_key(MODELS[model]), texts)
    ruled = vb.system_spans("veil", texts) if rules or model == "veil" else {}
    out = []
    for t in texts:
        k = vb._key(t)
        spans = [x for x in vb._named(t, found.get(k, [])) if x[3] >= tagged.THRESHOLD] + ruled.get(k, [])
        joined = []
        for s, e, *_ in sorted(spans):
            if joined and s <= joined[-1][1]:
                joined[-1][1] = max(joined[-1][1], e)
            else:
                joined.append([s, e])
        o = t
        for s, e in reversed(joined):
            o = o[:s] + "X_X" + o[e:]
        out.append(o)
    return out


ABOUT = {"veil": "veil's rules alone (FINANCE profile)",
         "edge": f"deerpark-PII-edge ({MODELS['edge']}) alone at {tagged.THRESHOLD}",
         "large": f"deerpark-PII-large ({MODELS['large']}) alone at {tagged.THRESHOLD}",
         "edge+rules": "veil + deerpark-PII-edge: every word either hides",
         "large+rules": "veil + deerpark-PII-large: every word either hides"}


# -- scoring and the report -----------------------------------------------------------------------------------------

def run(systems, per, docs):
    data = sets(per, docs)
    texts = list(dict.fromkeys(t for langs in data.values() for rows in langs.values() for t, _ in rows))
    print(f"{len(texts)} texts", file=sys.stderr, flush=True)
    outs = {spec: dict(zip(texts, hidden(spec, texts))) for spec in systems}
    report = {"per": per, "docs": docs, "threshold": tagged.THRESHOLD, "about": {s: ABOUT[s] for s in systems}, "sets": {}}
    for name, langs in data.items():
        report["sets"][name] = {}
        for lang, rows in langs.items():
            docs_ = [{"text": t, "spans": sp} for t, sp in rows]
            r = report["sets"][name][lang] = {"documents": len(rows), "systems": {}}
            for spec in systems:
                per_doc = [vb.score_doc(t, sp, outs[spec][t]) for t, sp in rows]
                s = vb.summarise(docs_, per_doc)
                kinds = sorted({g for p in per_doc for g in p[1]})
                s["by_kind"] = {g: [sum(p[0].get(g, 0) for p in per_doc), sum(p[1].get(g, 0) for p in per_doc)] for g in kinds}
                s["misses"] = [{"kind": g, "detail": t[a:b], "visible": vis}
                               for (t, _), p in zip(rows, per_doc) for a, b, g, vis in p[4]][:50]
                r["systems"][spec] = s
            print(f"{name:34} {lang:9} " + "  ".join(f"{spec} {r['systems'][spec]['found']:.1%}/{r['systems'][spec]['other_hidden']:.2%}"
                                                     for spec in systems), flush=True)
    return report


def markdown(rep):
    systems = list(rep["about"])
    out = []
    for name, langs in rep["sets"].items():
        n = next(iter(langs.values()))["documents"]
        out += [f"### {name}", "", f"{n} documents a language. Found / other words hidden:", "",
                "| Language | Details | " + " | ".join(systems) + " |", "|---|---|" + "---|" * len(systems)]
        for lang, r in langs.items():
            s = r["systems"]
            out.append(f"| {lang} | {s[systems[0]]['details']} | " +
                       " | ".join(f"{s[x]['found']:.1%} / {s[x]['other_hidden']:.2%}" for x in systems) + " |")
        kinds = sorted({g for r in langs.values() for s in r["systems"].values() for g in s["by_kind"]})
        for spec in [x for x in systems if x.endswith("+rules")] or systems[-1:]:
            out += ["", f"{spec}, found by kind of detail (details in brackets):", "",
                    "| Kind | " + " | ".join(langs) + " |", "|---|" + "---|" * len(langs)]
            for g in kinds:
                cells = []
                for r in langs.values():
                    h, t = r["systems"][spec]["by_kind"].get(g, [0, 0])
                    cells.append(f"{h / t:.0%} ({t})" if t else "–")
                out.append(f"| {g} | " + " | ".join(cells) + " |")
        out.append("")
    out += [f"* {s}: {a}" for s, a in rep["about"].items()]
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", choices=["fetch", "score"], default="score")
    ap.add_argument("--systems", default="veil,edge,edge+rules,large,large+rules")
    ap.add_argument("--per", type=int, default=200, help="ai4privacy messages a language")
    ap.add_argument("--docs", type=int, default=60, help="Gretel documents a language")
    ap.add_argument("--out", default="languages_report")
    a = ap.parse_args()
    fetch()
    if a.cmd == "fetch":
        return
    systems = [x.strip() for x in a.systems.split(",") if x.strip()]
    for s in systems:
        if s not in ABOUT:
            raise SystemExit(f"unknown system {s}: one of {', '.join(ABOUT)}")
    rep = run(systems, a.per, a.docs)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    json.dump(rep, open(out / "report.json", "w"), indent=1, ensure_ascii=False)
    (out / "report.md").write_text(markdown(rep), encoding="utf-8")
    print(f"wrote {out / 'report.json'} and {out / 'report.md'}")


if __name__ == "__main__":
    main()
