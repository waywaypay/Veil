# veil beyond the Gretel finance set

veil was tuned on Gretel's synthetic financial documents. These are tests on what it never saw: three
other makers' PII datasets (`external.py`), and one of them under the circumstances documents come in
(`conditions.py`). Raw labels, not adjudicated. Fixes made in this round were studied on each dataset's
training split; every number below is on its test split.

## Other datasets (2,000 documents each)

| Dataset | What it is | Found before | Found now | Other words hidden |
|---|---|---|---|---|
| NVIDIA Nemotron-PII | 50 domains, forms and prose, US and international | 88.0% | **91.3%** | 0.13% |
| Gretel pii-masking-en-v1 | many industries | 80.5% | **83.1%** | 1.24% |
| ai4privacy pii-masking-400k (English) | short messages | 50.4% | **52.6%** | 2.30% |

What each still misses:

* Nemotron: usernames in prose (41%), towns and postcodes alone (53%; veil hides them in a labelled field
  or an address, not a town named in a sentence), and some account numbers.
* Gretel en-v1: it labels any date as a date of birth and any code as a customer ID, so dates of
  birth score 73% and IDs 67%; and addresses written the way its generator does (`6 Darren view`).
* ai4privacy: its labels are fragments with little context: a building number alone (`349`), a surname
  alone, a phone in an invented format (`+15 11.387-4587`), random strings as names.

Other languages (ai4privacy, 800 messages each): English 49%, Dutch 49%, Spanish 48%, German 42%,
French 40%, Italian 36% found. veil's names, streets and labels are English and Western European; it is
not built for other languages.

## Circumstances (150 Nemotron test documents)

| Condition | Before | Now | Other words hidden now |
|---|---|---|---|
| plain text | 87.2% | **90.1%** | 0.12% |
| HTML | 87.2% | 89.7% | 0.11% |
| inside JSON | 87.2% | 90.1% | 0.12% |
| quoted in an email thread | 87.2% | 90.1% | 0.11% |
| ragged whitespace, CRLF | 84.5% | 88.0% | 0.19% |
| UPPER CASE | 81.3% | 84.0% | 0.54% |
| lower case | 49.0% | **73.2%** | 0.19% |
| typed in a chat (lower case) | 55.1% | **74.6%** | 0.17% |
| PDF with its text | 86.7% | 90.4% | 0.13% |
| scanned PDF (150 DPI) | 81.1% | 89.6% | 0.15% |
| clean image, serif | 86.9% | 89.2% | 0.17% |
| clean image, sans-serif | 86.7% | 89.4% | 0.15% |
| small print (8 point) | 42.6% | **88.6%** | 0.14% |
| phone photo (skewed, unevenly lit, JPEG) | 86.5% | 89.9% | 0.16% |
| fax (100 DPI, black and white) | 83.5% | 77.6% | 0.31% (was 5.52%) |
| grey, mottled page | 86.4% | 89.7% | 0.14% |
| two columns | 85.5% | 88.4% | 0.29% |
| turned sideways | 74.9% | **89.2%** | 0.18% (was 5.57%) |

Word documents (`.docx`, read with the standard library; made with python-docx, with each paragraph's runs
cut inside words as Word cuts them, or written by LibreOffice). Measured later than the table above, with
plain text on the same documents at 90.9%:

| Condition | Found | Other words hidden |
|---|---|---|
| Word document | 90.9% | 0.12% |
| Word form (a two-column table) | 90.1% | 0.13% |
| Word form, two fields a row, labels without colons | 90.2% | 0.12% |
| Word form, labels lined up with tabs | 90.9% | 0.12% |
| Word header and footer | 91.4% | 0.12% |
| Word text boxes (with the copy Word keeps for old readers) | 90.9% | 0.12% |
| Word tracked changes (deleted text left out) | 90.9% | 0.12% |
| Word written by LibreOffice | 90.9% | 0.12% |
| Word with a scanned page pasted in (OCR) | 92.3% | 0.13% |

The redacted Word documents `redact_docx` writes (`word_writer.py`) were checked on the same 150 test
documents, for each kind of Word document above except the pasted scan, whose picture is blanked. In all
eight:

* every file reads back as exactly the redacted text, so each placeholder is where the text it hides was;
* none of the 533 to 536 details veil hid in the text is anywhere in the file (any part of the package,
  its text and attributes);
* LibreOffice opens each file (30 of each kind) and shows every placeholder.

The fax's and the sideways page's earlier figures were propped up by hiding over 5% of every word.

## Other checks

* Restoring: on 2,000 Nemotron documents in all eight text forms (16,000 round trips) the restored text
  differs from the original in a handful, all a known person's name written another way (`jack.walsh`
  for Jack Walsh) and put back as known, as veil intends.
* Speed: a 560,000-character document (600 documents joined) redacts in 7 seconds; it took 25.
* Not read: the older Word `.doc`, and other office formats (spreadsheets, slides); `veil.files` reads PDFs,
  Word `.docx`, images and text.
