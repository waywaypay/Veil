"""Stress tests for the taxpayer-ID placeholders: many IDs, written every way K-1s, OCR and people
write them, in many surroundings, plus synthetic K-1 PDFs run through the parser and the agent.

A leak is the ID, or eight of its digits in a row, still readable in what the model would get."""

import json
import os
import random
import re
import zlib

import pytest

from veil import US_TAX_K1  # noqa: E402
from veil import TaxIdRedactor as _TaxIdRedactor  # noqa: E402


def TaxIdRedactor():
    return _TaxIdRedactor(US_TAX_K1)

DASHES = ["-", "\u2010", "\u2011", "\u2012", "\u2013", "\u2014", "\u2015", "\u2212", "\ufe58", "\ufe63", "\uff0d"]
SPACES = [" ", "\u00a0", "\u2007", "\u2009", "\u202f"]
LOOKALIKE = {"0": "O", "1": "l", "5": "S", "8": "B"}


def _groups(digits, kind):
    return (digits[:2], digits[2:]) if kind == "ein" else (digits[:3], digits[3:5], digits[5:])


def _ocr_misread(digits, kind):
    text = "-".join(_groups(digits, kind))
    i = next((i for i, c in enumerate(text) if c in LOOKALIKE), None)
    return text if i is None else text[:i] + LOOKALIKE[text[i]] + text[i + 1:]


FORMATS = {
    **{f"dash U+{ord(d):04X}": (lambda d: lambda x, k: d.join(_groups(x, k)))(d) for d in DASHES},
    **{f"space U+{ord(s):04X}": (lambda s: lambda x, k: s.join(_groups(x, k)))(s) for s in SPACES},
    "spaces around dash": lambda x, k: " - ".join(_groups(x, k)),
    "space before dash": lambda x, k: " -".join(_groups(x, k)),
    "dots": lambda x, k: ".".join(_groups(x, k)),
    "slashes": lambda x, k: "/".join(_groups(x, k)),
    "bare": lambda x, k: x,
    "line break after dash": lambda x, k: "-\n".join(_groups(x, k)),
    "zero-width spaces": lambda x, k: "\u200b-".join(_groups(x, k)),
    "soft hyphen between digits": lambda x, k: "\u00ad".join(x),
    "fullwidth digits": lambda x, k: "-".join(_groups(x, k)).translate(
        str.maketrans("0123456789", "\uff10\uff11\uff12\uff13\uff14\uff15\uff16\uff17\uff18\uff19")),
    "OCR misread digit": _ocr_misread,
}

CONTEXTS = {
    "alone": "{id}",
    "sentence": "Please file under {id} before April.",
    "SSN label": "SSN: {id}",
    "Soc. Sec. No. label": "Soc. Sec. No. {id}",
    "EIN label, next line": "Employer identification number\n{id}",
    "label after": "{id} (TIN)",
    "IRS item E": ("E  Partner's SSN or TIN (Do not use TIN of a disregarded entity. See instructions.)\n"
                   "F  Name, address, city, state, and ZIP code for partner entered in E.\nRowan N. Exemplar\n{id}\n"
                   "41 Main Street\nBoston, MA 02110"),
    "table row": "Name | TIN | Share\nRowan N. Exemplar | {id} | 12.5%",
    "file name": "K-1_Exemplar_{id}.pdf",
    "JSON": '{{"partner_tin": "{id}", "amount": "1250.00"}}',
    "next to an amount": "{id} 1,250",
}


def leaked(digits, text):
    flat = re.sub(r"\D", "", text.translate(str.maketrans(
        "\uff10\uff11\uff12\uff13\uff14\uff15\uff16\uff17\uff18\uff19OlSB", "0123456789" "0158")))
    return digits in flat or digits[:8] in flat or digits[1:] in flat


def _ids(seed, n=12):
    rng = random.Random(seed)
    for _ in range(n):
        yield "ssn", f"{rng.randint(1, 899):03d}{rng.randint(1, 99):02d}{rng.randint(1, 9999):04d}"
        yield "itin", f"9{rng.randint(0, 99):02d}{rng.choice([70, 78, 88, 94, 99])}{rng.randint(1, 9999):04d}"
        yield "ein", f"{rng.choice([13, 20, 46, 82, 98])}{rng.randint(0, 9999999):07d}"


