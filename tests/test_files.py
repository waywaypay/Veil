"""Images, PDFs and Word documents: read here and sent as redacted text, refused, or sent as they are, as ``files`` says."""

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
    pytest.importorskip("PIL")
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
    pytest.importorskip("PIL")
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
    ("at [support@mobilem\u00e9ney,.com](mailto", "at [support@mobilemeney.com](mailto"),
    ("mike.johnson@email.corn here", "mike.johnson@email.com here"),
    ('"Robinson-Patel","67.240. Nolan Junction, Suite 509"', '"Robinson-Patel","67240 Nolan Junction, Suite 509"'),
    ("Suite 300; Anytown,:AB T1Y 2B3", "Suite 300; Anytown, AB T1Y 2B3"),
    ("at Eleonore-Krebs-StraBe 6, Munich", "at Eleonore-Krebs-Stra\u00dfe 6, Munich"),
    ("London, UK\n\nSE1 12Z\n", "London, UK\n\nSE1 1ZZ\n"),
    ("Landing, RHSW 5RQ, South", "Landing, RH5W 5RQ, South"),
    ("Dear Mr. Tiziano Paolo loppi,", "Dear Mr. Tiziano Paolo Ioppi,"),
    ("Dear Insa |. Salz,", "Dear Insa I. Salz,"),
    ("\u201clast_name\u201d: \u201cSmith\u201d", '"last_name": "Smith"'),
    ("(mailto:mike.johnson@emai l.com)", "(mailto:mike.johnson@email.com)"),
    ("[olivia.davis@email.c om](mailto", "[olivia.davis@email.com](mailto"),
    ("Apt. 92806,lan Pamela Turner,9486", "Apt. 92806,Ian Pamela Turner,9486"),
    ("Name: Isabelle jourdan\n", "Name: Isabelle Jourdan\n"),
    ("2. Provided Rahe! with a list", "2. Provided Rahel with a list"),
    ("Engelbert He8: [name]", "Engelbert He\u00df: [name]"),
    ("London, UK\n\nSEl 122\n", "London, UK\n\nSE1 1ZZ\n"),
    ("Address: 456 Oak Street. Anytown, USA\n", "Address: 456 Oak Street, Anytown, USA\n"),
    ("address of 49249 Phillip junction, Katherineport", "address of 49249 Phillip Junction, Katherineport"),
    ("SSN: 384.35-2296\n", "SSN: 384-35-2296\n"),
    ("54652 Monica Mali (the", "54652 Monica Mall (the"),
    ("Telephone: +44 118 322 S111\n", "Telephone: +44 118 322 5111\n"),
    ("Email Address: johndoe@emai!.com\n", "Email Address: johndoe@email.com\n"),
    ("[a.b@email.com](mailto:a b@email.com)", "[a.b@email.com](mailto:a.b@email.com)"),
    ("Port Lauraberg, AB T2V 5}7, Canada", "Port Lauraberg, AB T2V 5J7, Canada"),
    ("at 1234 Main Street. Anytown. USA (", "at 1234 Main Street, Anytown, USA ("),
    ("located at 8905 johnson Fords, New Dennis", "located at 8905 Johnson Fords, New Dennis"),
    ("Dear isidro Armando Diego,", "Dear Isidro Armando Diego,"),
])
def test_ocr_misreadings_around_personal_details_are_mended(ocr, tidy):
    from veil.files import _tidy
    assert _tidy(ocr) == tidy


@pytest.mark.parametrize("text", [
    "1. Introduction", "We hired John. The team grew.", "Meeting at 10:30 Monday", "See www.Example.com",
    "Total: 1,234.56 at 2021.09.01", "We sold 500 Apple Pies, and", "<phone>819.496.2354</phone>", "Note: Payment due",
    "Maria lives here", "John loves it", "I live at 12 Oak Street. Then we left", "Wow! Great", "Dear friends,", "Phone Option: SOLO", "costs 1.240 Euro", "Big Strake", "Bob jumped", "Sarah just left",
])
def test_ocr_tidying_leaves_ordinary_text_alone(text):
    from veil.files import _tidy
    assert _tidy(text) == text


def test_a_pdf_s_wrapped_lines_are_joined():
    from veil.files import _rewrap
    text = "\n".join(["The tenant, Avery Mockridge, lives at 1234 Main Street, Anytown, DE 12345, and she pays the",
                     "rent each month by bank transfer to the landlord, who lives at 55 Oak Avenue, Springfield,",
                     "IL 62701, as the lease says it shall be paid, with any late fee added to it when due.",
                     "Name: Avery Mockridge", "Phone: 415-555-0134", "Date: 2024-01-01"])
    out = _rewrap(text)
    assert "Springfield, IL 62701" in out and "\nName: Avery Mockridge\nPhone: 415-555-0134" in out


