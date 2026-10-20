"""W-2s from the real IRS form: the IRS fillable Form W-2 PDF (fw2.pdf, 6 fillable pages of two forms each) filled with
made-up people and employers, then turned into text the ways real W-2s reach a redactor: pdftotext (layout, raw and
reading order), pypdf, and Tesseract OCR of the rendered page at several resolutions with real degradations (skew, blur,
noise, JPEG, low contrast).  Labels come from the values put into the fields, found again in the extracted text (exactly
for PDF extraction; by fuzzy match for OCR, and a document with a value that can't be found is dropped).

docs(n, seed) -> [(text, [(start, end, label)])]"""
import io
import logging
import os
import random
import re
import subprocess
import tempfile
from difflib import SequenceMatcher

logging.disable(logging.CRITICAL)
import numpy as np  # noqa: E402
from faker import Faker  # noqa: E402
from PIL import Image, ImageFilter  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402

IRS = os.environ.get("W2_IRS_PDF", "/tmp/claude-0/fw2.pdf")
PAGES = [1, 2, 3, 5, 7, 9]               # the pages with fillable forms (two forms each)
STATES = ["AL", "AZ", "CA", "CO", "CT", "GA", "IL", "IN", "KY", "MA", "MD", "MI", "MN", "MO", "NC", "NJ", "NY", "OH",
          "OR", "PA", "SC", "VA", "WI", "TX", "FL", "WA", "TN", "NV", "OK", "UT", "KS", "IA", "AR", "LA", "NE", "NM"]
LOCALES = ["en_US"] * 6 + ["es_MX", "pt_BR", "de_DE", "fr_FR", "it_IT", "en_IN", "nl_NL", "pl_PL", "sv_SE", "tr_TR", "vi_VN"]
BOX12 = ["A", "B", "C", "D", "DD", "E", "F", "G", "H", "AA", "BB", "EE", "W", "S", "T", "P"]
FIELD = {1: "ssn", 2: "ein", 3: "employer", 4: "control", 5: "first", 6: "last", 7: "suffix", 8: "address",
         9: "w1", 10: "w2", 11: "w3", 12: "w4", 13: "w5", 14: "w6", 15: "w7", 16: "w8", 17: "w9", 18: "w10",
         19: "w11", 20: "c12a", 21: "a12a", 22: "c12b", 23: "a12b", 24: "c12c", 25: "a12c", 26: "c12d", 27: "a12d",
         28: "o14a", 29: "o14b", 30: "o14c", 31: "state1", 32: "stid1", 33: "state2", 34: "stid2", 35: "sw1",
         36: "sw2", 37: "st1", 38: "st2", 39: "lw1", 40: "lw2", 41: "lt1", 42: "lt2", 43: "loc1", 44: "loc2"}

_READER = None


def reader():
    global _READER
    if _READER is None:
        _READER = PdfReader(IRS)
    return _READER


# -- made-up people and employers -----------------------------------------------------------------------------------

def ascii_name(s):
    import unicodedata
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode() or "Alex"


def person(rng, fake):
    first = ascii_name(fake.first_name())
    last = ascii_name(fake.last_name())
    if rng.random() < 0.12:
        last += "-" + ascii_name(fake.last_name())
    if rng.random() < 0.05:
        last = rng.choice(["O'", "D'", "Mc", "Mac", "De La ", "Van "]) + last
    first = first + rng.choice(["", "", "", " " + rng.choice("ABCDEFGHJKLMNPRSTW")])
    return first, last


def money(rng, x):
    return f"{x:,.2f}"


