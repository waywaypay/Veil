"""python breakdown.py <model>@<threshold> ... : the model alone on every dev slice, found and other-words-hidden per slice and
found per type of data (name, address, email, phone, ID number, account, date of birth, username), from the cached
model outputs (a slice with a text the model hasn't read yet is skipped, not read).  Writes breakdown.json."""
import json
import os
import re
import sys

sys.path.insert(0, "/tmp/claude-0/-home-user-Veil/190ab3d3-f9c1-50ad-a470-e321ea643401/scratchpad")
import round4 as R  # noqa: E402
import round7 as R7  # noqa: E402

T = R.T

# Score each specific type of data on its own, not veil's merged kinds.  GROUP and TAX_GROUP are changed in place, so
# every dev set built from them (round4, round6, round7, round3, the judged test sets) keeps the specific label.
FINE = {"name": "name", "street address": "address", "email address": "email", "phone number": "phone",
        "ssn": "SSN", "tax id": "tax / national ID", "passport number": "passport", "driver license number": "driver licence",
        "credit card number": "credit card", "account number": "account number", "iban": "IBAN", "swift code": "SWIFT",
        "date of birth": "date of birth", "customer id": "customer ID", "employee id": "employee ID", "username": "username"}
R.GROUP.clear()
R.GROUP.update(FINE)
import round3  # noqa: E402
round3.TAX_GROUP.clear()
round3.TAX_GROUP.update({"ssn": "SSN", "tax id": "tax / national ID", "name": "name", "street address": "address"})
BENCH = {"name": "name first_name last_name GIVENNAME SURNAME", "address": "street_address address STREET BUILDINGNUM city postcode CITY ZIPCODE",
         "email": "email EMAIL", "phone": "phone_number fax_number TELEPHONENUM", "SSN": "ssn SOCIALNUM",
         "tax / national ID": "TAXNUM tax_id national_id IDCARDNUM", "passport": "passport_number",
         "driver licence": "DRIVERLICENSENUM certificate_license_number",
         "credit card": "credit_debit_card credit_card_number CREDITCARDNUM",
         "account number": "account_number ACCOUNTNUM bank_routing_number", "SWIFT": "swift_bic",
         "date of birth": "date_of_birth DATEOFBIRTH", "customer ID": "customer_id", "employee ID": "employee_id",
         "username": "user_name USERNAME"}
BENCH_LABEL = {lab: g for g, labs in BENCH.items() for lab in labs.split()}
import external  # noqa: E402
import tagger_sets  # noqa: E402
tagger_sets._group = lambda label: "ordinary" if label in external.ORDINARY else BENCH_LABEL.get(label, "outside")
import gretel as _gretel  # noqa: E402
_gretel.LABEL_GROUP.clear()
_gretel.LABEL_GROUP.update({"name": "name", "first_name": "name", "last_name": "name", "street_address": "address", "email": "email",
                            "phone_number": "phone", "ssn": "SSN", "passport_number": "passport", "driver_license_number": "driver licence",
                            "iban": "IBAN", "bban": "account number", "swift_bic_code": "SWIFT", "credit_card_number": "credit card",
                            "bank_routing_number": "account number", "date_of_birth": "date of birth", "customer_id": "customer ID",
                            "employee_id": "employee ID"})
OUT = "/tmp/claude-0/-home-user-Veil/190ab3d3-f9c1-50ad-a470-e321ea643401/scratchpad/breakdown.json"


def cached(model):
    path = T.CACHE / (re.sub(r"[^\w.:-]+", "_", model) + ".jsonl")
    have = {}
    if path.exists():
        for line in open(path):
            r = json.loads(line)
            have[r["k"]] = [tuple(x) for x in r["s"]]
    return have


def main(specs):
    sets = R7.dev_sets()
    result = json.load(open(OUT)) if os.path.exists(OUT) else {}
    for spec in specs:
        model, _, th = spec.partition("@")
        th = float(th or T.THRESHOLD)
        have = cached(model)
        slices = {}
        for name, rows in sets.items():
            if not all(T.key(t) in have for t, _ in rows):
                print(f"  skipped {name}: not all texts read by {model}", file=sys.stderr)
                continue
            r = T.score(rows, [t for t, _ in rows], [T.alone(t, have[T.key(t)], th) for t, _ in rows])
            slices[name] = {"found": r["found"], "over": r["over"], "details": r["details"], "by": r["by"]}
        result[os.path.basename(model) + f"@{th:g}"] = slices
        print(spec, len(slices), "slices", file=sys.stderr)
    json.dump(result, open(OUT, "w"))


if __name__ == "__main__":
    if os.environ.get("PYTHONHASHSEED") != "0":
        os.execve(sys.executable, [sys.executable, *sys.argv], {**os.environ, "PYTHONHASHSEED": "0"})
    main(sys.argv[1:])