# -- Word documents ---------------------------------------------------------------------------------------

_NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
       'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
       'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape" '
       'xmlns:v="urn:schemas-microsoft-com:vml"')


def _docx(body, header="", footer="", footnotes="", comments="", more=None):
    """A .docx of the given WordprocessingML, as Word lays its parts out; ``more``: other parts, by name."""
    import zipfile

    parts = {"word/document.xml": f"<w:document {_NS}><w:body>{body}</w:body></w:document>", **(more or {})}
    if header:
        parts["word/header1.xml"] = f"<w:hdr {_NS}>{header}</w:hdr>"
    if footer:
        parts["word/footer1.xml"] = f"<w:ftr {_NS}>{footer}</w:ftr>"
    if footnotes:
        parts["word/footnotes.xml"] = f"<w:footnotes {_NS}>{footnotes}</w:footnotes>"
    if comments:
        parts["word/comments.xml"] = f"<w:comments {_NS}>{comments}</w:comments>"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        for name, xml in parts.items():
            z.writestr(name, xml)
    return buf.getvalue()


def _p(*runs):
    return "<w:p>" + "".join(f"<w:r><w:t xml:space='preserve'>{r}</w:t></w:r>" for r in runs) + "</w:p>"


DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_a_word_documents_text_is_read_from_all_its_parts():
    from veil.files import read_text

    box = ("<w:p><w:r><mc:AlternateContent><mc:Choice Requires='wps'><w:drawing><wps:txbx><w:txbxContent>"
           + _p("Boxed: 12 Oak Lane") + "</w:txbxContent></wps:txbx></w:drawing></mc:Choice><mc:Fallback><w:pict>"
           "<v:textbox><w:txbxContent>" + _p("Boxed: 12 Oak Lane") + "</w:txbxContent></v:textbox></w:pict>"
           "</mc:Fallback></mc:AlternateContent></w:r></w:p>")
    body = (_p("Dear Ave", "ry Mock", "ridge,")   # Word cuts runs inside words
            + "<w:p><w:r><w:t>Phone:</w:t></w:r><w:r><w:tab/></w:r><w:r><w:t>415-555-0134</w:t></w:r></w:p>"
            + "<w:p><w:r><w:t>Was </w:t></w:r><w:del><w:r><w:delText>Jane Roe</w:delText></w:r></w:del>"
              "<w:ins><w:r><w:t>John Doe</w:t></w:r></w:ins></w:p>"
            + "<w:p><w:r><w:instrText> MERGEFIELD Email </w:instrText></w:r><w:r><w:t>a@b.com</w:t></w:r></w:p>"
            + "<w:tbl><w:tr><w:tc>" + _p("First Name") + "</w:tc><w:tc>" + _p("Priya") + "</w:tc></w:tr></w:tbl>"
            + box)
    text = read_text(_docx(body, header=_p("Letterhead Ltd"), footer=_p("Page 1"),
                           footnotes="<w:footnote w:id='1'>" + _p("A note on Lisandro") + "</w:footnote>",
                           comments="<w:comment w:id='0'>" + _p("Check with Kwame") + "</w:comment>"), DOCX)
    assert "Dear Avery Mockridge," in text
    assert "Phone:\t415-555-0134" in text
    assert "Was John Doe" in text and "Jane Roe" not in text   # a tracked deletion is gone
    assert "MERGEFIELD" not in text and "a@b.com" in text
    assert "| First Name | Priya |" in text
    assert text.count("Boxed: 12 Oak Lane") == 1   # the copy for old readers isn't read twice
    for part in ("Letterhead Ltd", "Page 1", "A note on Lisandro", "Check with Kwame"):
        assert part in text


def test_what_veil_hides_in_a_word_form():
    from veil.files import read_text

    body = ("<w:tbl><w:tr><w:tc>" + _p("First Name") + "</w:tc><w:tc>" + _p("Wei") + "</w:tc><w:tc>"
            + _p("Last Name") + "</w:tc><w:tc>" + _p("Tan") + "</w:tc></w:tr></w:tbl>"
            + _p("The applicant, Avery Mockridge, lives at 1234 Main Street, Anytown, DE 12345."))
    out = Redactor(FINANCE).redact_text(read_text(_docx(body), DOCX))
    for secret in ("Wei", "Tan", "Mockridge", "1234 Main"):
        assert secret not in out


@pytest.mark.parametrize("data, media_type, message", [
    (b"not a zip", DOCX, "isn't a Word"), (b"\xd0\xcf\x11\xe0", "application/msword", "save it as .docx")])
def test_a_file_that_isnt_a_docx_says_so(data, media_type, message):
    from veil.files import read_text

    with pytest.raises(ValueError, match=message):
        read_text(data, media_type)