@pytest.mark.parametrize("fmt", list(FORMATS))
def test_no_format_leaks_in_any_surroundings(fmt):
    misses = []
    for kind, digits in _ids(seed=zlib.crc32(fmt.encode())):
        written = FORMATS[fmt](digits, kind)
        for context, template in CONTEXTS.items():
            text = template.format(id=written)
            # Left alone on purpose: "20 1250000" split only by a space is a K-1 box number and an
            # amount as often as an EIN whose prefix could be a box number; a label decides it.
            if kind == "ein" and fmt.startswith("space U+") and int(digits[:2]) <= 23 and \
                    context in ("alone", "sentence", "file name", "next to an amount"):
                assert TaxIdRedactor().redact_text(text) == text
                continue
            out = TaxIdRedactor().redact_text(text)
            if leaked(digits, out):
                misses.append((context, text, out))
    assert not misses, f"{len(misses)} leaks, e.g. {misses[:3]}"


NOT_TAXPAYER_IDS = [
    "1,234,567", "(1,234,567)", "-1,234,567", "$1,234,567", "1,234,567.89", "123456789.00", "$123456789",
    "$ 123456789", "123,456,789", "(123,456,789)", "12345678", "1234567890", "1 234 567",
    "Ordinary business income (loss) 1 123,456", "Box 20 Z 12,345 STMT", "11 ZZ* 2,500",
    "12/31/2024", "2024-12-31", "12-31-2024", "12.31.2024", "Dec 31, 2024", "20241231", "2024 12 31",
    "tax year beginning 07/01/2024 ending 06/30/2025",
    "(212) 555-1234", "212-555-1234", "212.555.1234", "1-800-829-1040", "+1 212 555 1234",
    "Boston, MA 02110", "Boston, MA 02110-1234", "02110 1234", "PO Box 12345",
    "Schedule K-1 (Form 1065) 2024", "OMB No. 1545-0123", "Cat. No. 11394R", "www.irs.gov/Form1065",
    "Page 2 of 3", "Line 20AE", "20-Z", "13-ZZ", "Section 199A", "Form 8949, Part II, line 1",
    "Account 1234-5678-9012", "Wire ref 2024-00123", "Investor No. 000123", "Ref: K1-2024-001",
    "Profit 12.3456%", "Beginning 25.000000% Ending 25.000000%", "XXX-XX-6789", "***-**-6789",
]


def test_amounts_dates_phone_numbers_and_form_text_are_left_alone():
    changed = [(t, TaxIdRedactor().redact_text(t)) for t in NOT_TAXPAYER_IDS]
    assert [c for c in changed if c[0] != c[1]] == []


SPECIMENS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "k1_specimens.json")


def test_real_k1_specimens_lose_every_taxpayer_id_and_nothing_else():
    """Fictional K-1 specimens, as Snowman's PDF reader read them."""
    tin = re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b\d{2}-\d{7}\b")
    with open(SPECIMENS) as f:
        specimens = json.load(f)
    for specimen in specimens:
        name, pages = specimen["file"], specimen["data"]["pages"]
        printed = {m for text in pages for m in tin.findall(text)}
        redactor = TaxIdRedactor()
        out = [redactor.redact_text(text) for text in pages]
        assert printed, name
        assert set(redactor._real.values()) == printed, name   # hid exactly the IDs printed on it
        assert not any(leaked(re.sub(r"\D", "", t), o) for t in printed for o in out), name


