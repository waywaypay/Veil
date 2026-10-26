"""Text out of PDFs and images, read on this machine, so it can be redacted before a model sees it.

    from veil.files import read_text

    text = read_text(pdf_bytes, "application/pdf")   # the PDF's own text; scanned pages are read with OCR
    text = read_text(png_bytes, "image/png")         # OCR
    safe = redactor.redact_text(text)

    safe_docx = redact_docx(docx_bytes, redactor)    # the Word document itself, its personal details replaced

PDFs need ``pypdf``; images and scanned pages need ``pytesseract``, ``Pillow`` and the Tesseract program
(``pip install "veil[files]"``, and ``apt install tesseract-ocr`` or ``brew install tesseract``).  Nothing
is sent anywhere: both run in this process.
"""

from __future__ import annotations

import io
import re
import unicodedata

IMAGE_TYPES = ("image/jpeg", "image/png", "image/gif", "image/webp")
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
# The most a Word document may unpack to, and the most files it may hold.  A .docx is a zip, and a small zip can
# unpack to gigabytes (a "zip bomb"); one over either limit is refused before anything in it is read.  Each
# file's unpacked size is the one the zip states, which reading holds it to.  Raise them if you need to.
DOCX_MAX_UNPACKED = 256 * 1024 * 1024
DOCX_MAX_PARTS = 10_000


def read_text(data: bytes, media_type: str) -> str:
    """The text in a PDF, a Word document or an image.  A PDF page with no text of its own (a scan) is read
    with OCR, and so is a page-sized picture in a Word document."""
    if media_type == "application/pdf":
        return _pdf(data)
    if media_type == DOCX_TYPE:
        return _docx(data)
    if media_type == "application/msword":
        raise ValueError("veil reads Word's .docx files, not the older .doc: save it as .docx first")
    if media_type in IMAGE_TYPES:
        return _ocr(_open_image(data))
    if media_type.startswith("text/"):
        return data.decode("utf-8", errors="replace")
    raise ValueError(f"veil can't read text out of {media_type} files")


def _pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ImportError('Reading PDFs needs pypdf: pip install "veil[files]"') from exc
    pages = []
    for page in PdfReader(io.BytesIO(data)).pages:
        text = page.extract_text() or ""
        if not text.strip():   # a scanned page: read the pictures on it
            text = "\n".join(_ocr(image.image) for image in page.images)
        pages.append(_rewrap(text.strip()))
    return "\n\n".join(p for p in pages if p)


def _rewrap(text: str) -> str:
    """A PDF's text with the lines its page wrapped joined again, as ``reflow`` joins OCR's: a line about as long
    as the page's longest, then one that carries on the sentence (no list mark or label starts it)."""
    lines = text.split("\n")
    counts = sorted(len(line) for line in lines if line.strip())
    if len(counts) < 5:
        return text
    longest = counts[int(0.95 * (len(counts) - 1))]
    out = [lines[0]]
    for line in lines[1:]:
        prev = out[-1]
        first = line.strip().split(" ")[0] if line.strip() else ""
        if first and len(prev) >= 0.75 * longest and len(prev) + 1 + len(first) > 0.9 * longest and \
                not re.match(r"[-*\u2022|#>]|\d{1,2}[.)]|[A-Z][\w ]{0,30}:", line.strip()) and \
                not prev.rstrip().endswith(":") and len(re.findall(r",(?! )|\|", prev)) < 3:
            out[-1] = prev.rstrip() + ("" if prev.rstrip().endswith("-") else " ") + line.strip()
        else:
            out.append(line)
    return "\n".join(out)


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"


def _docx(data: bytes) -> str:
    """A Word document's text, read with the standard library: its body, tables (a row to a line, its cells
    between bars, as a form's "| Name | Jane Doe |"), text boxes, headers and footers, footnotes, endnotes and
    comments, in that order.  Text a tracked change deleted is left out, as Word shows it struck through
    and the document no longer says it; field codes are left out, their results kept.  A picture big enough
    to be a pasted page is read with OCR, when Tesseract is there."""
    with _open_docx(data) as archive:
        names = archive.namelist()
        texts = [_wordml(archive.read(n)) for n in _text_parts(names)]
        for name in _part(names, r"word/media/[^/]+\.(?:png|jpe?g|gif|bmp|tiff?)"):
            try:
                image = _open_image(archive.read(name))
                if image.width >= 800 and image.height >= 500:   # a page, not a logo or a signature
                    texts.append(_ocr(image))
            except ImportError:
                break   # no OCR here: the document's own text is all there is
            except Exception:
                continue   # a picture Pillow can't open
    return "\n\n".join(t.strip() for t in texts if t.strip())


def _open_docx(data: bytes):
    import zipfile

    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("this isn't a Word (.docx) document") from exc
    if "word/document.xml" not in archive.namelist():
        archive.close()
        raise ValueError("this isn't a Word (.docx) document")
    infos = archive.infolist()
    unpacked = sum(i.file_size for i in infos)
    if len(infos) > DOCX_MAX_PARTS or unpacked > DOCX_MAX_UNPACKED:
        archive.close()
        raise ValueError(f"this Word document would unpack to {unpacked:,} bytes in {len(infos):,} files, over "
                         f"the limit of {DOCX_MAX_UNPACKED:,} bytes in {DOCX_MAX_PARTS:,} files "
                         "(veil.files.DOCX_MAX_UNPACKED, DOCX_MAX_PARTS)")
    return archive


def _part(names: list[str], pattern: str) -> list[str]:
    return sorted((n for n in names if re.fullmatch(pattern, n)),
                  key=lambda n: [int(d) if d.isdigit() else d for d in re.split(r"(\d+)", n)])


def _text_parts(names: list[str]) -> list[str]:
    return (["word/document.xml"] + _part(names, r"word/header\d*\.xml") + _part(names, r"word/footer\d*\.xml") +
            _part(names, r"word/(?:footnotes|endnotes|comments)\.xml"))


def _wordml(xml: bytes) -> str:
    """The text of one part of a Word document (its body, a header, the footnotes ...)."""
    return _read_wordml(_dom(xml).documentElement).text


def _dom(xml: bytes):
    from xml.dom import minidom

    return minidom.parseString(xml)


def _tag(node) -> str:
    return f"{{{node.namespaceURI}}}{node.localName}"


def _elements(node) -> list:
    return [c for c in node.childNodes if c.nodeType == c.ELEMENT_NODE]


def _own_text(node) -> str:
    return "".join(c.data for c in node.childNodes if c.nodeType in (c.TEXT_NODE, c.CDATA_SECTION_NODE))


class _Chars:
    """Text read out of a Word document, each character with where it came from: ``(a w:t element, its place
    in the element's text)``; ``(the element, None)`` for a tab or a break, which an element stands for; or
    None for what the reading put in (a table's bars, the line between two paragraphs)."""

    def __init__(self, chars: list[str] | None = None, where: list | None = None):
        self.chars = chars if chars is not None else []
        self.where = where if where is not None else []

    @property
    def text(self) -> str:
        return "".join(self.chars)

    def add(self, text: str, where=None) -> None:
        self.chars.extend(text)
        self.where.extend([where] * len(text))

    def add_t(self, element, text: str) -> None:
        self.chars.extend(text)
        self.where.extend((element, i) for i in range(len(text)))

    def extend(self, other: _Chars) -> None:
        self.chars.extend(other.chars)
        self.where.extend(other.where)

    def strip(self) -> _Chars:
        text = self.text
        a, b = len(text) - len(text.lstrip()), len(text.rstrip())
        return _Chars(self.chars[a:b], self.where[a:b]) if b > a else _Chars()

    @staticmethod
    def join(sep: str, parts: list[_Chars]) -> _Chars:
        out = _Chars()
        for k, part in enumerate(parts):
            if k:
                out.add(sep)
            out.extend(part)
        return out


