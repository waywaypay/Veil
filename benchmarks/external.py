"""veil on PII datasets it was never tuned on, from other makers and generators: ai4privacy's pii-masking-400k
(short messages, many locales; English only here), NVIDIA's Nemotron-PII (documents of 50 domains, structured
and not) and Gretel's pii-masking-en-v1 (documents of many industries).

Each dataset's labels are mapped onto what veil hides; labels for what veil doesn't look for (an IP address, a
medical record number, a password) are scored on their own, as "outside veil's kinds", and their words don't
count against it when hidden.  Raw labels, not adjudicated: these numbers are as the datasets label.

python external.py <ai4p|nemo|gretel_en> <parquet> <n> [seed]"""

import ast
import json
import random
import sys
from collections import defaultdict

import gretel as bench
import pandas as pd

from veil import FINANCE, Redactor

GROUP = {
    "name": "name first_name last_name GIVENNAME SURNAME",
    "street address": "street_address address STREET BUILDINGNUM",
    "city / postcode": "city postcode CITY ZIPCODE",
    "email": "email EMAIL",
    "phone / fax": "phone_number fax_number TELEPHONENUM",
    "SSN / ID / license / tax": "ssn SOCIALNUM IDCARDNUM DRIVERLICENSENUM TAXNUM tax_id national_id "
                                "certificate_license_number passport_number",
    "bank / card / account": "credit_debit_card credit_card_number CREDITCARDNUMBER account_number ACCOUNTNUM "
                             "bank_routing_number swift_bic",
    "date of birth": "date_of_birth DATEOFBIRTH",
    "customer / employee ID": "customer_id employee_id",
    "user name": "user_name USERNAME",
}
LABEL = {lab: g for g, labs in GROUP.items() for lab in labs.split()}
# Labelled, but not what a personal-information redactor is asked to hide: hiding these is over-redaction.
ORDINARY = set("company_name date time date_time occupation employment_status education_level language".split())


def load(kind, path, n, seed):
    d = pd.read_parquet(path)
    rows = []
    if kind == "ai4p":
        d = d[d.language == "en"]
        for text, mask in zip(d.source_text, d.privacy_mask):
            rows.append((text, [{"start": m["start"], "end": m["end"], "label": m["label"]} for m in mask]))
    elif kind == "nemo":
        for text, spans in zip(d.text, d.spans):
            rows.append((text, [{"start": s["start"], "end": s["end"], "label": s["label"]}
                                for s in ast.literal_eval(spans)]))
    else:   # gretel_en: entities without offsets, so each is found where it's written
        for text, ents in zip(d.text, d.entities):
            spans = []
            for e in ast.literal_eval(ents):
                pos = 0
                while (i := text.find(e["entity"], pos)) >= 0:
                    spans.append({"start": i, "end": i + len(e["entity"]), "label": e["types"][0]})
                    pos = i + len(e["entity"])
            rows.append((text, spans))
    random.Random(seed).shuffle(rows)
    return rows[:n]


def score(rows, fn=None):
    fn = fn or (lambda t: Redactor(FINANCE).redact_text(t))
    hit, tot = defaultdict(int), defaultdict(int)
    fp = fp_tot = 0
    for text, spans in rows:
        ws, kept = bench.redacted_mask(text, fn(text))
        personal = [False] * len(ws)
        for sp in spans:
            idx = [j for j, (_, s, e) in enumerate(ws) if s < sp["end"] and e > sp["start"]]
            if sp["label"] not in ORDINARY:
                for j in idx:
                    personal[j] = True
            idx = [j for j in idx if ws[j][0].lower() not in bench.TITLES]
            if not idx or sp["label"] in ORDINARY:
                continue
            g = LABEL.get(sp["label"], "outside veil's kinds")
            tot[g] += 1
            hit[g] += all(not kept[j] for j in idx)
        for j, (w, _, _) in enumerate(ws):
            if not personal[j] and w.lower() not in bench.TITLES:
                fp_tot += 1
                fp += not kept[j]
    return hit, tot, fp, fp_tot


def main(kind, path, n, seed=0):
    rows = load(kind, path, n, seed)
    hit, tot, fp, fp_tot = score(rows)
    groups = list(GROUP) + ["outside veil's kinds"]
    for g in groups:
        if tot[g]:
            print(f"  {g:28} {hit[g] / tot[g]:6.1%}  ({tot[g] - hit[g]} of {tot[g]} missed)")
    h = sum(hit[g] for g in GROUP)
    t = sum(tot[g] for g in GROUP)
    print(f"{kind}: {len(rows)} documents, veil's kinds {h / t:.1%} found, {fp / fp_tot:.2%} of other words hidden")
    print(json.dumps({"kind": kind, "docs": len(rows), "found": h / t, "over": fp / fp_tot,
                      "by": {g: [hit[g], tot[g]] for g in groups}}))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]) if len(sys.argv) > 4 else 0)
