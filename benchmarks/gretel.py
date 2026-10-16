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


def is_noise(text):
    return bool(_TEMPLATE.search(text) or _BARE_LABEL.match(text))


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


def score(docs, fn):
    hit, tot = defaultdict(int), defaultdict(int)
    keep_ok, keep_tot = defaultdict(int), defaultdict(int)
    fp = fp_tot = 0
    chit = ctot = 0
    t0 = time.perf_counter()
    outs = [fn(text) for text, _ in docs]
    elapsed = time.perf_counter() - t0
    for (text, spans), out in zip(docs, outs):
        a, kept = redacted_mask(text, out)
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
                if not is_noise(text[sp["start"]:sp["end"]]):
                    ctot += 1
                    chit += ok
            elif lab in LABEL_KEEP:
                g = LABEL_KEEP[lab]
                keep_tot[g] += 1
                keep_ok[g] += all(kept[i] for i in idx)
        for i, (w, _, _) in enumerate(a):
            if not in_gold[i] and w.lower() not in TITLES:
                fp_tot += 1
                fp += not kept[i]
    return {
        "recall": {g: (hit[g], tot[g]) for g in GROUPS},
        "recall_all": (sum(hit.values()), sum(tot.values())),
        "recall_clean": (chit, ctot),
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
