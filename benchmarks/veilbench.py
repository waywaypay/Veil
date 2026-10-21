"""Benchmark veil, its span tagger and other PII tools on labelled documents.

    python benchmarks/veilbench.py systems
    python benchmarks/veilbench.py score DATA [DATA ...] --systems union,model,veil,presidio --out report/
    python benchmarks/veilbench.py redact FILE [FILE ...] --system union --out redacted.html

DATA is a JSONL file of {"text": ..., "spans": [[start, end, type], ...], "group": "..."} (group optional), or of
agents' documents written with inline ⟦label|text⟧ markup ({"text": ..., "type": ...}, as in judged/docgen).  A span's
type is the kind of private detail (name, address, SSN, ...); "ordinary" marks words that must stay visible and
"outside" words scored neither way.

Each system is scored the same way.  Found: a labelled detail counts when every word of it is hidden (a title such as
"Mr" may stay).  Other words hidden: of the words no label covers, the share a system hid.  Found has a 95% interval
from resampling documents.  A tool is scored on what it hides, whatever type it gives a span.

What each system reads is cached under $VEIL_BENCH_DATA/cache, so a model reads a text once."""
import argparse
import html
import json
import os
import random
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gretel as bench  # noqa: E402

from veil import FINANCE, Redactor, tagged  # noqa: E402

DATA = Path(os.environ.get("VEIL_BENCH_DATA", Path(__file__).resolve().parent / "data"))
CACHE = DATA / "cache"
TAGGER = os.environ.get("VEIL_TAGGER", tagged.MODEL)
BATCH = int(os.environ.get("VEIL_BENCH_BATCH", 8))      # passages per forward pass; lower it for the 600M+ models on a small machine
GROUP = int(os.environ.get("VEIL_BENCH_GROUP", 50))     # documents per cache write

MARK = re.compile(r"⟦([^|⟦⟧]+)\|([^⟦⟧]*)⟧")
# label in the documents' markup -> the type of detail it is scored as
TYPE = {"name": "name", "street address": "address", "email address": "email", "phone number": "phone", "ssn": "SSN",
        "tax id": "tax / national ID", "passport number": "passport", "driver license number": "driver licence",
        "credit card number": "credit card", "account number": "account number", "iban": "IBAN", "swift code": "SWIFT",
        "date of birth": "date of birth", "customer id": "customer ID", "employee id": "employee ID", "username": "username"}

# -- reading data ----------------------------------------------------------------------------------------------------


def unmark(t):
    """The text of a document and its spans, from inline ⟦label|text⟧ markup."""
    out, spans, pos, n = [], [], 0, 0
    for m in MARK.finditer(t):
        out.append(t[pos:m.start()])
        n += m.start() - pos
        lab, txt = m.group(1).strip(), m.group(2)
        if txt.strip():
            lead = len(txt) - len(txt.lstrip())
            spans.append((n + lead, n + len(txt.rstrip()), TYPE.get(lab, lab)))
        out.append(txt)
        n += len(txt)
        pos = m.end()
    out.append(t[pos:])
    return "".join(out), spans


def read(paths):
    """[{"text", "spans", "group"}] from JSONL files of either form."""
    docs = []
    for p in paths:
        for line in open(p, encoding="utf-8"):
            if not line.strip():
                continue
            r = json.loads(line)
            if "spans" in r:
                docs.append({"text": r["text"], "spans": [tuple(s) for s in r["spans"]], "group": r.get("group", Path(p).stem)})
            else:
                text, spans = unmark(r["text"])
                docs.append({"text": text, "spans": spans, "group": r.get("type", Path(p).stem)})
    return docs


# -- systems: each gives [(start, end, label, score)] for a text -----------------------------------------------------
# A system's spans are cached at a low threshold; "@th" after its name scores it at another one.

