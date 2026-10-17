"""veil, a span tagger alone, and veil with what the tagger marks, on 20 test sets: veil's held-out Gretel finance
documents; NVIDIA's Nemotron-PII under nine conditions (case, markup, a chat, scans); Gretel's pii-masking-en-v1;
ai4privacy's short messages in English and five other languages; and text people wrote: court judgments (TAB),
news (CoNLL-2003) and OntoNotes (news, broadcast, phone calls, the web).  Results in benchmarks/model.md.

python tagger_sets.py fetch                        the test sets, to $VEIL_BENCH_DATA (benchmarks/data)
python tagger_sets.py <model>[@threshold] ...      e.g. knowledgator/gliner-pii-edge-v1.0@0.4 data/mixed::model_f16.onnx

Labels are each dataset's own, mapped onto veil's kinds as external.py does; TAB's are its people's names, CoNLL's and
OntoNotes' their person names (every other entity is ordinary).  The scanned conditions need Tesseract."""

import json
import os
import random
import sys
import urllib.request
from multiprocessing import Pool

import conditions
import external
import gretel as bench
import pandas as pd
import tagger as T

from veil import FINANCE, Redactor

HF = "https://huggingface.co/api/datasets"
FILES = {"gretel_test.parquet": f"{HF}/gretelai/synthetic_pii_finance_multilingual/parquet/default/test/0.parquet",
         "nemo_test.parquet": f"{HF}/nvidia/Nemotron-PII/parquet/default/test/0.parquet",
         "gretel_en_test.parquet": f"{HF}/gretelai/gretel-pii-masking-en-v1/parquet/default/test/0.parquet",
         "ai4p_val.parquet": f"{HF}/ai4privacy/pii-masking-400k/parquet/default/validation/0.parquet",
         "tab_test.parquet": f"{HF}/ildpil/text-anonymization-benchmark/parquet/default/test/0.parquet",
         "conll_test.parquet": f"{HF}/tner/conll2003/parquet/conll2003/test/0.parquet",
         "onto_test.parquet": f"{HF}/tner/ontonotes5/parquet/ontonotes5/test/0.parquet"}


def fetch(files=FILES):
    T.DATA.mkdir(parents=True, exist_ok=True)
    for name, url in files.items():
        if not (T.DATA / name).exists():
            print("fetching", name, file=sys.stderr, flush=True)
            urllib.request.urlretrieve(url, T.DATA / name)


def _group(label):
    return "ordinary" if label in external.ORDINARY else external.LABEL.get(label, "outside")


def from_external(kind, n, seed=0, language="en"):
    if kind == "ai4p":
        d = pd.read_parquet(T.DATA / "ai4p_val.parquet")
        d = d[d.language == language]
        rows = [(t, [{"start": m["start"], "end": m["end"], "label": m["label"]} for m in mask])
                for t, mask in zip(d.source_text, d.privacy_mask)]
        random.Random(seed).shuffle(rows)
        rows = rows[:n]
    else:
        rows = external.load(kind, T.DATA / "gretel_en_test.parquet", n, seed)
    return [(t, [(s["start"], s["end"], _group(s["label"])) for s in spans]) for t, spans in rows]


def gretel_rows(raw):
    """(text, pii_spans as JSON) -> rows, with the benchmark's noise spans neither scored nor counted against."""
    out = []
    for t, js in raw:
        spans = []
        for s in json.loads(js):
            lab = s["label"]
            if lab in bench.LABEL_GROUP:
                noise = bench.is_noise(t[s["start"]:s["end"]], lab, t[s["end"]:s["end"] + 60])
                spans.append((s["start"], s["end"], "outside" if noise else bench.LABEL_GROUP[lab]))
            else:
                spans.append((s["start"], s["end"], "ordinary" if lab in bench.LABEL_KEEP else "outside"))
        out.append((t, spans))
    return out


def gretel_finance(n=300):
    d = pd.read_parquet(T.DATA / "gretel_test.parquet")
    d = d[d.language == "English"].head(n)
    return gretel_rows(zip(d.generated_text, d.pii_spans))


def tab(n=60):
    """TAB's court judgments, one annotation of each: people's names that must be masked are scored, other masked
    entities are personal but not veil's kinds, and what needn't be masked is ordinary (but a person's name)."""
    d = pd.read_parquet(T.DATA / "tab_test.parquet").drop_duplicates("doc_id").head(n)
    out = []
    for t, mentions in zip(d.text, d.entity_mentions):
        spans = []
        for m in mentions:
            masked = m["identifier_type"] in ("DIRECT", "QUASI")
            g = "name" if m["entity_type"] == "PERSON" and masked else \
                "outside" if masked or m["entity_type"] == "PERSON" else "ordinary"
            spans.append((m["start_offset"], m["end_offset"], g))
        out.append((t, spans))
    return out


