"""veil with a span tagger beside it: veil's rules and a fine-tuned GLiNER model both read the original text, and every word
either one marks is hidden.  The model only adds to what veil hides.

    from veil.tagged import TaggedRedactor
    r = TaggedRedactor()                       # downloads Deerpark/veil-tagger-edge on first use
    text, spans = r.redact("Call Maria Lopez on 0412 555 019.")
    rr = r.redactor(reveal={"DOB": "month"})   # numbered placeholders that restore, as veil's own

Needs the ``tagger`` extra (gliner, torch).  ``system`` picks what hides: "union" (veil and the model), "model" or "veil".

Or, with the ``tagger-onnx`` extra (onnxruntime, tokenizers; no gliner, no PyTorch), the model's ONNX copy, named as
"folder or Hugging Face repo::file in it" (veil.onnx_tagger):

    r = TaggedRedactor(model=ONNX_MODEL)       # Deerpark/pii-tagger-edge::onnx/model_f16.onnx"""
from __future__ import annotations

import contextlib
import difflib
import json
import os
import re
from dataclasses import dataclass

from . import FINANCE, Redactor, hangul

MODEL = "Deerpark/veil-tagger-edge"
ONNX_MODEL = MODEL + "::onnx/model_f16.onnx"   # its weights in 16 bits, cast to 32 as ONNX Runtime loads them
THRESHOLD = 0.35   # chosen on the dev sets for round 7's model

# what the model is asked to find -> veil's kind of placeholder
LABELS = {"name": "NAME", "street address": "ADDRESS", "city": "ADDRESS", "postcode": "ADDRESS",
          "email address": "EMAIL", "phone number": "PHONE", "ssn": "SSN", "account number": "ACCOUNT",
          "credit card number": "ACCOUNT", "iban": "ACCOUNT", "swift code": "ACCOUNT", "date of birth": "DOB",
          "customer id": "ID", "employee id": "ID", "username": "ID", "passport number": "ID",
          "driver license number": "ID", "tax id": "ID"}
# Secrets, from round 10 on (benchmarks/judged/PROTOCOL.md), under veil's ID placeholder.  Asked for only of a model
# whose gliner_config.json lists them under "veil_labels", as one trained on them does: GLiNER reads every label's name
# with the text, so asking a model for labels it wasn't trained on can move its scores for the rest.
SECRET_LABELS = {"password or access code": "ID", "api key": "ID"}
_WORD = re.compile(r"\w+")   # the words the benchmarks score by


def model_labels(config: dict) -> dict[str, str]:
    """What a model with this gliner_config.json is asked to find: LABELS, and the SECRET_LABELS it lists under
    "veil_labels"."""
    trained = set(config.get("veil_labels", ()))
    return {**LABELS, **{k: v for k, v in SECRET_LABELS.items() if k in trained}}


