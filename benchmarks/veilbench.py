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
FLOOR = float(os.environ.get("VEIL_BENCH_FLOOR", 0.1))   # lowest score the GLiNER models keep, so each can be scored over a range of thresholds

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
                for (i, off, _), es in zip(batch, self.m.batch_predict_entities([p for _, _, p in batch], self.labels, threshold=FLOOR)):
                    found[i] += [(off + e["start"], off + e["end"], e["label"], round(e["score"], 3)) for e in es]
        return found


class Gliner2:
    """Fastino's GLiNER2 and GLiNER2.5 models (pip install gliner2): the same label list, spans with a confidence.
    AutoExtractor loads either kind (GLiNER2.5's boundary models need it); older gliner2 releases have only GLiNER2."""
    def __init__(self, model):
        try:
            from gliner2 import AutoExtractor as load
        except ImportError:
            from gliner2 import GLiNER2 as load
        self.m = load.from_pretrained(model)
        self.labels = list(tagged.LABELS)

    def spans(self, texts):
        out = []
        for t in texts:
            found = []
            for off, p in tagged.chunks(t):
                r = self.m.extract_entities(p, self.labels, threshold=FLOOR, include_spans=True, include_confidence=True)["entities"]
                for label, items in r.items():
                    found += [(off + e["start"], off + e["end"], label, round(e["confidence"], 3)) for e in items]
            out.append(found)
        return out


class PiiTracer:
    """Perplexity's PII-Tracer: a bidirectional Qwen3 encoder whose own predict() decodes BIOES tags into spans with a
    score (transformers>=5.2, trust_remote_code).  It reads up to 4,096 tokens, so it is given long passages; a threshold
    only drops spans from its one decoded path, so every span is kept and the sweep starts at 0."""
    def __init__(self, model="perplexity-ai/PII-Tracer", revision="d25c16f2e57e321f6d2527715c01df9112f956f5"):
        import torch
        from transformers import AutoModel
        torch.set_grad_enabled(False)
        self.m = AutoModel.from_pretrained(model, revision=revision, trust_remote_code=True).eval()   # the code read, pinned

    def spans(self, texts):
        out = []
        for t in texts:
            found = []
            for off, p in tagged.chunks(t, 1500):
                sp, _ = self.m.predict(p)
                found += [(off + s.start, off + s.end, s.label, round(s.score, 3)) for s in sp]
            out.append(found)
        return out


class TokenClassifier:
    """A Hugging Face token-classification model, its own label set, private-looking labels kept."""
    def __init__(self, model):
        from transformers import pipeline
        self.p = pipeline("token-classification", model=model, aggregation_strategy="simple", device=-1)

    def _run(self, batch):
        """The pipeline's entities for each passage; a passage that is too long for the model (more than its token limit
        after tokenizing) is cut into smaller ones and read in pieces."""
        try:
            return self.p([p for _, _, p in batch])
        except RuntimeError:
            outs = []
            for _, _, passage in batch:
                merged = []
                for off, piece in tagged.chunks(passage, 25):
                    try:
                        es = self.p([piece])[0]
                    except RuntimeError:
                        es = []
                    merged += [{**e, "start": e["start"] + off, "end": e["end"] + off} for e in es]
                outs.append(merged)
            return outs

    def spans(self, texts):
        found = [[] for _ in texts]
        pieces = [(i, off, p) for i, t in enumerate(texts) for off, p in tagged.chunks(t, 120)]
        for b in range(0, len(pieces), 2 * BATCH):
            batch = pieces[b:b + 2 * BATCH]
            for (i, off, _), es in zip(batch, self._run(batch)):
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


def _retry(call, tries=6):
    """call() again after a rate limit or a passing server error, waiting longer each time."""
    for k in range(tries):
        try:
            return call()
        except Exception as e:   # noqa: BLE001
            code = getattr(getattr(e, "response", None), "status_code", None)
            if k == tries - 1 or code not in (429, 500, 502, 503, 504):
                raise
            time.sleep(2 ** k * 3)


