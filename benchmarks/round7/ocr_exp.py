"""Does a better OCR plus number normalising get the span model to 99%+ on scanned W-2s?

The same degraded page image (seed 71, not used before) is read by Tesseract and by RapidOCR (PaddleOCR's detection and
recognition models run with ONNX), each with and without a length-preserving digit normaliser, and the span model runs on
the text.  Every private value of the form is looked up again in the text it was given (approximate match, as w2real does);
a value that cannot be found there was lost by the OCR and counts as missed.  A clean-text reference (pdftotext layout) is
scored on the same forms.

python ocr_exp.py <n per source> <model>@<threshold> ...   ->  llm/ocr_exp.json"""
import io
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, "/tmp/claude-0/-home-user-Veil/190ab3d3-f9c1-50ad-a470-e321ea643401/scratchpad")
import numpy as np  # noqa: E402
from faker import Faker  # noqa: E402
from PIL import Image  # noqa: E402

import round4 as R  # noqa: E402
import w2prov as P  # noqa: E402
import w2real as W  # noqa: E402

T = R.T
OUT = "/tmp/claude-0/-home-user-Veil/190ab3d3-f9c1-50ad-a470-e321ea643401/scratchpad/llm"
SEED = 71
_rapid = None


def rapid(img):
    """RapidOCR text in reading order: boxes grouped into lines by height, left to right."""
    global _rapid
    if _rapid is None:
        from rapidocr_onnxruntime import RapidOCR
        _rapid = RapidOCR()
    res, _ = _rapid(np.asarray(img.convert("RGB")))
    items = []
    for box, txt, _ in res or []:
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        items.append(((min(ys) + max(ys)) / 2, max(ys) - min(ys), min(xs), max(xs), txt))
    items.sort()
    lines, cur = [], []
    for it in items:
        if cur and abs(it[0] - cur[0][0]) > 0.6 * max(it[1], cur[0][1]):
            lines.append(cur)
            cur = []
        cur.append(it)
    if cur:
        lines.append(cur)
    out = []
    for ln in lines:
        ln.sort(key=lambda x: x[2])
        s, prev = "", None
        for _, h, x0, x1, txt in ln:
            s += ("" if prev is None else "  " if x0 - prev > h else " ") + txt
            prev = x1
        out.append(s)
    return "\n".join(out)


def tesseract(img):
    with tempfile.TemporaryDirectory() as d:
        img.save(f"{d}/o.png")
        return subprocess.run(["tesseract", f"{d}/o.png", "-", "--psm", "4"], capture_output=True, text=True, timeout=180).stdout


_DIG = {"O": "0", "o": "0", "D": "0", "Q": "0", "l": "1", "I": "1", "|": "1", "i": "1", "S": "5", "s": "5", "B": "8", "Z": "2", "z": "2", "G": "6", "g": "9", "q": "9"}


def normalise(text):
    """Length-preserving: inside a token that is mostly digits (SSN, EIN, amounts, codes), letters that are usually
    misread digits become digits."""
    def fix(m):
        tok = m.group(0)
        digits = sum(c.isdigit() for c in tok)
        if len(tok) >= 5 and digits >= 0.6 * sum(c.isalnum() for c in tok) and digits >= 3:
            return "".join(_DIG.get(c, c) if c.isalpha() else c for c in tok)
        return tok
    return re.sub(r"[0-9A-Za-z|][0-9A-Za-z|\-./,]*[0-9A-Za-z|]", fix, text)


def locate(text, form, copies):
    """([(start, end, label)], values lost, values total) for the private values of `form` looked up in `text`."""
    wants = [("ssn", form["ssn"], "ssn"), ("ein", form["ein"], "tax id")]
    if form.get("control"):
        wants.append(("control", form["control"], "employee id"))
    wants += [("first", form["first"], "name"), ("last", form["last"], "name")]
    street, city = form["address"].split("\n")
    wants += [("street", street, "street address"), ("city", city, "street address")]
    if form["household"]:
        wants += [("emp", form["employer_name"], "name"), ("empst", form["employer_street"], "street address")]
    wants.append(("stid", form["stid1"], "tax id"))
    spans, taken, lost, total = [], [], 0, 0
    for key, value, label in sorted(wants, key=lambda w: -len(w[1])):
        for _ in range(copies):
            total += 1
            hit = W.find_fuzzy(text, value, taken)
            if hit is None:
                lost += 1
                continue
            taken.append(hit)
            spans.append((hit[0], hit[1], label))
    return sorted(spans), lost, total


