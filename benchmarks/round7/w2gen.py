"""Synthetic US Form W-2s for training, labelled as w2_spec.txt says: the employee's name, address and SSN; the
employer's EIN and state ID; the control number (employee id); a private-person employer's name and address.  Rendered
the ways W-2s reach text: PDF extraction, payroll-provider prints, OCR scans, one character per box, portal JSON, bulk
CSV, W-2c corrections, and W-2s pasted into emails and chats.  docs(n, seed) -> [(text, [(start, end, label)])]"""
import json
import random

from faker import Faker

STATES = ["AL", "AZ", "CA", "CO", "CT", "GA", "IL", "IN", "KY", "MA", "MD", "MI", "MN", "MO", "NC", "NJ", "NY", "OH",
          "OR", "PA", "SC", "VA", "WI", "TX", "FL", "WA"]
LOCAL = {"NY": "NYC", "OH": "COLUMBUS", "PA": "PHILADELPHIA", "MI": "DETROIT", "KY": "LOUISVILLE", "MD": "BALT CITY",
         "IN": "MARION CO"}
CODES = ["D", "DD", "W", "C", "E", "AA", "P", "V", "12a", "BB"]
PROVIDERS = ["ADP", "Paychex", "Gusto", "QuickBooks Payroll", "Workday", "Paylocity", "Rippling", "OnPay"]
OCR = {"1": "lI|", "0": "OoD", "5": "S", "8": "B", "2": "Z", "6": "b", "l": "1", "O": "0", "S": "5", "I": "1"}
SUFFIX = ["", "", "", "", " Jr.", " Sr.", " III", " II"]


class Doc:
    def __init__(self):
        self.parts, self.n = [], 0

    def add(self, text, label=None):
        if label and text.strip():
            lead = len(text) - len(text.lstrip())
            trail = len(text.rstrip())
            self.parts.append((text, (self.n + lead, self.n + trail, label)))
        else:
            self.parts.append((text, None))
        self.n += len(text)
        return self

    def done(self):
        return "".join(p for p, _ in self.parts), [s for _, s in self.parts if s]


def ssn(rng):
    return f"{rng.randint(100, 899):03d}-{rng.randint(10, 99):02d}-{rng.randint(1000, 9999):04d}"


def ein(rng):
    return f"{rng.randint(10, 99):02d}-{rng.randint(1000000, 9999999):07d}"


def odd(rng, s):
    """An SSN or EIN written oddly: spaces, no dashes, dots, en dashes, masked."""
    k = rng.random()
    if k < 0.15:
        return s.replace("-", "")
    if k < 0.3:
        return s.replace("-", " ")
    if k < 0.4:
        return s.replace("-", "–")
    if k < 0.5 and len(s) == 11:
        return "XXX-XX-" + s[-4:] if rng.random() < 0.5 else "***-**-" + s[-4:]
    return s


def misread(rng, s, rate=0.15):
    return "".join(rng.choice(OCR[c]) if c in OCR and rng.random() < rate else c for c in s)


def person(rng, fake):
    first, last = fake.first_name(), fake.last_name()
    mid = rng.choice(["", "", fake.first_name()[0] + ". ", fake.first_name()[0] + " "])
    if rng.random() < 0.08:
        last = last + "-" + fake.last_name()
    return first, mid, last + rng.choice(SUFFIX)


def address(rng, fake, state):
    street = fake.street_address()
    if rng.random() < 0.2:
        street += rng.choice([" Apt ", " Unit ", " #"]) + str(rng.randint(1, 40)) + rng.choice(["", "B", "C"])
    if rng.random() < 0.07:
        street = f"PO Box {rng.randint(10, 9999)}"
    zipc = f"{rng.randint(10000, 99999)}" + (f"-{rng.randint(1000, 9999)}" if rng.random() < 0.3 else "")
    return street, f"{fake.city()}, {state} {zipc}"


def money(rng, lo, hi):
    return f"{rng.uniform(lo, hi):,.2f}"


