"""veil with a span tagger beside it: veil's rules and a fine-tuned GLiNER model both read the original text, and every word
either one marks is hidden.  The model only adds to what veil hides.

    from veil.tagged import TaggedRedactor
    r = TaggedRedactor()                       # downloads Deerpark/veil-tagger-edge on first use
    text, spans = r.redact("Call Maria Lopez on 0412 555 019.")

Needs the ``tagger`` extra (gliner, torch).  ``system`` picks what hides: "union" (veil and the model), "model" or "veil"."""
from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from . import FINANCE, Redactor

MODEL = "Deerpark/veil-tagger-edge"
THRESHOLD = 0.35   # chosen on the dev sets for round 7's model

# what the model is asked to find -> veil's kind of placeholder
LABELS = {"name": "NAME", "street address": "ADDRESS", "city": "ADDRESS", "postcode": "ADDRESS",
          "email address": "EMAIL", "phone number": "PHONE", "ssn": "SSN", "account number": "ACCOUNT",
          "credit card number": "ACCOUNT", "iban": "ACCOUNT", "swift code": "ACCOUNT", "date of birth": "DOB",
          "customer id": "ID", "employee id": "ID", "username": "ID", "passport number": "ID",
          "driver license number": "ID", "tax id": "ID"}
_WORD = re.compile(r"\w+")   # the words the benchmarks score by


@dataclass(frozen=True)
class Span:
    start: int
    end: int
    kind: str      # NAME, ADDRESS, ... for the model's spans; VEIL for a word only veil hid
    source: str    # "model" or "veil"


def chunks(text: str, max_words: int = 200) -> list[tuple[int, str]]:
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


def merged(found: list[tuple[int, int, str, float]], text: str) -> list[tuple[int, int, str, float]]:
    """Adjacent spans of one kind joined: a first and a last name, a street and its town and postcode."""
    out: list[tuple[int, int, str, float]] = []
    for s, e, kind, sc in sorted(found):
        if out and out[-1][2] == kind and s >= out[-1][1] and \
                re.fullmatch(r"[ \t.]*" if kind == "NAME" else r"[\s,.-]*", text[out[-1][1]:s]):
            out[-1] = (out[-1][0], e, kind, min(sc, out[-1][3]))
        elif not out or s >= out[-1][1]:
            out.append((s, e, kind, sc))
    return out


def veil_hidden(text: str, redacted: str) -> list[tuple[int, int]]:
    """The words of ``text`` that veil's output no longer has, as (start, end)."""
    a = [(m.group(), m.start(), m.end()) for m in _WORD.finditer(text)]
    b = [m.group() for m in _WORD.finditer(redacted)]
    kept = [False] * len(a)
    for blk in difflib.SequenceMatcher(None, [w for w, _, _ in a], b, autojunk=False).get_matching_blocks():
        for i in range(blk.a, blk.a + blk.size):
            kept[i] = True
    return [(s, e) for (_, s, e), k in zip(a, kept) if not k]


class TaggedRedactor:
    def __init__(self, model: str = MODEL, threshold: float = THRESHOLD, system: str = "union", profile=FINANCE,
                 batch_size: int = 8):
        if system not in ("union", "model", "veil"):
            raise ValueError("system is 'union', 'model' or 'veil'")
        self.model_name, self.threshold, self.system, self.profile = model, threshold, system, profile
        self.batch_size = batch_size
        self._model = None

    def _load(self):
        if self._model is None:
            from gliner import GLiNER
            self._model = GLiNER.from_pretrained(self.model_name)
            self._model.eval()
        return self._model

    def model_spans(self, texts: list[str], threshold: float | None = None) -> list[list[tuple[int, int, str, float]]]:
        """What the model marks in each text: [(start, end, kind, score)], at ``threshold`` (default: the redactor's)."""
        import torch
        th = self.threshold if threshold is None else threshold
        m = self._load()
        pieces = [(i, off, p) for i, t in enumerate(texts) for off, p in chunks(t)]
        found: list[list[tuple[int, int, str, float]]] = [[] for _ in texts]
        with torch.inference_mode():
            for b in range(0, len(pieces), self.batch_size):
                batch = pieces[b:b + self.batch_size]
                ents = m.batch_predict_entities([p for _, _, p in batch], list(LABELS), threshold=th)
                for (i, off, _), es in zip(batch, ents):
                    found[i] += [(off + e["start"], off + e["end"], LABELS[e["label"]], round(e["score"], 3)) for e in es]
        return [sorted(f) for f in found]

    def find(self, text: str) -> list[Span]:
        """Every span hidden in ``text``, overlapping spans joined; sorted."""
        out = []
        if self.system in ("union", "model"):
            out += [Span(s, e, k, "model") for s, e, k, _ in merged(self.model_spans([text])[0], text)]
        if self.system in ("union", "veil"):
            covered = [(s.start, s.end) for s in out]
            out += [Span(s, e, "VEIL", "veil") for s, e in veil_hidden(text, Redactor(self.profile).redact_text(text))
                    if not any(a <= s and e <= b for a, b in covered)]
        return _join(sorted(out, key=lambda s: (s.start, -s.end)))

    def redact(self, text: str) -> tuple[str, list[Span]]:
        """``text`` with each hidden span replaced by [KIND], and the spans."""
        spans = self.find(text)
        out = text
        for s in reversed(spans):
            out = out[:s.start] + f"[{s.kind}]" + out[s.end:]
        return out, spans


def _join(spans: list[Span]) -> list[Span]:
    out: list[Span] = []
    for s in spans:
        if out and s.start <= out[-1].end:
            last = out[-1]
            keep = last if last.source == "model" or s.source != "model" else s
            out[-1] = Span(last.start, max(last.end, s.end), keep.kind, keep.source)
        else:
            out.append(s)
    return out
