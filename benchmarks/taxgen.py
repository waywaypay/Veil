"""Synthetic tax-form snippets: SSNs, EINs and ITINs in the ways veil's README says they get written (odd dashes and
spaces, one digit per box, split across lines, HTML or %-escaped, Unicode digits, OCR misreads, masked to the last
four), among the form text that must stay visible (dates, amounts, form and line numbers, OMB numbers, references).
Labels: (start, end, label) with the tagger's label names.  Written from the README's list, not from veil's tests."""
import random

FIRST = ["Avery", "Rowan", "Jordan", "Priya", "Marcus", "Elena", "Tomás", "Aisha", "Kenji", "Olga", "Liam", "Fatima",
         "Noah", "Ingrid", "Diego", "Mei", "Samuel", "Chloé", "Ravi", "Zainab", "Lukas", "Hannah", "Mateo", "Yara"]
LAST = ["Mockridge", "Calder", "Okafor", "Lindqvist", "Varga", "Harrow", "Nakamura", "Petrov", "Quintero", "Adeyemi",
        "Brennan", "Sørensen", "Delacroix", "Whitlock", "Haddad", "Kowalski", "Ferreira", "Ashby", "Moreau", "Iyer"]
FIRMS = ["Marlow Vane Growth Fund, LP", "Northgate Capital Partners II, L.P.", "Harbor & Pine Holdings LLC",
         "Cedar Ridge Real Estate Fund III, LP", "Blue Fen Ventures, L.P.", "Kestrel Income Partners LLC"]
STREETS = ["Oak Lane", "Maple Avenue", "Harbor Road", "Willow Court", "Elm Street", "Cedar Drive", "Ridge Way"]
CITIES = [("Boston", "MA", "02110"), ("Austin", "TX", "78701"), ("Denver", "CO", "80202"), ("Columbus", "OH", "43215"),
          ("Portland", "OR", "97205"), ("Raleigh", "NC", "27601")]
DASHES = ["-", "–", "—", "‑", "−", " - ", " ", " ", ".", "/", "_", "~", "・", "‐"]
OCR = {"1": "lI|", "0": "OoD", "5": "Ss", "8": "B", "2": "Zz", "6": "b", "9": "g", "4": "A", "7": "T"}
WIDE = str.maketrans("0123456789", "０１２３４５６７８９")
SUP = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")
SSN_LABELS = ["SSN", "SSN:", "Social Security No.", "Partner's SSN or TIN", "Social security number", "Recipient's TIN",
              "Taxpayer identification number", "SS#", "Soc. Sec. No.", "Identifying number", "TIN", ""]
EIN_LABELS = ["EIN", "EIN:", "Employer identification number", "Partnership's EIN", "Fed. ID No.", "Payer's TIN",
              "Federal Tax ID", "Employer I.D. #", "FEIN", "Tax ID", ""]
ITIN_LABELS = ["ITIN", "ITIN:", "Individual taxpayer identification number"]


def number(r, kind):
    if kind == "ssn":
        while True:
            a = r.randint(1, 899)
            if a != 666:
                break
        return [f"{a:03d}", f"{r.randint(1, 99):02d}", f"{r.randint(1, 9999):04d}"]
    if kind == "itin":
        return [f"9{r.randint(0, 99):02d}", f"{r.choice([r.randint(50, 65), r.randint(70, 88), r.randint(90, 99)]):02d}",
                f"{r.randint(0, 9999):04d}"]
    return [f"{r.randint(10, 99):02d}", f"{r.randint(0, 9999999):07d}"]