SSN, EIN = "518206194", "471058392"
LEAKED_ONCE = [
    # PDFs that draw each group (or each digit) as its own text object give one per line.
    "E  Partner's SSN or TIN\n 518\n20\n6194\nF  Partner's name, address, city, state, and ZIP code",
    "A  Partnership's employer identification number\n 47\n1058392\nE  Partner's SSN or TIN",
    "Partner identifying number\n5\n1\n8\n2\n0\n6\n1\n9\n4\nPartner's name",
    "Investor\nTax ID\nDistribution\nJane Q. Doe\n518\n20\n6194\n47,950\nFund EIN\n47\n1058392",
    "Partner 518\r\n20\r\n6194 filed", "Partner 518\n-20\n-6194 filed", "Partner 518-\n\n20-\n\n6194 filed",
    # Comb boxes, table cells, wide spacing.
    "|5|1|8|2|0|6|1|9|4|", "SSN 518 | 20 | 6194", "SSN [5][1][8]-[2][0]-[6][1][9][4]",
    "Jane Doe 5 1 8 2 0 6 1 9 4 Testburg", "Partner 518    20    6194 filed", "Fund 47    1058392 filed",
    "SSN: 5    1    8    2    0    6    1    9    4", "SSN **518**-**20**-**6194**",
    # CSV rows: a comma after the number isn't money.
    "Investor,TIN,Distribution\nJane Doe,518206194,47950\nJohn Roe,471058392,30000",
    # Commas between groups, and 3-3-3 typed with single spaces.
    "Partner 518,20,6194 filed", "Fund 47,1058392 filed", "Partner 518, 20, 6194", "Partner 518 206 194 filed",
    "518 206 194 is my number", "Social 518 206 194", "Partner 518\u00a0206\u00a0194 filed",
    # OCR: an extra digit, lookalike letters, a digit glued to the label.
    "SSN 1518-20-6194", "SSN 518-20-61941", "EIN 47-10583921", "Partner 518-20-61944 filed",
    "SSN 518-20-6i94", "Partner 518-20-b194", "Partner 518-20-61q4", "Partner 518-20-6L94",
    "Partner 518-z0-6194", "Partner Sl8-2O-6194", "Partner Sl8-2O-6l94", "SSN5l8-20-6194", "Partner 518-2X-6194",
    # Other groupings, and labels written other ways or after the number.
    "Partner 518-206-194 filed", "Fund 47-105-8392 filed", "Partner 5182-06-194", "Fund 471-058392",
    "Employer I.D. No. 518 206 194", "Fed. I.D. # 518 206 194", "Tax I.D. 518 206 194", "I.D. No. 518 206 194",
    "Taxpayer No. 518 206 194", "ATIN 518 206 194", "Tax Reg. No. 518 206 194", "SSNs 518 206 194",
    "IRS number 518 206 194", "518 206 194 (SSN)", "SSN (see page 2): 518 206 194",
    "Partner's SSN or TIN (Form W-9 on file)\n518 206 194",
    # Separators.
    "Doe_518_20_6194_K1.pdf", "Partner 518_20_6194 filed", "Partner 518\u00b720\u00b76194 filed",
    "Partner 518--20--6194 filed", "Partner 518 -- 20 -- 6194 filed", "Partner 518\u30fc20\u30fc6194",
    "Partner 518\uff0e20\uff0e6194", "Partner 518\u058a20\u058a6194", "Partner 518~20~6194",
    # Encodings the model can read.
    "SSN 518&ndash;20&ndash;6194", "SSN 518&#8209;20&#8209;6194", "https://portal/x?tin=518%2D20%2D6194",
    'Paste: {"ssn": "518\\u201320\\u20136194"}', "No K-1 file has id '518\\xa020\\xa06194'.",
    # Digits and marks from elsewhere in Unicode.
    "Partner \u2075\u00b9\u2078-\u00b2\u2070-\u2076\u00b9\u2079\u2074",
    "Partner \u2464\u2460\u2467-\u2461\u24ea-\u2465\u2460\u2468\u2463", "Partner 5\u03001\u03008-20-6194",
    "Partner 518\ufe0f20\ufe0f6194", "Partner 518\U000e002020\U000e00206194", "Partner 518\u316420\u31646194",
    "Partner 518\u280020\u28006194", "Partner 518\x0020\x006194",
]


@pytest.mark.parametrize("text", LEAKED_ONCE)
def test_cases_that_once_leaked(text):
    out = TaxIdRedactor().redact_text(text)
    assert not leaked(SSN, out) and not leaked(EIN, out), out


def test_a_two_column_layout_leaves_at_most_the_last_four():
    for text in ("EIN\n47-\nSSN/TIN\n518-20-\n1058392\n6194",
                 "E Partner's SSN or TIN     F Partner's name\n518-20-     Jane Q. Doe\n6194        12 Elm St"):
        r = TaxIdRedactor()
        out = r.redact_text(text)
        assert "518" not in out and r.restore_text(out) == text