def _config(folder_or_repo: str) -> dict:
    """A model's gliner_config.json, from its folder or its Hugging Face repo."""
    path = os.path.join(folder_or_repo, "gliner_config.json")
    if not os.path.isfile(path):
        from huggingface_hub import hf_hub_download
        path = hf_hub_download(folder_or_repo, "gliner_config.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


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


# what can trail a name: a suffix (Jr., III, Esq.), or a single initial: "H." anywhere, a bare "H" only where the line or
# table cell ends (a bare capital elsewhere is as likely to be "A" or "I" the word)
_SUFFIX = r"(?:Jr|JR|Sr|SR|Esq|ESQ|II|III|IV|MD|M\.D|PhD|Ph\.D|CPA)"
_AFTER_NAME = re.compile(rf",?[ \t]+{_SUFFIX}(?!\w)\.?|[ \t]+[A-Z](?:\.(?!\w)|(?=[ \t]*(?:\n|\Z|[|;,)])))")


def extend_name(text: str, end: int) -> int:
    """Where a name that ends at ``end`` ends once its trailing initial and suffix are taken in: the model marks
    "Osborne William" and "Andrew P. Sutor" and leaves the "H" and the ", IV" showing."""
    if end <= 0 or not (text[end - 1].isalnum() or text[end - 1] == "."):
        return end
    for _ in range(2):
        m = _AFTER_NAME.match(text, end)
        if not m:
            break
        end = m.end()
    return end


def vetted(found: list[tuple[int, int, str, float]], text: str) -> list[tuple[int, int, str, float]]:
    """The model's spans without the names that can't be names: Korean ones made of everyday words (veil.hangul)."""
    return [x for x in found if x[2] != "NAME" or hangul.could_be_name(text[x[0]:x[1]])]


def merged(found: list[tuple[int, int, str, float]], text: str) -> list[tuple[int, int, str, float]]:
    """Adjacent spans of one kind joined, once ``vetted``: a first and a last name, a street and its town and postcode.
    A name takes in the initial or suffix that trails it, up to the next span."""
    out: list[tuple[int, int, str, float]] = []
    for s, e, kind, sc in sorted(vetted(found, text)):
        if out and out[-1][2] == kind and s >= out[-1][1] and \
                re.fullmatch(r"[ \t.]*" if kind == "NAME" else r"[\s,.-]*", text[out[-1][1]:s]):
            out[-1] = (out[-1][0], e, kind, min(sc, out[-1][3]))
        elif not out or s >= out[-1][1]:
            out.append((s, e, kind, sc))
    for i, (s, e, kind, sc) in enumerate(out):
        if kind == "NAME":
            nxt = out[i + 1][0] if i + 1 < len(out) else len(text)
            out[i] = (s, max(e, min(extend_name(text, e), nxt)), kind, sc)
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
                 batch_size: int = 1):
        # One piece at a time: in a batch every piece is padded to the longest, and on a CPU that padding costs more
        # than batching saves (0.75 -> 0.37 s per 200 words for the edge model, 4.65 -> 1.66 for the large one; the
        # same spans either way).
        if system not in ("union", "model", "veil"):
            raise ValueError("system is 'union', 'model' or 'veil'")
        self.model_name, self.threshold, self.system, self.profile = model, threshold, system, profile
        self.batch_size = batch_size
        self._model = None
        self.labels = LABELS   # what the model is asked to find; set from its gliner_config.json as it loads

    def _load(self):
        if self._model is None:
            if "::" in self.model_name:   # an ONNX file in a model's folder or repo: veil.onnx_tagger
                from .onnx_tagger import OnnxTagger
                folder, onnx_file = self.model_name.split("::", 1)
                if not os.path.isdir(folder):
                    from huggingface_hub import snapshot_download
                    folder = snapshot_download(folder, allow_patterns=["gliner_config.json", "tokenizer.json",
                                                                       "tokenizer_config.json", onnx_file])
                self._model = OnnxTagger(folder, onnx_file)
                self.labels = model_labels(_config(folder))
            else:
                from gliner import GLiNER
                self._model = GLiNER.from_pretrained(self.model_name)
                self._model.eval()
                self.labels = model_labels(_config(self.model_name))
        return self._model

    def model_spans(self, texts: list[str], threshold: float | None = None) -> list[list[tuple[int, int, str, float]]]:
        """What the model marks in each text: [(start, end, kind, score)], at ``threshold`` (default: the redactor's)."""
        th = self.threshold if threshold is None else threshold
        m = self._load()
        pieces = [(i, off, p) for i, t in enumerate(texts) for off, p in chunks(t)]
        found: list[list[tuple[int, int, str, float]]] = [[] for _ in texts]
        with _inference_mode(m):
            for b in range(0, len(pieces), self.batch_size):
                batch = pieces[b:b + self.batch_size]
                ents = m.batch_predict_entities([p for _, _, p in batch], list(self.labels), threshold=th)
                for (i, off, _), es in zip(batch, ents):
                    found[i] += [(off + e["start"], off + e["end"], self.labels[e["label"]], round(e["score"], 3))
                                 for e in es]
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

    def redactor(self, reveal=None, **kwargs) -> Redactor:
        """A veil ``Redactor`` with the model beside its rules: numbered placeholders that restore, for one
        conversation (``veil.anthropic.wrap`` takes it).  ``reveal`` and other keywords go to the Redactor."""
        seen: dict[str, list[tuple[int, int, str]]] = {}

        def finder(text: str) -> list[tuple[int, int, str]]:
            if text not in seen:   # a conversation's earlier turns are redacted again with every request
                if len(seen) > 512:
                    seen.clear()
                seen[text] = [(s, e, k) for s, e, k, _ in merged(self.model_spans([text])[0], text)]
            return seen[text]

        return Redactor(self.profile, finder=finder, reveal=reveal, **kwargs)

    def redact(self, text: str) -> tuple[str, list[Span]]:
        """``text`` with each hidden span replaced by [KIND], and the spans."""
        spans = self.find(text)
        out = text
        for s in reversed(spans):
            out = out[:s.start] + f"[{s.kind}]" + out[s.end:]
        return out, spans


def _inference_mode(model):
    """torch.inference_mode for a gliner model; nothing for the ONNX one, which runs without PyTorch."""
    if getattr(model, "without_torch", False):
        return contextlib.nullcontext()
    import torch
    return torch.inference_mode()


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