def _read_wordml(root, copies: bool = False) -> _Chars:
    """The text of a part of a Word document, as ``_wordml`` reads it, with where each character came from.
    ``copies``: read the copy of a text box Word keeps for old readers too, as the redacted file keeps it."""
    lines: list[_Chars] = []
    skip = {f"{_W}del", f"{_W}moveFrom", f"{_W}instrText", f"{_W}delText"} | (set() if copies else {f"{_MC}Fallback"})
    signs = {f"{_W}tab": "\t", f"{_W}br": "\n", f"{_W}cr": "\n", f"{_W}noBreakHyphen": "-"}

    def runs(node, out: _Chars, boxes: list) -> None:
        for child in _elements(node):
            tag = _tag(child)
            if tag in skip:
                continue   # deleted or moved-away text; a field's code; a drawing's copy for old readers
            if tag == f"{_W}t":
                out.add_t(child, _own_text(child))
            elif tag in signs:
                out.add(signs[tag], (child, None))
            elif tag == f"{_W}txbxContent":
                boxes.append(child)   # a text box: its paragraphs on their own lines, after this one
            else:
                runs(child, out, boxes)

    def paragraph(p) -> None:
        out = _Chars()
        boxes: list = []
        runs(p, out, boxes)
        lines.append(out)
        for box in boxes:
            block(box)

    def cell_text(tc) -> _Chars:
        parts = []
        for p in tc.getElementsByTagNameNS(_W[1:-1], "p"):
            out = _Chars()
            runs(p, out, [])
            parts.append(out.strip())
        cell = _Chars.join(" ", [x for x in parts if x.chars])
        cell.chars = ["/" if c == "|" else c for c in cell.chars]
        return cell

    def table(tbl) -> None:
        for tr in _elements(tbl):
            if _tag(tr) != f"{_W}tr":
                continue
            cells = [cell_text(tc) for tc in _elements(tr) if _tag(tc) == f"{_W}tc"]
            if any(c.chars for c in cells):
                row = _Chars()
                row.add("| ")
                row.extend(_Chars.join(" | ", cells))
                row.add(" |")
                lines.append(row)
        lines.append(_Chars())

    def block(node) -> None:
        for child in _elements(node):
            tag = _tag(child)
            if tag == f"{_W}p":
                paragraph(child)
            elif tag == f"{_W}tbl":
                table(child)
            elif tag in (f"{_W}sdt", f"{_W}sdtContent", f"{_W}body", f"{_W}customXml", f"{_W}hdr", f"{_W}ftr",
                         f"{_W}footnote", f"{_W}endnote", f"{_W}comment", f"{_W}txbxContent", f"{_W}ins",
                         f"{_W}moveTo"):
                block(child)

    body = next((c for c in _elements(root) if _tag(c) == f"{_W}body"), root)
    block(body)
    text = _Chars.join("\n", lines)
    keep = bytearray(b"\x01") * len(text.chars)
    for m in re.finditer(r"\n{3,}", text.text):   # as many blank lines as there are, one
        keep[m.start() + 2:m.end()] = bytes(m.end() - m.start() - 2)
    return _Chars([c for c, k in zip(text.chars, keep) if k], [w for w, k in zip(text.where, keep) if k])


# -- writing a redacted Word document ---------------------------------------------------------------------

_PICTURE = re.compile(r"(?i).+\.(png|jpe?g|gif|bmp|tiff?|emf|wmf|svg|wdp|jxr)")
# A part with no text and none of these is left as it is (styles, fonts, the theme, numbering).
_MAY_SAY = re.compile(rb">\s*[^<\s]|(?:author|initials|descr|title|tooltip|instr|alt|string)=")
_AUTHORS = ("creator", "lastModifiedBy", "Manager")   # docProps: who wrote it, last saved it, manages it
_ALT_TEXT = ("descr", "title", "name")                # a picture's: its alt text, title and file's name
_NOT_AUTHORS = frozenset(("microsoft office user", "unknown author", "author", "user", "administrator"))


