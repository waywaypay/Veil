"""Synthetic US tax forms other than the W-2, labelled as taxforms_spec.txt says: Schedule K-1 (1065, 1120-S, 1041),
W-9, W-4, the 1099 family, Form 1040 with dependants, 1095-A/B/C and 1098 / 1098-T / 1098-E.  Each is rendered as PDF
extraction, an OCR scan, portal JSON or an email, at random.  docs(n, seed) -> [(text, [(start, end, label)])]"""
import json
import random

from faker import Faker

from w2gen import Doc, address, ein, misread, odd, person, ssn, STATES

K1_FORMS = [("1065", "Partner", "Partnership"), ("1120-S", "Shareholder", "Corporation"), ("1041", "Beneficiary", "Estate or trust")]
F1099 = {"NEC": ["1 Nonemployee compensation"], "MISC": ["1 Rents", "3 Other income"], "INT": ["1 Interest income"],
         "DIV": ["1a Total ordinary dividends", "1b Qualified dividends"], "B": ["1d Proceeds", "1e Cost or other basis"],
         "R": ["1 Gross distribution", "2a Taxable amount"], "G": ["1 Unemployment compensation"],
         "K": ["1a Gross amount of payment card/third party network transactions"], "SA": ["1 Gross distribution"]}
FUNDS = ["{} Capital Partners II, L.P.", "{} Growth Fund, LP", "{} & Co. Real Estate Fund III", "{} Family Trust",
         "{} Holdings, LLC"]


def money(rng, lo=100, hi=90000):
    return f"{rng.uniform(lo, hi):,.2f}"


def org(rng, fake):
    return rng.choice([fake.company() + rng.choice([" Inc.", " LLC", " Corp.", ""]),
                       rng.choice(FUNDS).format(fake.last_name()), fake.company() + " Bank"])


def who(rng, fake):
    st = rng.choice(STATES)
    first, mid, last = person(rng, fake)
    return {"name": f"{first} {mid}{last}", "first": first, "last": last, "ssn": ssn(rng), "addr": address(rng, fake, st),
            "dob": fake.date_of_birth(minimum_age=0, maximum_age=90).strftime(rng.choice(["%m/%d/%Y", "%Y-%m-%d", "%m-%d-%y"]))}


def put_addr(d, a, sep="\n", caps=False):
    s = a[0] + sep + a[1]
    d.add(s.upper() if caps else s, "street address")


def k1(rng, fake, d, ocr):
    form, role, ent = rng.choice(K1_FORMS)
    p, e = who(rng, fake), org(rng, fake)
    m = (lambda s: misread(rng, s)) if ocr else (lambda s: s)
    d.add(f"Schedule K-1 (Form {form}) {rng.choice(['2023', '2024', '2025'])}  {role}'s Share of Income, Deductions, Credits, etc.\n")
    d.add(f"Part I  Information About the {ent}\nA {ent}'s employer identification number\n").add(m(odd(rng, ein(rng))), "tax id")
    d.add(f"\nB {ent}'s name, address, city, state, and ZIP code\n{e}\n{fake.street_address()}, {fake.city()}, {rng.choice(STATES)} {rng.randint(10000, 99999)}\n")
    d.add(f"Part II  Information About the {role}\nE {role}'s identifying number  ").add(m(odd(rng, p["ssn"])), "ssn")
    d.add(f"\nF {role}'s name, address, city, state, and ZIP code\n").add(m(p["name"]), "name").add("\n")
    put_addr(d, (m(p["addr"][0]), m(p["addr"][1])))
    d.add(f"\nPart III  {role}'s Share of Current Year Income\n1 {money(rng)}  5 {money(rng)}  ")
    d.add(f"20 {rng.choice('ABVZ')} {rng.randint(1000, 999999)}\n")


def w9(rng, fake, d, ocr):
    p = who(rng, fake)
    sole = rng.random() < 0.5
    d.add("Form W-9 (Rev. March 2024) Request for Taxpayer Identification Number and Certification\n1 Name ").add(p["name"], "name")
    d.add("\n2 Business name/disregarded entity name, if different from above ")
    if sole:
        d.add(p["last"].split()[0] + " " + rng.choice(["Consulting", "Design", "Plumbing", "Photography"]), None)
    d.add("\n3a [" + ("x" if sole else " ") + "] Individual/sole proprietor  [ ] C corporation  [ ] LLC\n5 Address ")
    d.add(p["addr"][0], "street address").add("\n6 City, state, and ZIP code ").add(p["addr"][1], "street address")
    d.add(f"\nRequester's name and address (optional) {org(rng, fake)}\nPart I Taxpayer Identification Number (TIN)\n")
    if rng.random() < 0.6:
        d.add("Social security number  | ").add(" | ".join(p["ssn"].replace("-", "")) if ocr else p["ssn"], "ssn").add(" |")
    else:
        d.add("Employer identification number  ").add(ein(rng), "tax id")
    d.add(f"\nSignature of U.S. person ▶ ").add(p["name"], "name").add(f"   Date ▶ {fake.date_this_year().strftime('%m/%d/%Y')}")


