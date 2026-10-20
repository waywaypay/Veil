"""Field parser for digital W-2s: reads a PDF's text layer with word coordinates (pdftotext -bbox), finds the labels of the
private boxes (SSN, EIN, control number, employee name, address, state ID) and hides the value beside or below each one,
plus any SSN/EIN-shaped string anywhere.  No model, no OCR.  It only decides which words of the text layer to hide.

parse(pdf_bytes) -> (words, hide)  where words = [(x0, y0, x1, y1, text)] and hide is the set of word indexes to hide."""
import html
import re
import subprocess
import tempfile

# private boxes: label text -> kind.  Written from the IRS form's captions and the usual wording of payroll software;
# the chunk is lower-cased and a leading box letter or number removed first.
PRIVATE = [
    ("ssn", r"(employee'?s?\s+)?(social security (number|no)|ssn)\b"),
    ("ein", r"(employer'?s?\s+)?(federal\s+)?(identification number|ein|fein)\b"),
    ("control", r"(control number|file number|emp\.? ?#|employee id)"),
    ("name", r"(employee'?s?\s+)?((first )?name\b|last name|suff)"),
    ("address", r"(employee'?s?\s+)?(name,?\s+(and\s+|&\s+)?)?address"),
    ("stid", r"(employer'?s?\s+)?state\s+(employer\s+)?(id|ident)|employer\s+state\s+(id|ident)"),
]
# other captions, so a value is never read past the next box
OTHER = re.compile(
    r"^(wages|social security (wages|tax)|medicare (wages|tax)|federal income|allocated|advance|dependent care|nonqualified|"
    r"statutory|retirement|third.party|other\b|state wages|state income|local wages|local income|locality|void|copy|form w|"
    r"wage and tax|department|omb|for official|cat\.|do not|this information|employer'?s?\s+(name|address)|city, state|"
    r"employer\b|company\b|box\b|value\b|description|questions|13\b|14\b|15\b|16\b|17\b|18\b|19\b|20\b|12[a-d]?\b|code\b|"
    r"gross wages|federal (tax|w/h)|ss (wages|tax)|medicare|state id|state\s*/)")


