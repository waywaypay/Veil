import os
import sys

import pytest

np = pytest.importorskip("numpy")

from veil.onnx_tagger import OnnxTagger, decode  # noqa: E402
from veil.tagged import LABELS, TaggedRedactor, chunks  # noqa: E402


def logits(words, labels, marks):
    """Logits for ``words`` x ``labels``: every probability 0.01, but those in ``marks``:
    {(word, label, 0 start | 1 end | 2 inside): probability}."""
    p = np.full((words, labels, 3), 0.01, dtype=np.float32)
    for (w, label, which), prob in marks.items():
        p[w, label, which] = prob
    return np.log(p / (1 - p))


def span(first, last, label, start=0.9, end=0.9, inside=0.9):
    return {**{(w, label, 2): inside for w in range(first, last + 1)}, (first, label, 0): start, (last, label, 1): end}


def test_a_span_runs_from_a_start_to_an_end_of_its_label_through_words_inside_it():
    out = decode(logits(6, 2, {**span(1, 3, 0, start=0.8, end=0.7, inside=0.95), **span(5, 5, 1)}), 0.5)
    assert [(s, e, label) for s, e, label, _ in out] == [(1, 3, 0), (5, 5, 1)]
    assert out[0][3] == pytest.approx(0.7, abs=1e-5)   # the lowest of its start, end and inside scores


def test_no_span_without_its_inside_or_across_labels():
    marks = span(1, 3, 0)
    marks[(2, 0, 2)] = 0.3   # a word inside it isn't
    assert decode(logits(5, 2, marks), 0.5) == []
    assert decode(logits(5, 2, {(1, 0, 0): 0.9, (1, 0, 2): 0.9, (2, 1, 1): 0.9, (2, 1, 2): 0.9}), 0.5) == []


def test_the_threshold_is_strict_for_starts_and_ends_and_not_for_inside():
    at = span(0, 1, 0, start=0.5, end=0.9)
    assert decode(logits(2, 1, at), 0.5) == []
    inside = span(0, 1, 0, inside=0.5)
    assert len(decode(logits(2, 1, inside), 0.5)) == 1


def test_overlapping_spans_go_to_the_higher_score_in_text_order():
    marks = {**span(0, 2, 0, start=0.7, end=0.7, inside=0.7), **span(2, 3, 1, start=0.9, end=0.9, inside=0.9),
             **span(5, 6, 0, start=0.6, end=0.6, inside=0.6)}
    assert [(s, e, label) for s, e, label, _ in decode(logits(7, 2, marks), 0.5)] == [(2, 3, 1), (5, 6, 0)]
    # one start with two ends: the longer span wins when it scores higher, and the shorter one overlaps it
    two = {**span(0, 2, 0), (0, 0, 1): 0.6}
    assert [(s, e) for s, e, _, _ in decode(logits(3, 1, two), 0.5)] == [(0, 2)]


@pytest.fixture
def tagger():
    """An OnnxTagger with a small WordPiece tokenizer and no ONNX file: what the session answers is set per test."""
    tokenizers = pytest.importorskip("tokenizers")
    from tokenizers import models, pre_tokenizers, processors
    vocab = {t: i for i, t in enumerate(["[PAD]", "[UNK]", "[CLS]", "[SEP]", "<<ENT>>", "<<SEP>>", "name", "phone",
                                         "number", "call", "maria", "lopez", "at", "415", "-", "555", "##0", ","])}
    tok = tokenizers.Tokenizer(models.WordPiece(vocab, unk_token="[UNK]"))
    tok.pre_tokenizer = pre_tokenizers.BertPreTokenizer()
    tok.post_processor = processors.TemplateProcessing(single="[CLS] $A [SEP]",
                                                       special_tokens=[("[CLS]", 2), ("[SEP]", 3)])
    tok.add_special_tokens(["<<ENT>>", "<<SEP>>"])
    t = OnnxTagger.__new__(OnnxTagger)
    t.ent_token, t.sep_token, t.tokenizer = "<<ENT>>", "<<SEP>>", tok
    return t