def redact_docx(data: bytes, redactor=None, pictures: str = "blank") -> bytes:
    """A Word document with its personal information replaced by ``redactor``'s placeholders, everything else
    as it was: the formatting, tables, headers and footers, comments, footnotes and layout.

    The text is redacted as ``read_text`` reads it, all of it at once, so a form's labels and the names it
    gives count everywhere in it; each placeholder takes the place of what it hides in the document's own
    runs, in the first run's formatting.  Also hidden: who wrote the document, its comments and its tracked
    changes (as placeholders), initials, a picture's alt text, field codes ("HYPERLINK mailto:..."), link
    addresses, and the document's title, subject and keywords.  Tracked deletions are accepted, as the
    document no longer says them.

    ``pictures``: "blank" (the default) puts a white picture in place of each picture (a signature, a pasted
    scan, the document's thumbnail), as veil can't hide what's in one; "keep" leaves them.  A file embedded
    in the document (a spreadsheet, a PDF) is refused, as veil can't redact what's inside one, except a
    chart's own spreadsheet, which is left out (the chart stays, its data no longer editable).

    ``redactor``: a ``veil.Redactor``, to share placeholders with the conversation the document goes into
    (``restore_docx`` puts the real text back); a new one by default."""
    import posixpath

    from veil.redactor import Redactor, _fold

    if pictures not in ("blank", "keep"):
        raise ValueError('pictures must be "blank" or "keep"')
    redactor = redactor if redactor is not None else Redactor()
    redactor.register_kind("NAME")
    with _open_docx(data) as archive:
        infos = archive.infolist()
        files = {i.filename: archive.read(i.filename) for i in infos}
    names = list(files)
    xml = {n for n in names if n.lower().endswith((".xml", ".rels", ".vml"))}
    doms = {n: _dom(files[n]) for n in sorted(xml) if n.endswith(".rels") or _MAY_SAY.search(files[n])}

    # What's in the package that isn't XML or a picture: a chart's spreadsheet is left out; anything else
    # embedded (an OLE object, a spreadsheet, a PDF, macros) is refused.
    dropped: set[str] = set()
    for rels_name in [n for n in doms if n.endswith(".rels")]:
        source = posixpath.join(posixpath.dirname(posixpath.dirname(rels_name)),
                                posixpath.basename(rels_name)[:-len(".rels")])
        for rel in doms[rels_name].getElementsByTagName("Relationship"):
            if rel.getAttribute("TargetMode") == "External":
                continue
            target = rel.getAttribute("Target")
            path = target.lstrip("/") if target.startswith("/") else \
                posixpath.normpath(posixpath.join(posixpath.dirname(source), target))
            if path in files and re.fullmatch(r"word/charts/chart\d*\.xml", source) and \
                    path.startswith("word/embeddings/"):
                dropped.add(path)
                rel.parentNode.removeChild(rel)
                chart = doms.setdefault(source, _dom(files[source]))
                for data_ref in chart.getElementsByTagNameNS("*", "externalData"):
                    data_ref.parentNode.removeChild(data_ref)
    for name in names:
        if name in xml or name in dropped or name.endswith("/") or _PICTURE.fullmatch(name) or \
                re.fullmatch(r"word/(?:fonts/[^/]+\.odttf|printerSettings/[^/]+\.bin)", name):
            continue
        raise ValueError(f"veil can't redact what's inside {name}, a file embedded in this document: "
                         "take it out, or redact it on its own")
    if dropped and "[Content_Types].xml" in xml:
        doms["[Content_Types].xml"] = _dom(files["[Content_Types].xml"])
        for override in doms["[Content_Types].xml"].getElementsByTagName("Override"):
            if override.getAttribute("PartName").lstrip("/") in dropped:
                override.parentNode.removeChild(override)

    authors: dict[str, str] = {}

    def author(name: str) -> str:
        name = " ".join(name.split())
        if name and name not in authors:
            found = redactor.redact_text(name)
            authors[name] = found if redactor._placeholder_re.fullmatch(found) else \
                redactor._placeholder("NAME", f"NAME:{_fold(name)}", name, False)
        return authors.get(name, name)

    def target(path: str) -> str:   # a link's address; a template's, with its user's folder in it
        return re.sub(r"(?i)((?:^|[\\/])(?:Users|Documents and Settings|home)[\\/])([^\\/]+)",
                      lambda m: m.group(1) + author(m.group(2)), redactor.redact_text(path))

    # The people who wrote it are hidden wherever the text names them.
    for dom in doms.values():
        for node in _walk(dom.documentElement):
            for attr in list(node.attributes.values()) if node.attributes else ():
                if attr.localName == "author" and len(attr.value.split()) > 1 and _fold(attr.value) not in _NOT_AUTHORS:
                    redactor.add_person(attr.value)
            if node.localName in _AUTHORS and len(_own_text(node).split()) > 1 and \
                    _fold(_own_text(node)) not in _NOT_AUTHORS:
                redactor.add_person(_own_text(node))

    # The text, as read_text reads it, redacted as one, each placeholder put where what it hides was.
    parts = [n for n in _text_parts(names) if n in doms]
    texts = []
    for name in parts:
        root = doms[name].documentElement
        for node in [n for n in _walk(root) if _tag(n) in (f"{_W}del", f"{_W}moveFrom")]:
            if node.parentNode is not None:
                node.parentNode.removeChild(node)   # a tracked deletion, accepted
        texts.append(_read_wordml(root).strip())
    for name in ("docProps/core.xml", "docProps/app.xml", "docProps/custom.xml"):   # its title, subject ...
        lines = []
        for node in _walk(doms[name].documentElement) if name in doms else ():
            if node.localName not in _AUTHORS and not _elements(node) and _own_text(node).strip():
                lines.append(_Chars())
                lines[-1].add_t(node, _own_text(node))
        texts.append(_Chars.join("\n", lines))
    whole = _Chars.join("\n\n", [t for t in texts if t.chars])
    read = {w[0] for w in whole.where if w is not None and w[1] is not None}
    _rewrite(whole, _replaced(whole.text, redactor.redact_text(whole.text), redactor))
    for name in parts:   # a field's code, which Word can split across runs ("HYPERLINK \"mailto:avery.mock" ...)
        for code in _field_codes(doms[name].documentElement):
            read.update(w[0] for w in code.where)
            _rewrite(code, _replaced(code.text, redactor.redact_text(code.text), redactor))
        for choice, fallback in _text_box_copies(doms[name].documentElement):   # Word's copy for old readers
            if choice is not None:
                for child in list(fallback.childNodes):
                    fallback.removeChild(child)
                for child in choice.childNodes:
                    fallback.appendChild(child.cloneNode(True))
            else:
                copy = _read_wordml(fallback).strip()
                _rewrite(copy, _replaced(copy.text, redactor.redact_text(copy.text), redactor))
            read.update(_walk(fallback))

    # The rest on its own: field codes, a chart's labels, the document's title, alt text, link addresses.
    for name, dom in doms.items():
        if name == "[Content_Types].xml":
            continue
        for node in _walk(dom.documentElement):
            if name.endswith(".rels"):
                if node.getAttribute("TargetMode") == "External":
                    node.setAttribute("Target", target(node.getAttribute("Target")))
                continue
            if node.localName == "presenceInfo":   # an author's account and address
                node.parentNode.removeChild(node)
                continue
            for attr in list(node.attributes.values()) if node.attributes else ():
                if attr.localName == "author":
                    attr.value = author(attr.value)
                elif attr.localName == "initials":
                    node.removeAttributeNode(attr)
                elif attr.localName in ("tooltip", "instr", "alt") or \
                        (attr.localName, node.localName) in (("val", "docVar"), ("string", "textpath")) or \
                        (attr.localName in _ALT_TEXT and node.localName in ("docPr", "cNvPr", "imagedata")):
                    attr.value = redactor.redact_text(attr.value)
            if node in read:
                continue
            for child in node.childNodes:
                if child.nodeType in (child.TEXT_NODE, child.CDATA_SECTION_NODE) and child.data.strip():
                    child.data = author(child.data) if node.localName in _AUTHORS else redactor.redact_text(child.data)
    for name in names:
        if name in doms:
            files[name] = _xml(doms[name])
        elif pictures == "blank" and _PICTURE.fullmatch(name):
            files[name] = _blank_picture(name)
    return _zip(infos, files, dropped)


def restore_docx(data: bytes, redactor) -> bytes:
    """A Word document with ``redactor``'s placeholders in it turned back into what they hid, as
    ``redactor.restore_text`` puts them back: a document ``redact_docx`` made, edited by someone who never
    saw the real names.  Pictures ``redact_docx`` blanked stay blank."""
    with _open_docx(data) as archive:
        infos = archive.infolist()
        files = {i.filename: archive.read(i.filename) for i in infos}
    doms = {n: _dom(files[n]) for n in files if n.lower().endswith((".xml", ".rels", ".vml")) and
            redactor._placeholder_re.search(files[n].decode("utf-8", "replace"))}
    parts = [n for n in _text_parts(list(files)) if n in doms]
    whole = _Chars.join("\n\n", [t for t in (_read_wordml(doms[n].documentElement, copies=True).strip()
                                             for n in parts) if t.chars])
    read = {w[0] for w in whole.where if w is not None and w[1] is not None}
    text = whole.text
    _rewrite(whole, [(a, b, redactor.restore_text(text[a:b])) for a, b in redactor._placeholder_spans(text)])
    for name, dom in doms.items():
        for node in _walk(dom.documentElement):
            for attr in list(node.attributes.values()) if node.attributes else ():
                if redactor._placeholder_re.search(attr.value):
                    attr.value = redactor.restore_text(attr.value)
            if node in read:
                continue
            for child in node.childNodes:
                if child.nodeType in (child.TEXT_NODE, child.CDATA_SECTION_NODE) and \
                        redactor._placeholder_re.search(child.data):
                    child.data = redactor.restore_text(child.data)
        files[name] = _xml(dom)
    return _zip(infos, files, set())


