"""A span tagger beside veil: a GLiNER model that marks names, addresses, numbers and the like in a text, and the ways
of adding what it marks to what veil hides.  Shared by tagger_sets.py, chats.py and train_tagger.py.

A model is a Hugging Face name ("knowledgator/gliner-pii-edge-v1.0"), a directory a model was saved to, or an ONNX
file in such a directory, written "dir::model_w8.onnx".  What a model marks in a text is kept in
$VEIL_BENCH_DATA/cache (benchmarks/data/cache by default), so each model reads each text once.  Needs gliner, torch
and onnxruntime."""

import hashlib
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path

import gretel as bench

from veil import FINANCE, Redactor
from veil import redactor as R

DATA = Path(os.environ.get("VEIL_BENCH_DATA", Path(__file__).resolve().parent / "data"))
CACHE = DATA / "cache"
THRESHOLD = 0.35   # chosen on dev sets for the fine-tuned models

# what the model is asked to find -> veil's kind of placeholder
LABELS = {"name": "NAME", "street address": "ADDRESS", "city": "ADDRESS", "postcode": "ADDRESS",
          "email address": "EMAIL", "phone number": "PHONE", "ssn": "SSN", "account number": "ACCOUNT",
          "credit card number": "ACCOUNT", "iban": "ACCOUNT", "swift code": "ACCOUNT", "date of birth": "DOB",
          "customer id": "ID", "employee id": "ID", "username": "ID", "passport number": "ID",
          "driver license number": "ID", "tax id": "ID"}
# NVIDIA's model was trained on Nemotron-PII's own label names
NEMO_LABELS = {"first_name": "NAME", "last_name": "NAME", "street_address": "ADDRESS", "city": "ADDRESS",
               "postcode": "ADDRESS", "email": "EMAIL", "phone_number": "PHONE", "fax_number": "PHONE", "ssn": "SSN",
               "account_number": "ACCOUNT", "credit_debit_card": "ACCOUNT", "bank_routing_number": "ACCOUNT",
               "swift_bic": "ACCOUNT", "date_of_birth": "DOB", "customer_id": "ID", "employee_id": "ID",
               "user_name": "ID", "national_id": "ID", "tax_id": "ID", "passport_number": "ID",
               "certificate_license_number": "ID"}


def chunks(text, max_words=200):
    """(offset, piece) runs of whole lines under ``max_words`` words, a longer line cut at spaces: the model reads a
    few hundred words at a time."""
    out, start, words = [], 0, 0
    for m in re.finditer(r"[^\n]*\n?", text):
        if not m.group():
            break
        n = len(m.group().split())
        if words and words + n > max_words:
            out.append((start, text[start:m.start()]))
            start, words = m.start(), 0
        if n > max_words:
            for w in re.finditer(r"(?:\S+\s*){1,%d}" % max_words, m.group()):
                out.append((m.start() + w.start(), w.group()))
            start, words = m.end(), 0
            continue
        words += n
    if start < len(text):
        out.append((start, text[start:]))
    return [(o, p) for o, p in out if p.strip()]


def key(text):
    return hashlib.sha1(text.encode()).hexdigest()


def load(model):
    from gliner import GLiNER
    if "::" in model:
        model_dir, onnx_file = model.split("::")
        return GLiNER.from_pretrained(model_dir, load_onnx_model=True, load_tokenizer=True, onnx_model_file=onnx_file)
    m = GLiNER.from_pretrained(model)
    m.eval()
    return m


