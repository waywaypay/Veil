"""W-2s in payroll-provider layouts.  Providers (ADP, Paychex, Gusto, QuickBooks, small-business software) print their own
substitute Forms W-2: different box positions, label wording, fonts, borders, one or two copies to a page, headers and
footers.  This draws a W-2 with reportlab in a randomly chosen layout (grid of boxed cells, labelled lines, a ledger,
a table), then turns the PDF into text with the same extractors and OCR as w2real.py and labels it from the values drawn.

docs(n, seed) -> [(text, [(start, end, label)])]"""
import io
import random
import re

from faker import Faker
from reportlab.lib.colors import Color, black
from reportlab.pdfgen import canvas

import w2real as W

FONTS = [("Helvetica", "Helvetica-Bold"), ("Times-Roman", "Times-Bold"), ("Courier", "Courier-Bold")]
PROVIDERS = ["ADP", "Paychex", "Gusto", "QuickBooks Payroll", "Paylocity", "Rippling", "Workday", "OnPay", "Patriot Payroll",
             "Square Payroll", "Zenefits", "Justworks", "TriNet", "Ceridian Dayforce", "UKG", "Payroll4Free", "ezW2"]
COPIES = ["Copy B—To Be Filed With Employee's FEDERAL Tax Return", "Copy C—For EMPLOYEE'S RECORDS",
          "Copy 2—To Be Filed With Employee's State, City, or Local Income Tax Return", "Employee Copy", "Copy D—For Employer"]
LABELS = {
    "ssn": ["Employee's social security number", "Social Security No.", "SSN", "Employee SSN", "a Employee's social security number"],
    "ein": ["Employer identification number (EIN)", "Federal EIN", "Employer FEIN", "b Employer identification number (EIN)", "EIN"],
    "control": ["Control number", "Employee ID", "Emp #", "File Number", "d Control number"],
    "name": ["Employee's first name and initial   Last name", "Employee name", "Name", "e Employee's name"],
    "address": ["Employee's address and ZIP code", "Address", "f Employee's address", "Employee address"],
    "employer": ["Employer's name, address, and ZIP code", "Employer", "c Employer's name, address, ZIP", "Company"],
    "w1": ["Wages, tips, other compensation", "1 Wages, tips, other comp.", "Box 1 - Wages", "Gross wages (Box 1)"],
    "w2": ["Federal income tax withheld", "2 Federal income tax withheld", "Box 2 - Federal W/H", "Federal tax withheld (Box 2)"],
    "w3": ["Social security wages", "3 Social security wages", "Box 3 - SS wages"],
    "w4": ["Social security tax withheld", "4 Social security tax withheld", "Box 4 - SS tax"],
    "w5": ["Medicare wages and tips", "5 Medicare wages and tips", "Box 5 - Medicare wages"],
    "w6": ["Medicare tax withheld", "6 Medicare tax withheld", "Box 6 - Medicare tax"],
    "stid": ["Employer's state ID number", "15 State / Employer's state ID no.", "State ID", "Box 15 State ID"],
    "sw1": ["State wages, tips, etc.", "16 State wages", "Box 16"],
    "st1": ["State income tax", "17 State income tax", "Box 17"],
}


def fix_case(rng, form):
    """Same details, written the way some providers write them: capitals, 'LAST, FIRST', no middle initial."""
    f = dict(form)
    if rng.random() < 0.35:
        for k in ("first", "last", "employer_name", "employer_street"):
            f[k] = f[k].upper()
        f["address"] = f["address"].upper()
    return f


