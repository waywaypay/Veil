"""Render each document to an image, clean and degraded like a scan (125 DPI, a slight tilt, blur, speckle,
JPEG), and keep Tesseract's words and their boxes, which veil.files.reflow turns into text.  Run with
OMP_THREAD_LIMIT=1, or Tesseract's threads fight over the CPUs."""

import io
import json
import random
import sys
import textwrap
from multiprocessing import Pool

import pandas as pd
import pytesseract
from PIL import Image, ImageDraw, ImageFilter, ImageFont

KEYS = ("block_num", "par_num", "line_num", "word_num", "left", "top", "width", "height", "conf", "text")


def data(img):
    """Tesseract's words with their boxes, as veil.files reads them."""
    d = pytesseract.image_to_data(img.convert("RGB"), output_type=pytesseract.Output.DICT)
    return {k: d[k] for k in KEYS}


FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)  # ~11pt at 200 DPI


def render(text):
    lines = []
    for para in text.split("\n"):
        lines += textwrap.wrap(para, 95, replace_whitespace=False, drop_whitespace=False) or [""]
    h = 40 * len(lines) + 160
    img = Image.new("L", (1700, max(h, 400)), 255)
    d = ImageDraw.Draw(img)
    for n, line in enumerate(lines):
        d.text((80, 80 + 40 * n), line, font=FONT, fill=0)
    return img


def degrade(img, seed):
    rnd = random.Random(seed)
    w, h = img.size
    img = img.resize((int(w * 0.62), int(h * 0.62)), Image.BILINEAR)  # ~125 DPI
    img = img.rotate(rnd.uniform(-1.0, 1.0), expand=True, fillcolor=255)  # a slightly skewed scan
    img = img.filter(ImageFilter.GaussianBlur(0.6))
    px = img.load()
    for _ in range(img.size[0] * img.size[1] // 150):  # speckle
        x, y = rnd.randrange(img.size[0]), rnd.randrange(img.size[1])
        px[x, y] = rnd.choice((0, 90, 255))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=55)
    return Image.open(io.BytesIO(buf.getvalue()))


def png(img):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, "PNG")
    return buf.getvalue()


def work(args):
    i, text = args
    img = render(text)
    return i, data(img), data(degrade(img, i))


if __name__ == "__main__":
    path, n, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    d = pd.read_parquet(path)
    d = d[d.language == "English"].head(n)
    with Pool(4) as pool:
        res = sorted(pool.map(work, list(enumerate(d.generated_text)), chunksize=4))
    json.dump({"clean": [r[1] for r in res], "scanned": [r[2] for r in res]}, open(out, "w"))
    print("done", len(res))