def w4(rng, fake, d, ocr):
    p = who(rng, fake)
    d.add("Form W-4 Employee's Withholding Certificate  OMB No. 1545-0074\nStep 1(a) First name and middle initial ")
    d.add(p["first"], "name").add("  Last name ").add(p["last"], "name").add("\n(b) Social security number ")
    d.add(odd(rng, p["ssn"]), "ssn").add("\nAddress ").add(p["addr"][0], "street address").add("\nCity or town, state, and ZIP code ")
    d.add(p["addr"][1], "street address").add(f"\n(c) [x] Single  [ ] Married filing jointly\nStep 3 Claim dependent amounts ${rng.randint(0, 6) * 500:,}\n")
    d.add(f"Employers only: Employer's name and address {fake.company()}  First date of employment {fake.date_this_year().strftime('%m/%d/%Y')}  EIN ")
    d.add(ein(rng), "tax id")


def f1099(rng, fake, d, ocr):
    kind = rng.choice(list(F1099))
    p, payer = who(rng, fake), org(rng, fake)
    m = (lambda s: misread(rng, s)) if ocr else (lambda s: s)
    d.add(f"Form 1099-{kind} {rng.choice(['2024', '2025'])}  {'CORRECTED' if rng.random() < .1 else ''}\nPAYER'S name, street address, city or town\n{payer}\n")
    d.add(f"PAYER'S TIN ").add(m(ein(rng)), "tax id").add("   RECIPIENT'S TIN ").add(m(odd(rng, p["ssn"])), "ssn")
    d.add("\nRECIPIENT'S name\n").add(m(p["name"].upper() if rng.random() < .4 else p["name"]), "name").add("\nStreet address (including apt. no.)\n")
    d.add(m(p["addr"][0]), "street address").add("\nCity or town, state or province, country, and ZIP or foreign postal code\n")
    d.add(m(p["addr"][1]), "street address").add("\nAccount number (see instructions) ")
    d.add(f"{rng.choice(['', 'X'*4, ''])}{rng.randint(10000000, 999999999)}", "account number").add("\n")
    for box in F1099[kind]:
        d.add(f"{box} ${money(rng)}\n")
    d.add("4 Federal income tax withheld $" + money(rng, 0, 9000))


def f1040(rng, fake, d, ocr):
    a, b = who(rng, fake), who(rng, fake)
    d.add(f"Form 1040 U.S. Individual Income Tax Return {rng.choice(['2023', '2024'])} OMB No. 1545-0074\nFiling Status [x] Married filing jointly\n")
    d.add("Your first name and middle initial ").add(a["first"], "name").add("  Last name ").add(a["last"], "name")
    d.add("  Your social security number ").add(odd(rng, a["ssn"]), "ssn").add("\nIf joint return, spouse's first name ")
    d.add(b["first"], "name").add("  Last name ").add(a["last"], "name").add("  Spouse's social security number ").add(odd(rng, b["ssn"]), "ssn")
    d.add("\nHome address (number and street) ").add(a["addr"][0], "street address").add("\nCity, town, or post office, state, ZIP ")
    d.add(a["addr"][1], "street address").add("\nDependents  (1) First name Last name  (2) SSN  (3) Relationship\n")
    for _ in range(rng.randint(0, 3)):
        c = who(rng, fake)
        d.add(c["first"] + " " + a["last"], "name").add("  ").add(c["ssn"], "ssn").add("  " + rng.choice(["Son", "Daughter", "Stepson"]) + "\n")
    d.add(f"1a Total amount from Form(s) W-2, box 1 {money(rng, 20000, 300000)}\n35a Refund {money(rng, 100, 6000)}\n")
    d.add("b Routing number ").add(f"{rng.randint(10000000, 99999999)}{rng.randint(0, 9)}", "account number")
    d.add("  c Type: [x] Checking  d Account number ").add(str(rng.randint(10**7, 10**12)), "account number")
    if rng.random() < .5:
        pr = who(rng, fake)
        d.add("\nPaid Preparer Use Only  Preparer's name ").add(pr["name"], "name").add("  PTIN ").add(f"P{rng.randint(10**7, 10**8 - 1)}", "tax id")
        d.add(f"  Firm's name {fake.company()}  Firm's EIN ").add(ein(rng), "tax id")


