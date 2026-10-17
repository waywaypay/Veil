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
import unicodedata

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
    return reflow(ocr_data(image))


def ocr_data(image) -> dict:
    """Tesseract's words and their boxes (``image_to_data``) for an image.  A scan's speckle is taken out first
    (a median filter), and a page whose letters are small, as a scan at a low resolution has them, is read again
    twice the size: Tesseract reads letters best some 20 pixels high."""
    try:
        import pytesseract
        from PIL import Image, ImageFilter
    except ImportError as exc:
        raise ImportError('Reading images needs pytesseract: pip install "veil[files]"') from exc

    def read(img) -> dict:
        return pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

    gray = image.convert("L").filter(ImageFilter.MedianFilter(3))
    data = read(gray)
    heights = sorted(h for h, t, c in zip(data["height"], data["text"], data["conf"]) if t.strip() and float(c) > 60)
    if heights and heights[len(heights) // 2] < 20:
        data = read(gray.resize((gray.width * 2, gray.height * 2), Image.LANCZOS))
    return data


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
            records = all(t.count(",") + t.count("|") + t.count(";") >= 3 for t in (prev_text, text))
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