def facts(rng, fake):
    state = rng.choice(STATES)
    first, mid, last = person(rng, fake)
    household = rng.random() < 0.12
    if household:
        ef, em, el = person(rng, fake)
        employer = f"{ef} {el}"
    else:
        employer = fake.company() + rng.choice(["", " Inc.", " LLC", " Corp."])
    wages = rng.uniform(9000, 240000)
    f = {"state": state, "first": first, "mid": mid, "last": last, "ssn": ssn(rng), "ein": ein(rng),
         "household": household, "employer": employer, "eaddr": address(rng, fake, state),
         "addr": address(rng, fake, state), "control": rng.choice(["", f"{rng.randint(100, 99999)}",
                                                                   f"A{rng.randint(1000, 9999)}-{rng.randint(10, 99)}"]),
         "w1": f"{wages:,.2f}", "w2": f"{wages * rng.uniform(.08, .22):,.2f}", "w3": f"{min(wages, 168600):,.2f}",
         "w4": f"{min(wages, 168600) * .062:,.2f}", "w5": f"{wages:,.2f}", "w6": f"{wages * .0145:,.2f}",
         "stid": f"{rng.randint(100000, 99999999)}" + rng.choice(["", "-" + str(rng.randint(100, 999))]),
         "w16": f"{wages:,.2f}", "w17": f"{wages * rng.uniform(.02, .07):,.2f}",
         "codes": [(rng.choice(CODES[:6]), money(rng, 200, 20000)) for _ in range(rng.randint(0, 3))],
         "year": rng.choice(["2023", "2024", "2025"]), "retire": rng.random() < 0.4}
    f["full"] = f"{first} {mid}{last}"
    return f


def employer_block(d, f, sep="\n"):
    lab = "name" if f["household"] else None
    d.add(f["employer"], lab).add(sep)
    lab = "street address" if f["household"] else None
    d.add(f["eaddr"][0] + sep + f["eaddr"][1], lab)


def employee_block(d, f, sep="\n", caps=False):
    nm = f["full"].upper() if caps else f["full"]
    d.add(nm, "name").add(sep)
    a = f["addr"][0] + sep + f["addr"][1]
    d.add(a.upper() if caps else a, "street address")


def pdf_extract(rng, f):
    d = Doc()
    d.add(f"a Employee's social security number ").add(odd(rng, f["ssn"]), "ssn").add(" OMB No. 1545-0029\n")
    if rng.random() < 0.5:
        d.add(f"b Employer identification number (EIN) ").add(odd(rng, f["ein"]), "tax id")
        d.add(f" 1 Wages, tips, other compensation {f['w1']} 2 Federal income tax withheld {f['w2']}\n")
    else:
        d.add(f"1 Wages, tips, other compensation 2 Federal income tax withheld\n{f['w1']} {f['w2']}\n")
        d.add("b Employer identification number (EIN)\n").add(odd(rng, f["ein"]), "tax id").add("\n")
    d.add("c Employer's name, address, and ZIP code 3 Social security wages 4 Social security tax withheld\n")
    employer_block(d, f, rng.choice(["\n", " "]))
    d.add(f" {f['w3']} {f['w4']}\n5 Medicare wages and tips {f['w5']} 6 Medicare tax withheld {f['w6']}\n")
    d.add("d Control number ")
    if f["control"]:
        d.add(f["control"], "employee id")
    d.add("\ne Employee's first name and initial Last name Suff. ")
    d.add(f["first"] + " " + f["mid"] + f["last"], "name").add("\n")
    d.add("f Employee's address and ZIP code\n").add(f["addr"][0] + rng.choice(["\n", " "]) + f["addr"][1], "street address")
    d.add("\n13 Statutory employee Retirement plan Third-party sick pay " + ("X" if f["retire"] else "") + "\n")
    for i, (c, v) in enumerate(f["codes"]):
        d.add(f"12{'abcd'[i]} {c} {v}\n")
    d.add(f"15 State Employer's state ID number {f['state']} | ").add(f["stid"], "tax id")
    d.add(f" 16 State wages, tips, etc. {f['w16']} 17 State income tax {f['w17']}\n")
    if f["state"] in LOCAL:
        d.add(f"18 Local wages {f['w16']} 19 Local income tax {money(rng, 100, 3000)} 20 Locality name {LOCAL[f['state']]}\n")
    d.add(f"Form W-2 Wage and Tax Statement {f['year']} Department of the Treasury—Internal Revenue Service\n")
    d.add(rng.choice(["Copy B—To Be Filed With Employee's FEDERAL Tax Return.", "Copy C—For EMPLOYEE'S RECORDS",
                      "Copy 2—To Be Filed With Employee's State, City, or Local Income Tax Return."]))
    return d