def one_form(rng, fake, us):
    state = rng.choice(STATES)
    first, last = person(rng, fake)
    household = rng.random() < 0.1
    if household:
        ef, el = person(rng, us)
        employer = f"{ef} {el}"
    else:
        employer = us.company()
    wages = rng.uniform(8000, 260000)
    ss = min(wages, 168600)
    street = us.street_address().replace("\n", " ")
    if rng.random() < 0.2:
        street += rng.choice([" Apt ", " Unit ", " Suite ", " #"]) + str(rng.randint(1, 900))
    estreet = us.street_address().replace("\n", " ")
    ecity = f"{us.city()}, {state} {rng.randint(10000, 99999)}"
    ecity = ecity if rng.random() < 0.8 else ecity.upper()
    ssn = f"{rng.randint(100, 899):03d}-{rng.randint(10, 99):02d}-{rng.randint(1000, 9999):04d}"
    ein = f"{rng.randint(10, 99)}-{rng.randint(1000000, 9999999)}"
    control = rng.choice(["", "", str(rng.randint(100, 99999)), f"{rng.choice('ABCDEFGHJK')}{rng.randint(1000, 9999)}-{rng.randint(10, 99)}"])
    stid = str(rng.randint(100000, 99999999)) + rng.choice(["", "", f"-{rng.randint(10, 999)}", f"{rng.choice('ABCDE')}"])
    f = {"ssn": ssn, "ein": ein, "employer": f"{employer}\n{estreet}\n{ecity}", "control": control, "first": first,
         "last": last, "address": f"{street}\n{us.city()}, {state} {rng.randint(10000, 99999)}", "household": household,
         "employer_name": employer, "employer_street": estreet,
         "w1": money(rng, wages), "w2": money(rng, wages * rng.uniform(.05, .22)), "w3": money(rng, ss),
         "w4": money(rng, ss * .062), "w5": money(rng, wages), "w6": money(rng, wages * .0145),
         "state1": state, "stid1": stid, "sw1": money(rng, wages), "st1": money(rng, wages * rng.uniform(.02, .07))}
    for k in range(rng.randint(0, 3)):
        f["c12" + "abcd"[k]] = rng.choice(BOX12)
        f["a12" + "abcd"[k]] = money(rng, rng.uniform(100, 22000))
    if rng.random() < 0.15:
        f.update(state2=rng.choice(STATES), stid2=str(rng.randint(10**5, 10**8)), sw2=money(rng, wages / 3), st2=money(rng, wages / 40))
    if rng.random() < 0.2:
        f.update(lw1=money(rng, wages), lt1=money(rng, wages * .01), loc1=rng.choice(["NYC", "PHILA", "COLUMBUS", "DETROIT", "BALT", "KC"]))
    return f


# -- filling and extracting --------------------------------------------------------------------------------------------

def fill(page_no, forms):
    """PDF bytes of one fillable page with ``forms`` (a list of 1 or 2 form dicts) put into its fields."""
    w = PdfWriter(clone_from=reader())
    keep = page_no
    for i in sorted(range(len(w.pages)), reverse=True):
        if i != keep:
            w.remove_page(i)
    page = w.pages[0]
    vals = {}
    for a in page["/Annots"]:
        a = a.get_object()
        t = a.get("/T")
        ft = a.get("/FT") or (a["/Parent"].get_object().get("/FT") if a.get("/Parent") else None)
        m = re.match(r"f\d+_(\d+)\[0\]", str(t or ""))
        if ft == "/Tx" and m:
            n = int(m.group(1))
            copy, idx = (0, n) if n <= 44 else (1, n - 44)
            if copy < len(forms) and idx in FIELD and forms[copy].get(FIELD[idx]) not in (None, ""):
                vals[str(t)] = forms[copy][FIELD[idx]]
    # the two forms on a page share field names f<p>_01..f<p>_88, 1-44 and 45-88
    w.update_page_form_field_values(page, vals, auto_regenerate=False)
    w.set_need_appearances_writer(True)
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def pdftotext(pdf, mode):
    with tempfile.NamedTemporaryFile(suffix=".pdf") as t:
        t.write(pdf)
        t.flush()
        args = ["pdftotext", "-nopgbrk"] + {"layout": ["-layout"], "raw": ["-raw"], "order": []}[mode] + [t.name, "-"]
        return subprocess.run(args, capture_output=True, text=True, timeout=60).stdout


def pypdf_text(pdf):
    return PdfReader(io.BytesIO(pdf)).pages[0].extract_text()


def degrade(img, rng):
    img = img.convert("L")
    if rng.random() < 0.7:
        img = img.rotate(rng.uniform(-1.4, 1.4), resample=Image.BICUBIC, fillcolor=255, expand=True)
    if rng.random() < 0.6:
        img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.3, 0.9)))
    a = np.asarray(img).astype(np.float32)
    if rng.random() < 0.7:
        a = 255 - (255 - a) * rng.uniform(0.55, 1.0)            # faded ink
    if rng.random() < 0.7:
        a += np.random.default_rng(rng.randint(0, 10**6)).normal(0, rng.uniform(3, 12), a.shape)
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    if rng.random() < 0.5:
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=rng.randint(30, 70))
        img = Image.open(io.BytesIO(buf.getvalue()))
    return img


