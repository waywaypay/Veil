"""Images and PDFs: read here and sent as redacted text, refused, or sent as they are, as ``files`` says."""

import base64
import io
import json
import shutil

import pytest

from veil import FINANCE, Redactor
from veil.anthropic import FILE_UNREAD, FileError, wrap

anthropic = pytest.importorskip("anthropic")
from test_anthropic import FakeClient, _message, _sent  # noqa: E402

K1 = "Partner: Avery Mockridge\nSSN 123-45-6789\n1 Ordinary business income 1250000"


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _pdf_block(data=b"%PDF-fake", **extra):
    return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": _b64(data)},
            **extra}


def _image_block(data=b"png-fake", source=None):
    return {"type": "image", "source": source or {"type": "base64", "media_type": "image/png", "data": _b64(data)}}


class Reader:
    def __init__(self, text=K1):
        self.text = text
        self.calls = []

    def __call__(self, data, media_type):
        self.calls.append((data, media_type))
        return self.text


def test_a_pdf_goes_out_as_its_text_with_placeholders_and_is_read_once():
    fake = FakeClient([_message("NAME_001's K-1 is in."), _message("ok")])
    reader = Reader()
    client = wrap(fake, Redactor(FINANCE), files=reader)
    messages = [{"role": "user", "content": [_pdf_block(title="Avery Mockridge K-1.pdf", cache_control={"type": "ephemeral"}),
                                             {"type": "text", "text": "Add this partner"}]}]
    reply = client.messages.create(model="m", max_tokens=10, messages=messages)
    assert reply.content[0].text == "Avery Mockridge's K-1 is in."

    messages += [{"role": "assistant", "content": reply.content}, {"role": "user", "content": "Thanks"}]
    client.messages.create(model="m", max_tokens=10, messages=messages)

    sent = _sent(fake)
    for secret in ("Mockridge", "123-45-6789", "6789", _b64(b"%PDF-fake")):
        assert secret not in sent
    doc = fake.requests[0]["messages"][0]["content"][0]
    assert doc["type"] == "document" and doc["source"]["type"] == "text"
    assert "NAME_001" in doc["source"]["data"] and "SSN_001" in doc["source"]["data"]
    assert doc["title"] == "NAME_001 K-1.pdf"
    assert doc["cache_control"] == {"type": "ephemeral"}
    assert reader.calls == [(b"%PDF-fake", "application/pdf")]   # not again on the second request
    assert fake.requests[1]["messages"][0]["content"][0] == doc   # same text both times, so the cache holds


