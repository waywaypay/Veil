"""Field-label pass: a value written next to the caption of a private field is hidden, whatever the value looks like.

Covers "Caption: value", "Caption ..... value", "Caption<tab or wide gap>value", "| Caption | value |", JSON and key=value
pairs, CSV/TSV/pipe tables by their header row, and a value on the line below a caption that stands alone.

ranges(text) -> [(start, end, kind)]"""
import re

# caption words per kind, lower case; matched as whole words at the start of a caption
CAPTIONS = {
    "NAME": r"(full |first |last |given |family |sur|maiden |legal |preferred |middle |employee'?s? |patient'?s? |customer'?s? |"
            r"client'?s? |applicant'?s? |account holder'?s? |card ?holder'?s? |member'?s? |student'?s? |tenant'?s? |borrower'?s? |"
            r"recipient'?s? |sender'?s? |contact )?name|applicant|policy ?holder|beneficiary|next of kin|emergency contact|guardian|"
            r"parent|spouse|contact person|attn|attention|c/o|account holder|card ?holder|insured|tenant|borrower|co-borrower|"
            r"signed|signature|patient|employee|claimant|witness|nachname|vorname|nom|prénom|nombre|apellidos?|nome|cognome|"
            r"imię|nazwisko|naam",
    "ADDRESS": r"(home |mailing |residential |street |postal |billing |shipping |permanent |current |previous |employee'?s? |"
               r"patient'?s? |customer'?s? |delivery |correspondence )?address|addr|street|anschrift|adresse|dirección|domicilio|"
               r"indirizzo|adres",
    "DOB": r"dob|d\.o\.b\.?|date of birth|birth ?date|born|geburtsdatum|fecha de nacimiento|date de naissance|data di nascita|"
           r"data urodzenia|geboortedatum",
    "ID": r"ssn|social security( number| no\.?| #)?|sin|nin|national insurance( number| no\.?)?|tin|itin|tax ?id( number| no\.?)?|"
          r"taxpayer id|tax identification( number)?|ein|fein|employer identification( number)?|pan|aadhaar|nif|nie|dni|cpf|"
          r"steuer-?id|steuernummer|codice fiscale|pesel|bsn|personnummer|nric|national id( number)?|id number|id no\.?|"
          r"passport( number| no\.?| #)?|driver'?s? licen[cs]e( number| no\.?| #)?|dl ?#|licen[cs]e (number|no\.?)|"
          r"state id( number)?|employer'?s? state id( number)?|medicare (number|no\.?)|nhs (number|no\.?)|health card",
    "EMPLOYEE_ID": r"employee (id|number|no\.?|#)|emp\.? ?(id|#|no\.?)|staff (id|number|no\.?)|personnel (number|no\.?)|"
                   r"payroll (id|number|no\.?)|worker id|badge( number| no\.?| #)?|associate id|file (number|no\.?)|"
                   r"control (number|no\.?|#)|ctrl ?#|personalnummer",
    "CUSTOMER_ID": r"(customer|client|member|membership|patient|student|subscriber|loyalty|rewards?|applicant|claimant|"
                   r"beneficiary|account holder|user|policy|mrn|medical record|case|tenant|guest|passenger|frequent flyer)"
                   r" ?(id|number|no\.?|#)|mrn|medical record|kundennummer|n[ºo°] (de )?client",
    "ACCOUNT": r"(bank |checking |savings |loan |card |credit card |debit card )?(account|acct|a/c)( number| no\.?| #)?|"
               r"iban|routing( number| no\.?)?|aba|sort code|bsb|swift|bic|card (number|no\.?)|pan|kontonummer",
    "USERNAME": r"user ?name|login|log-?in|handle|screen name|user ?id|benutzername",
    "PHONE": r"(home |work |mobile |cell |daytime |evening |contact )?(phone|tel\.?|telephone|mobile|cell|fax)( number| no\.?| #)?|"
             r"telefon|téléphone|teléfono|telefono",
    "EMAIL": r"e-?mail( address)?|correo|courriel",
}
_CAP = {k: re.compile(r"(?:%s)" % v, re.I) for k, v in CAPTIONS.items()}
_ANY = re.compile(r"^\W*(?:[a-z]\s|\d{1,2}[a-z]?\s+)?(?P<cap>" + "|".join(f"(?:{v})" for v in CAPTIONS.values()) + r")\W*$", re.I)
_EMPTY = re.compile(r"^\W*(n/?a|none|nil|null|-+|—|tbd|unknown|not applicable|see (above|below)|same|x+_?x*|\[.*\])\W*$", re.I)
_SEP = r"(?:\s*[:=]\s*|\s*[-–—]\s+|\s*\.{2,}\s*|\t+\s*| {2,}|\s*\|\s*)"


