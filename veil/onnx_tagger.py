"""A GLiNER span tagger run with ONNX Runtime alone: no gliner, no PyTorch.

``veil.tagged`` runs the tagger through gliner, which imports PyTorch even for an ONNX model; PyTorch is most of what
an app that ships the tagger has to carry.  This reads the same model folder (``gliner_config.json``,
``tokenizer.json`` and an ONNX file, as the model's repo has them) with ``onnxruntime``, ``tokenizers`` and ``numpy``
(the tagger-onnx extra), and marks the same spans gliner does from that file, as tests/test_onnx_tagger.py checks.

It handles the token-level GLiNER the tagger is ("span_mode": "token_level", as Deerpark/pii-tagger-edge and its base
knowledgator/gliner-pii-edge-v1.0 are):

* the text is split into words as gliner's whitespace splitter does (``\\w+(?:[-_]\\w+)*|\\S``), and the model is given
  "<<ENT>> label <<ENT>> label ... <<SEP>>" and then the words, each tokenized on its own, with the first subtoken of
  each word numbered in ``words_mask``;
* it returns, for each word and label, logits for a span starting there, ending there and running through it;
* a span runs from a word whose start score is over the threshold to one, at or after it, whose end score is, for the
  same label, with every word from one to the other scoring at least the threshold inside; its score is the lowest of
  those;
* the spans are taken highest score first, each one only where it overlaps none taken before (gliner's flat NER).
"""
from __future__ import annotations

import json
import os
import re

import numpy as np

_WORD = re.compile(r"\w+(?:[-_]\w+)*|\S")   # gliner's WhitespaceTokenSplitter


class OnnxTagger:
    """A token-level GLiNER model from ``model_dir``, run from its ONNX file ``onnx_file`` (relative to the folder).
    ``batch_predict_entities`` answers as gliner's does: for each text, [{"start", "end", "text", "label", "score"}]."""

    without_torch = True   # veil.tagged runs gliner's models under torch.inference_mode, and this one without

    def __init__(self, model_dir: str, onnx_file: str = "onnx/model_f16.onnx", threads: int | None = None):
        import onnxruntime as ort
        from tokenizers import Tokenizer

        with open(os.path.join(model_dir, "gliner_config.json"), encoding="utf-8") as f:
            config = json.load(f)
        if config.get("span_mode") != "token_level":
            raise ValueError(f"{model_dir} is a {config.get('span_mode')!r} GLiNER model; only token_level ones run here")
        self.ent_token = config.get("ent_token", "[ENT]")
        self.sep_token = config.get("sep_token", "[SEP]")
        self.tokenizer = Tokenizer.from_file(os.path.join(model_dir, "tokenizer.json"))
        self.tokenizer.no_truncation()
        self.tokenizer.no_padding()
        options = ort.SessionOptions()
        if threads:
            options.intra_op_num_threads = threads
        self.session = ort.InferenceSession(os.path.join(model_dir, onnx_file), options,
                                            providers=["CPUExecutionProvider"])

    def inputs(self, words: list[str], labels: list[str]) -> dict[str, np.ndarray]:
        """What the model is given for ``words`` and ``labels``, as gliner builds it."""
        prompt = [t for label in labels for t in (self.ent_token, label)] + [self.sep_token]
        encoding = self.tokenizer.encode(prompt + words, is_pretokenized=True, add_special_tokens=True)
        mask, previous = [], None
        for word in encoding.word_ids:
            first = word is not None and word >= len(prompt) and word != previous
            mask.append(word - len(prompt) + 1 if first else 0)
            previous = word
        ids = np.array([encoding.ids], dtype=np.int64)
        return {"input_ids": ids, "attention_mask": np.ones_like(ids), "words_mask": np.array([mask], dtype=np.int64),
                "text_lengths": np.array([[len(words)]], dtype=np.int64)}

    def predict_entities(self, text: str, labels: list[str], threshold: float = 0.5) -> list[dict]:
        words = [(m.group(), m.start(), m.end()) for m in _WORD.finditer(text)]
        if not words or not labels:
            return []
        logits = self.session.run(["logits"], self.inputs([w for w, _, _ in words], list(labels)))[0][0]
        out = []
        for start, end, label, score in decode(logits, threshold):
            a, b = words[start][1], words[end][2]
            out.append({"start": a, "end": b, "text": text[a:b], "label": labels[label], "score": score})
        return out

    def batch_predict_entities(self, texts: list[str], labels: list[str], threshold: float = 0.5) -> list[list[dict]]:
        # One text at a time: a batch pads every text to its longest, which on a CPU costs more than it saves.
        return [self.predict_entities(text, labels, threshold) for text in texts]


def decode(logits: np.ndarray, threshold: float) -> list[tuple[int, int, int, float]]:
    """The spans in one text's ``logits`` (words x labels x [start, end, inside]), as (first word, last word, label,
    score), sorted by first word; gliner's TokenDecoder with flat NER."""
    p = 1.0 / (1.0 + np.exp(-logits.astype(np.float32)))
    start, end, inside = p[..., 0], p[..., 1], p[..., 2]
    ends = list(zip(*np.where(end > threshold)))
    found = []
    for st, label in zip(*np.where(start > threshold)):
        for ed, label_ed in ends:
            if ed < st or label_ed != label:
                continue
            ins = inside[st:ed + 1, label]
            if (ins < threshold).any():
                continue
            found.append((int(st), int(ed), int(label), float(min(ins.min(), start[st, label], end[ed, label]))))
    taken: list[tuple[int, int, int, float]] = []
    for span in sorted(found, key=lambda s: -s[3]):
        if not any(span[0] <= t[1] and t[0] <= span[1] for t in taken):
            taken.append(span)
    return sorted(taken, key=lambda s: s[0])