def f1095(rng, fake, d, ocr):
    kind = rng.choice("ABC")
    p = who(rng, fake)
    d.add(f"Form 1095-{kind} Health {'Insurance Marketplace Statement' if kind == 'A' else 'Coverage'}\n")
    d.add("1 Name of employee/recipient ").add(p["name"], "name").add("  2 Social security number (SSN) ").add(odd(rng, p["ssn"]), "ssn")
    d.add("\n3 Street address ").add(p["addr"][0], "street address").add("  4 City, State, ZIP ").add(p["addr"][1], "street address")
    if kind == "A":
        d.add("\nPolicy number ").add(f"{rng.randint(10**6, 10**9)}", "account number")
    d.add(f"\n7 Name of employer/issuer {fake.company()}  8 Employer identification number (EIN) ").add(ein(rng), "tax id")
    d.add("\nPart III Covered Individuals  (a) Name  (b) SSN or other TIN  (c) DOB (if SSN or other TIN is not available)\n")
    for i in range(rng.randint(1, 4)):
        c = who(rng, fake)
        d.add(f"{23 + i} ").add(c["first"] + " " + p["last"], "name").add("  ")
        if rng.random() < .7:
            d.add(c["ssn"], "ssn").add("  \n")
        else:
            d.add("  ").add(c["dob"], "date of birth").add("\n")


def f1098(rng, fake, d, ocr):
    kind = rng.choice(["", "-T", "-E"])
    p = who(rng, fake)
    d.add(f"Form 1098{kind} {rng.choice(['2024', '2025'])}\n{'RECIPIENT/LENDER' if kind != '-T' else 'FILER'}'S name and address {org(rng, fake)}\n")
    d.add("RECIPIENT'S/LENDER'S TIN " if kind != "-T" else "FILER'S employer identification no. ").add(ein(rng), "tax id")
    d.add("  PAYER'S/BORROWER'S TIN " if kind != "-T" else "  STUDENT'S TIN ").add(odd(rng, p["ssn"]), "ssn")
    d.add("\nName ").add(p["name"], "name").add("\nStreet address ").add(p["addr"][0], "street address")
    d.add("\nCity, state, ZIP ").add(p["addr"][1], "street address").add("\nAccount number ").add(str(rng.randint(10**6, 10**10)), "account number")
    d.add(f"\n1 {'Mortgage interest received' if kind == '' else 'Payments received for qualified tuition' if kind == '-T' else 'Student loan interest'} ${money(rng)}")
    if kind == "":
        d.add("\n8 Address of property securing mortgage ").add(p["addr"][0] + rng.choice(["", " (same)"]).replace(" (same)", ""), "street address")


FORMS = [k1, w9, w4, f1099, f1040, f1095, f1098]


def wrap(rng, fake, d, inner):
    """Most go out as form text; some are pasted into an email or turned into portal JSON-ish key lines."""
    k = rng.random()
    if k < .2:
        p = who(rng, fake)
        d.add("From: ").add(p["name"], "name").add(" <").add(f"{p['first'].lower()}{rng.randint(1, 99)}@{rng.choice(['gmail.com', 'icloud.com'])}", "email address")
        d.add(">\nSubject: tax docs\n\nHi — pasting the form below since the PDF won't open.\n\n")
    inner(rng, fake, d, ocr=rng.random() < .25)
    if k < .2:
        d.add("\n\nThanks,\n").add(p["first"], "name")


def docs(n, seed):
    rng = random.Random(seed)
    fake = Faker("en_US")
    fake.seed_instance(seed)
    out = []
    for i in range(n):
        d = Doc()
        wrap(rng, fake, d, FORMS[i % len(FORMS)])
        text, spans = d.done()
        for s, e, _ in spans:
            assert text[s:e].strip() == text[s:e] and e > s, text[s:e]
        out.append((text, spans))
    return out


if __name__ == "__main__":
    for t, s in docs(7, 3):
        print(t, "\n", [(t[a:b], l) for a, b, l in s], "\n" + "-" * 60)