def _not_private(label):
    """Labels the tools emit for things this benchmark's rule does not treat as a private person's detail."""
    return bool(re.search(r"^(B-|I-)?(ORG|ORGANI[SZ]ATION|COMPANY|MISC|DATE(TIME|_TIME)?|TIME|AGE|JOB|JOBTITLE|JOB_TITLE|"
                          r"CURRENCY|AMOUNT|MONEY|GENDER|SEX|NRP|TITLE|PREFIX|URL|PERCENT|CARDINAL|ORDINAL|QUANTITY|"
                          r"PRODUCT|EVENT|WORK_OF_ART|LAW|LANGUAGE|NORP|GPE|COUNTRY|STATE|CITY_NAME_GENERIC)$", label, re.I))


class Tagger:
    """veil's tagger alone (system "model") or with veil (system "union")."""
    def __init__(self, model=TAGGER):
        self.r = tagged.TaggedRedactor(model=model)

    def spans(self, texts):
        return self.r.model_spans(texts, 0.3)


class Gliner:
    def __init__(self, model, labels=None, nemo=False):
        from gliner import GLiNER
        self.m = GLiNER.from_pretrained(model)
        self.m.eval()
        self.labels = labels or (["first_name", "last_name", "street_address", "city", "postcode", "email", "phone_number",
                                  "fax_number", "ssn", "account_number", "credit_debit_card", "bank_routing_number",
                                  "swift_bic", "date_of_birth", "customer_id", "employee_id", "user_name", "national_id",
                                  "tax_id", "passport_number", "certificate_license_number"] if nemo else list(tagged.LABELS))

    def spans(self, texts):
        import torch
        pieces = [(i, off, p) for i, t in enumerate(texts) for off, p in tagged.chunks(t)]
        found = [[] for _ in texts]
        with torch.inference_mode():
            for b in range(0, len(pieces), BATCH):
                batch = pieces[b:b + BATCH]
                for (i, off, _), es in zip(batch, self.m.batch_predict_entities([p for _, _, p in batch], self.labels, threshold=0.3)):
                    found[i] += [(off + e["start"], off + e["end"], e["label"], round(e["score"], 3)) for e in es]
        return found


class TokenClassifier:
    """A Hugging Face token-classification model, its own label set, private-looking labels kept."""
    def __init__(self, model):
        from transformers import pipeline
        self.p = pipeline("token-classification", model=model, aggregation_strategy="simple", device=-1)

    def spans(self, texts):
        found = [[] for _ in texts]
        pieces = [(i, off, p) for i, t in enumerate(texts) for off, p in tagged.chunks(t, 120)]
        for b in range(0, len(pieces), 2 * BATCH):
            batch = pieces[b:b + 2 * BATCH]
            for (i, off, _), es in zip(batch, self.p([p for _, _, p in batch])):
                for e in es:
                    lab = e.get("entity_group") or e.get("entity", "")
                    if lab and lab not in ("O", "o") and not _not_private(lab):
                        found[i].append((off + e["start"], off + e["end"], lab, round(float(e["score"]), 3)))
        return found


class Presidio:
    """Microsoft Presidio's analyzer with its default recognizers and spaCy en_core_web_lg."""
    def __init__(self):
        from presidio_analyzer import AnalyzerEngine
        self.a = AnalyzerEngine()

    def spans(self, texts):
        out = []
        for t in texts:
            rs = self.a.analyze(text=t, language="en")
            out.append([(r.start, r.end, r.entity_type, round(r.score, 3)) for r in rs if not _not_private(r.entity_type)])
        return out


class Scrubadub:
    """scrubadub's default detectors (emails, phones, URLs, credentials, ...)."""
    def spans(self, texts):
        import scrubadub
        s = scrubadub.Scrubber()
        out = []
        for t in texts:
            out.append([(f.beg, f.end, f.type, 1.0) for f in s.iter_filth(t) if not _not_private(f.type)])
        return out


class Spacy:
    """spaCy's en_core_web_lg named entities: people and facilities."""
    def __init__(self):
        import spacy
        self.nlp = spacy.load("en_core_web_lg")

    def spans(self, texts):
        return [[(e.start_char, e.end_char, e.label_, 1.0) for e in self.nlp(t).ents if e.label_ in ("PERSON", "FAC")]
                for t in texts]


class Veil:
    def spans(self, texts):
        return [[(s, e, "VEIL", 1.0) for s, e in tagged.veil_hidden(t, Redactor(FINANCE).redact_text(t))] for t in texts]