def payroll_print(rng, f):
    d = Doc()
    prov = rng.choice(PROVIDERS)
    d.add(f"{prov} — {f['year']} W-2 Wage and Tax Statement\n{'=' * 46}\nEMPLOYER\n")
    employer_block(d, f)
    d.add("\nFederal EIN: ").add(odd(rng, f["ein"]), "tax id")
    d.add(f"\n\nEMPLOYEE\n")
    employee_block(d, f, caps=rng.random() < 0.4)
    d.add("\nSSN: ").add(odd(rng, f["ssn"]), "ssn")
    if f["control"]:
        d.add("   Employee #: ").add(f["control"], "employee id")
    d.add(f"\n\nBox 1  Wages ............ {f['w1']:>12}\nBox 2  Fed W/H .......... {f['w2']:>12}\n")
    d.add(f"Box 3  SS Wages ......... {f['w3']:>12}\nBox 4  SS Tax ........... {f['w4']:>12}\n")
    d.add(f"Box 5  Medicare Wages ... {f['w5']:>12}\nBox 6  Medicare Tax ..... {f['w6']:>12}\n")
    for c, v in f["codes"]:
        d.add(f"Box 12 {c:<3} ............ {v:>12}\n")
    d.add(f"Box 15 {f['state']}  State ID ").add(f["stid"], "tax id")
    d.add(f"\nBox 16 State Wages ...... {f['w16']:>12}\nBox 17 State Tax ........ {f['w17']:>12}\n")
    d.add(f"\nQuestions? Contact {prov} at 1-800-{rng.randint(200, 999)}-{rng.randint(1000, 9999)}.")
    return d


def ocr_scan(rng, f):
    d = Doc()
    d.add("a Emp1oyee's soc1al security numbcr\n").add(misread(rng, odd(rng, f["ssn"])), "ssn")
    d.add("\nb Emp1oyer identificati0n number (EIN)  ").add(misread(rng, f["ein"]), "tax id")
    d.add(f"\nc Employer's narne, address, and ZIP code\n")
    if f["household"]:
        d.add(misread(rng, f["employer"].upper(), .08), "name").add("\n")
        d.add(misread(rng, (f["eaddr"][0] + "\n" + f["eaddr"][1]).upper(), .08), "street address")
    else:
        d.add(misread(rng, f["employer"].upper(), .08) + "\n" + misread(rng, (f["eaddr"][0] + "\n" + f["eaddr"][1]).upper(), .08))
    d.add(f"\n1 {misread(rng, f['w1'])}   2 {misread(rng, f['w2'])}\n")
    d.add("e Employee's first narne and initia1   Last narne\n")
    d.add(misread(rng, f["full"].upper(), .1), "name").add("\n")
    d.add(misread(rng, (f["addr"][0] + "\n" + f["addr"][1]).upper(), .1), "street address")
    d.add(f"\n15 {f['state']} ").add(misread(rng, f["stid"]), "tax id").add(f"  16 {misread(rng, f['w16'])}\n")
    d.add("Forrn W-2 Wage and Tax Staternent " + f["year"])
    return d


def boxed(rng, f):
    d = Doc()
    box = lambda s: " | ".join(s)  # noqa: E731
    d.add(f"FORM W-2 ({f['year']}) — keyed entry\na. Employee SSN:   | ").add(box(f["ssn"].replace("-", "")), "ssn")
    d.add(" |\nb. Employer EIN:   | ").add(box(f["ein"].replace("-", "")), "tax id").add(" |\n")
    d.add("e. First name:     | ").add(box(f["first"].upper()), "name").add(" |\n")
    d.add("   Last name:      | ").add(box(f["last"].upper().replace(" ", "")), "name").add(" |\n")
    d.add("f. Address:        ").add(f["addr"][0].upper() + ", " + f["addr"][1].upper(), "street address").add("\n")
    d.add(f"1. Wages:          {f['w1']}\n2. Fed tax:        {f['w2']}\n")
    if f["control"]:
        d.add("d. Control no.:    ").add(f["control"], "employee id").add("\n")
    return d


def portal_json(rng, f):
    d = Doc()
    d.add('{\n  "taxYear": ' + f["year"] + ',\n  "formType": "W-2",\n  "employee": {\n    "firstName": "')
    d.add(f["first"], "name").add('",\n    "lastName": "').add(f["last"], "name").add('",\n    "ssn": "')
    d.add(odd(rng, f["ssn"]), "ssn").add('",\n    "address": {"line1": "').add(f["addr"][0], "street address")
    d.add('", "cityStateZip": "').add(f["addr"][1], "street address").add('"}')
    if f["control"]:
        d.add(',\n    "employeeId": "').add(f["control"], "employee id").add('"')
    d.add('\n  },\n  "employer": {\n    "name": "')
    d.add(f["employer"], "name" if f["household"] else None).add('",\n    "ein": "').add(f["ein"], "tax id")
    d.add(f'"\n  }},\n  "boxes": {{"1": "{f["w1"]}", "2": "{f["w2"]}", "3": "{f["w3"]}", "4": "{f["w4"]}", ')
    d.add(f'"5": "{f["w5"]}", "6": "{f["w6"]}"}},\n  "state": [{{"code": "{f["state"]}", "employerStateId": "')
    d.add(f["stid"], "tax id").add(f'", "wages": "{f["w16"]}", "tax": "{f["w17"]}"}}]\n}}')
    return d