def read(pdf):
    with tempfile.NamedTemporaryFile(suffix=".pdf") as t:
        t.write(pdf)
        t.flush()
        out = subprocess.run(["pdftotext", "-bbox", "-nopgbrk", t.name, "-"], capture_output=True, text=True, timeout=60).stdout
    return [(float(a), float(b), float(c), float(d), html.unescape(w))
            for a, b, c, d, w in re.findall(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>', out)]


def chunks(words):
    """Words joined into chunks: words on one line that are close together.  [(x0, y0, x1, y1, text, [word indexes])]"""
    order = sorted(range(len(words)), key=lambda i: ((words[i][1] + words[i][3]) / 2, words[i][0]))
    lines, cur = [], []
    for i in order:
        w = words[i]
        if cur and abs((w[1] + w[3]) / 2 - (words[cur[0]][1] + words[cur[0]][3]) / 2) > 0.45 * (w[3] - w[1]):
            lines.append(cur)
            cur = []
        cur.append(i)
    if cur:
        lines.append(cur)
    out = []
    for ln in lines:
        ln.sort(key=lambda i: words[i][0])
        grp = [ln[0]]
        for i in ln[1:]:
            h = words[i][3] - words[i][1]
            if words[i][0] - words[grp[-1]][2] > 1.1 * h:
                out.append(grp)
                grp = []
            grp.append(i)
        out.append(grp)
    res = []
    for g in out:
        ws = [words[i] for i in g]
        res.append((min(w[0] for w in ws), min(w[1] for w in ws), max(w[2] for w in ws), max(w[3] for w in ws),
                    " ".join(w[4] for w in ws), g))
    return res


def classify(text):
    t = text.lower().replace("’", "'").replace("‘", "'").strip().rstrip(":")
    t = re.sub(r"^(\d{1,2}|[a-f](/[a-f])?)\s+(?=[a-z])", "", t)          # box letter / number
    if len(t) > 70 or sum(c.isdigit() for c in t) > 0.35 * max(1, len(t)):
        return None
    for kind, pat in PRIVATE:
        if (re.search(pat, t) if kind == "stid" else re.match(pat, t)):
            return kind
    if OTHER.match(t):
        return "other"
    return None


def inline_value(words, c, kind):
    """Word indexes of a value written in the same chunk as its label: 'Label: value' or 'Name value'."""
    idx = c[5]
    for j, i in enumerate(idx[:-1]):
        if words[i][4].endswith(":"):
            return idx[j + 1:]
    t = c[4].lower().replace("’", "'")
    if kind == "name" and re.match(r"^(employee'?s?\s+)?name\s+\S", t) and not re.search(r"first name|last name|initial", t):
        k = len(re.match(r"^(employee'?s?\s+)?name", t).group(0).split())
        return idx[k:]
    return []


_STREET = re.compile(r"^\d{1,6}[A-Za-z]?\s+[A-Za-z#]")
_CITY = re.compile(r"^[A-Za-z][A-Za-z .'\-]+,?\s+[A-Za-z]{2}\s+\d{5}(-\d{4})?[\s+*]*$")
_ONE_LINE = re.compile(r"^\d{1,6}[A-Za-z]?\s+\S.*,\s*[A-Za-z][A-Za-z .'\-]+,?\s+[A-Za-z]{2}\s+\d{5}")


def address_pass(words, ch, kinds, hide):
    """A street line with its city/state/ZIP line below (or both on one line) is a person's address unless it belongs to
    an employer block; the line above it, when it is a name and not a caption, goes with it."""
    def col(a, b):
        return b[2] > a[0] - 14 and b[0] < a[2] + 14

    def employer_block(c):
        h = max(1.0, c[3] - c[1])
        cands = [d for d in ch if d is not c and d[3] <= c[1] + 0.3 * h and c[1] - d[3] < 8 * h and col(c, d)
                 and re.search(r"employer|company|employee|payer|issued by|\bfrom\b", d[4].lower())]
        if not cands:
            return False
        near = max(cands, key=lambda d: d[3])
        t = near[4].lower()
        return bool(re.search(r"employer|company|payer|issued by", t)) and "employee" not in t

    for n, c in enumerate(ch):
        if not _STREET.match(c[4]) or kinds[n] is not None:
            continue
        h = max(1.0, c[3] - c[1])
        lines = [n]
        if not _ONE_LINE.match(c[4]):
            below = [m for m, d in enumerate(ch) if d[1] >= c[3] - 0.3 * h and d[1] - c[3] < 2.2 * h and col(c, d) and _CITY.match(d[4])]
            if not below:
                continue
            lines.append(min(below, key=lambda m: ch[m][1]))
        if employer_block(c):
            continue
        for m in lines:
            hide.update(ch[m][5])
        above = [m for m, d in enumerate(ch) if d[3] <= c[1] + 0.3 * h and c[1] - d[3] < 2.2 * h and col(c, d) and kinds[m] is None
                 and not re.search(r"\d", d[4]) and 1 <= len(d[4].split()) <= 5 and d[4].lower() not in ("employee", "employer")]
        if above:
            m = max(above, key=lambda m: ch[m][3])
            if not re.search(r"employee|employer|address|name|copy|wage|statement|form", ch[m][4].lower()):
                hide.update(ch[m][5])


def parse(pdf):
    words = read(pdf)
    ch = [c for c in chunks(words) if (c[3] - c[1]) <= 2 * (c[2] - c[0])]     # not the rotated margin text
    kinds = [classify(c[4]) for c in ch]
    hide = set()
    left = min((c[0] for c, k in zip(ch, kinds) if k not in (None, "other")), default=0)
    for n, c in enumerate(ch):
        kind = kinds[n]
        if kind in (None, "other"):
            continue
        h = max(1.0, c[3] - c[1])
        cy = (c[1] + c[3]) / 2
        inline = inline_value(words, c, kind)
        if inline:
            hide.update(inline)
            continue
        got = []
        # 1. below, in the label's column, whole lines: grids and stacked layouts
        lo, hi = c[0] - 14, (c[2] if c[2] - c[0] >= 80 else c[0] + (200 if kind == "control" else 70)) + 14
        limit = 2 if kind == "address" else 1

        def column(m, d=None):
            d = ch[m]
            return d[2] > lo and d[0] < hi

        def take(cands, step):
            """cands: chunk indexes in reading direction; whole lines in the column until a label or a gap."""
            out, lines, last = [], 0, None
            for m in cands:
                d = ch[m]
                if kinds[m] is not None:
                    break
                if last is not None and abs(d[1] - last) < 0.5 * h:      # same line as the last one taken
                    out.append(m)
                    continue
                if lines >= limit:
                    break
                if lines and abs(d[1] - last) > 2.6 * h:
                    break
                out.append(m)
                lines += 1
                last = d[1]
            return out

        below = sorted((m for m, d in enumerate(ch) if d[1] >= c[3] - 0.3 * h and d[1] - c[3] < 4 * h and column(m)), key=lambda m: (ch[m][1], ch[m][0]))
        got = take(below, 1)
        # 2. above the label (the IRS form puts the address lines above its caption)
        if not got and kind == "address":
            above = sorted((m for m, d in enumerate(ch) if d[3] <= c[1] + 0.3 * h and c[1] - d[3] < 9 * h and column(m)), key=lambda m: (-ch[m][3], ch[m][0]))
            got = take(above, -1)
        # 3. to the right on the same line, for a label in the left column: ledger and table layouts
        if not got and c[0] <= left + 6:
            right = sorted((m for m, d in enumerate(ch) if m != n and d[0] >= c[2] - 1 and abs((d[1] + d[3]) / 2 - cy) < 0.5 * h and d[0] - c[2] < 320),
                           key=lambda m: ch[m][0])
            for m in right:
                if kinds[m] is not None:
                    break
                if len(ch[m][4]) <= 2 and not got:       # a lone box number or letter, not a value
                    break
                got.append(m)
            # a second line of the same value in the value column (an address on two lines), unless that line has its own label
            if got and kind == "address":
                r = ch[got[0]]
                nxt = sorted((m for m, d in enumerate(ch) if m not in got and d[1] >= r[3] - 0.3 * h and d[1] - r[3] < 1.8 * h and d[2] > r[0] - 14 and d[0] < r[2] + 60),
                             key=lambda m: ch[m][1])
                for m in nxt[:1]:
                    d = ch[m]
                    same_line = [x for x in ch if abs((x[1] + x[3]) / 2 - (d[1] + d[3]) / 2) < 0.5 * h and x[2] <= r[0] + 1]
                    if kinds[m] is None and not any(x[0] <= left + 6 for x in same_line):
                        got.append(m)
        for m in got:
            hide.update(ch[m][5])
    address_pass(words, ch, kinds, hide)
    # SSN / EIN shaped strings anywhere
    for i, w in enumerate(words):
        if re.fullmatch(r"\d{3}-\d{2}-\d{4}|\d{2}-\d{7}|[xX*]{3}-[xX*]{2}-\d{4}", w[4]):
            hide.add(i)
    return words, hide