def written(r, groups):
    """One of the ways a taxpayer ID gets written."""
    digits = "".join(groups)
    style = r.randrange(16)
    if style == 0:
        return r.choice(DASHES).join(groups)
    if style == 1:
        return digits
    if style == 2:   # one digit per box
        sep = r.choice(["|", " ", "  ", "][", " | "])
        s = sep.join(digits)
        return f"|{s}|" if sep == "|" else f"[{s}]" if sep == "][" else s
    if style == 3:   # groups on their own lines
        return r.choice(["\n", "\n ", "\r\n", "\n-", "-\n"]).join(groups)
    if style == 4:   # a digit a line
        return "\n".join(digits)
    if style == 5:   # wide spacing, tabs, table cells
        return r.choice(["    ", "\t", " | ", "   "]).join(groups)
    if style == 6:   # markup around the groups
        tag = r.choice([("**", "**"), ("<b>", "</b>"), ("<span>", "</span>"), ("`", "`")])
        return r.choice(["-", " "]).join(f"{tag[0]}{g}{tag[1]}" for g in groups)
    if style == 7:   # HTML entities, %-escapes, JSON escapes
        sep = r.choice(["&ndash;", "&#8209;", "&#45;", "%2D", "\\u2013", "&nbsp;"])
        return sep.join(groups)
    if style == 8:   # Unicode digits
        return r.choice(["-", " "]).join(groups).translate(r.choice([WIDE, SUP]))
    if style == 9:   # OCR misreads
        s = list("-".join(groups))
        for _ in range(r.randint(1, 2)):
            i = r.choice([i for i, c in enumerate(s) if c in OCR])
            s[i] = r.choice(OCR[s[i]])
        return "".join(s)
    if style == 10:  # masked to the last four
        return r.choice(["***-**-", "XXX-XX-", "xxx-xx-", "•••-••-", "*****"]) + digits[-4:]
    if style == 11:  # three groups of three
        return r.choice([" ", "-", "."]).join([digits[:3], digits[3:6], digits[6:]])
    if style == 12:  # commas between groups
        return r.choice([",", ", "]).join(groups)
    if style == 13:  # another grouping
        cut = r.choice([2, 4, 5])
        return "-".join([digits[:cut], digits[cut:]])
    if style == 14:  # comb boxes with dashes
        return "-".join("".join(f"[{d}]" for d in g) for g in groups)
    return "-".join(groups)


def date(r):
    y, m, d = r.randint(2018, 2025), r.randint(1, 12), r.randint(1, 28)
    return r.choice([f"{y}-{m:02d}-{d:02d}", f"{m:02d}/{d:02d}/{y}", f"{m}-{d}-{y}", f"{d:02d}.{m:02d}.{y}",
                     f"{['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'][m - 1]} {d}, {y}",
                     f"12/31/{y}", f"tax year {y}"])


def amount(r):
    v = r.randint(10, 9_999_999)
    return r.choice([f"{v:,}", f"${v:,}.00", f"({v:,})", f"{v}", f"{v:,}".replace(",", " "), f"-{v:,}", f"{v / 100:,.2f}",
                     f"{r.randint(1, 99)}.{r.randint(0, 9999):04d}%"])


def form_text(r):
    """Text from tax forms that must stay visible."""
    return r.choice([f"OMB No. 1545-{r.randint(0, 2999):04d}", f"Form {r.choice(['1065', '1120-S', '1099-DIV', 'W-9', '8865'])}",
                     f"Line {r.randint(1, 21)}{r.choice(['', 'A', 'B', 'AE', 'ZZ', 'V'])}",
                     f"Box {r.randint(1, 20)}{r.choice(['', 'A', 'B', 'C'])}", f"Code {r.choice(['A', 'AH', 'Z', 'ZZ'])}",
                     f"Ref: K1-{r.randint(2018, 2025)}-{r.randint(1, 999):03d}", f"Cat. No. {r.randint(10000, 99999)}{r.choice('ABCDEFGHJKLMNPRSTUVWXYZ')}",
                     f"page {r.randint(1, 9)} of {r.randint(9, 20)}", f"www.irs.gov/Form{r.choice(['1065', '1120S', 'W9'])}",
                     f"Invoice {r.randint(100000, 999999)}", f"Version {r.randint(1, 9)}.{r.randint(0, 20)}",
                     f"Account period {date(r)} to {date(r)}", f"Ownership {amount(r)}"])