HID_WHAT_IT_SHOULDNT = [
    # Dates, near a label word or not.
    "Ignore the TIN for now; the distribution was paid on 03/15/2025.",
    "No SSN on this one. Distribution date 03-15-2025, amount 25,000.",
    "Partner: Jane Q. Doe   TIN: XXX-XX-XXXX\nStatement of distributions\nDate 03/15/2025   Amount 25,000",
    "Investor Tax ID: on file with administrator\nFor the period 01/01/2025 through 12/31/2025",
    # Words that start like a label.
    "Einstein Ventures II, LP - capital call due 04/01/2025", "Tina Marsh, distribution 03/15/2025",
    "Feinberg Growth Partners, LP\nStatement of distributions\nDate 03/15/2025 Amount 25,000",
    "Social Sector Impact Fund, LP\nDistribution 03/15/2025", "Tinley Park, IL 60477-1234",
    # Amounts, alone and next to box numbers.
    "Interest income 312.45 1250.00", "Distribution   250.00   2025-03-15", "Paid 500.00 2025 estimated tax",
    "Box 20 1250000", "11  2500000", "19 A Distributions\n19 1500000", "13 ZZ 1250000",
    "Record Fund II 1250000 as the 2025 distribution", "Ending profit share 12.3456789%", "Price 101.25 1000 par",
    "Total partnership capital 125000000", "Net loss (125000000)", "USD 125000000", "$  125000000",
    "Tax ID: on file\nInterest 250.00 34.50", "Investor ID 1234567", "K1|Fund III|20251231|", "|1250000|",
    "Pinecrest Gate Real Es\u00adtate Fund III, LP", "Rowan N. Exemplar\u200f",
    # Commas and spaces that belong to amounts and lists.
    "Boxes 1,2,3,4,5,6,7,8,9 are blank", "Box,Amount\n20,1250000", "Amounts 125   300   175",
    "Beginning\n125\n300\n175", "Total 1,250,000", "$518,206,194", "123,456,789", "100,250,300",
    "Q1, 2025, 1250, 300",
]


@pytest.mark.parametrize("text", HID_WHAT_IT_SHOULDNT)
def test_cases_that_once_hid_what_they_shouldnt(text):
    assert TaxIdRedactor().redact_text(text) == text


def test_a_placeholder_is_put_back_as_the_text_it_replaced():
    for text in ("Invoice 100-25-2024", "Brokerage acct 12-3456789", "CUSIP 037833100", "Boston, MA 021101234",
                 "Smith_K1_518-20-6194.pdf", "Fund-47-1058392_2025.pdf", "DoeJane518-20-6194.pdf",
                 "Partner TIN:\u00a0518\u00a0206\u00a0194", "Units held 25.1234567"):
        r = TaxIdRedactor()
        out = r.redact_text(text)
        assert out != text and r.restore_text(out) == text, (text, out)


def test_placeholder_shaped_text_in_a_document_isnt_mistaken_for_one():
    r = TaxIdRedactor()
    out = r.redact_text("the fund showed as TIN_001 Holdings")
    assert "TIN_001" not in out
    r.redact_text("Partner 518206194")
    assert r.restore_text(out) == out   # never turned into the partner's number


def test_keys_and_long_whole_numbers_in_structures_are_hidden_too():
    r = TaxIdRedactor()
    assert r.redact({"518-20-6194": 518206194, "n": [471058392, 2024]}) == {"SSN_001": "SSN_001",
                                                                             "n": ["TIN_001", 2024]}


def test_a_label_in_one_string_counts_for_the_others():
    r = TaxIdRedactor()
    out = r.redact({"file": "Doe K-1 518 206 194.pdf", "page": 1, "text": "Partner's SSN: 518 206 194"})
    assert out["file"] == "Doe K-1 TIN_001.pdf" and out["text"] == "Partner's SSN: TIN_001"


def test_a_page_full_of_numbers_stays_fast():
    import time
    page = "\n".join(f"Holding {i}: CUSIP {100000000 + i * 7919} units 1,000" for i in range(600))
    began = time.perf_counter()
    TaxIdRedactor().redact_text(page)
    assert time.perf_counter() - began < 2.0