def spans(model, texts):
    """{key(text): [(start, end, kind, score)]}: what ``model`` marks in each text at a threshold of 0.3, from the cache
    or by reading the texts not yet cached, 200 at a time, saving as it goes."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (re.sub(r"[^\w.:-]+", "_", model) + ".jsonl")
    have = {}
    if path.exists():
        for line in open(path):
            r = json.loads(line)
            have[r["k"]] = [tuple(x) for x in r["s"]]
    todo = list(dict.fromkeys(t for t in texts if key(t) not in have))
    if not todo:
        return have
    import torch
    torch.set_num_threads(os.cpu_count())
    m = load(model)
    labels = NEMO_LABELS if model.startswith("nvidia/") else LABELS
    t0, done = time.perf_counter(), 0
    for g in range(0, len(todo), 200):
        group = todo[g:g + 200]
        pieces = sorted(((i, off, p) for i, t in enumerate(group) for off, p in chunks(t)), key=lambda x: len(x[2]))
        found = defaultdict(list)
        with torch.inference_mode():
            for b in range(0, len(pieces), 8):
                batch = pieces[b:b + 8]
                ents = m.batch_predict_entities([p for _, _, p in batch], list(labels), threshold=0.3)
                for (i, off, _), es in zip(batch, ents):
                    found[i] += [(off + e["start"], off + e["end"], labels[e["label"]], round(e["score"], 3)) for e in es]
        with open(path, "a") as f:
            for i, t in enumerate(group):
                have[key(t)] = sorted(found[i])
                f.write(json.dumps({"k": key(t), "s": sorted(found[i])}) + "\n")
        done += sum(map(len, group))
        print(f"  {model}: {g + len(group)} of {len(todo)} texts, {done} characters in "
              f"{time.perf_counter() - t0:.0f} s", file=sys.stderr, flush=True)
    return have


# -- adding what the model marks to what veil hides ---------------------------------------------------------------

_V = Redactor(FINANCE)._v


def _everyday(word):
    f = R._ascii(word).casefold()
    return f in R._common_words() or f in _V.not_names or f in _V.stop


def checked(kind, v):
    """A span with the shape of its kind: digits in a number, a name-like word in a name."""
    digits = sum(c.isdigit() for c in v)
    words = re.findall(r"[^\W\d_]+", v)
    if kind in ("ACCOUNT", "PHONE", "SSN"):
        return digits >= 5
    if kind == "DOB":
        return digits >= 2
    if kind == "ID":
        return digits >= 2 or bool(re.fullmatch(r"\S*\w[._@]\w\S*", v.strip()))
    if kind == "EMAIL":
        return "@" in v or " at " in v.casefold()
    if kind == "ADDRESS":
        return bool(words) and not all(_everyday(w) for w in words)
    if kind == "NAME":
        return digits == 0 and bool(words) and any(
            R._name_listed(R._ascii(w).casefold(), set()) or not _everyday(w) for w in words)
    return True


_DATE = re.compile(r"\b(?:\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4})\b|"
                   r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?(?![a-z])", re.IGNORECASE)
_AMOUNT = re.compile(r"[$€£]?\s*\d[\d,]*\.\d+\s*[kKmM]?|\d+(?:\.\d+)?\s*[kKmM]")


def strict(kind, v):
    """As ``checked``, and as veil does: a place only with a number in it (a street, a postcode), not a town alone;
    no date or amount taken for an account, phone, taxpayer or other ID."""
    if not checked(kind, v):
        return False
    if kind in ("ACCOUNT", "PHONE", "SSN", "ID") and (_DATE.search(v) or _AMOUNT.fullmatch(v.strip())):
        return False
    return kind != "ADDRESS" or any(c.isdigit() for c in v)


def names_only(kind, v):
    return kind == "NAME" and checked(kind, v)


GATES = {"all kinds": lambda kind, v: True, "checked": checked, "strict": strict, "names only": names_only}


def merged(found, text):
    """Adjacent spans of one kind joined: a first and a last name, a street and its town and postcode."""
    out = []
    for s, e, kind, sc in sorted(found):
        if out and out[-1][2] == kind and s >= out[-1][1] and \
                re.fullmatch(r"[ \t.]*" if kind == "NAME" else r"[\s,.-]*", text[out[-1][1]:s]):
            out[-1] = (out[-1][0], e, kind, min(sc, out[-1][3]))
        elif not out or s >= out[-1][1]:
            out.append((s, e, kind, sc))
    return out


def with_veil(text, found, gate, threshold=THRESHOLD, typed=False, redactor=None):
    """veil first; then what the model marked that veil left visible, and ``gate`` lets through, is added (a name with
    ``add_person``, so all its spellings are covered) and the text redacted again.  The model only ever adds.  Pass
    a conversation's ``redactor`` to keep its placeholders across turns."""
    r = redactor or Redactor(FINANCE)
    out = r.redact_text(text, typed)
    found = [x for x in found if x[3] >= threshold]
    candidates = {(s, e, k) for s, e, k, _ in merged(found, text)} | {(s, e, k) for s, e, k, _ in found}
    added = False
    for s, e, kind in sorted(candidates, key=lambda x: x[0] - x[1]):   # longest first
        v = text[s:e]
        if len(v.strip()) >= 3 and gate(kind, v) and v in out:
            r.add_person(v) if kind == "NAME" else r.add(v, kind)
            added = True
    return r.redact_text(out, typed) if added else out


def alone(text, found, threshold=THRESHOLD):
    """The text with what the model marked, and nothing else, replaced."""
    out = text
    for s, e, kind, _ in sorted(merged([x for x in found if x[3] >= threshold], text), reverse=True):
        out = out[:s] + f"{kind}_X" + out[e:]
    return out


# -- scoring --------------------------------------------------------------------------------------------------------

def score(rows, inputs, outs):
    """Found and over-redacted, for rows of (text, [(start, end, group)]): a group is one of veil's kinds, "outside"
    (personal, but no kind veil hides: neither scored nor counted against it) or "ordinary" (labelled, but hiding
    it is a mistake).  ``inputs`` are what each tool was given (the text, or a transformed or OCR'd copy of it)."""
    hit, tot = defaultdict(int), defaultdict(int)
    fp = fp_tot = 0
    for (text, spans_), given, out in zip(rows, inputs, outs):
        ws = bench.words(text)
        if given == text:
            _, kept = bench.redacted_mask(text, out)
            seen = [True] * len(ws)
        else:
            _, kept_given = bench.redacted_mask(given, out)
            m = bench.word_map(text, given)
            kept = [j is not None and kept_given[j] for j in m]
            seen = [j is not None for j in m]
        personal = [False] * len(ws)
        for s, e, g in spans_:
            idx = [j for j, (_, a, b) in enumerate(ws) if a < e and b > s]
            if g != "ordinary":
                for j in idx:
                    personal[j] = True
            idx = [j for j in idx if ws[j][0].lower() not in bench.TITLES]
            if idx and g not in ("ordinary", "outside"):
                tot[g] += 1
                hit[g] += all(not kept[j] for j in idx)
        for j, (w, _, _) in enumerate(ws):
            if not personal[j] and seen[j] and w.lower() not in bench.TITLES:
                fp_tot += 1
                fp += not kept[j]
    h, t = sum(hit.values()), sum(tot.values())
    return {"found": h / max(1, t), "details": t, "over": fp / max(1, fp_tot),
            "by": {g: [hit[g], tot[g]] for g in tot}}