class GoogleDLP:
    """Google Cloud Sensitive Data Protection (DLP) content:inspect with its default detectors, every likelihood kept.
    Needs pip install google-auth requests, GOOGLE_APPLICATION_CREDENTIALS (a service account allowed to use the DLP
    API) and GOOGLE_CLOUD_PROJECT, or a project in the credentials.  A finding's likelihood becomes its score:
    VERY_UNLIKELY 0.1, UNLIKELY 0.3, POSSIBLE 0.5 (the service's own default floor), LIKELY 0.7, VERY_LIKELY 0.9."""
    LIKELY = {"VERY_UNLIKELY": .1, "UNLIKELY": .3, "POSSIBLE": .5, "LIKELY": .7, "VERY_LIKELY": .9}
    PUBLIC = {"LOCATION", "ORGANIZATION_NAME", "DOMAIN_NAME", "ETHNIC_GROUP", "MEDICAL_TERM", "COUNTRY_DEMOGRAPHIC", "TIME"}

    def __init__(self):
        import google.auth
        from google.auth.transport.requests import AuthorizedSession
        creds, project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        self.project = os.environ.get("GOOGLE_CLOUD_PROJECT") or project
        self.s = AuthorizedSession(creds)

    def _inspect(self, text):
        r = self.s.post(f"https://dlp.googleapis.com/v2/projects/{self.project}/content:inspect",
                        json={"item": {"value": text}, "inspectConfig": {"minLikelihood": "VERY_UNLIKELY", "includeQuote": False,
                                                                          "limits": {"maxFindingsPerRequest": 0}}})
        r.raise_for_status()
        return r.json().get("result", {}).get("findings", [])

    def spans(self, texts):
        out = []
        for t in texts:
            found = []
            for f in _retry(lambda: self._inspect(t)):
                kind, cp = f["infoType"]["name"], f["location"].get("codepointRange", {})
                if kind in self.PUBLIC or _not_private(kind):
                    continue
                found.append((int(cp.get("start", 0)), int(cp["end"]), kind, self.LIKELY.get(f.get("likelihood"), .5)))
            out.append(found)
        return out


class AzureLanguage:
    """Azure AI Language PII detection (kind PiiEntityRecognition, the service's default categories), each entity with
    its confidence.  Needs AZURE_LANGUAGE_ENDPOINT and AZURE_LANGUAGE_KEY.  Passages go five to a request, as the free
    tier allows; offsets are counted in code points to match Python's."""
    PUBLIC = {"Organization", "DateTime", "Age", "URL", "Quantity", "PersonType", "IPAddress"}

    def __init__(self):
        import requests
        self.s = requests.Session()
        self.url = os.environ["AZURE_LANGUAGE_ENDPOINT"].rstrip("/") + "/language/:analyze-text?api-version=2023-04-01"
        self.s.headers["Ocp-Apim-Subscription-Key"] = os.environ["AZURE_LANGUAGE_KEY"]

    def _call(self, docs):
        r = self.s.post(self.url, json={"kind": "PiiEntityRecognition", "parameters": {"stringIndexType": "UnicodeCodePoint"},
                                        "analysisInput": {"documents": [{"id": str(k), "language": "en", "text": p}
                                                                        for k, p in enumerate(docs)]}})
        r.raise_for_status()
        res = r.json()["results"]
        got = {d["id"]: d["entities"] for d in res["documents"]}
        return [got.get(str(k), []) for k in range(len(docs))]

    def spans(self, texts):
        found = [[] for _ in texts]
        pieces = [(i, off + o2, q) for i, t in enumerate(texts) for off, p in tagged.chunks(t)
                  for o2, q in ([(0, p)] if len(p) <= 5000 else tagged.chunks(p, 60))]
        for b in range(0, len(pieces), 5):
            batch = pieces[b:b + 5]
            for (i, off, _), es in zip(batch, _retry(lambda: self._call([p for _, _, p in batch]))):
                found[i] += [(off + e["offset"], off + e["offset"] + e["length"], e["category"], round(e["confidenceScore"], 3))
                             for e in es if e["category"] not in self.PUBLIC and not _not_private(e["category"])]
        return found