def _text_box_copies(root) -> list[tuple]:
    """Each text box in a drawing's copy for old readers, with the text box it copies (the redacted one, to
    copy again), or None where the two don't pair up."""
    pairs = []
    for node in _walk(root):
        if _tag(node) == f"{_MC}AlternateContent":
            choice = [b for c in _elements(node) if _tag(c) == f"{_MC}Choice"
                      for b in c.getElementsByTagNameNS(_W[1:-1], "txbxContent")]
            fallback = [b for c in _elements(node) if _tag(c) == f"{_MC}Fallback"
                        for b in c.getElementsByTagNameNS(_W[1:-1], "txbxContent")]
            paired = len(choice) == len(fallback)
            pairs += [(choice[k] if paired else None, box) for k, box in enumerate(fallback)]
    return pairs


def _field_codes(root) -> list[_Chars]:
    """Each field's code in a part (``HYPERLINK "mailto:..."``), its pieces in the runs it's split across."""
    codes, code = [], _Chars()
    for node in _walk(root):
        if _tag(node) == f"{_W}instrText":
            code.add_t(node, _own_text(node))
        elif _tag(node) in (f"{_W}fldChar", f"{_W}p") and code.chars:
            codes.append(code)
            code = _Chars()
    return codes + ([code] if code.chars else [])


def _walk(root):
    """Every element under ``root``, ``root`` first, in document order; safe to remove the one just given."""
    stack = [root]
    while stack:
        node = stack.pop()
        yield node
        stack.extend(reversed(_elements(node)))


def _replaced(text: str, out: str, redactor) -> list[tuple[int, int, str]]:
    """Where in ``text`` each placeholder in ``out`` (``text`` redacted) took the place of what it hides, as
    ``(start, end, placeholder)``: the text between placeholders is ``text``'s own, so each stretch of it is
    found in turn.  (A redactor writes an underscore that isn't in one of its placeholders as a hyphen.)"""
    spans = redactor._placeholder_spans(out)
    if not spans:
        return []
    plain, said = text.replace("_", "‐"), out.replace("_", "‐")
    stretches = [said[a:b] for a, b in zip([0] + [e for _, e in spans], [s for s, _ in spans] + [len(out)])]
    if not plain.startswith(stretches[0]) or not plain.endswith(stretches[-1]):
        raise RuntimeError("veil couldn't place its placeholders in the document: nothing was written")
    found, at = [], len(stretches[0])
    for (start, end), stretch in zip(spans, stretches[1:-1]):
        nxt = plain.find(stretch, at + 1)
        if nxt < 0:
            raise RuntimeError("veil couldn't place its placeholders in the document: nothing was written")
        found.append((at, nxt, out[start:end]))
        at = nxt + len(stretch)
    if len(plain) - len(stretches[-1]) <= at:
        raise RuntimeError("veil couldn't place its placeholders in the document: nothing was written")
    found.append((at, len(plain) - len(stretches[-1]), out[spans[-1][0]:spans[-1][1]]))
    return found


def _rewrite(chars: _Chars, changes: list[tuple[int, int, str]]) -> None:
    """Each ``(start, end, new)`` of ``chars``'s text written into the elements it was read from: ``new`` in
    the first w:t of the stretch, where it starts, and the rest of the stretch taken out of its elements (a tab
    or a break in it too)."""
    cuts: dict = {}
    gone = []
    for start, end, new in changes:
        k = start
        while k < end:
            where = chars.where[k]
            if where is None:
                k += 1
                continue
            element, i = where
            if i is None:
                gone.append(element)
                k += 1
                continue
            j = k
            while j + 1 < end and chars.where[j + 1] is not None and chars.where[j + 1][0] is element and \
                    chars.where[j + 1][1] == chars.where[j][1] + 1:
                j += 1
            cuts.setdefault(element, []).append((i, chars.where[j][1] + 1, new))
            new = ""
            k = j + 1
    for element, spans in cuts.items():
        text = _own_text(element)
        for a, b, new in sorted(spans, reverse=True):
            text = text[:a] + new + text[b:]
        for child in list(element.childNodes):
            element.removeChild(child)
        element.appendChild(element.ownerDocument.createTextNode(text))
        element.setAttribute("xml:space", "preserve")
    for element in gone:
        if element.parentNode is not None:
            element.parentNode.removeChild(element)


def _xml(dom) -> bytes:
    return b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\r\n' + dom.documentElement.toxml().encode("utf-8")


def _zip(infos, files: dict[str, bytes], dropped: set[str]) -> bytes:
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as out:
        for info in infos:
            if info.filename not in dropped:
                out.writestr(zipfile.ZipInfo(info.filename, info.date_time), files[info.filename],
                             zipfile.ZIP_DEFLATED)
    return buf.getvalue()


def _blank_picture(name: str) -> bytes:
    """A white picture, one pixel (Word stretches it to the picture's place), in the format ``name`` says."""
    import base64
    import struct

    ext = name.rsplit(".", 1)[-1].lower()
    if ext in _BLANK:
        return base64.b64decode(_BLANK[ext])
    if ext == "svg":
        return b'<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>'
    if ext == "emf":
        header = struct.pack("<II4i4iIIIIHHIIIiiii", 1, 88, 0, 0, 0, 0, 0, 0, 100, 100, 0x464D4520, 0x10000,
                             108, 2, 1, 0, 0, 0, 0, 1024, 768, 320, 240)
        return header + struct.pack("<IIIII", 14, 20, 0, 16, 20)
    if ext == "wmf":
        return struct.pack("<HHHIHIH", 1, 9, 0x0300, 12, 0, 3, 0) + struct.pack("<IH", 3, 0)
    raise ValueError(f"veil can't blank the picture {name}: pass pictures=\"keep\" to leave it as it is")


_BLANK = {   # one white pixel
    "png": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4//8/AAX+Av4N70a4AAAAAElFTkSuQmCC",
    "gif": "R0lGODdhAQABAIEAAP///wAAAAAAAAAAACwAAAAAAQABAAAIBAABBAQAOw==",
    "bmp": "Qk06AAAAAAAAADYAAAAoAAAAAQAAAAEAAAABABgAAAAAAAQAAADEDgAAxA4AAAAAAAAAAAAA////AA==",
    "tif": "SUkqAAgAAAAKAAABBAABAAAAAQAAAAEBBAABAAAAAQAAAAIBAwADAAAAhgAAAAMBAwABAAAAAQAAAAYBAwABAAAAAgAAABEBBAABAA"
           "AAjAAAABUBAwABAAAAAwAAABYBBAABAAAAAQAAABcBBAABAAAAAwAAABwBAwABAAAAAQAAAAAAAAAIAAgACAD///8=",
    "jpg": "/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAx"
           "NDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIy"
           "MjIyMjIyMjL/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUF"
           "BAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVW"
           "V1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi"
           "4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAEC"
           "AxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVm"
           "Z2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq"
           "8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD3+iiigD//2Q==",
}
_BLANK["tiff"], _BLANK["jpeg"] = _BLANK["tif"], _BLANK["jpg"]


def _open_image(data: bytes):
    try:
        from PIL import Image
    except ImportError as exc:
        raise ImportError('Reading images needs Pillow and pytesseract: pip install "veil[files]"') from exc
    return Image.open(io.BytesIO(data))


def _ocr(image) -> str:
    return reflow(ocr_data(image))