def kind_of(caption):
    """The kind of a caption ('Employee ID' -> EMPLOYEE_ID), or None; the longest matching kind wins."""
    c = re.sub(r"^\W*(?:[a-z]\s|\d{1,2}[a-z]?\s+)?", "", caption.strip().lower()).strip(" :.-|*")
    c = re.sub(r"\s+", " ", c)
    best = None
    for k, rx in _CAP.items():
        m = rx.fullmatch(c)
        if m and (best is None or len(m.group(0)) > best[1]):
            best = (k, len(m.group(0)))
    return best[0] if best else None


def _value_end(line, start, kind):
    """Where the value starting at `start` in `line` ends: a wide gap, a pipe or a tab, or the line's end."""
    m = re.compile(r" {3,}|\t|\s\|").search(line, start)
    end = m.start() if m else len(line)
    return end


def _ok(value, kind=None):
    v = value.strip()
    if kind in ("ID", "EMPLOYEE_ID", "CUSTOMER_ID", "ACCOUNT", "PHONE") and not re.search(r"\d", v):
        return False
    if kind == "USERNAME" and (" " in v or not re.search(r"[\d._@-]|[a-z][A-Z]", v)):
        return False
    return bool(v) and len(v) <= 80 and re.search(r"[0-9A-Za-zÀ-ÿ]", v) and not _EMPTY.match(v) and kind_of(v) is None


def ranges(text):
    out = []
    pos = 0
    lines = text.split("\n")
    starts = []
    for ln in lines:
        starts.append(pos)
        pos += len(ln) + 1
    # 1. "Caption <sep> value" anywhere on a line (several pairs per line allowed)
    cap_re = re.compile(r"(?P<cap>(?:\b[a-z]\s)?[A-Za-zÀ-ÿ][\w'’./#&-]*(?: [\w'’./#&-]+){0,4}?)" + _SEP + r"(?P<val>\S)", re.I)
    for li, ln in enumerate(lines):
        for m in cap_re.finditer(ln):
            # try the shortest tail of the caption words that names a field
            words = m.group("cap").split(" ")
            kind = None
            for i in range(len(words)):
                kind = kind_of(" ".join(words[i:]))
                if kind:
                    break
            if not kind:
                continue
            vs = m.start("val")
            ve = _value_end(ln, vs, kind)
            v = ln[vs:ve]
            if _ok(v, kind):
                out.append((starts[li] + vs, starts[li] + vs + len(v.rstrip(" ,;")), kind))
        # 2. a caption alone on its line, the value on the next non-empty line
        if _ANY.match(ln) and ln.strip():
            kind = kind_of(ln)
            for lj in range(li + 1, min(li + 3, len(lines))):
                nxt = lines[lj]
                if nxt.strip():
                    v = nxt.strip()
                    if _ok(v, kind):
                        s = starts[lj] + nxt.index(v)
                        out.append((s, s + len(v), kind))
                    break
    # 3. JSON / key=value with quoted or bare values
    for m in re.finditer(r"[\"']?(?P<key>[A-Za-z_][\w .-]{1,40})[\"']?\s*[:=]\s*\"(?P<val>[^\"\n]{1,80})\"", text):
        kind = kind_of(m.group("key").replace("_", " "))
        if kind and _ok(m.group("val"), kind):
            out.append((m.start("val"), m.end("val"), kind))
    # 4. delimited tables: a header row naming fields, then rows
    for li, ln in enumerate(lines):
        for d in (",", "\t", "|", ";"):
            cells = [c.strip().strip('"') for c in ln.split(d)]
            if len(cells) < 3:
                continue
            kinds = [kind_of(c.replace("_", " ")) if c and len(c) < 40 else None for c in cells]
            if sum(k is not None for k in kinds) < 1 or sum(1 for c in cells if c) < 3:
                continue
            for lj in range(li + 1, len(lines)):
                row = lines[lj]
                if row.count(d) < len(cells) - 1 - (1 if d == "|" else 0) or not row.strip():
                    break
                p = 0
                for ci, cell in enumerate(row.split(d)):
                    if ci < len(kinds) and kinds[ci]:
                        v = cell.strip().strip('"')
                        if _ok(v, kinds[ci]):
                            s = starts[lj] + p + cell.index(v) if v in cell else None
                            if s is not None:
                                out.append((s, s + len(v), kinds[ci]))
                    p += len(cell) + 1
            break
    return out