def _bomb(size):
    """A small .docx whose one other part unpacks to ``size`` bytes of zeros."""
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("word/document.xml", f"<w:document {_NS}><w:body>{_p('Hi')}</w:body></w:document>")
        z.writestr("word/media/fill.bin", b"\0" * size)
    return buf.getvalue()


def test_a_word_document_that_would_unpack_too_far_is_refused_before_it_is_read(monkeypatch):
    from veil import Redactor
    from veil.files import read_text, redact_docx, restore_docx

    monkeypatch.setattr("veil.files.DOCX_MAX_UNPACKED", 1_000_000)
    bomb = _bomb(2_000_000)
    assert len(bomb) < 20_000
    for read in (lambda: read_text(bomb, DOCX), lambda: redact_docx(bomb), lambda: restore_docx(bomb, Redactor())):
        with pytest.raises(ValueError, match="would unpack to 2,000,"):
            read()
    assert read_text(_bomb(100_000), DOCX) == "Hi"


def test_a_word_document_with_too_many_parts_is_refused(monkeypatch):
    from veil.files import read_text

    monkeypatch.setattr("veil.files.DOCX_MAX_PARTS", 3)
    many = _docx(_p("Hi"), more={f"word/part{n}.xml": "<x/>" for n in range(3)})
    with pytest.raises(ValueError, match="in 5 files"):
        read_text(many, DOCX)


def test_a_word_document_that_lies_about_its_size_isnt_read_past_it():
    """The limit is on the sizes the zip states; reading a part stops at its stated size, so a part that
    unpacks to more than it says fails its checksum rather than filling memory."""
    import struct
    import zipfile

    from veil.files import read_text

    data = bytearray(_bomb(5_000_000))
    for signature, at, name_at, start in ((b"PK\x03\x04", 22, 26, 30), (b"PK\x01\x02", 24, 28, 46)):
        i = data.find(signature)
        while i != -1:
            length = struct.unpack_from("<H", data, i + name_at)[0]
            if data[i + start:i + start + length] == b"word/media/fill.bin":
                struct.pack_into("<I", data, i + at, 10)   # "unpacks to 10 bytes"
            i = data.find(signature, i + 4)
    with zipfile.ZipFile(io.BytesIO(bytes(data))) as z, pytest.raises(zipfile.BadZipFile):
        z.read("word/media/fill.bin")
    assert read_text(bytes(data), DOCX) == "Hi"   # the size check passes; the part is never read for text


def test_files_read_sends_a_word_document_as_its_text_with_placeholders():
    fake = FakeClient([_message("ok")])
    client = wrap(fake, Redactor(FINANCE), files="read")
    data = _docx(_p("Partner: Avery Mockridge") + _p("SSN 123-45-6789"))
    block = {"type": "document", "source": {"type": "base64", "media_type": DOCX, "data": _b64(data)}}
    client.messages.create(model="m", max_tokens=10, messages=[{"role": "user", "content": [block]}])
    sent = _sent(fake)
    assert "Mockridge" not in sent and "6789" not in sent
    doc = fake.requests[0]["messages"][0]["content"][0]
    assert doc["source"]["type"] == "text" and "NAME_001" in doc["source"]["data"]


def test_a_word_document_is_refused_by_name():
    client = wrap(FakeClient([_message("ok")]))
    block = {"type": "document", "source": {"type": "base64", "media_type": DOCX, "data": _b64(b"x")}}
    with pytest.raises(FileError, match="A Word document"):
        client.messages.create(model="m", max_tokens=10, messages=[{"role": "user", "content": [block]}])


_CORE = ('<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
         'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Lease for Priya Natarajan</dc:title>'
         '<dc:creator>Avery Mockridge</dc:creator><cp:lastModifiedBy>jdoe</cp:lastModifiedBy></cp:coreProperties>')
_RELS = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
         '<Relationship Id="rId9" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" '
         'Target="mailto:avery.mockridge@example.com" TargetMode="External"/></Relationships>')