def tagged(name, person_tags, n_docs, per_doc=8):
    """Tokenized sentences, ``per_doc`` to a document: the person tags (B-, I-) are names, other entities ordinary."""
    begin = min(person_tags)
    d = pd.read_parquet(T.DATA / name)
    out = []
    sents = list(zip(d.tokens, d.tags))[:n_docs * per_doc]
    for k in range(0, len(sents), per_doc):
        text, spans = "", []
        for tokens, tags in sents[k:k + per_doc]:
            cur = None
            for tok, tag in zip(tokens, tags):
                if text and not text.endswith("\n"):
                    text += " "
                start = len(text)
                text += tok
                g = "name" if tag in person_tags else None if tag == 0 else "ordinary"
                if g and cur and cur[2] == g and tag != begin:
                    cur[1] = len(text)
                elif g:
                    cur = [start, len(text), g]
                    spans.append(cur)
                else:
                    cur = None
            text += "\n"
        out.append((text, [tuple(s) for s in spans]))
    return out


def ocr_texts(rows, names):
    """veil.files' readings of each document set on a page, scanned, photographed or faxed (conditions.py)."""
    path = T.CACHE / "ocr.json"
    have = json.load(open(path)) if path.exists() else {}
    todo = [(i, t, set(names)) for i, (t, _) in enumerate(rows) if str(i) not in have]
    if todo:
        T.CACHE.mkdir(parents=True, exist_ok=True)
        with Pool(4, initializer=os.environ.__setitem__, initargs=("OMP_THREAD_LIMIT", "1")) as pool:
            for i, got in pool.imap_unordered(conditions.work, todo):
                have[str(i)] = got
        json.dump(have, open(path, "w"))
    return {name: [have[str(i)][name] for i in range(len(rows))] for name in names}


def sets():
    """name -> (rows, what each tool is given, typed)"""
    out = {}
    nemo = [(t, [(s["start"], s["end"], _group(s["label"])) for s in spans])
            for t, spans in [r for r in external.load("nemo", T.DATA / "nemo_test.parquet", 2000, 7)
                             if len(r[0]) < 2500][:100]]
    texts = [t for t, _ in nemo]
    rows = gretel_finance()
    out["Gretel finance (veil's held-out)"] = (rows, [t for t, _ in rows], False)
    out["Nemotron: plain"] = (nemo, texts, False)
    out["Nemotron: lower case"] = (nemo, [t.lower() for t in texts], False)
    out["Nemotron: typed in a chat"] = (nemo, [t.lower() for t in texts], True)
    out["Nemotron: UPPER CASE"] = (nemo, [t.upper() for t in texts], False)
    out["Nemotron: HTML"] = (nemo, [conditions.html_of(t) for t in texts], False)
    out["Nemotron: inside JSON"] = (nemo, [json.dumps({"id": i, "note": t}) for i, t in enumerate(texts)], False)
    for name, given in ocr_texts(nemo, ["scanned PDF", "phone photo", "fax"]).items():
        out[f"Nemotron: {name}"] = (nemo, given, False)
    rows = from_external("gretel_en", 500)
    out["Gretel en-v1"] = (rows, [t for t, _ in rows], False)
    rows = from_external("ai4p", 500)
    out["ai4privacy: English"] = (rows, [t for t, _ in rows], False)
    for lang, name in [("de", "German"), ("fr", "French"), ("es", "Spanish"), ("it", "Italian"), ("nl", "Dutch")]:
        rows = from_external("ai4p", 200, language=lang)
        out[f"ai4privacy: {name}"] = (rows, [t for t, _ in rows], False)
    rows = tab()
    out["TAB court judgments (real)"] = (rows, [t for t, _ in rows], False)
    rows = tagged("conll_test.parquet", {3, 4}, 125)
    out["CoNLL-2003 news (real)"] = (rows, [t for t, _ in rows], False)
    rows = tagged("onto_test.parquet", {4, 5}, 150)
    out["OntoNotes (real)"] = (rows, [t for t, _ in rows], False)
    return out


def main(models):
    data = sets()
    inputs = [x for _, xs, _ in data.values() for x in xs]
    results = {"veil": {name: T.score(rows, xs, [Redactor(FINANCE).redact_text(x, typed) for x in xs])
                        for name, (rows, xs, typed) in data.items()}}
    for spec in models:
        model, _, th = spec.partition("@")
        th = float(th or T.THRESHOLD)
        found = T.spans(model, inputs)
        r = {}
        for name, (rows, xs, typed) in data.items():
            r[name] = {"alone": T.score(rows, xs, [T.alone(x, found[T.key(x)], th) for x in xs])}
            for gate in ("names only", "checked", "strict"):
                r[name][f"veil + {gate}"] = T.score(rows, xs, [T.with_veil(x, found[T.key(x)], T.GATES[gate], th, typed)
                                                              for x in xs])
        results[spec] = r
    json.dump(results, open(T.DATA / "tagger_sets.json", "w"), indent=1)
    cols = [("veil", None)] + [(m, v) for m in models for v in ("alone", "veil + names only")]
    for name in data:
        cells = [results["veil"][name] if v is None else results[m][name][v] for m, v in cols]
        print(f"{name:34}" + "".join(f"  {c['found']:6.1%} / {c['over']:5.2%}" for c in cells))
    print("columns: veil, then for each model: alone, veil + its names (found / other words hidden)")


if __name__ == "__main__":
    fetch() if sys.argv[1:] == ["fetch"] else main(sys.argv[1:])
