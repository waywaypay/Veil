"""Benchmark veil against Presidio and scrubadub on Gretel's synthetic finance PII test set (English).

Each tool gets the raw document and returns redacted text. Scoring is tool-agnostic:
words of the original are aligned against words of the output; a word missing from
the output counts as redacted.

  recall      = share of gold PII spans whose every word was redacted (no part leaks)
  over-redact = share of words outside all gold spans that were redacted
  kept        = share of company / generic-date spans left fully intact (utility)
"""
import difflib
import json
import re
import sys
import time
from collections import defaultdict

import pandas as pd

GROUPS = {
    "name": {"name", "first_name", "last_name"},
    "street address": {"street_address"},
    "email": {"email"},
    "phone": {"phone_number"},
    "SSN / passport / license": {"ssn", "passport_number", "driver_license_number"},
    "bank / card / IBAN / SWIFT": {"iban", "bban", "swift_bic_code", "credit_card_number", "bank_routing_number"},
    "date of birth": {"date_of_birth"},
    "customer / employee ID": {"customer_id", "employee_id"},
}
KEEP = {"company": {"company"}, "ordinary date": {"date"}}
LABEL_GROUP = {lab: g for g, labs in GROUPS.items() for lab in labs}
LABEL_KEEP = {lab: g for g, labs in KEEP.items() for lab in labs}
WORD = re.compile(r"\w+")
TITLES = {"mr", "mrs", "ms", "miss", "dr", "prof", "sir", "mx", "dame", "captain", "capt", "officer", "detective",
          "inspector", "sergeant", "sgt", "lieutenant", "lt", "judge", "coach", "nurse", "pastor", "rev", "reverend",
          "rabbi", "imam", "professor", "agent"}
# Gold spans that aren't personal details at all: blank template fields and bare labels.
_TEMPLATE = re.compile(r"\[[^\]]*\]|\{[^}]*\}|<[^>]*>|_{3,}|^[\W_]*$|\b(?:MM|DD|YYYY|XXX+|X{2,}-)\b")
_BARE_LABEL = re.compile(r"(?i)^\W*(?:(?:full |first |last |your |customer |employee )?name|address|street address|"
                         r"date of birth|dob|email(?: address)?|phone(?: number)?|ssn|passport(?: number)?|lessee|lessor|"
                         r"(?:fixed|floating) rate payer|borrower|lender|tenant|landlord|employer|employee)\W*$")


_BUSINESS_WORDS = None
_EVERYDAY = None


def _lists():
    global _BUSINESS_WORDS, _EVERYDAY
    if _BUSINESS_WORDS is None:
        import gzip
        from pathlib import Path
        root = Path(__file__).resolve().parent / "lists"
        _BUSINESS_WORDS = set(open(root / "business_words.txt").read().split())
        _EVERYDAY = set(gzip.open(root / "common_words.txt.gz", "rt").read().split())
        _EVERYDAY -= set(open(root / "name_words.txt").read().split())
    return _BUSINESS_WORDS, _EVERYDAY


_ADDRESS_LABEL_WORDS = set("""address addresses street city state province postal zip code country mailing residential
registered home permanent current billing wallet specified line apt suite unit""".split())


def is_noise(text, label=None, after=""):
    """A gold span that's no personal detail: a blank template field or a bare label; and, for a name, one
    with a business's word in it ("Capecchi & Associates", "... Stock Index") or only everyday words that
    are no name ("impartial expert", "The Shareholder"), or no letters at all."""
    if _TEMPLATE.search(text) or _BARE_LABEL.match(text):
        return True
    if label == "street_address":
        words = re.findall(r"[^\W\d_]+", text.casefold())
        if not re.search(r"\d", text) and all(w in _ADDRESS_LABEL_WORDS for w in words):
            return True   # "mailing address", "Street, City, State/Province, Postal Code"
        if " " not in text.strip() and len(text.strip()) > 25:
            return True   # a crypto wallet's address
    if label in ("name", "first_name", "last_name"):
        business, everyday = _lists()
        words = [w.casefold() for w in re.findall(r"[^\W\d_]+", text)]
        if not words or any(w in business for w in words):
            return True
        if all(w in everyday for w in words):
            return True
        if any(w.islower() and w.casefold() in everyday for w in re.findall(r"[^\W\d_]+", text)):
            return True   # runs into ordinary words: "Penelope's business", "case manager"
        # a person's name in a business's ("Taylor Healthcare Fund", "Capecchi & Associates")
        following = [w.casefold() for w in re.findall(r"[^\W\d_]+", after)[:4]]
        lead = re.match(r"[ \t]*(?:&|and\b|,)?", after)
        if following and (following[0] in business or
                          (lead and lead.group().strip() and any(w in business for w in following[:3]))):
            return True
        if following and any(w in business for w in following[:3]) and \
                all(w[:1].isupper() for w in re.findall(r"[^\W\d_]+", after)[:following.index(next(
                    w for w in following[:3] if w in business)) + 1]):
            return True
    return False


def words(text):
    return [(m.group(), m.start(), m.end()) for m in WORD.finditer(text)]