SYSTEMS = {
    "veil": (Veil, "veil's rules alone (FINANCE profile)", 1.0),
    "model": (Tagger, f"veil's tagger alone ({TAGGER})", tagged.THRESHOLD),
    "union": (None, "veil + its tagger: every word either hides", tagged.THRESHOLD),
    "presidio": (Presidio, "Microsoft Presidio, default recognizers, spaCy en_core_web_lg", 0.0),
    "scrubadub": (Scrubadub, "scrubadub, default detectors", 0.0),
    "spacy": (Spacy, "spaCy en_core_web_lg, PERSON and FAC entities", 0.0),
    "gliner-pii-edge": (lambda: Gliner("knowledgator/gliner-pii-edge-v1.0"), "knowledgator/gliner-pii-edge-v1.0 (the tagger's base)", 0.5),
    "gliner-pii-base": (lambda: Gliner("knowledgator/gliner-pii-base-v1.0"), "knowledgator/gliner-pii-base-v1.0", 0.5),
    "gliner-pii-large": (lambda: Gliner("knowledgator/gliner-pii-large-v1.0"), "knowledgator/gliner-pii-large-v1.0", 0.5),
    "gliner-multi-pii": (lambda: Gliner("urchade/gliner_multi_pii-v1"), "urchade/gliner_multi_pii-v1", 0.5),
    "nvidia-gliner-pii": (lambda: Gliner("nvidia/gliner-PII", nemo=True), "nvidia/gliner-PII", 0.5),
    "piiranha": (lambda: TokenClassifier("iiiorg/piiranha-v1-detect-personal-information"), "iiiorg/piiranha-v1 (non-commercial licence)", 0.0),
    "ai4privacy-openpii": (lambda: TokenClassifier("ai4privacy/llama-ai4privacy-english-anonymiser-openpii"), "ai4privacy/llama-ai4privacy-english-anonymiser-openpii", 0.0),
    "deberta-ai4privacy": (lambda: TokenClassifier("Isotonic/deberta-v3-base_finetuned_ai4privacy_v2"), "Isotonic/deberta-v3-base_finetuned_ai4privacy_v2 (non-commercial)", 0.0),
    "deberta-pii": (lambda: TokenClassifier("lakshyakh93/deberta_finetuned_pii"), "lakshyakh93/deberta_finetuned_pii", 0.0),
    "bert-small-pii": (lambda: TokenClassifier("gravitee-io/bert-small-pii-detection"), "gravitee-io/bert-small-pii-detection", 0.0),
    "stanford-deid": (lambda: TokenClassifier("StanfordAIMI/stanford-deidentifier-base"), "StanfordAIMI/stanford-deidentifier-base (clinical)", 0.0),
    "bert-ner": (lambda: TokenClassifier("dslim/bert-base-NER"), "dslim/bert-base-NER (general NER: people, places)", 0.0),
}


def _key(text):
    import hashlib
    return hashlib.sha1(text.encode()).hexdigest()