def test_an_image_in_a_tool_result_becomes_a_text_block():
    fake = FakeClient([_message("ok")])
    client = wrap(fake, files=Reader("Call Priya Patel at 415-555-0134"))
    client.messages.create(model="m", max_tokens=10, messages=[
        {"role": "user", "content": "Read the scan"},
        {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "scan", "input": {}}]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": [_image_block()]}]}])
    block = fake.requests[0]["messages"][2]["content"][0]["content"][0]
    assert block == {"type": "text", "text": "[Text read from an image]\nCall NAME_001 at PHONE_001"}


def test_an_image_from_the_user_becomes_a_titled_document():
    fake = FakeClient([_message("ok")])
    client = wrap(fake, files=Reader(""))
    client.messages.create(model="m", max_tokens=10, messages=[{"role": "user", "content": [_image_block()]}])
    doc = fake.requests[0]["messages"][0]["content"][0]
    assert doc["title"] == "Text read from an image" and doc["source"]["data"] == FILE_UNREAD


@pytest.mark.parametrize("block", [_pdf_block(), _image_block()])
def test_by_default_a_request_with_a_file_is_refused_and_nothing_is_sent(block):
    fake = FakeClient([_message("ok")])
    client = wrap(fake)
    with pytest.raises(FileError, match='Nothing was sent. Pass files="read"'):
        client.messages.create(model="m", max_tokens=10, messages=[{"role": "user", "content": [block]}])
    assert fake.requests == []


@pytest.mark.parametrize("source", [{"type": "url", "url": "https://example.com/k1.png"},
                                    {"type": "file", "file_id": "file_123"}])
def test_files_veil_cant_read_first_are_refused(source):
    fake = FakeClient([_message("ok")])
    client = wrap(fake, files=Reader())
    with pytest.raises(FileError, match="base64"):
        client.messages.create(model="m", max_tokens=10, messages=[{"role": "user", "content": [_image_block(source=source)]}])
    assert fake.requests == []


def test_a_reader_that_fails_sends_nothing():
    def broken(data, media_type):
        raise ValueError("bad file")

    fake = FakeClient([_message("ok")])
    client = wrap(fake, files=broken)
    with pytest.raises(FileError, match="bad file"):
        client.messages.create(model="m", max_tokens=10, messages=[{"role": "user", "content": [_pdf_block()]}])
    assert fake.requests == []


def test_send_lets_files_go_as_they_are_but_document_text_is_redacted():
    fake = FakeClient([_message("ok")])
    client = wrap(fake, files="send")
    client.redactor.add_person("Avery Mockridge")
    content_doc = {"type": "document", "source": {"type": "content", "content": [
        {"type": "text", "text": "Avery Mockridge, SSN 123-45-6789"}, _image_block()]}}
    client.messages.create(model="m", max_tokens=10, messages=[{"role": "user", "content": [
        _pdf_block(context="For Avery Mockridge"), _image_block(), content_doc]}])
    sent = fake.requests[0]["messages"][0]["content"]
    assert sent[0]["source"] == _pdf_block()["source"] and sent[0]["context"] == "For NAME_001"
    assert sent[1] == _image_block()
    assert sent[2]["source"]["content"] == [{"type": "text", "text": "NAME_001, SSN SSN_001"}, _image_block()]


def test_files_must_be_a_known_choice():
    with pytest.raises(ValueError):
        wrap(FakeClient([]), files="maybe")


# -- reading real files --------------------------------------------------------------------------------------

def _text_pdf(text: str) -> bytes:
    """A one-page PDF with ``text`` on it in Helvetica."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [b"<< /Type /Catalog /Pages 2 0 R >>",
               b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
               b"/Resources << /Font << /F1 5 0 R >> >> >>",
               b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out, offsets = io.BytesIO(), []
    out.write(b"%PDF-1.4\n")
    for n, body in enumerate(objects, 1):
        offsets.append(out.tell())
        out.write(b"%d 0 obj\n" % n + body + b"\nendobj\n")
    xref = out.tell()
    out.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1))
    for offset in offsets:
        out.write(b"%010d 00000 n \n" % offset)
    out.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref))
    return out.getvalue()


def _picture_of(text: str):
    from PIL import Image, ImageDraw, ImageFont
    image = Image.new("RGB", (1400, 140), "white")
    ImageDraw.Draw(image).text((20, 40), text, fill="black", font=ImageFont.load_default(size=48))
    return image


needs_ocr = pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract isn't installed")


def test_read_text_reads_a_pdf():
    pytest.importorskip("pypdf")
    from veil.files import read_text
    assert read_text(_text_pdf("Partner Avery Mockridge SSN 123-45-6789"), "application/pdf") == \
        "Partner Avery Mockridge SSN 123-45-6789"


@needs_ocr
def test_read_text_reads_an_image_and_a_scanned_pdf():
    pytest.importorskip("pytesseract")
    pytest.importorskip("pypdf")
    from veil.files import read_text
    picture = _picture_of("SSN 123-45-6789")
    png, scan = io.BytesIO(), io.BytesIO()
    picture.save(png, format="PNG")
    picture.save(scan, format="PDF")
    assert "123-45-6789" in read_text(png.getvalue(), "image/png")
    assert "123-45-6789" in read_text(scan.getvalue(), "application/pdf")


@needs_ocr
def test_files_read_sends_no_taxpayer_id_from_a_scan():
    pytest.importorskip("pytesseract")
    png = io.BytesIO()
    _picture_of("SSN 123-45-6789").save(png, format="PNG")
    fake = FakeClient([_message("ok")])
    client = wrap(fake, files="read")
    client.messages.create(model="m", max_tokens=10, messages=[
        {"role": "user", "content": [_image_block(png.getvalue())]}])
    sent = _sent(fake)
    assert "6789" not in sent and "SSN_001" in json.loads(sent)[0]["messages"][0]["content"][0]["source"]["data"]


def _words(lines):
    """image_to_data's columns for lines of (left, words), each word 10px a letter, lines 40px apart."""
    data = {k: [] for k in ("block_num", "par_num", "line_num", "word_num", "left", "top", "width", "height", "text")}
    for n, (left, text) in enumerate(lines):
        x = left
        for k, word in enumerate(text.split()):
            for key, value in (("block_num", 1), ("par_num", 1), ("line_num", n + 1), ("word_num", k + 1), ("left", x),
                               ("top", 40 * n), ("width", 10 * len(word)), ("height", 30), ("text", word)):
                data[key].append(value)
            x += 10 * (len(word) + 1)
    return data


def test_reflow_joins_the_lines_a_page_wrapped_and_keeps_a_forms_lines():
    from veil.files import reflow
    wrapped = _words([(0, "The tenant, Avery Mockridge, lives at 1234 Main"), (0, "Street, Anytown, DE 12345, and pays all of"),
                      (0, "the rent each month to Lisandro Carballo-"), (0, "Ariza by bank transfer.")])
    assert reflow(wrapped) == ("The tenant, Avery Mockridge, lives at 1234 Main Street, Anytown, DE 12345, and pays all of "
                               "the rent each month to Lisandro Carballo-Ariza by bank transfer.")
    form = _words([(0, "Name: Avery Mockridge"), (0, "Address: 1234 Main Street"), (0, "Phone: 415-555-0134"),
                   (0, "The tenant pays the rent on the first day of every month, without fail, by bank transfer.")])
    assert reflow(form).split("\n")[:3] == ["Name: Avery Mockridge", "Address: 1234 Main Street", "Phone: 415-555-0134"]


@pytest.mark.parametrize("ocr, tidy", [
    ("Email: john:smith@example. com", "Email: john.smith@example.com"),
    ("jane,smith@example,com", "jane.smith@example.com"),
    ("residing at 5678. Elm Street, Toronto", "residing at 5678 Elm Street, Toronto"),
    ("640 Yoder Plains.Apt. 519", "640 Yoder Plains Apt. 519"),
    ("355 Kelly.Ramp", "355 Kelly Ramp"),
    ("located at 4826 Kristi Hil, which", "located at 4826 Kristi Hill, which"),
    ("Phorie:.+1-800-123-4567", "Phone: +1-800-123-4567"),
    ("Telephone: +44°1234.567890", "Telephone: +44 1234 567890"),
    ("Empioyee !D: 17028517", "Employee ID: 17028517"),
    ("means Claire Z: Thibault, whose", "means Claire Z. Thibault, whose"),
    ("Dear josephine M, Miller,", "Dear Josephine M. Miller,"),
    ("appointed Leoriard Leigh Rowe as", "appointed Leonard Leigh Rowe as"),
    ("Vancouver, BC, V6B.1C3", "Vancouver, BC, V6B 1C3"),
])
def test_ocr_misreadings_around_personal_details_are_mended(ocr, tidy):
    from veil.files import _tidy
    assert _tidy(ocr) == tidy


@pytest.mark.parametrize("text", [
    "1. Introduction", "We hired John. The team grew.", "Meeting at 10:30 Monday", "See www.Example.com",
    "Total: 1,234.56 at 2021.09.01", "We sold 500 Apple Pies, and", "<phone>819.496.2354</phone>", "Note: Payment due",
])
def test_ocr_tidying_leaves_ordinary_text_alone(text):
    from veil.files import _tidy
    assert _tidy(text) == text