class AwsComprehend:
    """Amazon Comprehend DetectPiiEntities (English), each entity with its score.  Needs boto3 and AWS credentials with
    comprehend:DetectPiiEntities; AWS_REGION picks the region (default us-east-1)."""
    PUBLIC = {"DATE_TIME", "AGE", "URL", "IP_ADDRESS", "MAC_ADDRESS"}

    def __init__(self):
        import boto3
        self.c = boto3.client("comprehend", region_name=os.environ.get("AWS_REGION", "us-east-1"))

    def spans(self, texts):
        found = [[] for _ in texts]
        for i, t in enumerate(texts):
            for off, p in tagged.chunks(t):
                es = _retry(lambda: self.c.detect_pii_entities(Text=p, LanguageCode="en"))["Entities"]
                found[i] += [(off + e["BeginOffset"], off + e["EndOffset"], e["Type"], round(e["Score"], 3))
                             for e in es if e["Type"] not in self.PUBLIC]
        return found


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
    "google-dlp": (GoogleDLP, "Google Cloud Sensitive Data Protection (DLP), default detectors", 0.5),
    "azure-language": (AzureLanguage, "Azure AI Language PII detection, default categories", 0.01),
    "aws-comprehend": (AwsComprehend, "Amazon Comprehend DetectPiiEntities", 0.01),
    "gliner-pii-edge": (lambda: Gliner("knowledgator/gliner-pii-edge-v1.0"), "knowledgator/gliner-pii-edge-v1.0 (the tagger's base)", 0.5),
    "gliner-pii-base": (lambda: Gliner("knowledgator/gliner-pii-base-v1.0"), "knowledgator/gliner-pii-base-v1.0", 0.5),
    "gliner-pii-large": (lambda: Gliner("knowledgator/gliner-pii-large-v1.0"), "knowledgator/gliner-pii-large-v1.0", 0.5),
    "gliner-multi-pii": (lambda: Gliner("urchade/gliner_multi_pii-v1"), "urchade/gliner_multi_pii-v1", 0.5),
    "nvidia-gliner-pii": (lambda: Gliner("nvidia/gliner-PII", nemo=True), "nvidia/gliner-PII", 0.5),
    "gliner2-pii-multi": (lambda: Gliner2("fastino/gliner2-privacy-filter-PII-multi"), "fastino/gliner2-privacy-filter-PII-multi (GLiNER2, 278M)", 0.5),
    "gliner2-guardrails-pii": (lambda: Gliner2("fastino/GLiNER2-Guardrails-PII-Multi"), "fastino/GLiNER2-Guardrails-PII-Multi", 0.5),
    "gliner2-base": (lambda: Gliner2("fastino/gliner2-base-v1"), "fastino/gliner2-base-v1 (general GLiNER2)", 0.5),
    "gliner2-large": (lambda: Gliner2("fastino/gliner2-large-v1"), "fastino/gliner2-large-v1 (general GLiNER2)", 0.5),
    "gliner2.5-small": (lambda: Gliner2("fastino/gliner2.5-small-v1"), "fastino/gliner2.5-small-v1 (GLiNER2.5, 74M)", 0.5),
    "gliner2.5-base": (lambda: Gliner2("fastino/gliner2.5-base-v1"), "fastino/gliner2.5-base-v1 (GLiNER2.5, 194M)", 0.5),
    "gliner2.5-multi": (lambda: Gliner2("fastino/gliner2.5-multi-v1"), "fastino/gliner2.5-multi-v1 (GLiNER2.5, 287M, multilingual)", 0.5),
    "pii-tracer": (PiiTracer, "perplexity-ai/PII-Tracer (bidirectional Qwen3, 596M)", 0.5),
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
    path = CACHE / (f"bench_{name}_f{FLOOR:g}.jsonl" if name.startswith(("gliner", "nvidia")) else f"bench_{name}.jsonl")
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


SWEEP = [0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.6, 0.7, 0.8, 0.9]


