"""Text out of PDFs and images, read on this machine, so it can be redacted before a model sees it.

    from veil.files import read_text

    text = read_text(pdf_bytes, "application/pdf")   # the PDF's own text; scanned pages are read with OCR
    text = read_text(png_bytes, "image/png")         # OCR
    safe = redactor.redact_text(text)

PDFs need ``pypdf``; images and scanned pages need ``pytesseract``, ``Pillow`` and the Tesseract program
(``pip install "veil[files]"``, and ``apt install tesseract-ocr`` or ``brew install tesseract``).  Nothing
is sent anywhere: both run in this process.
"""

from __future__ import annotations

import io
import re

IMAGE_TYPES = ("image/jpeg", "image/png", "image/gif", "image/webp")


def read_text(data: bytes, media_type: str) -> str:
    """The text in a PDF or image.  A PDF page with no text of its own (a scan) is read with OCR."""
    if media_type == "application/pdf":
        return _pdf(data)
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
        pages.append(text.strip())
    return "\n\n".join(p for p in pages if p)


def _open_image(data: bytes):
    try:
        from PIL import Image
    except ImportError as exc:
        raise ImportError('Reading images needs Pillow and pytesseract: pip install "veil[files]"') from exc
    return Image.open(io.BytesIO(data))


def _ocr(image) -> str:
    try:
        import pytesseract
    except ImportError as exc:
        raise ImportError('Reading images needs pytesseract: pip install "veil[files]"') from exc
    return reflow(pytesseract.image_to_data(image.convert("RGB"), output_type=pytesseract.Output.DICT))


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
            wrapped = right - prev_right < width + 2.5 * char and top - prev_bottom < 1.8 * line_height and \
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
_DOTS = r"(?:[ ]?\.[ ]?|[,:](?=[\w+-]))"   # a dot with spaces round it, or a comma or a colon for one
_BROKEN_EMAIL = re.compile(rf"(?<![\w.@])([\w+-]+(?:{_DOTS}[\w+-]+)*)[ ]?@[ ]?([\w-]+(?:{_DOTS}[\w-]+)*{_DOTS}[A-Za-z]{{2,6}})"
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
             "Mission Motorway Mountain Mountains Overpass Radial Shoal Shoals Skyway Squares Stravenue Streets Ways").split()
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

    text = _PHONE_AFTER_LABEL.sub(phone, text)
    return re.sub(r"(?<=[A-Z0-9])[:](?=\d{3,}-\d)", "-", text)   # a license number's dash read as a colon


def _tidy_names(text: str) -> str:
    """OCR's misreadings inside a person's name: an initial's period read as a colon or a comma ("Claire Z:
    Thibault"), a period or a colon after a first name ("Melanie. Robin", "Bas: Timo"), a capital J read
    small ("Hello john,"), stray quotes ("Emil\u2018 Winkler"), and a hyphen broken by spaces ("Payne- -Gilbert")."""
    from veil.redactor import _GIVEN, _given_names, _wordlike

    def given(word: str) -> bool:
        w = word.casefold()
        return w in _GIVEN or (w in _given_names() and not _wordlike(w))

    text = re.sub(r"(?<=[a-z] [A-Z])(?:[:,]|\.\.|\.[,:])[ ]?(?=[A-Z][a-z])", ". ", text)       # Claire Z: Thibault
    text = re.sub(r"(?<=\b(?:Mr|Ms|Dr))\.?:[ ]?(?=[A-Z])|(?<=\bMrs)\.?:[ ]?(?=[A-Z])", ". ", text)  # Mr.:Smith
    text = re.sub(r"(?<=[a-z])[\u2018\u2019'](?=[ ]?[A-Z](?:[a-z]|\.))", "", text)            # Emil' Winkler
    text = re.sub(r"(?<=[a-z])-[ ]+-?(?=[A-Z][a-z])|(?<=[a-z])[ ]+-[ ]?-(?=[A-Z][a-z])", "-", text)   # Payne- -Gilbert
    text = re.sub(r"\bj([a-z]{2,})\b(?=[ ,.]+[A-Z]|,)", lambda m: "J" + m.group(1) if given("J" + m.group(1)) else
                  m.group(), text)                                                          # john Doe, Hello john,
    text = re.sub(r"\b(Dear|Hello|Hi|Thanks|welcome|Name:|you,) j([a-z]{2,})\b",
                  lambda m: f"{m.group(1)} J{m.group(2)}" if given("J" + m.group(2)) else m.group(), text)
    # A period or colon after a first name, before another name: "Melanie. Robin Jordan", "Bas: Timo Evers"
    from veil.redactor import _SURNAMES, _common_words, _surname_list

    def name_next(m: re.Match) -> bool:
        w = m.group(2).casefold()
        return len(w) == 1 or ((given(m.group(2)) or w in _SURNAMES or w in _surname_list()) and w not in _common_words())

    return re.sub(r"\b([A-Z][a-z]{2,})(?:\.|:)[ ]?(?=([A-Z](?:[a-z]+)?)(?:\.)?[ ,.])",
                  lambda m: m.group(1) + " " if given(m.group(1)) and name_next(m) else m.group(), text)


def _tidy(text: str) -> str:
    def email(m: re.Match) -> str:
        fix = lambda part: re.sub(_DOTS, ".", part)
        return f"{fix(m.group(1))}@{fix(m.group(2))}"

    text = _tidy_labels(text)
    text = _BROKEN_EMAIL.sub(email, text)
    text = re.sub(r"(?<![\w.,$])(\d{3,6})\.[ ]?(?=[A-Z][a-z])", r"\1 ", text)
    text = re.sub(r"(?<![\w.,$])(\d{1,2})\.[ ]?(?=[A-Z][a-z]+ (?:Street|St|Road|Avenue|Lane|Drive|Way|Place|Court)\b)",
                  r"\1 ", text)                                                            # 43. High Street
    text = re.sub(r"(?<=\d)['\u00b0\u2018\u2019]+(?= [A-Z][a-z])", "", text)              # 10110'\u00b0 Jennifer
    text = _STREET_WORDS.sub(_street_word, text)
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