def bulk_csv(rng, fake):
    d = Doc()
    d.add("tax_year,emp_id,first,last,ssn,address,city_state_zip,box1,box2,box16,state,employer_ein\n")
    e = ein(rng)
    for _ in range(rng.randint(2, 6)):
        f = facts(rng, fake)
        d.add(f["year"] + ",").add(f["control"] or str(rng.randint(100, 9999)), "employee id").add(",")
        d.add(f["first"], "name").add(",").add(f["last"], "name").add(",").add(f["ssn"], "ssn").add(",\"")
        d.add(f["addr"][0], "street address").add("\",\"").add(f["addr"][1], "street address")
        d.add(f"\",\"{f['w1']}\",\"{f['w2']}\",\"{f['w16']}\",{f['state']},").add(e, "tax id").add("\n")
    return d


def w2c(rng, f):
    d = Doc()
    old = ssn(rng)
    d.add(f"Form W-2c Corrected Wage and Tax Statement — for {f['year']}\na Employer's name, address, ZIP\n")
    employer_block(d, f)
    d.add("\nb Employer's Federal EIN ").add(f["ein"], "tax id")
    d.add("\nc Tax year/Form corrected " + f["year"] + " / W-2\nd Employee's correct SSN ").add(f["ssn"], "ssn")
    d.add("\nf Employee's previously reported SSN ").add(odd(rng, old), "ssn")
    d.add("\ne Employee's first name and initial, Last name\n").add(f["full"], "name")
    d.add("\nh Employee's address and ZIP code\n").add(f["addr"][0] + "\n" + f["addr"][1], "street address")
    d.add(f"\nPreviously reported / Correct information\n1 Wages {money(rng, 9000, 90000)} / {f['w1']}")
    return d


def emailed(rng, f, fake):
    d = Doc()
    hr_first, hr_last = fake.first_name(), fake.last_name()
    who = rng.choice(["my accountant", "the lender", "you"])
    d.add("From: ").add(f["full"], "name").add(" <")
    d.add(f"{f['first'].lower()}.{f['last'].split()[0].lower()}@{rng.choice(['gmail.com', 'yahoo.com', 'outlook.com'])}", "email address")
    d.add(">\nSubject: W-2 numbers for " + f["year"] + "\n\nHi,\n\nHere's what's on my W-2 for " + who + ":\n")
    d.add("Employer: ").add(f["employer"], "name" if f["household"] else None).add(", EIN ").add(odd(rng, f["ein"]), "tax id")
    d.add(f"\nBox 1 wages {f['w1']}, box 2 withheld {f['w2']}\nMy SSN on it is ").add(odd(rng, f["ssn"]), "ssn")
    d.add(rng.choice([" (please double check, last year's had a typo)", "", " — same as before"]) + "\nAddress on file: ")
    d.add(f["addr"][0] + ", " + f["addr"][1], "street address").add("\n\nThanks,\n").add(f["first"], "name")
    if rng.random() < 0.5:
        d.add("\n\n> On payroll's side, ").add(hr_first + " " + hr_last, "name")
        d.add(" said the corrected copy goes out Friday.")
    return d


def chat(rng, f):
    d = Doc()
    d.add(rng.choice(["can you help me fill in my 1040? my W-2 says ", "is this right? W-2 from my job: ",
                      "I got my W-2, box 1 is "]))
    d.add(f"{f['w1']} and box 2 is {f['w2']}. employer ").add(f["employer"], "name" if f["household"] else None)
    d.add(" EIN ").add(f["ein"], "tax id").add(". my name on it is spelled ").add(f["full"], "name")
    d.add(" and ssn ").add(odd(rng, f["ssn"]), "ssn").add(". state is " + f["state"] + ".")
    return d


def docs(n, seed):
    rng = random.Random(seed)
    fake = Faker("en_US")
    fake.seed_instance(seed)
    out = []
    kinds = [pdf_extract, payroll_print, ocr_scan, boxed, portal_json, w2c, "csv", "email", chat]
    weights = [3, 3, 2, 1, 1, 1, 1, 1, 1]
    for _ in range(n):
        k = rng.choices(kinds, weights)[0]
        if k == "csv":
            d = bulk_csv(rng, fake)
        elif k == "email":
            d = emailed(rng, facts(rng, fake), fake)
        else:
            d = k(rng, facts(rng, fake))
        text, spans = d.done()
        for s, e, _ in spans:
            assert text[s:e].strip() == text[s:e] and e > s, (k, text[s:e])
        out.append((text, spans))
    return out


if __name__ == "__main__":
    for t, s in docs(3, 1):
        print(t, "\n", [(t[a:b], l) for a, b, l in s], "\n" + "-" * 60)
