"""veil.files.redact_docx on Word documents made from Nemotron-PII's test documents by word.py's builders.

For each document and builder: does the redacted file read back as the redacted text (each placeholder
put where what it hides was), is anything veil hid in the text still somewhere in the file (any part of the
package, its XML unescaped), and does LibreOffice open it and show each placeholder.

python word_writer.py <nemotron parquet> <n> [libreoffice checks]"""

import html
import io
import os
import re
import subprocess
import sys
import tempfile
import zipfile

import external
import word

from veil import FINANCE, Redactor
from veil.files import DOCX_TYPE, read_text, redact_docx

BUILDERS = {"plain": word.plain, "form": word.form, "wide form": word.wide_form, "tab form": word.tab_form,
            "header and footer": word.header_footer, "text boxes": word.text_boxes, "tracked": word.tracked,
            "from LibreOffice": word.libreoffice}


def package_text(data: bytes) -> str:
    """What every part of the package says: its text, and its attributes but the numbers of its layout (a
    font's signature "80000000" isn't a postcode)."""
    said = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            xml = z.read(name).decode("utf-8", "replace")
            said += [html.unescape(x) for x in re.findall(r">([^<]+)<", xml)]
            said += [html.unescape(x) for x in re.findall(r'="([^"]*)"', xml) if not re.fullmatch(r"-?[\dA-Fa-f.]+", x)]
    return "\n".join(said)


def libreoffice_reads(data: bytes) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "doc.docx"), "wb") as f:
            f.write(data)
        subprocess.run(["soffice", "--headless", f"-env:UserInstallation=file://{tmp}/profile", "--convert-to",
                        "pdf", "--outdir", tmp, os.path.join(tmp, "doc.docx")], capture_output=True,
                       timeout=120, check=True)   # as a PDF, headers and footers and all
        return subprocess.run(["pdftotext", os.path.join(tmp, "doc.pdf"), "-"], capture_output=True, text=True,
                              check=True).stdout


def main(path, n, lo_checks=20):
    rows = [r for r in external.load("nemo", path, 20 * n, 7) if len(r[0]) < 2500][:n]
    for name, make in BUILDERS.items():
        same = leaks = hidden = opened = tried = 0
        for i, (text, spans) in enumerate(rows):
            data, _ = make(text, i)
            expected = Redactor(FINANCE).redact_text(read_text(data, DOCX_TYPE))
            out = redact_docx(data, Redactor(FINANCE))
            same += read_text(out, DOCX_TYPE) == expected
            everything = package_text(out)
            for sp in spans:
                value = text[sp["start"]:sp["end"]]
                if sp["label"] in external.LABEL and len(value) >= 4 and value not in expected:
                    hidden += 1
                    leaks += value in everything
            if i < lo_checks:
                tried += 1
                shown = libreoffice_reads(out)
                opened += all(p in shown for p in re.findall(r"\b[A-Z]+_\d{3}\b", expected))
        print(f"  {name:18} reads back as redacted {same}/{len(rows)}   hidden details still in the file "
              f"{leaks}/{hidden}   LibreOffice reads {opened}/{tried}")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]) if len(sys.argv) > 3 else 20)