def redacted_mask(orig, out):
    a, b = words(orig), words(out)
    sm = difflib.SequenceMatcher(None, [w for w, _, _ in a], [w for w, _, _ in b], autojunk=False)
    kept = [False] * len(a)
    for blk in sm.get_matching_blocks():
        for i in range(blk.a, blk.a + blk.size):
            kept[i] = True
    return a, kept


def word_map(orig, ocr):
    """For each word of ``orig``, the index of the word OCR made of it in ``ocr`` (misread or not), or None when
    OCR dropped it."""
    a, b = words(orig), words(ocr)
    sm = difflib.SequenceMatcher(None, [w.lower() for w, _, _ in a], [w.lower() for w, _, _ in b], autojunk=False)
    out = [None] * len(a)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal" or (op == "replace" and i2 - i1 == j2 - j1):
            for k in range(i2 - i1):
                out[i1 + k] = j1 + k
        elif op == "replace":
            for i in range(i1, i2):
                best = max(range(j1, j2), key=lambda j: difflib.SequenceMatcher(None, a[i][0].lower(), b[j][0].lower()).ratio())
                if difflib.SequenceMatcher(None, a[i][0].lower(), b[best][0].lower()).ratio() >= 0.6:
                    out[i] = best
    return out


def score(docs, fn, inputs=None):
    """``inputs``: what each tool is given instead of the document itself (its OCR text); the gold spans stay
    on the original, and a word counts as kept when the word OCR made of it is kept."""
    hit, tot = defaultdict(int), defaultdict(int)
    keep_ok, keep_tot = defaultdict(int), defaultdict(int)
    fp = fp_tot = 0
    chit = ctot = 0
    chit_g, ctot_g = defaultdict(int), defaultdict(int)
    inputs = inputs or [text for text, _ in docs]
    t0 = time.perf_counter()
    outs = [fn(x) for x in inputs]
    elapsed = time.perf_counter() - t0
    for (text, spans), given, out in zip(docs, inputs, outs):
        if given is text:
            a, kept = redacted_mask(text, out)
            seen = [True] * len(a)
        else:
            _, kept_given = redacted_mask(given, out)
            a = words(text)
            m = word_map(text, given)
            kept = [j is not None and kept_given[j] for j in m]
            seen = [j is not None for j in m]
        in_gold = [False] * len(a)
        for sp in spans:
            idx = [i for i, (w, s, e) in enumerate(a) if s < sp["end"] and e > sp["start"]]
            for i in idx:
                in_gold[i] = True
            idx = [i for i in idx if a[i][0].lower() not in TITLES]
            if not idx:
                continue
            lab = sp["label"]
            if lab in LABEL_GROUP:
                g = LABEL_GROUP[lab]
                ok = all(not kept[i] for i in idx)
                tot[g] += 1
                hit[g] += ok
                if not is_noise(text[sp["start"]:sp["end"]], lab, text[sp["end"]:sp["end"] + 60]):
                    ctot += 1
                    chit += ok
                    ctot_g[g] += 1
                    chit_g[g] += ok
            elif lab in LABEL_KEEP:
                g = LABEL_KEEP[lab]
                if all(seen[i] for i in idx):
                    keep_tot[g] += 1
                    keep_ok[g] += all(kept[i] for i in idx)
        for i, (w, _, _) in enumerate(a):
            if not in_gold[i] and w.lower() not in TITLES and seen[i]:
                fp_tot += 1
                fp += not kept[i]
    return {
        "recall": {g: (hit[g], tot[g]) for g in GROUPS},
        "recall_all": (sum(hit.values()), sum(tot.values())),
        "recall_clean": (chit, ctot),
        "recall_clean_by": {g: (chit_g[g], ctot_g[g]) for g in GROUPS},
        "over_redact": (fp, fp_tot),
        "kept": {g: (keep_ok[g], keep_tot[g]) for g in KEEP},
        "ms_per_doc": 1000 * elapsed / len(docs),
    }


def tools():
    from veil import FINANCE, GENERIC, Redactor

    out = {
        "veil (GENERIC)": lambda t: Redactor(GENERIC).redact_text(t),
        "veil (FINANCE)": lambda t: Redactor(FINANCE).redact_text(t),
    }

    import spacy

    nlp = spacy.load("en_core_web_lg")

    def spacy_names(t):
        return [e.text for e in nlp(t).ents if e.label_ == "PERSON"]

    out["veil (FINANCE) + spaCy names"] = lambda t: Redactor(FINANCE, name_finder=spacy_names).redact_text(t)

    from presidio_analyzer import AnalyzerEngine
    from presidio_anonymizer import AnonymizerEngine

    an, anon = AnalyzerEngine(), AnonymizerEngine()
    out["Presidio (default)"] = lambda t: anon.anonymize(t, an.analyze(t, language="en")).text

    import scrubadub

    scrubber = scrubadub.Scrubber()
    out["scrubadub (default)"] = scrubber.clean
    return out


def main(path, n, out_path):
    d = pd.read_parquet(path)
    d = d[d.language == "English"].head(n)
    docs = [(t, json.loads(s)) for t, s in zip(d.generated_text, d.pii_spans)]
    results = {}
    for name, fn in tools().items():
        print("running", name, file=sys.stderr, flush=True)
        results[name] = score(docs, fn)
    results["_meta"] = {"docs": len(docs)}
    json.dump(results, open(out_path, "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), sys.argv[3])
