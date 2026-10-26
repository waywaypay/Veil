import json

import pytest

from veil.tagged import (
    LABELS,
    SECRET_LABELS,
    Span,
    TaggedRedactor,
    _join,
    chunks,
    extend_name,
    merged,
    model_labels,
    veil_hidden,
)


def test_chunks_keep_offsets():
    text = "line one\n" + "word " * 450 + "\nlast line"
    for off, piece in chunks(text):
        assert text[off:off + len(piece)] == piece
    assert all(len(p.split()) <= 200 for _, p in chunks(text))


def test_merged_joins_a_first_and_last_name():
    text = "Maria Lopez called"
    assert merged([(0, 5, "NAME", 0.9), (6, 11, "NAME", 0.8)], text) == [(0, 11, "NAME", 0.8)]


@pytest.mark.parametrize("text, name, rest", [
    ("Reporting person: Osborne William H\n5. Relationship", "Osborne William", " H"),
    ("Name | Andrew P. Sutor, IV | Director", "Andrew P. Sutor", ", IV"),
    ("signed by Robert Hale Jr. on Monday", "Robert Hale", " Jr."),
    ("Dr. Anna Wu, MD, PhD", "Dr. Anna Wu", ", MD, PhD"),
    ("Walter Boyd M. Reeves", "Walter Boyd", " M."),
    ("Dana Cole III and Mary Ng", "Dana Cole", " III"),
])
def test_a_name_takes_in_its_trailing_initial_and_suffix(text, name, rest):
    end = text.index(name) + len(name)
    assert text[end:extend_name(text, end)] == rest


@pytest.mark.parametrize("text, name", [
    ("Mary Jones I think so", "Mary Jones"),
    ("Please ask John Smith A new form is due", "John Smith"),
    ("Tell Maria Lopez about it", "Maria Lopez"),
    ("Chair Pat Noor V of the board", "Pat Noor"),
    ("Anna Wu\nIV. Next item", "Anna Wu"),
])
def test_a_name_keeps_the_words_that_are_not_part_of_it(text, name):
    end = text.index(name) + len(name)
    assert extend_name(text, end) == end


def test_merged_extends_a_name_up_to_the_next_span():
    text = "Osborne William H, 11892 South Brookglen Drive"
    spans = [(0, 15, "NAME", 0.9), (19, 46, "ADDRESS", 0.8)]
    assert merged(spans, text)[0][:2] == (0, 17)
    assert merged([(0, 15, "NAME", 0.9), (16, 17, "NAME", 0.9)], text)[0][:2] == (0, 17)


def test_veil_hidden_finds_the_words_veil_replaced():
    text = "Write to jane.doe@example.com today"
    hidden = veil_hidden(text, "Write to EMAIL_001 today")
    assert [text[s:e] for s, e in hidden] == ["jane", "doe", "example", "com"]


def test_veil_alone_needs_no_model():
    text, spans = TaggedRedactor(system="veil").redact("Email jane.doe@example.com now")
    assert "jane" not in text and spans and all(s.source == "veil" for s in spans)


def test_join_prefers_the_model_kind():
    spans = [Span(0, 5, "VEIL", "veil"), Span(3, 11, "NAME", "model")]
    assert _join(spans) == [Span(0, 11, "NAME", "model")]


def test_redactor_puts_the_model_beside_the_rules(monkeypatch):
    r = TaggedRedactor()
    text = "Member No. MTS-009914 for Kipchumba arap Ruto."
    i = text.index("MTS-009914")
    monkeypatch.setattr(r, "model_spans", lambda texts, threshold=None: [[(i, i + 10, "ID", 0.9)] for _ in texts])
    red = r.redactor()
    out = red.redact_text(text)
    assert "MTS-009914" not in out and red.restore_text(out) == text


def test_one_piece_per_model_call_by_default():
    pytest.importorskip("torch")   # model_spans runs under torch.inference_mode

    class Model:   # records what each call is given
        calls: list[int] = []

        def batch_predict_entities(self, pieces, labels, threshold):
            self.calls.append(len(pieces))
            return [[] for _ in pieces]

    r = TaggedRedactor()
    r._model = Model()
    r.model_spans(["word " * 450, "Maria Lopez called"])
    assert Model.calls and set(Model.calls) == {1}   # a batch pads every piece to its longest: slower on a CPU


def test_secret_labels_only_for_a_model_trained_on_them():
    assert model_labels({}) == LABELS   # round 7's model: asked for what it was trained on, and nothing more
    assert model_labels({"veil_labels": ["api key", "not a label"]}) == {**LABELS, "api key": "ID"}
    assert model_labels({"veil_labels": list(SECRET_LABELS)}) == {**LABELS, **SECRET_LABELS}


@pytest.mark.parametrize("trained", [[], ["password or access code", "api key"]])
def test_a_model_is_asked_for_the_labels_its_config_lists(tmp_path, monkeypatch, trained):
    import veil.onnx_tagger

    asked = []

    class Model:
        without_torch = True

        def __init__(self, folder, onnx_file):
            pass

        def batch_predict_entities(self, pieces, labels, threshold):
            asked.append(labels)
            return [[{"start": p.index("sk-"), "end": len(p) - 1, "label": "api key", "score": 0.9}]
                    if "sk-" in p and "api key" in labels else [] for p in pieces]

    (tmp_path / "gliner_config.json").write_text(json.dumps({"span_mode": "token_level", "veil_labels": trained}))
    monkeypatch.setattr(veil.onnx_tagger, "OnnxTagger", Model)
    r = TaggedRedactor(model=f"{tmp_path}::onnx/model_f16.onnx")
    found = r.model_spans(["My key is sk-abc123def456."])
    assert set(asked[0]) == set(LABELS) | set(trained)
    assert found == ([[(10, 25, "ID", 0.9)]] if trained else [[]])