class Page:
    def __init__(self, rng):
        self.rng = rng
        self.buf = io.BytesIO()
        self.c = canvas.Canvas(self.buf, pagesize=(612, 792))
        self.font, self.bold = rng.choice(FONTS)
        self.size = rng.choice([7, 8, 8.5, 9, 10])
        self.lab = max(5.5, self.size - rng.choice([1.5, 2, 2.5]))
        self.border = rng.random() < 0.6
        self.grey = rng.random() < 0.3
        self.items = []         # (x, y, text, labelled?)

    def text(self, x, y, s, label=None, bold=False, size=None):
        self.c.setFont(self.bold if bold else self.font, size or self.size)
        self.c.setFillColor(black)
        self.c.drawString(x, y, s)

    def cell(self, x, y, w, h, label, lines, label_above=True):
        c = self.c
        if self.border:
            c.setStrokeColor(Color(.2, .2, .2))
            c.rect(x, y, w, h)
        if self.grey:
            c.setFillColor(Color(.93, .93, .93)); c.rect(x, y + h - self.lab - 3, w, self.lab + 3, fill=0, stroke=0)
        if label_above:
            self.text(x + 3, y + h - self.lab - 1, label, size=self.lab)
            for i, ln in enumerate(lines):
                self.text(x + 5, y + h - self.lab - 4 - (i + 1) * (self.size + 1.5), ln)
        else:
            self.text(x + 3, y + h - self.size - 2, label, size=self.lab)
            for i, ln in enumerate(lines):
                self.text(x + w * 0.45, y + h - self.size - 2 - i * (self.size + 1.5), ln)


def cells_of(rng, f, us_style):
    """The boxes of one W-2 as (key, label, [lines]) in the order the layout will draw them."""
    L = lambda k: rng.choice(LABELS[k])   # noqa: E731
    street, city = f["address"].split("\n")
    first, last = f["first"], f["last"]
    caps = first.isupper()
    name_line = rng.choice([f"{first} {last}", f"{last}, {first}", f"{first}  {last}"])
    emp = f["employer"].split("\n")
    out = [("ssn", L("ssn"), [f["ssn"]]), ("ein", L("ein"), [f["ein"]]),
           ("name", L("name"), [name_line]),
           ("address", L("address"), [street, city] if rng.random() < 0.7 else [f"{street}, {city}"]),
           ("employer", L("employer"), emp if rng.random() < 0.8 else [emp[0], f"{emp[1]}, {emp[2]}"])]
    if f.get("control"):
        out.append(("control", L("control"), [f["control"]]))
    for k in ("w1", "w2", "w3", "w4", "w5", "w6"):
        out.append((k, L(k), [f[k]]))
    out += [("stid", L("stid"), [f"{f['state1']}  {f['stid1']}"]), ("sw1", L("sw1"), [f["sw1"]]), ("st1", L("st1"), [f["st1"]])]
    for k in "abcd":
        if f.get("c12" + k):
            out.append(("b12" + k, f"12{k} Code / Amount", [f"{f['c12' + k]}  {f['a12' + k]}"]))
    return out