def make(n):
    rng = random.Random(SEED)
    us = Faker("en_US")
    us.seed_instance(SEED)
    fakes = {l: Faker(l) for l in set(W.LOCALES)}
    for i, f in enumerate(fakes.values()):
        f.seed_instance(SEED + i + 1)
    out = []
    for src in ("IRS form", "provider layout"):
        for _ in range(n):
            form = W.one_form(rng, fakes[rng.choice(W.LOCALES)], us)
            if src == "IRS form":
                pdf, copies = W.fill(rng.choice(W.PAGES), [form]), 1
            else:
                form = P.fix_case(rng, form)
                form["year"] = rng.choice(["2023", "2024", "2025"])
                pdf, copies = P.provider_pdf(rng, form)
            with tempfile.TemporaryDirectory() as d:
                open(f"{d}/a.pdf", "wb").write(pdf)
                dpi = rng.choice([150, 200, 200, 250])
                subprocess.run(["pdftoppm", "-r", str(dpi), "-png", f"{d}/a.pdf", f"{d}/p"], check=True, capture_output=True, timeout=120)
                img = W.degrade(Image.open(f"{d}/" + sorted(f for f in os.listdir(d) if f.endswith(".png"))[0]), rng)
            out.append({"src": src, "form": form, "copies": copies, "pdf": pdf, "img": img})
    return out


def main(n, specs):
    docs = make(n)
    t0 = time.time()
    texts = {}
    for i, d in enumerate(docs):
        clean = W.pdftotext(d["pdf"], "layout")
        t = {"clean text": clean, "Tesseract": tesseract(d["img"]), "RapidOCR": rapid(d["img"])}
        t["Tesseract + normalise"] = normalise(t["Tesseract"])
        t["RapidOCR + normalise"] = normalise(t["RapidOCR"])
        texts[i] = {k: re.sub(r"\n{3,}", "\n\n", v).strip("\n") for k, v in t.items()}
        if i % 10 == 0:
            print(f"ocr {i + 1}/{len(docs)} {time.time() - t0:.0f} s", flush=True)
    variants = ["clean text", "Tesseract", "Tesseract + normalise", "RapidOCR", "RapidOCR + normalise"]
    result = {}
    for spec in specs:
        model, _, th = spec.partition("@")
        th = float(th)
        found = T.spans(model, [texts[i][v] for i in texts for v in variants])
        for v in variants:
            for src in ("all", "IRS form", "provider layout"):
                hit = tot = lost = over_n = over_d = 0
                for i, d in enumerate(docs):
                    if src != "all" and d["src"] != src:
                        continue
                    text = texts[i][v]
                    spans, l, total = locate(text, d["form"], d["copies"] if v != "clean text" else d["copies"])
                    r = T.score([(text, spans)], [text], [T.alone(text, found[T.key(text)], th)])
                    hit += sum(h for h, _ in r["by"].values())
                    tot += total
                    lost += l
                    over_n += r["over"]
                    over_d += 1
                result.setdefault(os.path.basename(model) + f"@{th:g}", {}).setdefault(v, {})[src] = {
                    "found_end_to_end": hit / tot, "values": tot, "lost_by_ocr": lost / tot, "over": over_n / over_d}
    json.dump(result, open(f"{OUT}/ocr_exp.json", "w"), indent=1)
    for m, vs in result.items():
        print(m)
        for v, srcs in vs.items():
            print(f"  {v:24}", "   ".join(f"{s}: found {x['found_end_to_end']:.1%} (OCR lost {x['lost_by_ocr']:.1%}, over {x['over']:.2%})" for s, x in srcs.items()))


if __name__ == "__main__":
    if os.environ.get("PYTHONHASHSEED") != "0":
        os.execve(sys.executable, [sys.executable, *sys.argv], {**os.environ, "PYTHONHASHSEED": "0"})
    main(int(sys.argv[1]), sys.argv[2:])