def _word_letter():
    box = ("<w:p><w:r><mc:AlternateContent><mc:Choice Requires='wps'><w:drawing><wps:txbx><w:txbxContent>"
           + _p("Tenant: Wei Tan") + "</w:txbxContent></wps:txbx></w:drawing></mc:Choice><mc:Fallback><w:pict>"
           "<v:textbox><w:txbxContent>" + _p("Tenant: Wei Tan") + "</w:txbxContent></v:textbox></w:pict>"
           "</mc:Fallback></mc:AlternateContent></w:r></w:p>")
    body = ("<w:p><w:r><w:t>Dear Ave</w:t></w:r><w:r><w:rPr><w:b/></w:rPr><w:t>ry Mock</w:t></w:r>"
            "<w:r><w:t>ridge,</w:t></w:r></w:p>"
            + "<w:p><w:r><w:t>Phone:</w:t></w:r><w:r><w:tab/></w:r><w:r><w:t>415-555-0134</w:t></w:r></w:p>"
            + "<w:p><w:r><w:t xml:space='preserve'>Was </w:t></w:r><w:del w:author='Avery Mockridge'><w:r>"
              "<w:delText>Jane Roe</w:delText></w:r></w:del><w:ins w:author='Avery Mockridge'><w:r>"
              "<w:t>the landlord</w:t></w:r></w:ins></w:p>"
            + "<w:p><w:r><w:fldChar w:fldCharType='begin'/></w:r><w:r><w:instrText xml:space='preserve'> HYPERLINK "
              "\"mailto:avery.mock</w:instrText></w:r><w:r><w:instrText>ridge@example.com\" </w:instrText></w:r>"
              "<w:r><w:fldChar w:fldCharType='separate'/>"
              "</w:r><w:r><w:t>Email me</w:t></w:r><w:r><w:fldChar w:fldCharType='end'/></w:r></w:p>"
            + "<w:tbl><w:tr><w:tc>" + _p("SSN") + "</w:tc><w:tc>" + _p("123-45-6789") + "</w:tc></w:tr></w:tbl>"
            + box)
    return _docx(body, header=_p("Avery Mockridge, 1234 Main Street, Anytown, DE 12345"),
                 comments="<w:comment w:id='0' w:author='Avery Mockridge' w:initials='AM'>"
                          + _p("Ask Priya to sign") + "</w:comment>",
                 more={"docProps/core.xml": _CORE, "word/_rels/document.xml.rels": _RELS,
                       "word/_rels/settings.xml.rels": _RELS.replace("mailto:avery.mockridge@example.com",
                                                                     "file:///C:\\Users\\jdoe\\Normal.dotm"),
                       "word/media/image1.png": _png_bytes()})


def _png_bytes():
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (40, 20), "black").save(buf, "PNG")
    return buf.getvalue()


def _package(data):
    import zipfile

    with zipfile.ZipFile(io.BytesIO(data)) as z:
        return {n: z.read(n) for n in z.namelist()}


def test_a_redacted_word_document_says_nothing_personal_anywhere_in_it():
    from veil.files import redact_docx

    parts = _package(redact_docx(_word_letter(), Redactor(FINANCE)))
    everything = b"".join(parts.values())
    for secret in (b"Mockridge", b"Avery", b"415-555", b"6789", b"avery.mock", b"Main Street", b"Priya",
                   b"Natarajan", b"Wei Tan", b"Jane Roe", b"jdoe", b"w:initials"):
        assert secret not in everything, secret
    assert parts["word/media/image1.png"] != _png_bytes()   # a white picture in its place


def test_a_redacted_word_document_keeps_its_runs_and_reads_as_the_redacted_text():
    from veil.files import read_text, redact_docx

    redactor = Redactor(FINANCE)
    out = redact_docx(_word_letter(), redactor)
    text = read_text(out, DOCX)
    assert "Dear NAME_001," in text and "Phone:\tPHONE_001" in text and "| SSN | SSN_001 |" in text
    assert "Was the landlord" in text and "Email me" in text and text.count("Tenant: NAME_") == 1
    body = _package(out)["word/document.xml"].decode()
    assert "<w:t xml:space=\"preserve\">Dear NAME_001</w:t>" in body   # in the first run, as it was
    assert body.count("<w:b/>") == 1 and "mailto:EMAIL_001" in body
    assert 'w:author="NAME_001"' in _package(out)["word/comments.xml"].decode()


def test_a_redacted_word_document_comes_back_with_restore_docx():
    from veil.files import read_text, redact_docx, restore_docx

    redactor = Redactor(FINANCE)
    original = _word_letter()
    back = restore_docx(redact_docx(original, redactor), redactor)
    assert read_text(back, DOCX) == read_text(original, DOCX)
    parts = _package(back)
    assert b"<dc:creator>Avery Mockridge</dc:creator>" in parts["docProps/core.xml"]
    assert b"mailto:avery.mockridge@example.com" in parts["word/_rels/document.xml.rels"]


def test_a_word_document_keeps_its_pictures_when_asked():
    from veil.files import redact_docx

    assert _package(redact_docx(_word_letter(), pictures="keep"))["word/media/image1.png"] == _png_bytes()
    with pytest.raises(ValueError, match="pictures"):
        redact_docx(_word_letter(), pictures="hide")


def test_a_file_embedded_in_a_word_document_is_refused():
    from veil.files import redact_docx

    data = _docx(_p("Name: Avery Mockridge"), more={"word/embeddings/oleObject1.bin": b"\xd0\xcf\x11\xe0"})
    with pytest.raises(ValueError, match="oleObject1.bin"):
        redact_docx(data)
