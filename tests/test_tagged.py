from veil.tagged import Span, TaggedRedactor, _join, chunks, merged, veil_hidden


def test_chunks_keep_offsets():
    text = "line one\n" + "word " * 450 + "\nlast line"
    for off, piece in chunks(text):
        assert text[off:off + len(piece)] == piece
    assert all(len(p.split()) <= 200 for _, p in chunks(text))


def test_merged_joins_a_first_and_last_name():
    text = "Maria Lopez called"
    assert merged([(0, 5, "NAME", 0.9), (6, 11, "NAME", 0.8)], text) == [(0, 11, "NAME", 0.8)]


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
