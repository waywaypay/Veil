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
    return pytesseract.image_to_string(image.convert("RGB")).strip()