def sweep(name, docs, texts, budget):
    """Found and other words hidden at each threshold from FLOOR up, and the point with the most found while other words
    hidden stay within ``budget`` (None when no threshold gets there)."""
    pts = []
    for th in SWEEP:
        floor = FLOOR if name.startswith(("gliner", "nvidia")) else 0.3 if name in ("model", "union") else 0.0   # what each cache keeps
        if th < floor:
            continue
        outs = outputs(f"{name}@{th}", texts)
        r = summarise(docs, [score_doc(d["text"], d["spans"], o) for d, o in zip(docs, outs)], boot=0)
        pts.append({"threshold": th, "found": r["found"], "other_hidden": r["other_hidden"]})
    ok = [p for p in pts if p["other_hidden"] <= budget]
    return pts, (max(ok, key=lambda p: p["found"]) if ok else None)


def score(paths, systems, outdir, budget=0.04, do_sweep=True):
    docs = read(paths)
    texts = [d["text"] for d in docs]
    report = {"data": [str(p) for p in paths], "documents": len(docs), "systems": {}}
    for spec in systems:
        name = spec.partition("@")[0]
        outs = outputs(spec, texts)
        per = [score_doc(d["text"], d["spans"], o) for d, o in zip(docs, outs)]
        r = summarise(docs, per)
        r["about"] = SYSTEMS[name][1]
        if do_sweep and "@" not in spec and name not in ("veil",) and SYSTEMS[name][2] > 0:
            r["sweep"], r["at_budget"] = sweep(name, docs, texts, budget)
            r["budget"] = budget
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
        if r.get("at_budget"):
            b = r["at_budget"]
            print(f"{'':22} within {budget:.0%} other words hidden: found {b['found']:.1%} at threshold {b['threshold']}", flush=True)
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    json.dump(report, open(outdir / "report.json", "w"), indent=1, ensure_ascii=False)
    (outdir / "report.md").write_text(markdown(report), encoding="utf-8")
    print(f"wrote {outdir / 'report.json'} and {outdir / 'report.md'}")


def markdown(report):
    rows = sorted(report["systems"].items(), key=lambda kv: -kv[1]["found"])
    budget = next((r["budget"] for _, r in rows if "budget" in r), None)
    out = [f"{report['documents']} documents from {', '.join(report['data'])}.", "",
           "| System | Found | 95% interval | Other words hidden | |", "|---|---|---|---|---|"]
    for spec, r in rows:
        out.append(f"| {spec} | {r['found']:.1%} | {r['lo']:.1%}–{r['hi']:.1%} | {r['other_hidden']:.2%} | {r['about']} |")
    if budget:
        out += ["", f"Each model at the threshold that finds the most while hiding at most {budget:.0%} of other words "
                    "(models without a score, such as veil's rules, as they are):", "",
                "| System | Found | Other words hidden | Threshold |", "|---|---|---|---|"]
        best = sorted(((s, r["at_budget"] if r.get("at_budget") else {"found": r["found"], "other_hidden": r["other_hidden"],
                                                                        "threshold": None}) for s, r in rows if "sweep" in r or r["other_hidden"] <= budget),
                      key=lambda x: -x[1]["found"])
        for spec, b in best:
            out.append(f"| {spec} | {b['found']:.1%} | {b['other_hidden']:.2%} | {b['threshold'] if b['threshold'] is not None else '–'} |")
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
    s.add_argument("--budget", type=float, default=0.04, help="other words hidden allowed when comparing models at their best threshold")
    s.add_argument("--no-sweep", action="store_true")
    r = sub.add_parser("redact")
    r.add_argument("files", nargs="+")
    r.add_argument("--system", default="union", choices=["union", "model", "veil"])
    r.add_argument("--out", default="redacted.html")
    a = ap.parse_args()
    if a.cmd == "systems":
        for k, (_, about, th) in SYSTEMS.items():
            print(f"{k:22} threshold {th:<5} {about}")
    elif a.cmd == "score":
        score(a.data, [x.strip() for x in a.systems.split(",") if x.strip()], a.out, a.budget, not a.no_sweep)
    else:
        redact(a.files, a.system, a.out)


if __name__ == "__main__":
    main()