def system_spans(name, texts):
    """{key(text): [(start, end, label, score)]} for a system, from the cache or by running it on what is missing."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / f"bench_{name}.jsonl"
    have = {}
    if path.exists():
        for line in open(path):
            r = json.loads(line)
            have[r["k"]] = [tuple(x) for x in r["s"]]
    todo = list(dict.fromkeys(t for t in texts if _key(t) not in have))
    if todo:
        make = SYSTEMS[name][0]
        sysobj = make()
        t0 = time.perf_counter()
        for g in range(0, len(todo), GROUP):
            group = todo[g:g + GROUP]
            res = sysobj.spans(group)
            with open(path, "a") as f:
                for t, s in zip(group, res):
                    have[_key(t)] = sorted(tuple(x) for x in s)
                    f.write(json.dumps({"k": _key(t), "s": have[_key(t)]}) + "\n")
            print(f"  {name}: {g + len(group)} of {len(todo)} texts in {time.perf_counter() - t0:.0f} s", file=sys.stderr, flush=True)
    return have


def outputs(spec, texts):
    """Each text with what system ``spec`` ("name" or "name@threshold") hides replaced."""
    name, _, th = spec.partition("@")
    th = float(th) if th else SYSTEMS[name][2]
    if name == "union":
        m, v = system_spans("model", texts), system_spans("veil", texts)
        get = lambda t: [x for x in m[_key(t)] if x[3] >= th] + v[_key(t)]   # noqa: E731
    else:
        sp = system_spans(name, texts)
        get = lambda t: [x for x in sp[_key(t)] if x[3] >= th]   # noqa: E731
    out = []
    for t in texts:
        rs = sorted((s, e) for s, e, *_ in get(t))
        joined = []
        for s, e in rs:
            if joined and s <= joined[-1][1]:
                joined[-1][1] = max(joined[-1][1], e)
            else:
                joined.append([s, e])
        o = t
        for s, e in reversed(joined):
            o = o[:s] + "X_X" + o[e:]
        out.append(o)
    return out


# -- scoring -----------------------------------------------------------------------------------------------------------

def score_doc(text, spans, out):
    """(hits by type, details by type, other words hidden, other words, misses) for one document."""
    ws = bench.words(text)
    _, kept = bench.redacted_mask(text, out)
    hit, tot, personal, misses = defaultdict(int), defaultdict(int), [False] * len(ws), []
    for s, e, g in spans:
        idx = [j for j, (_, a, b) in enumerate(ws) if a < e and b > s]
        if g != "ordinary":
            for j in idx:
                personal[j] = True
        idx = [j for j in idx if ws[j][0].lower() not in bench.TITLES]
        if idx and g not in ("ordinary", "outside"):
            tot[g] += 1
            ok = all(not kept[j] for j in idx)
            hit[g] += ok
            if not ok:
                misses.append((s, e, g, [ws[j][0] for j in idx if kept[j]]))
    fp = fp_tot = 0
    for j, (w, _, _) in enumerate(ws):
        if not personal[j] and w.lower() not in bench.TITLES:
            fp_tot += 1
            fp += not kept[j]
    return hit, tot, fp, fp_tot, misses


def summarise(docs, per, idx=None, boot=2000):
    idx = list(range(len(docs))) if idx is None else idx
    H = sum(sum(per[i][0].values()) for i in idx)
    N = sum(sum(per[i][1].values()) for i in idx)
    fp = sum(per[i][2] for i in idx)
    fpt = sum(per[i][3] for i in idx)
    rng = random.Random(7)
    vals = []
    for _ in range(boot if N else 0):
        s = [rng.choice(idx) for _ in idx]
        n = sum(sum(per[i][1].values()) for i in s)
        vals.append(sum(sum(per[i][0].values()) for i in s) / max(1, n))
    vals.sort()
    lo, hi = (vals[int(.025 * len(vals))], vals[int(.975 * len(vals)) - 1]) if vals else (0, 0)
    return {"found": H / max(1, N), "lo": lo, "hi": hi, "details": N, "other_hidden": fp / max(1, fpt), "other_words": fpt}


def score(paths, systems, outdir):
    docs = read(paths)
    texts = [d["text"] for d in docs]
    report = {"data": [str(p) for p in paths], "documents": len(docs), "systems": {}}
    for spec in systems:
        name = spec.partition("@")[0]
        outs = outputs(spec, texts)
        per = [score_doc(d["text"], d["spans"], o) for d, o in zip(docs, outs)]
        r = summarise(docs, per)
        r["about"] = SYSTEMS[name][1]
        types = sorted({g for p in per for g in p[1]})
        r["by_type"] = {g: [sum(p[0].get(g, 0) for p in per), sum(p[1].get(g, 0) for p in per)] for g in types}
        groups = sorted({d["group"] for d in docs})
        r["by_group"] = {g: summarise(docs, per, [i for i, d in enumerate(docs) if d["group"] == g], boot=0) for g in groups}
        r["misses"] = [{"group": docs[i]["group"], "type": g, "detail": docs[i]["text"][s:e], "visible": vis,
                        "context": docs[i]["text"][max(0, s - 80):e + 80]}
                       for i, p in enumerate(per) for s, e, g, vis in p[4]]
        report["systems"][spec] = r
        print(f"{spec:22} found {r['found']:.1%} [{r['lo']:.1%}, {r['hi']:.1%}] of {r['details']}   "
              f"other words hidden {r['other_hidden']:.2%}", flush=True)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    json.dump(report, open(outdir / "report.json", "w"), indent=1, ensure_ascii=False)
    (outdir / "report.md").write_text(markdown(report), encoding="utf-8")
    print(f"wrote {outdir / 'report.json'} and {outdir / 'report.md'}")


def markdown(report):
    rows = sorted(report["systems"].items(), key=lambda kv: -kv[1]["found"])
    out = [f"{report['documents']} documents from {', '.join(report['data'])}.", "",
           "| System | Found | 95% interval | Other words hidden | |", "|---|---|---|---|---|"]
    for spec, r in rows:
        out.append(f"| {spec} | {r['found']:.1%} | {r['lo']:.1%}–{r['hi']:.1%} | {r['other_hidden']:.2%} | {r['about']} |")
    types = sorted({g for _, r in rows for g in r["by_type"]}, key=lambda g: -max(r["by_type"].get(g, [0, 0])[1] for _, r in rows))
    out += ["", "Found by type of detail:", "", "| Type | Details | " + " | ".join(s for s, _ in rows) + " |",
            "|---|---|" + "---|" * len(rows)]
    for g in types:
        n = max(r["by_type"].get(g, [0, 0])[1] for _, r in rows)
        out.append(f"| {g} | {n} | " + " | ".join(f"{r['by_type'][g][0] / max(1, r['by_type'][g][1]):.1%}" if g in r["by_type"] else "–"
                                                  for _, r in rows) + " |")
    return "\n".join(out) + "\n"


# -- redacting files for a look ---------------------------------------------------------------------------------------

def redact(files, system, out):
    from veil.files import read_text
    r = tagged.TaggedRedactor(model=TAGGER, system=system)
    parts = []
    for f in files:
        data = Path(f).read_bytes()
        kind = {".pdf": "application/pdf", ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}.get(
            Path(f).suffix.lower(), "text/plain")
        text = read_text(data, kind) if kind != "text/plain" else data.decode("utf-8", "replace")
        spans = r.find(text)
        h, pos = [], 0
        for s in spans:
            h.append(html.escape(text[pos:s.start]))
            h.append(f'<mark class="{s.source}" title="{s.kind}">{html.escape(text[s.start:s.end])}</mark>')
            pos = s.end
        h.append(html.escape(text[pos:]))
        parts.append(f"<h2>{html.escape(str(f))}</h2><p>{len(spans)} spans hidden</p><pre>{''.join(h)}</pre>")
    page = ("<!doctype html><meta charset=utf-8><title>veil redaction</title><style>body{font:14px system-ui;margin:2em}"
            "pre{white-space:pre-wrap;background:#f6f6f4;padding:1em}mark.model{background:#ffd9a8}mark.veil{background:#bfe3ff}"
            "</style><p><mark class=model>hidden by the tagger</mark> <mark class=veil>hidden by veil only</mark></p>" + "".join(parts))
    Path(out).write_text(page, encoding="utf-8")
    print("wrote", out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("systems")
    s = sub.add_parser("score")
    s.add_argument("data", nargs="+")
    s.add_argument("--systems", default="union,model,veil")
    s.add_argument("--out", default="veilbench_report")
    r = sub.add_parser("redact")
    r.add_argument("files", nargs="+")
    r.add_argument("--system", default="union", choices=["union", "model", "veil"])
    r.add_argument("--out", default="redacted.html")
    a = ap.parse_args()
    if a.cmd == "systems":
        for k, (_, about, th) in SYSTEMS.items():
            print(f"{k:22} threshold {th:<5} {about}")
    elif a.cmd == "score":
        score(a.data, [x.strip() for x in a.systems.split(",") if x.strip()], a.out)
    else:
        redact(a.files, a.system, a.out)


if __name__ == "__main__":
    main()