def draw_copy(pg, rng, f, top, height, provider):
    """One W-2 in the area from y = top - height to top, in a random layout."""
    cells = cells_of(rng, f, False)
    style = rng.choices(["grid", "ledger", "table", "stack"], [5, 3, 2, 2])[0]
    x0, w = 36, 540
    pg.text(x0, top - 12, f"{provider}  Form W-2 Wage and Tax Statement  {f.get('year', '2025')}", bold=True, size=pg.size + 2)
    pg.text(x0, top - 24, rng.choice(COPIES), size=pg.lab)
    y = top - 30
    order = list(cells)
    if rng.random() < 0.5:
        rng.shuffle(order)
    elif rng.random() < 0.5:
        order.sort(key=lambda c: c[0] in ("w1", "w2", "w3", "w4", "w5", "w6", "stid", "sw1", "st1"))
    if style == "grid":
        cols = rng.choice([2, 3, 4])
        cw = w / cols
        ch = max(pg.size * 4.4, 30)
        i = 0
        row = 0
        while i < len(order):
            for col in range(cols):
                if i >= len(order):
                    break
                k, label, lines = order[i]
                h = ch + (len(lines) - 1) * (pg.size + 1.5)
                span = 2 if (k in ("employer", "address", "name") and col + 1 < cols and rng.random() < 0.6) else 1
                pg.cell(x0 + col * cw, y - ch * (row + 1) - 4, cw * span, max(h, ch), label, lines, label_above=True)
                col += span - 1
                i += 1
            row += 1
    elif style == "ledger":
        gap = pg.size + 3.4
        for k, label, lines in order:
            pg.text(x0, y, label + ":", size=pg.lab + 1)
            for j, ln in enumerate(lines):
                pg.text(x0 + w * rng.choice([0.42, 0.5, 0.55]), y - j * gap, ln)
            y -= gap * max(len(lines), 1) + 2
    elif style == "table":
        gap = pg.size + 4
        pg.text(x0, y, "Box / Description", bold=True, size=pg.lab + 1)
        pg.text(x0 + w * 0.6, y, "Value", bold=True, size=pg.lab + 1)
        y -= gap
        for k, label, lines in order:
            pg.text(x0, y, label, size=pg.lab + 1)
            pg.text(x0 + w * 0.6, y, lines[0])
            for j, ln in enumerate(lines[1:], 1):
                pg.text(x0 + w * 0.6, y - j * (pg.size + 1.5), ln)
            y -= gap + (len(lines) - 1) * (pg.size + 1.5)
    else:   # stack: label line then value line(s)
        gap = pg.size + 2.4
        for k, label, lines in order:
            pg.text(x0, y, label, size=pg.lab)
            y -= gap
            for ln in lines:
                pg.text(x0 + 12, y, ln)
                y -= gap
            y -= 3


def provider_pdf(rng, f):
    pg = Page(rng)
    provider = rng.choice(PROVIDERS)
    copies = rng.choice([1, 1, 2])
    heights = [740] if copies == 1 else [380, 380]
    top = 770
    for h in heights:
        draw_copy(pg, rng, f, top, h, provider)
        top -= h
    if rng.random() < 0.3:      # an earnings-statement stub or notice at the bottom of the page
        pg.text(36, 40, f"Questions? Contact {provider} at 1-800-{rng.randint(200, 999)}-{rng.randint(1000, 9999)}", size=pg.lab)
    pg.c.showPage()
    pg.c.save()
    return pg.buf.getvalue(), copies


def docs(n, seed):
    rng = random.Random(seed)
    us = Faker("en_US")
    us.seed_instance(seed)
    fakes = {l: Faker(l) for l in set(W.LOCALES)}
    for i, f in enumerate(fakes.values()):
        f.seed_instance(seed + i + 1)
    out, tries = [], 0
    while len(out) < n and tries < n * 4:
        tries += 1
        form = fix_case(rng, W.one_form(rng, fakes[rng.choice(W.LOCALES)], us))
        form["year"] = rng.choice(["2023", "2024", "2025"])
        pdf, copies = provider_pdf(rng, form)
        mode = rng.choices(["layout", "raw", "order", "pypdf", "ocr"], [3, 2, 3, 1, 4])[0]
        fuzzy = mode == "ocr"
        text = W.ocr(pdf, rng) if fuzzy else W.pypdf_text(pdf) if mode == "pypdf" else W.pdftotext(pdf, mode)
        text = re.sub(r"\n{3,}", "\n\n", text).strip("\n")
        # OCR on a two-copy page is read once per copy; drawn values appear `copies` times
        spans = W.labelled(text, form, fuzzy, copies)
        if spans is None or any(spans[i][1] > spans[i + 1][0] for i in range(len(spans) - 1)):
            continue
        out.append((text, spans))
    return out


if __name__ == "__main__":
    import sys
    for t, s in docs(int(sys.argv[1]) if len(sys.argv) > 1 else 3, 31):
        print(t[:1500], "\n", [(t[a:b], l) for a, b, l in s], "\n" + "=" * 70)