def ocr(pdf, rng):
    with tempfile.TemporaryDirectory() as d:
        open(f"{d}/a.pdf", "wb").write(pdf)
        dpi = rng.choice([110, 130, 150, 200, 200, 250])
        subprocess.run(["pdftoppm", "-r", str(dpi), "-png", f"{d}/a.pdf", f"{d}/p"], check=True, capture_output=True, timeout=120)
        png = sorted(f for f in os.listdir(d) if f.endswith(".png"))[0]
        img = degrade(Image.open(f"{d}/{png}"), rng)
        img.save(f"{d}/o.png")
        psm = rng.choice([4, 4, 6, 3])
        out = subprocess.run(["tesseract", f"{d}/o.png", "-", "--psm", str(psm)], capture_output=True, text=True, timeout=180)
        return out.stdout


# -- finding the values again ------------------------------------------------------------------------------------------

def _free(text, s, e):
    return (s == 0 or not text[s - 1].isalnum()) and (e >= len(text) or not text[e].isalnum())


def find_exact(text, value, taken):
    for m in re.finditer(re.escape(value), text):
        if _free(text, m.start(), m.end()) and not any(m.start() < e and s < m.end() for s, e in taken):
            return m.start(), m.end()
    return None


def find_fuzzy(text, value, taken, min_ratio=0.72):
    """Best approximate occurrence of ``value`` in OCR ``text``: (start, end) or None."""
    v = value.lower()
    n = len(v)
    best = (0.0, None)
    low = text.lower()
    for ln in {max(2, n - 2), max(2, n - 1), n, n + 1, n + 2}:
        for s in range(0, len(low) - ln + 1):
            seg = low[s:s + ln]
            if v[0] != seg[0] and v[-1] != seg[-1] and v[len(v) // 2] != seg[len(seg) // 2]:
                continue
            if not _free(low, s, s + ln) or any(a < s + ln and s < b for a, b in taken):
                continue
            r = SequenceMatcher(None, v, seg).ratio()
            if r > best[0]:
                best = (r, (s, s + ln))
    return best[1] if best[0] >= min_ratio else None


def labelled(text, form, fuzzy, copies):
    """[(start, end, label)] for every occurrence of the values of ``form`` in ``text`` (``copies`` of each, one per
    copy of the form on the page), or None if one can't be found."""
    wants = [("ssn", form["ssn"], "ssn"), ("ein", form["ein"], "tax id")]
    if form.get("control"):
        wants.append(("control", form["control"], "employee id"))
    wants += [("first", form["first"], "name"), ("last", form["last"], "name")]
    street, city = form["address"].split("\n")
    wants += [("street", street, "street address"), ("city", city, "street address")]
    if form["household"]:
        wants += [("emp", form["employer_name"], "name"), ("empst", form["employer_street"], "street address")]
    wants.append(("stid", form["stid1"], "tax id"))
    spans, taken = [], []
    for key, value, label in sorted(wants, key=lambda w: -len(w[1])):   # longest first
        hits = []
        for _ in range(copies):
            hit = (find_fuzzy if fuzzy else find_exact)(text, value, taken + hits)
            if hit is None:
                return None
            hits.append(hit)
        if not fuzzy and find_exact(text, value, taken + hits) is not None:
            return None                       # more occurrences than copies: something else matches the value
        taken += hits
        spans += [(h[0], h[1], label) for h in hits]
    return sorted(spans)


def docs(n, seed):
    rng = random.Random(seed)
    us = Faker("en_US")
    us.seed_instance(seed)
    fakes = {l: Faker(l) for l in set(LOCALES)}
    for i, f in enumerate(fakes.values()):
        f.seed_instance(seed + i + 1)
    out, tries = [], 0
    while len(out) < n and tries < n * 4:
        tries += 1
        page = rng.choice(PAGES)
        form = one_form(rng, fakes[rng.choice(LOCALES)], us)
        mode = rng.choices(["layout", "raw", "order", "pypdf", "ocr"], [3, 2, 2, 1, 5])[0]
        fuzzy = mode == "ocr"
        copies = 1 if fuzzy else 2
        pdf = fill(page, [form] * copies)         # a page carries two copies of one person's W-2
        text = ocr(pdf, rng) if fuzzy else pypdf_text(pdf) if mode == "pypdf" else pdftotext(pdf, mode)
        text = re.sub(r"\n{3,}", "\n\n", text).strip("\n")
        spans = labelled(text, form, fuzzy, copies)
        if spans is None or any(spans[i][1] > spans[i + 1][0] for i in range(len(spans) - 1)):
            continue
        out.append((text, spans))
    return out


if __name__ == "__main__":
    import sys
    for t, s in docs(int(sys.argv[1]) if len(sys.argv) > 1 else 3, 11):
        print(t[:1800], "\n", [(t[a:b], l) for a, b, l in s], "\n" + "=" * 70)