def test_the_inputs_are_the_prompt_then_the_words_with_each_words_first_subtoken_numbered(tagger):
    inputs = tagger.inputs(["call", "maria", "415-5550"], ["name", "phone number"])
    ids = [tagger.tokenizer.id_to_token(i) for i in inputs["input_ids"][0].tolist()]
    assert ids[:8] == ["[CLS]", "<<ENT>>", "name", "<<ENT>>", "phone", "number", "<<SEP>>", "call"]
    # call maria 415 - 555 ##0: the third word is four subtokens, numbered on its first
    assert inputs["words_mask"][0].tolist() == [0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 0, 0, 0, 0]
    assert inputs["text_lengths"].tolist() == [[3]]
    assert inputs["attention_mask"].shape == inputs["input_ids"].shape


def test_spans_come_back_as_gliner_gives_them(tagger):
    text = "Call Maria Lopez at 415-5550, please"   # words: Call Maria Lopez at 415-5550 , please
    labels = ["name", "phone number"]

    class Session:
        def run(self, outputs, feed):
            assert feed["text_lengths"].tolist() == [[7]]
            return [logits(7, 2, {**span(1, 2, 0), **span(4, 4, 1, start=0.8)})[None]]

    tagger.session = Session()
    assert tagger.batch_predict_entities([text], labels, threshold=0.5) == [[
        {"start": 5, "end": 16, "text": "Maria Lopez", "label": "name", "score": pytest.approx(0.9, abs=1e-5)},
        {"start": 20, "end": 28, "text": "415-5550", "label": "phone number", "score": pytest.approx(0.8, abs=1e-5)}]]
    assert tagger.predict_entities("", labels, 0.5) == [] and tagger.predict_entities("  \n", labels, 0.5) == []


def test_the_tagged_redactor_runs_an_onnx_model_without_torch(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", None)   # import torch fails

    class Model:
        without_torch = True

        def batch_predict_entities(self, pieces, labels, threshold):
            return [[{"start": p.index("Ruto"), "end": p.index("Ruto") + 4, "label": "name", "score": 0.9}]
                    if "Ruto" in p else [] for p in pieces]

    r = TaggedRedactor(model="some/model::onnx/model_f16.onnx")
    r._model = Model()
    assert r.model_spans(["Paid to Kipchumba arap Ruto."]) == [[(23, 27, "NAME", 0.9)]]


# With a model to hand (VEIL_TAGGER_ONNX_TEST="folder::onnx/file.onnx", and gliner installed): the same spans and scores
# as gliner gives from the same file.
ONNX_TEST = os.environ.get("VEIL_TAGGER_ONNX_TEST", "")


@pytest.mark.skipif(not ONNX_TEST, reason="set VEIL_TAGGER_ONNX_TEST to compare with gliner on a real model")
def test_the_same_spans_as_gliner_from_the_same_file():
    gliner = pytest.importorskip("gliner")
    folder, onnx_file = ONNX_TEST.split("::", 1)
    theirs = gliner.GLiNER.from_pretrained(folder, load_onnx_model=True, load_tokenizer=True, onnx_model_file=onnx_file)
    ours = OnnxTagger(folder, onnx_file)
    texts = ["Call Maria Lopez on 0412 555 019.", "Partner: Thandiwe Okonkwo, 1192 Michael Cove, Palo Alto, CA 94301",
             "Email jane.doe@example.com; SSN 123-45-6789; IBAN GB29 NWBK 6016 1331 9268 19", "José García — München",
             "Account 4401-2231-9987 at Calder Ridge Capital Fund II, LP"]
    pieces = [p for t in texts for _, p in chunks(t)]
    for p in pieces:
        want = theirs.predict_entities(p, list(LABELS), threshold=0.3)
        got = ours.predict_entities(p, list(LABELS), threshold=0.3)
        assert [(e["start"], e["end"], e["label"]) for e in got] == [(e["start"], e["end"], e["label"]) for e in want]
        assert [e["score"] for e in got] == pytest.approx([e["score"] for e in want], abs=1e-5)