def doc(r):
    """A snippet and its labels."""
    parts, labels = [], []

    def add(text, label=None):
        start = sum(len(p) for p in parts)
        parts.append(text)
        if label:
            labels.append((start, start + len(text), label))

    name = f"{r.choice(FIRST)} {r.choice(LAST)}"
    city, state, zipc = r.choice(CITIES)
    layout = r.randrange(4)
    entries = []
    for _ in range(r.randint(1, 3)):
        kind = r.choices(["ssn", "ein", "itin"], [5, 4, 1])[0]
        entries.append((kind, written(r, number(r, kind))))
    if layout == 0:   # a form's boxes, one a line
        add(r.choice(["Schedule K-1 (Form 1065)", "Form W-9", "Form 1099-DIV", "Partner's Share of Income"]) + f" {date(r)}\n")
        for kind, num in entries:
            lab = r.choice(SSN_LABELS if kind == "ssn" else ITIN_LABELS if kind == "itin" else EIN_LABELS)
            add(f"{form_text(r)}\n{lab}{r.choice([' ', chr(10), ': ', '  '])}")
            add(num, "ssn" if kind == "ssn" else "tax id")
            add("\n")
        add(f"{r.choice(['Partnership', 'Payer'])}: {r.choice(FIRMS)}\n")
        add("Partner's name\n")
        add(name, "name")
        add("\n")
        add(f"{r.randint(10, 9999)} {r.choice(STREETS)}, {city}, {state} {zipc}", "street address")
        add(f"\n{form_text(r)} {amount(r)}\n{form_text(r)} {amount(r)}\n")
    elif layout == 1:   # a CSV or table
        sep = r.choice([",", "\t", " | "])
        add(sep.join(["Investor", "TIN", "Distribution", "Date"]) + "\n")
        for kind, num in entries:
            add(f"{r.choice(FIRST)} {r.choice(LAST)}", "name")
            add(sep)
            add(num.replace("\r", "").replace("\n", " "), "ssn" if kind == "ssn" else "tax id")
            add(f"{sep}{amount(r)}{sep}{date(r)}\n")
    elif layout == 2:   # a sentence, as a person types
        for kind, num in entries:
            lab = r.choice(SSN_LABELS if kind == "ssn" else EIN_LABELS)
            add(r.choice([f"my {lab or 'number'} is ", f"Please update {lab} to ", f"the {lab or 'TIN'} on file ({form_text(r)}) is ",
                          f"{lab} ", "use "]))
            add(num, "ssn" if kind == "ssn" else "tax id")
            add(r.choice([f" for {r.choice(FIRMS)}. ", f", filed {date(r)}. ", f" ({form_text(r)}). ", ". ", f" and the amount is {amount(r)}. "]))
    else:   # JSON or a file name or a URL
        for kind, num in entries:
            key = r.choice(["ssn", "tin", "taxId", "ein", "partner_tin", "fein"])
            how = r.randrange(3)
            if how == 0:
                add(f'{{"{key}": "')
                add(num.replace("\r", "").replace("\n", "\\n"), "ssn" if kind == "ssn" else "tax id")
                add(f'", "amount": "{amount(r)}", "date": "{date(r)}"}}\n')
            elif how == 1:
                add(f"{r.choice(LAST)}_")
                add(num.replace("\r", "").replace("\n", "_").replace(" ", "_"), "ssn" if kind == "ssn" else "tax id")
                add(f"_K1_{r.randint(2018, 2025)}.pdf\n")
            else:
                add(f"https://portal.example.com/k1?{key}=")
                add(num.replace("\r", "").replace("\n", "%0A").replace(" ", "%20"), "ssn" if kind == "ssn" else "tax id")
                add(f"&year={r.randint(2018, 2025)}\n")
    # some snippets with no taxpayer ID at all: only form text that must stay
    if r.random() < 0.2:
        parts, labels = [], []
        for _ in range(r.randint(3, 8)):
            add(f"{form_text(r)} {r.choice([amount(r), date(r), ''])}\n")
    return "".join(parts), labels


def docs(n, seed):
    r = random.Random(seed)
    return [doc(r) for _ in range(n)]


if __name__ == "__main__":
    for t, labels in docs(6, 1):
        print("----\n" + t)
        print([(t[s:e], lab) for s, e, lab in labels])
