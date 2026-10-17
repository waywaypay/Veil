"""veil under the circumstances documents come in: the same documents (NVIDIA's Nemotron-PII, never tuned on)
written in capitals or lower case, as HTML, inside JSON, quoted in an email thread, with ragged whitespace, typed
into a chat; and as files read by veil.files: a PDF with its text, a scanned PDF, a clean image, small print, a
phone photo of a page, a fax, a page turned on its side, two columns, a grey page.

Each document's labelled personal details are looked for in what veil makes of the transformed text: the words of
the original are matched to the words veil was given (veil.files' OCR output, or the transformed text), and a
detail counts as found when every word of it was hidden.  Run with OMP_THREAD_LIMIT=1.

python conditions.py <nemotron parquet> <n> <out.json> [conditions,to,run]"""

import html
import io
import json
import math
import random
import sys
import textwrap
from multiprocessing import Pool

import external
import gretel as bench
import word
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from veil import FINANCE, Redactor
from veil.files import read_text

FONTS = "/usr/share/fonts/truetype"
SANS = f"{FONTS}/liberation/LiberationSans-Regular.ttf"
SERIF = f"{FONTS}/liberation/LiberationSerif-Regular.ttf"


def page(text, font=SERIF, size=30, width=1700, chars=95, columns=1, bg=255):
    """The text set on a page, as at 200 DPI: 30 pixels is an 11 point letter."""
    f = ImageFont.truetype(font, size)
    lines = []
    for para in text.split("\n"):
        lines += textwrap.wrap(para, chars // columns, replace_whitespace=False) or [""]
    step = int(size * 1.35)
    per_column = math.ceil(len(lines) / columns)
    img = Image.new("L", (width, max(400, step * per_column + 160)), bg)
    d = ImageDraw.Draw(img)
    for n, line in enumerate(lines):
        c, row = divmod(n, per_column)
        d.text((80 + c * (width - 80) // columns, 80 + step * row), line, font=f, fill=0)
    return img


def png(img, kind="PNG", **kw):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, kind, **kw)
    return buf.getvalue()


def photo(img, seed):
    """A phone's photo of the page: seen a little from the side, lit unevenly, soft, compressed."""
    rnd = random.Random(seed)
    w, h = img.size
    d = 0.04
    quad = [rnd.uniform(0, d) * w, rnd.uniform(0, d) * h, rnd.uniform(0, d) * w, h - rnd.uniform(0, d) * h,
            w - rnd.uniform(0, d) * w, h - rnd.uniform(0, d) * h, w - rnd.uniform(0, d) * w, rnd.uniform(0, d) * h]
    img = img.transform((w, h), Image.QUAD, quad, Image.BILINEAR, fillcolor=255)
    shade = Image.linear_gradient("L").resize((w, h)).point(lambda v: 255 - v // 3)   # darker to one side
    img = Image.blend(img, shade, 0.25)
    img = img.filter(ImageFilter.GaussianBlur(1.0)).resize((w * 3 // 4, h * 3 // 4))
    return Image.open(io.BytesIO(png(img, "JPEG", quality=60)))


def fax(img):
    """A fax: 100 DPI, black and white."""
    small = img.resize((img.width // 2, img.height // 2), Image.BILINEAR)
    return small.point(lambda v: 0 if v < 150 else 255).convert("1").convert("L")


def grey(img, seed):
    """A grey, mottled page, as a photocopy of coloured paper."""
    rnd = random.Random(seed)
    noise = Image.effect_noise(img.size, 40).filter(ImageFilter.GaussianBlur(3))
    tint = Image.new("L", img.size, 200 + rnd.randrange(20))
    return Image.blend(Image.composite(img, tint, img.point(lambda v: 255 if v > 128 else 0)), noise, 0.2)


def pdf(text, scanned=False):
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    if scanned:
        img = page(text, size=21, width=1275, chars=95)   # 150 DPI
        c.drawImage(ImageReader(img.convert("RGB")), 0, letter[1] - img.height * 72 / 150,
                    width=img.width * 72 / 150, height=img.height * 72 / 150)
    else:
        y = letter[1] - 54
        for para in text.split("\n"):
            for line in textwrap.wrap(para, 100) or [""]:
                if y < 54:
                    c.showPage()
                    y = letter[1] - 54
                c.setFont("Helvetica", 9)
                c.drawString(54, y, line)
                y -= 12
    c.save()
    return buf.getvalue()


def html_of(text):
    return "<html><body>" + "".join(f"<p>{html.escape(p)}</p>\n" for p in text.split("\n")) + "</body></html>"


def ragged(text, seed):
    rnd = random.Random(seed)
    return "".join(c + ("  " if c == " " and rnd.random() < 0.15 else "\t" if c == " " and rnd.random() < 0.03 else "")
                   for c in text).replace("\n", "\r\n")


TEXT = {
    "plain": lambda t, i: t,
    "UPPER CASE": lambda t, i: t.upper(),
    "lower case": lambda t, i: t.lower(),
    "HTML": lambda t, i: html_of(t),
    "inside JSON": lambda t, i: json.dumps({"id": i, "note": t}),
    "quoted email": lambda t, i: "On Mon, the sender wrote:\n" + "\n".join("> " + x for x in t.split("\n")),
    "ragged whitespace": lambda t, i: ragged(t, i),
}
FILES = {
    "PDF with text": lambda t, i: (pdf(t), "application/pdf"),
    "scanned PDF": lambda t, i: (pdf(t, scanned=True), "application/pdf"),
    "clean image": lambda t, i: (png(page(t)), "image/png"),
    "sans-serif image": lambda t, i: (png(page(t, font=SANS)), "image/png"),
    "small print": lambda t, i: (png(page(t, size=17, width=1000)), "image/png"),
    "phone photo": lambda t, i: (png(photo(page(t), i), "JPEG", quality=70), "image/jpeg"),
    "fax": lambda t, i: (png(fax(page(t))), "image/png"),
    "grey page": lambda t, i: (png(grey(page(t), i)), "image/png"),
    "two columns": lambda t, i: (png(page(t, columns=2, width=2400, chars=150)), "image/png"),
    "turned sideways": lambda t, i: (png(page(t).rotate(90, expand=True, fillcolor=255)), "image/png"),
    "Word document": lambda t, i: word.plain(t, i),
    "Word form (a table)": lambda t, i: word.form(t, i),
    "Word header and footer": lambda t, i: word.header_footer(t, i),
    "Word form with two fields a row": lambda t, i: word.wide_form(t, i),
    "Word form aligned with tabs": lambda t, i: word.tab_form(t, i),
    "Word text boxes": lambda t, i: word.text_boxes(t, i),
    "Word tracked changes": lambda t, i: word.tracked(t, i),
    "Word from LibreOffice": lambda t, i: word.libreoffice(t, i),
    "Word with a pasted scan": lambda t, i: word.pasted_scan(t, i, page),
}


def work(args):
    i, text, only = args
    out = {}
    for name, make in FILES.items():
        if only and name not in only:
            continue
        try:
            out[name] = read_text(*make(text, i))
        except Exception as exc:   # a file veil can't read: nothing found in it
            out[name] = f"<error {type(exc).__name__}>"
    return i, out


def score(rows, inputs, typed=False):
    """Found and over-redacted, matching each original's words to the words of what veil was given."""
    def fn(t):
        return Redactor(FINANCE).redact_text(t, typed=typed)

    hit = tot = fp = fp_tot = 0
    for (text, spans), given in zip(rows, inputs):
        out = fn(given)
        _, kept_given = bench.redacted_mask(given, out)
        ws = bench.words(text)
        m = bench.word_map(text, given)
        kept = [j is not None and kept_given[j] for j in m]   # a word the reading lost isn't in the output
        seen = [j is not None for j in m]
        personal = [False] * len(ws)
        for sp in spans:
            idx = [j for j, (_, s, e) in enumerate(ws) if s < sp["end"] and e > sp["start"]]
            if sp["label"] not in external.ORDINARY:
                for j in idx:
                    personal[j] = True
            idx = [j for j in idx if ws[j][0].lower() not in bench.TITLES]
            if idx and sp["label"] in external.LABEL:
                tot += 1
                hit += all(not kept[j] for j in idx)
        for j, (w, _, _) in enumerate(ws):
            if not personal[j] and seen[j] and w.lower() not in bench.TITLES:
                fp_tot += 1
                fp += not kept_given[m[j]]
    return hit / tot, fp / max(1, fp_tot)


def main(path, n, out_path, only=()):
    rows = [r for r in external.load("nemo", path, 20 * n, 7) if len(r[0]) < 2500][:n]
    results = {}
    for name, make in TEXT.items():
        if not only or name in only:
            results[name] = score(rows, [make(t, i) for i, (t, _) in enumerate(rows)])
    if not only or "typed" in only:
        results["typed in a chat (lower case)"] = score(rows, [t.lower() for t, _ in rows], typed=True)
    with Pool(4) as pool:
        files = dict(pool.map(work, [(i, t, only) for i, (t, _) in enumerate(rows)], chunksize=1))
    for name in FILES:
        if not only or name in only:
            results[name] = score(rows, [files[i][name] for i in range(len(rows))])
    json.dump({"docs": len(rows), "results": results}, open(out_path, "w"), indent=1)
    for name, (found, over) in results.items():
        print(f"  {name:30} {found:6.1%} found   {over:6.2%} other words hidden")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), sys.argv[3], tuple(sys.argv[4].split(",")) if len(sys.argv) > 4 else ())