def ocr_data(image) -> dict:
    """Tesseract's words and their boxes (``image_to_data``) for an image, read the way that reads best.  A page
    on its side or upside down is turned upright first.  A page whose letters are small, as a scan at a low
    resolution or small print has them, is read enlarged: Tesseract reads letters best some 25 pixels high.
    And it's read both as it is and with a scan's speckle taken out (a median filter, which would wear away
    small clean letters), and an enlarged page smoothed too, keeping whichever Tesseract is surest of."""
    try:
        import pytesseract
        from PIL import Image, ImageFilter
    except ImportError as exc:
        raise ImportError('Reading images needs pytesseract: pip install "veil[files]"') from exc

    def read(img) -> dict:
        return pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

    def sure(data: dict) -> float:   # how much Tesseract is sure it read: its confident words' confidence
        return sum(float(c) - 50 for t, c in zip(data["text"], data["conf"]) if t.strip() and float(c) > 50)

    gray = image.convert("L")
    first = read(gray)
    words = sum(1 for t in first["text"] if t.strip())
    if words and sure(first) < 15 * words:   # hardly a word read with confidence: maybe the page is turned
        try:
            angle = int(re.search(r"Rotate: (\d+)", pytesseract.image_to_osd(gray)).group(1))
        except Exception:   # too little text for Tesseract to tell
            angle = 0
        if angle:
            gray = gray.rotate(-angle, expand=True, fillcolor=255)
            first = read(gray)
    heights = sorted(h for h, t, c in zip(first["height"], first["text"], first["conf"]) if t.strip() and float(c) > 30)
    height = heights[len(heights) // 2] if heights else 0
    scale = min(4, max(2, round(30 / height))) if 0 < height < 20 else 1
    if scale > 1:
        gray = gray.resize((gray.width * scale, gray.height * scale), Image.LANCZOS)
    candidates = [read(gray) if scale > 1 else first]
    cleaned = (image.convert("L").filter(ImageFilter.MedianFilter(3)) if gray.size == image.size else None)
    if cleaned is None:   # turned or enlarged: take the speckle out of what's read, at its own size first
        cleaned = gray.resize((max(1, gray.width // scale), max(1, gray.height // scale)), Image.LANCZOS) \
            .filter(ImageFilter.MedianFilter(3)).resize(gray.size, Image.LANCZOS)
    candidates.append(read(cleaned))
    if scale > 1:   # enlarged, a fax's or a low resolution's jagged edges read better smoothed
        candidates.append(read(gray.filter(ImageFilter.GaussianBlur(scale / 2))))
    return max(candidates, key=sure)


def reflow(data: dict) -> str:
    """The text of Tesseract's words (``image_to_data``), with the lines a page wrapped joined up again, so an
    address, a name or an email split across two lines reads as one: "1234 Main" and "Street, Anytown" become
    "1234 Main Street, Anytown", and "Carballo-" and "Ariza" become "Carballo-Ariza".  A line was wrapped
    when the next line's first word wouldn't have fitted at its end; short lines, as a form's fields are,
    keep their own lines.  Paragraphs are kept apart by a blank line."""
    lines: dict[tuple[int, int, int], list[tuple[int, int, int, int, str]]] = {}
    for i, word in enumerate(data["text"]):
        if word and word.strip():
            key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            lines.setdefault(key, []).append((data["left"][i], data["top"][i], data["width"][i],
                                              data["height"][i], word.strip()))
    if not lines:
        return ""
    ordered = [lines[key] for key in sorted(lines)]
    # the text's right margin: most lines that run full end there (one overlong line doesn't move it)
    ends = sorted(max(left + width for left, _, width, _, _ in words) for words in ordered)
    right = ends[int(0.95 * (len(ends) - 1))] if len(ends) >= 5 else ends[-1]
    # and in letters, for a page wrapped by its letters' count rather than their width
    counts = sorted(len(" ".join(w for *_, w in words)) for words in ordered)
    longest = counts[int(0.95 * (len(counts) - 1))] if len(counts) >= 5 else counts[-1]
    out, prev = [], None
    for key, words in zip(sorted(lines), ordered):
        text = " ".join(w for *_, w in words)
        if prev is not None:
            prev_key, prev_words = prev
            left, top, width, height, _ = words[0]
            prev_right = max(x + w for x, _, w, _, _ in prev_words)
            prev_bottom = max(y + h for _, y, _, h, _ in prev_words)
            char = sum(w for _, _, w, _, _ in prev_words) / max(1, sum(len(t) for *_, t in prev_words))
            line_height = max(h for _, _, _, h, _ in prev_words)
            prev_text = " ".join(w for *_, w in prev_words)
            full = right - prev_right < width + 2.5 * char or \
                (len(prev_text) >= 0.8 * longest and len(prev_text) + 1 + len(words[0][4]) > longest)
            # rows of a CSV or a table are each their own line, however long
            records = all(len(re.findall(r"[,;](?! )|\|", t)) >= 3 for t in (prev_text, text))
            wrapped = full and not records and top - prev_bottom < 1.8 * line_height and \
                abs(left - min(x for x, *_ in prev_words)) < 4 * char and \
                not re.match(r"[-*\u2022]|\d{1,2}[.)]|[A-Z][\w ]{0,30}:", text) and not prev_words[-1][4].endswith(":")
            if wrapped:
                out.append("" if out[-1].endswith("-") else " ")
            elif key[:2] == prev_key[:2]:
                out.append("\n")
            else:
                out.append("\n\n")
        out.append(text)
        prev = (key, words)
    return _tidy("".join(out).strip())


# OCR's usual misreadings around what veil looks for: an email with a comma, a colon or spaces for its dots
# ("john:smith@example. com"), a house number with a period after it ("5678. Elm Street"), a period for the
# space before a unit ("Plains.Apt. 519"), and a stray opening quote glued to a word ("1331\u2018James").
# a dot with spaces round it, or a comma or a colon for one, or a dot and a comma both ("mobilemoney,.com")
_DOTS = r"(?:[ ]?\.[ ]?|[,:]\.?(?=[\w+-])|\.[,:](?=\w))"
_BROKEN_EMAIL = re.compile(rf"(?<![\w.@])(?!mailto:)([\w+-]+(?:{_DOTS}[\w+-]+)*)[ ]?@[ ]?([\w-]+(?:{_DOTS}[\w-]+)*{_DOTS}[A-Za-z]{{2,6}})"
                           r"(?![\w@])")


# The words of labels that say what follows, which OCR misreads letter by letter ("Phorie", "Empioyee").
_LABEL_WORDS = frozenset("""phone telephone mobile number address customer employee passport license licence
birth date email account name street contact identification""".split())
_LOOKS = (("rn", "m"), ("ri", "n"), ("rri", "m"), ("ii", "u"), ("i", "l"), ("l", "i"), ("1", "l"), ("0", "o"),
          ("c", "e"), ("e", "c"), ("o", "e"), ("a", "o"))
# A phone number after its label, with OCR's colons, degree signs and dots for its separators.
_PHONE_AFTER_LABEL = re.compile(r"(?i)\b(phone(?:\s+number)?|tel(?:ephone)?(?:\s+number)?|fax|mobile|cell|contact\s+number"
                                r"|call(?:\s+us)?(?:\s+at)?|(?:contact|reach)\s+us\s+at)([^\n\d+(]{0,6})"
                                r"([+(]?\d[\d ()\-.:\u00b0]{7,24}\d)")


# A street's kind, misread after its number and name: "4826 Kristi Hil", "709 Karina Traii", "693 Horton Fail".
_SUFFIXES = ("Street Avenue Road Boulevard Lane Drive Court Place Way Terrace Circle Parkway Highway Square Trail Plaza "
             "Alley Loop Row Path Pike Crescent Center Centre Crossing Heights Walk Hill Hills Fall Falls Well Wells Mill "
             "Mills Ridge Ridges Island Islands Isle Junction Lake Lakes Manor Meadow Meadows Mount Park Point Points Port "
             "Ramp Rapid Rapids River Shore Shores Spring Springs Station Summit Valley View Village Villages Ville Vista "
             "Fork Forks Forge Fort Glen Green Greens Grove Harbor Harbors Haven Knoll Lodge Loaf Oval Pass Pine Pines "
             "Plain Plains Ranch Run Stream Tunnel Union Unions Views Cove Creek Club Common Corner Divide Estate Estates "
             "Flat Flats Garden Gardens Gateway Landing Light Lights Locks Neck Orchard Prairie Rest Spur Throughway "
             "Trace Track Trafficway Turnpike Underpass Burg Burgs Bypass Camp Canyon Cape Causeway Cliff Cliffs Course "
             "Courts Crest Curve Dale Dam Expressway Extension Extensions Ferry Field Fields Freeway Hollow Inlet Key Keys "
             "Mission Motorway Mountain Mountains Overpass Radial Shoal Shoals Skyway Squares Stravenue Streets Ways "
             "Annex Arcade Bayou Beach Bend Bluff Bluffs Bottom Bridge Bridges Brook Brooks Centers Circles Commons "
             "Concourse Corners Coves Crossroad Crossroads Drives Esplanade Ford Fords Forest Forges Glens Groves "
             "Junctions Knolls Mall Manors Mews Parks Parkways Passage Pier Ports Promenade Quay Roads Route Spurs "
             "Valleys Viaduct Walks Wall Wharf Yards").split()
_STREET_WORDS = re.compile(r"(?<![\w.])(\d{1,6}[ ]+[A-Z][a-z]+[ ]+)([A-Z][a-z]{1,11})(?=[ ]?[,.;:(\n\"]|[ ]+(?:Apt|Suite)\b|$)")


def _street_word(m: re.Match) -> str:
    import difflib

    from veil.redactor import _common_words

    word = m.group(2)
    if word in _SUFFIXES:
        return m.group()
    for a, b in _LOOKS + (("t", "l"), ("ii", "il"), ("il", "ill")):   # a letter OCR mistakes for another
        if word.replace(a, b) in _SUFFIXES:
            return m.group(1) + word.replace(a, b)
    if word.casefold() in _common_words():   # "500 Apple Pies"
        return m.group()
    close = difflib.get_close_matches(word, _SUFFIXES, n=1, cutoff=0.75)
    return m.group(1) + close[0] if close else m.group()


def _tidy_labels(text: str) -> str:
    from veil.redactor import _common_words

    def word(m: re.Match) -> str:
        w = m.group()
        low = w.casefold()
        if low in _LABEL_WORDS or low in _common_words() or len(low) < 4:
            return w
        for a, b in _LOOKS:
            fixed = low.replace(a, b)
            if fixed != low and fixed in _LABEL_WORDS:
                return fixed.capitalize() if w[0].isupper() else fixed
        return w

    text = re.sub(r"[A-Za-z01]{4,12}", word, text)
    # Employee 1D, Customer !D, employee. ID: an ID's label
    text = re.sub(r"\b(employee|customer|user|member|Employee|Customer|User|Member)[ .:]*[1!l|I]D\b(?:[ ]?[;.])?",
                  r"\1 ID", text)

    def phone(m: re.Match) -> str:
        label = m.group(1) + re.sub(r"[.:;]+[ ]?$", ": ", m.group(2))
        if re.fullmatch(r"[+(]?[\d()]+(?:[.][\d()]+)+|[+(]?[\d() -]+", m.group(3)):   # dots alone, or no misreading
            return label + m.group(3)
        number = re.sub(r"(?<=\d)[ ]*[:\u00b0.][ ]*(?=\d)|(?<=[)])[ ]*[:.][ ]*(?=\d)", " ", m.group(3))
        return label + number

    # +44 118 322 S111: an S or an O OCR read for a digit in a phone number
    text = re.sub(r"(?i)\b((?:tele)?phone|tel|mobile|fax)\b([^\n]{0,30})",
                  lambda m: m.group(1) + re.sub(r"(?<=[\d ])S(?=\d)|(?<=\d)S(?=[ \d])", "5",
                                                re.sub(r"(?<=\d)O(?=[\d ])|(?<=[\d ])O(?=\d)", "0", m.group(2))), text)
    text = _PHONE_AFTER_LABEL.sub(phone, text)
    return re.sub(r"(?<=[A-Z0-9])[:](?=\d{3,}-\d)", "-", text)   # a license number's dash read as a colon


def _tidy_names(text: str) -> str:
    """OCR's misreadings inside a person's name: an initial's period read as a colon or a comma ("Claire Z:
    Thibault"), a period or a colon after a first name ("Melanie. Robin", "Bas: Timo"), a capital J read
    small ("Hello john,"), stray quotes ("Emil\u2018 Winkler"), and a hyphen broken by spaces ("Payne- -Gilbert")."""
    from veil.redactor import _GIVEN, _WORD_GIVEN, _ascii, _given_names, _wordlike

    def given(word: str) -> bool:
        w = _ascii(word).casefold()
        return w in _GIVEN or w in _WORD_GIVEN or (w in _given_names() and not _wordlike(w))

    from veil.redactor import _SURNAMES, _common_surnames, _common_words, _name_listed, _surname_list, _top_surnames

    def known(word: str) -> bool:
        w = _ascii(word).casefold()
        return given(word) or w in _SURNAMES or w in _surname_list() or w in _top_surnames()

    def mend(m: re.Match) -> str:
        # Tarnmy -> Tammy, Leoriard -> Leonard, lda -> Ida: lookalike letters, when that makes a name and the word
        # read is none
        w = m.group()
        if w[0] == "l" and known("I" + w[1:]) and w.casefold() not in _common_words() and m.end() < len(text) and \
                re.match(r"[ ]+[A-Z][a-z]+[ ]+[A-Z]|[ ]+[A-Z]\.", text[m.end():m.end() + 30]):
            return "I" + w[1:]   # lan Pamela Turner, lda G. Lopresti: an I read as an l, before more of a name
        if w.casefold() in _common_words() or known(w):
            return w
        for a, b in (("rn", "m"), ("ri", "n"), ("rri", "m"), ("ii", "il"), ("!l", "l"), ("!", "i"), ("1", "l")):
            if a in w and known(w.replace(a, b)):
                return w.replace(a, b)
        if w[0] == "l" and known("I" + w[1:]):
            return "I" + w[1:]
        return w

    text = re.sub(r"\b(?:[A-Z][a-z!1]{2,}|l[a-z]{1,})\b(?=[ ,.]+[A-Z])|(?<=[A-Z][a-z] )[A-Z][a-z!1]{2,}\b", mend, text)
    # this isSarah, DearLarry, andEnzo, between-Sarah: a name glued to the word before it
    text = re.sub(r"\b(is|and|Dear|between|including|means|by|to|of|for|with|Hi|Hello)-?(?=([A-Z][a-z]{2,}))",
                  lambda m: m.group(1) + " " if given(m.group(2)) else m.group(), text)
    text = re.sub(r"\b([A-Z][a-z]{2,})([A-Z])\.(?= [A-Z])", lambda m: f"{m.group(1)} {m.group(2)}." if given(m.group(1))
                  else m.group(), text)                                                         # DawnB. Neal
    # an initial, its period misread: "Mark G; Evans", "Amber. M. Martinez", "Arsenio.M: Boiardo", "E.-Colas"
    text = re.sub(r"\b([A-Z][^\W\d_]{2,})[.]?[ ]?([A-Z])(?:[.:;,]|\.[\u2019'\-:,_]|\.\.)[ ]?(?=[A-Z][^\W\d_])",
                  lambda m: f"{m.group(1)} {m.group(2)}. " if given(m.group(1)) else m.group(), text)
    text = re.sub(r"(?<=[a-z] [A-Z])(?:[:,;]|\.\.|\.[,:])[ ]?(?=[A-Z][a-z])", ". ", text)       # Claire Z: Thibault
    # a first name, a colon or "._", a surname: "John: Doe", "John._Doe"
    text = re.sub(r"\b([A-Z][a-z]{2,})(?::|\._|_)[ ]?(?=([A-Z][a-z]{2,}))",
                  lambda m: m.group(1) + " " if given(m.group(1)) and (known(m.group(2)) or m.group(2).casefold() in
                                                                        _common_surnames()) else m.group(), text)
    text = re.sub(r"(?<=\b(?:Mr|Ms|Dr))\.?:[ ]?(?=[A-Z])|(?<=\bMrs)\.?:[ ]?(?=[A-Z])", ". ", text)  # Mr.:Smith
    # Tiziano Paolo loppi: an I read as an l, starting the surname after a first name
    text = re.sub(r"\b([A-Z][a-z]{2,}[ ](?:[A-Z][a-z]{2,}[ ])?)l([a-z]{3,})\b",
                  lambda m: m.group(1) + "I" + m.group(2) if given(m.group(1).split()[0]) and
                  ("l" + m.group(2)) not in _common_words() else m.group(), text)
    text = re.sub(r"\b([A-Z][a-z]{2,} )\|\.(?= [A-Z][a-z])", r"\1I.", text)                 # Insa |. Salz
    text = re.sub(r"(?<=[a-z])[\u2018\u2019'](?=[ ]?[A-Z](?:[a-z]|\.))", "", text)            # Emil' Winkler
    text = re.sub(r"(?<=[a-z])-[ ]+-?(?=[A-Z][a-z])|(?<=[a-z])[ ]+-[ ]?-(?=[A-Z][a-z])", "-", text)   # Payne- -Gilbert
    text = re.sub(r"\bj([a-z]{2,})\b(?=[ ,.]+[A-Z]|,)", lambda m: "J" + m.group(1) if given("J" + m.group(1)) else
                  m.group(), text)                                                          # john Doe, Hello john,
    # Melanie Robin jordan, "Bob","johnson": a surname's J read small, after a first name
    text = re.sub(r"\b([A-Z][a-z]{1,20}(?: [A-Z][a-z]{1,20})?(?: |\",\s?\"))j([a-z]{2,})\b",
                  lambda m: f"{m.group(1)}J{m.group(2)}" if given(m.group(1).strip(' ",').split()[0]) and
                  _name_listed(_ascii("j" + m.group(2)), set()) and ("j" + m.group(2)) not in _common_words()
                  else m.group(), text)
    # Rahe! for Rahel, No\u00e9! for No\u00ebl, He8 or He& for He\u00df: the last letter of a name misread
    text = re.sub(r"\b([A-Z][a-z\u00c0-\u024f]{1,15})!(?=[ ,.:;]|$)",
                  lambda m: m.group(1) + "l" if given(m.group(1) + "l") or known(m.group(1) + "l") else m.group(), text)
    text = re.sub(r"\b([A-Z][a-z]{1,15} )([A-Z][a-z]{1,15})[8&](?=[ ,.:;\]]|$)",
                  lambda m: f"{m.group(1)}{m.group(2)}\u00df" if given(m.group(1).strip()) else m.group(), text)
    text = re.sub(r"\b(Dear|Hello|Hi) ([a-z])([a-z]{2,})(?= [A-Z]|,)",
                  lambda m: f"{m.group(1)} {m.group(2).upper()}{m.group(3)}"
                  if given(m.group(2).upper() + m.group(3)) else m.group(), text)                  # Dear isidro Armando
    text = re.sub(r"\b(Dear|Hello|Hi|Thanks|welcome|Name:|you,) j([a-z]{2,})\b",
                  lambda m: f"{m.group(1)} J{m.group(2)}" if given("J" + m.group(2)) else m.group(), text)
    # A period or colon after a first name, before another name: "Melanie. Robin Jordan", "Bas: Timo Evers"
    def name_next(m: re.Match) -> bool:
        w = m.group(2).casefold()
        return len(w) == 1 or ((given(m.group(2)) or w in _SURNAMES or w in _surname_list()) and w not in _common_words())

    return re.sub(r"\b([A-Z][a-z]{2,})(?:\.|:)[ ]?(?=([A-Z](?:[a-z]+)?)(?:\.)?[ ,.])",
                  lambda m: m.group(1) + " " if given(m.group(1)) and name_next(m) else m.group(), text)


def _unaccent(text: str) -> str:
    """An email's letters without the accents OCR puts on them ("mobilem\u00e9ney")."""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def _tidy(text: str) -> str:
    def email(m: re.Match) -> str:
        domain = re.sub(r"\.c(?:orn|orm|om[nr])$", ".com", re.sub(_DOTS, ".", m.group(2)))   # .corn: rn for m
        return _unaccent(f"{re.sub(_DOTS, '.', m.group(1))}@{domain}")

    text = text.replace("\u201c", '"').replace("\u201d", '"')   # curly quotes, as OCR reads a JSON's or a CSV's
    text = _tidy_labels(text)
    # a space OCR put inside an email's domain: "@emai l.com", "@email.c om"
    text = re.sub(r"(?<=@)([\w-]{2,}) ([\w-]{1,3}\.(?:com|org|net|co|io)\b)", r"\1\2", text)
    text = re.sub(r"(?<=@)([\w.-]+\.c) ?(o) ?(m)\b", r"\1\2\3", text)
    text = re.sub(r"(?<=@)([\w.-]*?)!(?=[\w.-]*\.[a-z]{2,4}\b)", r"\1l", text)                # @emai!.com
    text = re.sub(r"(?<=mailto:)([\w-]+) (?=[\w.-]+@)", r"\1.", text)                       # mailto:mike johnson@
    text = _BROKEN_EMAIL.sub(email, text)
    # "charlie brown@yahoo.com" where the same email is written with its dot elsewhere
    for e in set(re.findall(r"[\w-]+\.[\w.-]+@[\w.-]+\.[a-z]{2,6}", text)):
        local, domain = e.split("@", 1)
        text = re.sub(rf"(?<![\w.]){re.escape(local.replace('.', ' '))}@{re.escape(domain)}", e, text)
    # Stra\u00dfe read StraBe, StraRe, Strake: its \u00df
    text = re.sub(r"(?<=[A-Za-z\u00c0-\u024f-])([Ss])tra(?:B|R|k|&|8|G|f)e\b", "\\1tra\u00dfe", text)
    # SE1 12Z, RHSW 5RQ: a UK postcode with a 2 for a Z, an S for a 5
    text = re.sub(r"\b([A-Z]{1,2})l( \d[A-Z\d]{2})\b", r"\g<1>1\2", text)                     # SEl 122
    text = re.sub(r"\b([A-Z]{1,2}\d[A-Z\d]?) (\d)([A-Z2])([A-Z2])\b",
                  lambda m: f"{m.group(1)} {m.group(2)}{m.group(3).replace('2', 'Z')}{m.group(4).replace('2', 'Z')}"
                  if "2" in m.group(3) + m.group(4) else m.group(), text)
    text = re.sub(r"\b([A-Z]{2})S([A-Z]?) (\d[A-Z]{2})\b", r"\g<1>5\2 \3", text)
    # 67.240. Nolan Junction: a street's number with a dot in it
    text = re.sub(rf"(?<![\w.,$])(\d{{1,3}})\.(\d{{3}})\.?[ ]?(?=(?:[A-Z][\w'-]+[ ]){{1,3}}(?:{'|'.join(_SUFFIXES)})\b)",
                  r"\1\2 ", text)
    text = re.sub(r"(?<=\w),[:;.][ ]?(?=[A-Z0-9])", ", ", text)                              # Anytown,:AB
    text = re.sub(r"(?<![\w.,$])(\d{3,6})\.[ ]?(?=[A-Z][a-z])", r"\1 ", text)
    text = re.sub(r"(?<![\w.,$])(\d{1,2})\.[ ]?(?=[A-Z][a-z]+ (?:Street|St|Road|Avenue|Lane|Drive|Way|Place|Court)\b)",
                  r"\1 ", text)                                                            # 43. High Street
    text = re.sub(r"(?<=\d)['\u00b0\u2018\u2019]+(?= [A-Z][a-z])", "", text)              # 10110'\u00b0 Jennifer
    text = re.sub(r"(?<![\w.,$])(\d{1,2})\.[ ]?(?=(?:Rue|Calle|Via|Avenida|Avenue|Plaza|Piazza)\b)", r"\1 ", text)  # 45.Rue
    text = re.sub(r"(?<![\w.,$])(\d{2,6}):[ ]?\n(?=[A-Z][a-z])", r"\1 ", text)                 # 642:\nAnderson Rapid
    text = re.sub(r"(?<=[:(\s])[.\-+]{1,2}(?=\d{2,6}[ ][A-Z][a-z])", "", text)                   # -.708 Sandra Burgs
    text = re.sub(r"\b([ABCEGHJ-NPRSTVXY]\d[A-Z]) (\d)[}\]](\d)\b", r"\1 \2J\3", text)            # T2V 5}7
    text = re.sub(r"\b([ABCEGHJ-NPRSTVXY])S[)}](?= \d[A-Z]\d\b)", r"\g<1>5J", text)                # MS) 2H7
    text = re.sub(r"\b([ABCEGHJ-NPRSTVXY]\d[A-Z])[.\-)]?[ ]?(\d[A-Z]\d)\b", r"\1 \2", text)   # V6B.1C3
    # the street's own words split by a colon or a period: "7190 Peter:Crossing", "34611 Canyon. View"
    text = re.sub(r"\b(\d{1,6}[ ]+[A-Z][a-z]{2,})(?:[:.][ ]?)(?=([A-Z][a-z]+)\b)",
                  lambda m: m.group(1) + " " if m.group(2) in _SUFFIXES else m.group(), text)
    text = _STREET_WORDS.sub(_street_word, text)
    # 456 Oak Street. Anytown, USA: a period read for the comma before the town
    text = re.sub(rf"(\b\d{{1,6}}[ ]+(?:[A-Z][\w'-]+[ ]+){{1,3}}(?:{'|'.join(_SUFFIXES)}))\.[ ]"
                  r"(?=[A-Z][\w'-]+(?:[ ][A-Z][\w'-]+)?(?:,|[ ]*\n|[ ]*$))", r"\1, ", text)
    # Toronto. ON, Canada; Lodge. 02116, Beasleytown: more periods for commas in an address's line
    def commas(m: re.Match) -> str:
        line = re.sub(rf"^(.*?\b(?:{'|'.join(_SUFFIXES)}))\.[ ](?=[A-Z][\w'-]+(?:[ ][A-Z][\w'-]+)?[.,][ ])", r"\1, ",
                      m.group())
        return re.sub(r"(?<=[A-Za-z])\.[ ](?=(?:[A-Z]{2}\b|\d{4,6}\b|USA\b|Canada\b|UK\b|United\b|[A-Z]\d[A-Z]))",
                      ", ", line)
    text = re.sub(rf"\b\d{{1,6}}[ ]+(?:[A-Z][\w'-]+[ ]+){{1,3}}(?:{'|'.join(_SUFFIXES)})\b[^\n]{{0,80}}", commas, text)
    # 8905 johnson Fords: a street's name with its first letter read small
    text = re.sub(rf"(\b\d{{1,6}}[ ]+)j(?=[a-z]+[ ]+(?:{'|'.join(_SUFFIXES)})\b)", r"\1J", text)
    # a lower case j for the J starting a street's kind or a name after a capitalized word: "Phillip junction"
    text = re.sub(rf"(\b\d{{1,6}}[ ]+[A-Z][\w'-]+[ ])j(?=(?:{'|'.join(w[1:] for w in _SUFFIXES if w[0] == 'J')})\b)",
                  r"\1J", text)
    text = re.sub(r"(?<=\d)\.(?=\d{2}-\d{4}\b)", "-", text)                                 # SSN: 384.35-2296
    text = re.sub(r"(?<=[a-z])\.(?=(?:Apt|Suite|Ste|Unit|Flat)\b)", " ", text)
    text = re.sub(r"(?<!www)(?<=[a-z])\.(?!(?:Com|Org|Net|Edu|Gov|Io|Co|Uk)\b)(?=[A-Z][a-z]{2,}(?![\w-]*\.[A-Za-z]))",
                  " ", text)                                                               # Kelly.Ramp
    text = re.sub(r"(?<![\w:.])(\d{2,6}):[ ]?(?=[A-Z][a-z]{2,})", r"\1 ", text)       # 087:Jonathan Ramp
    text = re.sub(r"(?<=[a-z])[ ]?[.\-+](?=\d{2,6}[ ][A-Z][a-z])", " ", text)  # at.74662 Karen, at-1234 Fifth
    text = re.sub(r"(?<=[:(\s])[.\-+](?=\d{2,6}[ ][A-Z][a-z])", "", text)             # Customer: .394 Perkins
    text = re.sub(r"(?<![\w.-])(\d{2,6})-(?=[A-Z][a-z]{2,}[ ,])", r"\1 ", text)       # 123-High Street
    text = re.sub(r"(?<=[a-z])[ ]?-(?=(?:Street|Road|Avenue|Lane|Drive|Way|Place|Court|Roads|Streets)\b)", " ", text)
    text = _tidy_names(text)
    text = re.sub(r"(?<=\s)\u2018(?=[A-Z0-9])", "", text)
    return re.sub(r"(?<=[A-Za-z0-9])\u2018(?=[A-Z0-9])", " ", text)
