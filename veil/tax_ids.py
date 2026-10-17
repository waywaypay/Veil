"""Taxpayer IDs (US SSNs, EINs, ITINs) swapped for placeholders.

This is the engine under ``veil.Redactor``: a conversation's placeholders
(``SSN_001``), the normalized copy text is read through, and the finding of
taxpayer IDs.  The real values stay in memory in the redactor and are put
back with ``restore``.

How a number is found.  The text is read through a normalized copy, so the
original is never changed except where a number is replaced: digits of any
script or style become 0-9, every dash and minus sign becomes "-", HTML
entities, %-escapes and backslash escapes are decoded, and invisible and
combining characters are dropped.  The copy is split into groups of digits
and what separates them.  A run of groups is a taxpayer ID when its digits
add up to nine and:

- it's shaped like one: 123-45-6789 (with any separators, spaces or line
  breaks between the groups, since PDFs often put each group on its own
  line), 12-3456789 (with a dash, dot, slash and the like), nine digits in a
  row, or nine single digits (boxes printed one digit each);
- or a label (SSN, TIN, EIN, Soc. Sec. No., Tax I.D., "identifying number"
  ...) is just before or after it, whatever the grouping;
- or it's a number already caught.

Eight or ten digits count too after a label, or near a number already caught,
when OCR has dropped or added one.  OCR misreads of a few digits as lookalike
letters ("l23-45-6789", "6i94") are read as digits.

What isn't: amounts (after a currency sign, with cents, thousands commas or
a percent sign, or round like 125000000: no SSN ends in 0000), dates, IP
addresses (14.47.149.44, any part of one, or one with a port after it), and
digits that touch a word made of other letters.  With a profile that sets
``form_box_max`` (``US_TAX_K1``), a 2-7 grouping split only by a space or a
comma is left alone unless a label is near, because a form's box number
before an unformatted amount looks just like it ("20 1250000", a CSV row's
"20,1250000").  So is a 3-3-3 grouping spaced wider than one space or one
per line, like a column of small amounts.

A placeholder is put back as the text it replaced, in the usual dashed form
when the document wrote the number that way, so a false alarm never comes
back as an invented ID.  Every number caught is checked against every later
text too, by its digits.
"""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from veil.profiles import GENERIC, Profile

# Letters OCR reads in a digit's place.
_LOOKALIKES = {"O": "0", "o": "0", "Q": "0", "I": "1", "l": "1", "i": "1", "L": "1", "Z": "2", "z": "2",
               "S": "5", "s": "5", "G": "6", "b": "6", "T": "7", "B": "8", "g": "9", "q": "9",
               "X": "0", "x": "0"}   # X: a digit the document masked
# Dashes NFKC leaves alone, and blank characters Unicode doesn't call spaces.
_DASH_LIKE = set("\u2212\u2043\u02d7\u30fc\uff70\u2e3a\u2e3b")
_BLANKS = set("\u115f\u1160\u3164\uffa0\u2800")
_MONEY = set("$\u20ac\u00a3\u00a5\u00a2\u20b9%")
_ESCAPE = re.compile(r"&(?:#\d{1,7}|#[xX][0-9A-Fa-f]{1,6}|[A-Za-z]{2,10});|%[0-9A-Fa-f]{2}|"
                     r"\\u[0-9A-Fa-f]{4}|\\U[0-9A-Fa-f]{8}|\\x[0-9A-Fa-f]{2}|\\[nrt]")
_MAYBE_DIGITS = re.compile(r"[\d\u00b2\u00b3\u00b9\u2070-\u2079\u2080-\u2089\u2460-\u24ff\u2776-\u2793]|"
                           r"&#|%3[0-9]|\\[uUx]")
# Inside a word: digits, with lookalikes only between digits ("5l8", not the "l" of "Total1250").
_SEGMENT = re.compile(r"\d(?:[\d" + "".join(_LOOKALIKES) + r"]*\d)?")
# The built-in kinds of placeholder: SSN_001, NAME_001, ...  ``register_kind`` adds more.
KINDS = ("SSN", "EIN", "TIN", "NAME", "ADDRESS", "EMAIL", "PHONE", "ACCOUNT", "DOB", "ID")
TAX_ID_KINDS = ("SSN", "EIN", "TIN")
_KIND_NAME = re.compile(r"[A-Z][A-Z0-9]*")


@lru_cache(maxsize=64)
def _patterns(kinds: tuple[str, ...]) -> tuple[re.Pattern, re.Pattern]:
    """A placeholder of any of ``kinds``; and a placeholder or a word."""
    placeholder = re.compile(rf"(?:{'|'.join(sorted(kinds, key=len, reverse=True))})_\d{{3,}}(?!\d)")
    return placeholder, re.compile(rf"(?P<placeholder>{placeholder.pattern})|(?P<word>[^\W_]+)")
_LABEL = re.compile(
    r"(?<![^\W\d_])(?i:"
    r"s\.?\s?s\.?\s?ns?\b\.?|ss\s?(?:#|no\b\.?)|i?tins?|atins?|f?eins?|"
    r"tax\s*reg(?:istration|\.)?\s*(?:no\b\.?|number|#)|irs\s*(?:no\b\.?|number|#)|"
    r"soc(?:ial|\.)?\s*sec(?:urity|\.)?(?:\s*(?:no\b\.?|number|#))?|"
    r"(?:taxpayer|employer|federal|fed\.?|tax)\s*(?:id\b\.?|i\.\s?d\b\.?|identification|identifying|no\b\.?|number|#)"
    r"(?:\s*(?:no\b\.?|number|#))?|"
    r"(?:id\b\.?|i\.\s?d\b\.?)\s*(?:no\b\.?|number|#)|"
    r"identif(?:ying|ication)\s+(?:no\b\.?|number|#))"
    r"(?![^\W\d_])(?!_\d)")
_LABEL_BEFORE, _LABEL_AFTER = 200, 20   # how near a label must be, in characters
_DATE_SHAPES = {(2, 2, 4), (1, 2, 4), (2, 1, 4), (1, 1, 4), (4, 2, 2), (4, 1, 2), (4, 2, 1), (4, 1, 1)}


def _norm(c: str) -> str:
    """One character of the normalized copy ("" to drop it)."""
    if c == "\n":
        return "\n"
    if c in "\t\r":
        return " " if c == "\t" else ""
    if c in _BLANKS:
        return " "
    category = unicodedata.category(c)
    if category in ("Mn", "Me", "Cf", "Cc", "Co", "Cs"):
        return ""
    if c.isdigit():
        digit = unicodedata.digit(c, None)
        if digit is not None:
            return str(digit)
    if category.startswith("Z"):
        return " "
    if category == "Pd" or c in _DASH_LIKE:
        return "-"
    folded = unicodedata.normalize("NFKC", c)
    return folded if len(folded) == 1 else c


def _decode(escape: str) -> str | None:
    try:
        if escape[0] == "&":
            decoded = html.unescape(escape)
            return decoded if decoded != escape else None
        if escape[0] == "%":
            return chr(int(escape[1:], 16))
        if escape[1] in "uUx":
            return chr(int(escape[2:], 16))
        return {"n": "\n", "r": "\r", "t": "\t"}[escape[1]]
    except (ValueError, OverflowError):
        return None


def _shadow(text: str) -> tuple[str, list[int], list[int]]:
    """The normalized copy, and for each of its characters the span of ``text`` it came from."""
    chars: list[str] = []
    starts: list[int] = []
    ends: list[int] = []

    def put(source: str, start: int, end: int, step: bool):
        for i, c in enumerate(source):
            for out in _norm(c):
                chars.append(out)
                starts.append(start + i if step else start)
                ends.append(start + i + 1 if step else end)

    pos = 0
    for m in _ESCAPE.finditer(text):
        decoded = _decode(m.group())
        if decoded is None:
            continue
        put(text[pos:m.start()], pos, m.start(), True)
        put(decoded, m.start(), m.end(), False)
        pos = m.end()
    put(text[pos:], pos, len(text), True)
    return "".join(chars), starts, ends


@dataclass
class _Group:
    start: int            # in the normalized copy
    end: int
    digits: str           # as 0-9, lookalikes read as digits
    lookalikes: int = 0
    money: bool = False


@dataclass
class _Candidate:
    first: int            # index of its first and last group in the cluster
    last: int
    kind: str             # SSN, EIN or TIN
    score: int
    dashed: bool          # written as 123-45-6789 / 12-3456789 with real digits


def _is_date(digits: str, sizes: tuple[int, ...]) -> bool:
    if sizes not in _DATE_SHAPES and sizes != (8,):
        return False
    for year, month, day in ((digits[:4], digits[4:6], digits[6:]), (digits[4:], digits[:2], digits[2:4])):
        if 1900 <= int(year) <= 2099 and 1 <= int(month) <= 12 and 1 <= int(day) <= 31:
            return True
    return False


def _joins(gap: str) -> bool:
    """Whether what lies between two groups of digits keeps them one number: separators only, few."""
    if not gap or len(gap) > 10 or gap.count("\n") > 2 or any(c in _MONEY for c in gap):
        return False
    marks = gap.replace(" ", "").replace("\n", "")
    if ":" in marks:
        return False   # a field's tag between them, as SWIFT writes ":64:/130929"
    return len(marks) <= 6 and len(gap.replace("\n", "")) <= 8 and not any(c.isalnum() for c in marks)


# Dates and times: 2022-02-15, 15/02/2022, 2022-02-15T10:30:00, 10:30, 20220301-12:34.
_DATE_TIME = re.compile(r"(?<!\d)(?:(?:19|20)\d{2}([-/.])(?:0?[1-9]|1[0-2])\1(?:0?[1-9]|[12]\d|3[01])"
                        r"|(?:0?[1-9]|[12]\d|3[01])([-/.])(?:0?[1-9]|[12]\d|3[01])\2(?:19|20)\d{2}"
                        r"|(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])(?=[-T ]?\d{1,2}:\d{2}))(?!\d)"
                        r"|(?<![\d.])(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d(?:[.,]\d{1,9})?)?(?!\d)")
# IP addresses: 192.168.0.12, four numbers up to 255 joined by dots, with nothing dotted around them.
_OCTET = r"(?:25[0-5]|2[0-4]\d|[01]?\d?\d)"
_IPV4 = re.compile(rf"(?<!\d)(?<!\d\.){_OCTET}(?:\.{_OCTET}){{3}}(?!\d)(?!\.\d)")


def _mark_amounts(copy: str, clusters) -> None:
    """Groups written as money: 1,234,567 / 1234.56 / 12.5% / a decimal like 25.1234567; dates and times; and
    IP addresses."""
    spans = [(m.start(), m.end()) for pattern in (_DATE_TIME, _IPV4) for m in pattern.finditer(copy)]
    if spans:
        for groups, _ in clusters:
            for group in groups:
                if any(s <= group.start and group.end <= e for s, e in spans):
                    group.money = True
    for groups, joins in clusters:
        for i, group in enumerate(groups):
            after = copy[group.end:group.end + 5]
            before = copy[max(0, group.start - 2):group.start]
            thousands_after = len(group.digits) <= 3 and re.match(r",\d{3}(?!\d)", after)
            thousands_before = len(group.digits) == 3 and len(before) == 2 and before[1] == "," and before[0].isdigit()
            if after[:1] == "%" or thousands_after or thousands_before:
                group.money = True
            # One dot between two groups, with no other dots joining them, and at most six decimals (or a
            # percent sign): a decimal number.  "47.1058392" is an EIN written with a dot.
            if i + 1 < len(groups) and joins[i] == "." and not (i > 0 and joins[i - 1] == ".") and \
                    not (i + 2 < len(groups) and joins[i + 1] == ".") and \
                    (len(groups[i + 1].digits) <= 6 or copy[groups[i + 1].end:groups[i + 1].end + 1] == "%"):
                group.money = groups[i + 1].money = True


class TaxIdRedactor:
    """One conversation's placeholders: the same number always gets the same one."""

    def __init__(self, profile: Profile | None = None):
        self.profile = profile or GENERIC
        self._kinds: tuple[str, ...] = KINDS
        self._placeholder_re, self._token_re = _patterns(self._kinds)
        self._by_digits: dict[str, str] = {}   # "123456789" -> "SSN_001"
        self._real: dict[str, str] = {}        # "SSN_001" -> the text it stands for
        self._counts: dict[str, int] = {}
        self._literals: dict[str, str] = {}    # text another detector found, as written -> placeholder
        self._near: set[str] = set()           # each caught number with one digit wildcarded or dropped

    def __len__(self) -> int:
        return len(self._real)

    @property
    def kinds(self) -> tuple[str, ...]:
        return self._kinds

    @property
    def mapping(self) -> dict[str, str]:
        """Each placeholder handed out so far, and the text it stands for."""
        return dict(self._real)

    def register_kind(self, kind: str) -> None:
        """Allow placeholders of a new ``kind`` (capital letters and digits, e.g. "MRN") from now on."""
        if not _KIND_NAME.fullmatch(kind or ""):
            raise ValueError(f"{kind!r} isn't a placeholder kind: use capital letters and digits, e.g. MRN.")
        if kind not in self._kinds:
            self._kinds = self._kinds + (kind,)
            self._placeholder_re, self._token_re = _patterns(self._kinds)
            self._kinds_changed()

    def _kinds_changed(self) -> None:
        pass

    # -- placeholders --------------------------------------------------------

    def add(self, text: str, kind: str = "TIN") -> str:
        """Hide ``text`` from now on, wherever it appears as written (another detector found it, such as a
        Bedrock guardrail); returns its placeholder.  A taxpayer ID shares the placeholder of the same digits."""
        if not text.strip():
            raise ValueError("Nothing to hide.")
        self.register_kind(kind)
        digits = "".join(c for c in _shadow(text)[0] if c.isdigit())
        key = digits if kind in TAX_ID_KINDS and digits else f"{kind}:{' '.join(text.casefold().split())}"
        self._literals[text] = self._placeholder(kind, key, text, dashed=False)
        return self._literals[text]

    def _placeholder(self, kind: str, digits: str, written: str, dashed: bool) -> str:
        if digits not in self._by_digits:
            if len(digits) == 9 and digits.isdigit():
                self._near.update(digits[:i] + "?" + digits[i + 1:] for i in range(9))
                self._near.update(digits[:i] + digits[i + 1:] for i in range(9))
            self._counts[kind] = self._counts.get(kind, 0) + 1
            placeholder = f"{kind}_{self._counts[kind]:03d}"
            self._by_digits[digits] = placeholder
            self._real[placeholder] = written
        placeholder = self._by_digits[digits]
        if dashed:   # the document's own dashed form is the one to put back
            self._real[placeholder] = (f"{digits[:3]}-{digits[3:5]}-{digits[5:]}" if kind == "SSN"
                                       else f"{digits[:2]}-{digits[2:]}")
        return placeholder

    def _known(self, digits: str) -> bool:
        """A number already caught, or one digit off from one (changed, dropped or added)."""
        if digits in self._by_digits:
            return True
        if len(digits) == 9:
            return any(digits[:i] + "?" + digits[i + 1:] in self._near for i in range(9))
        if len(digits) == 8:
            return digits in self._near
        return len(digits) == 10 and any(digits[:i] + digits[i + 1:] in self._by_digits for i in range(10))

    # -- finding numbers -------------------------------------------------------

    def _clusters(self, copy: str) -> list[tuple[list[_Group], list[str]]]:
        """Runs of digit groups joined only by separators, each with the separators between its groups."""
        clusters: list[tuple[list[_Group], list[str]]] = []
        groups: list[_Group] = []
        joins: list[str] = []
        money_next = False

        def close():
            nonlocal groups, joins
            if groups:
                clusters.append((groups, joins))
            groups, joins = [], []

        def add_group(group: _Group, gap: str):
            nonlocal money_next
            if money_next or any(c in _MONEY for c in gap):
                group.money = True
            money_next = False
            if groups and _joins(gap):
                joins.append(gap)
            else:
                close()
            groups.append(group)

        pos = 0
        for m in self._token_re.finditer(copy):
            gap = copy[pos:m.start()]
            pos = m.end()
            word = m.group("word")
            if word is None:   # a placeholder already in the text ends any run
                close()
                continue
            if any(c.isdigit() for c in word) and all(c.isdigit() or c in _LOOKALIKES for c in word) and \
                    (len(word) <= 9 or (word[0].isdigit() and word[-1].isdigit())):
                digits = "".join(c if c.isdigit() else _LOOKALIKES[c] for c in word)
                add_group(_Group(m.start(), m.end(), digits, sum(not c.isdigit() for c in word)), gap)
                continue
            # A word with other letters: its runs of digits (and lookalikes between digits) are groups,
            # and its other letters end any run of groups.
            runs = [r for r in _SEGMENT.finditer(word) if any(c.isdigit() for c in r.group())]
            if not runs or runs[0].start() > 0:
                close()
            for n, run in enumerate(runs):
                if n:
                    close()
                text = run.group()
                add_group(_Group(m.start() + run.start(), m.start() + run.end(),
                                 "".join(c if c.isdigit() else _LOOKALIKES[c] for c in text),
                                 sum(not c.isdigit() for c in text)), gap if run.start() == 0 else "")
            if not runs or runs[-1].end() < len(word):
                close()
                money_next = word.upper() in ("USD", "US", "EUR", "GBP")
        close()
        _mark_amounts(copy, clusters)
        return clusters

    def _judge(self, run: list[_Group], joins: list[str], labels) -> tuple[str, int, bool] | None:
        digits = "".join(g.digits for g in run)
        sizes = tuple(len(g.digits) for g in run)
        if any(g.money for g in run):   # an amount or a date, even one whose digits match a number caught
            return None
        known = self._known(digits)
        if known and digits not in self._by_digits and len(set(digits)) == 1:
            known = False   # 000000000 is one digit off 000000001, but no number
        lookalikes = sum(g.lookalikes for g in run)
        # A comma is a weak separator, like a space: in a CSV row "20,1250000" is a box and an amount.
        punct = all(j.strip(" \n,") for j in joins)
        dashes = bool(joins) and all("-" in j for j in joins)
        dashed = punct and not lookalikes and all(j.strip(" \n") == "-" for j in joins)
        if known and digits in self._by_digits:
            return ("SSN" if sizes == (3, 2, 4) else "EIN" if sizes == (2, 7) else "TIN"), 100, \
                dashed and sizes in ((3, 2, 4), (2, 7))
        # A few misread digits are fine; four only in a dashed SSN or EIN, and five real digits at least.
        if any(g.money for g in run) or lookalikes > 4 or (lookalikes and len(digits) - lookalikes < 5) or \
                (lookalikes == 4 and not (punct and sizes in ((3, 2, 4), (2, 7)))):
            return None
        if known:
            return "TIN", 90, False
        start, end = run[0].start, run[-1].end

        def near(before: int, after: int) -> bool:
            return any(0 <= start - label_end <= before or 0 <= label_start - end <= after
                       for label_start, label_end in labels)

        if len(set(digits)) == 1 and not near(_LABEL_BEFORE, _LABEL_AFTER):
            return None   # 0,0,0,0,0,0,0,0,0: a row of empty fields, no number

        if len(digits) == 9:
            if digits.endswith("0000") and sizes != (3, 2, 4) and sizes != (2, 7):
                return None   # no SSN ends in 0000: a round amount such as 125000000
            if digits.startswith("00") and sizes == (9,) and not near(_LABEL_BEFORE, _LABEL_AFTER):
                return None   # no SSN, EIN or ITIN starts 00: a counter such as 000000001
            if sizes in ((9,), (3, 2, 4)):
                return ("SSN" if sizes == (3, 2, 4) else "TIN"), 80, dashed and sizes == (3, 2, 4)
            if sizes == (2, 7):
                # Split only by spaces, "20 1250000" is more likely a form's box number and an amount.
                box_max = self.profile.form_box_max
                if box_max is None or punct or near(_LABEL_BEFORE, _LABEL_AFTER) or run[0].digits[0] == "0" \
                        or int(run[0].digits) > box_max:
                    return "EIN", 80, dashed
                return None
            if all(s == 1 for s in sizes) and all(len(j) <= 3 and "," not in j and "\n" not in j for j in joins):
                return "TIN", 75, False   # one digit per box on a line (a list "1,2,3,...,9" isn't)
            # "518 206 194" typed with single spaces; a table's column of small amounts is spaced wider.
            if sizes == (3, 3, 3) and all(j == " " for j in joins):
                return "TIN", 70, False
            # Joined by dashes or dots, any grouping is an ID typed oddly ("518-206-194"); not a ZIP+4.
            if punct and sizes not in ((5, 4), (4, 5)) and min(sizes) > 1 and \
                    all(len(j.strip(" ")) == 1 and j.strip(" ") in "-./" for j in joins):
                return "TIN", 70, False
            return ("TIN", 60, False) if near(_LABEL_BEFORE, _LABEL_AFTER) else None
        # Eight or ten digits: OCR dropped or added one.  Never a date or a phone number.
        if _is_date(digits, sizes) or sizes in ((3, 3, 4), (10,), (1, 3, 3, 4)):
            return None
        if sizes in ((3, 2, 3), (2, 6), (4, 2, 4), (3, 2, 5), (2, 8)):
            if (punct and len(digits) == 8) or (dashes and len(digits) == 10) or near(_LABEL_BEFORE, _LABEL_AFTER):
                return ("SSN" if len(sizes) == 3 else "EIN"), 50, False
            return None
        return ("TIN", 40, False) if near(30, _LABEL_AFTER) else None

    def redact_text(self, text: str) -> str:
        return self._redact_ids(self._prepare(text))

    def _prepare(self, text: str) -> str:
        """``text`` with what another detector found replaced, and placeholder-shaped text that isn't
        ours broken up, since it would later be "put back" as a real value."""
        for literal in sorted(self._literals, key=len, reverse=True):
            text = text.replace(literal, self._literals[literal])
        return self._placeholder_re.sub(lambda m: m.group() if self._resolve(m.group()) else m.group().replace("_", "\u2010"),
                                text)

    def _resolve(self, token: str) -> tuple[str, str] | None:
        """``(our placeholder, the digits after it)`` for placeholder-shaped ``token``, or None if it isn't
        ours.  A placeholder can sit right before digits: "K1_NAME_0012024.pdf" is NAME_001 and 2024."""
        kind, _, digits = token.partition("_")
        for n in range(len(digits), 2, -1):
            if f"{kind}_{digits[:n]}" in self._real:
                return f"{kind}_{digits[:n]}", digits[n:]
        return None

    def _placeholder_spans(self, text: str) -> list[tuple[int, int]]:
        """Where this conversation's placeholders are in ``text``, letters glued on before them or not."""
        spans = []
        for m in self._placeholder_re.finditer(text):
            ours = self._resolve(m.group())
            if ours:
                spans.append((m.start(), m.start() + len(ours[0])))
        return spans

    def _redact_ids(self, text: str) -> str:
        if not _MAYBE_DIGITS.search(text):
            return text
        copy, starts, ends = _shadow(text)
        for start, end in self._placeholder_spans(copy):   # their digits are no part of any number
            copy = copy[:start] + "k" * (end - start) + copy[end:]
        labels = [(m.start(), m.end()) for m in _LABEL.finditer(copy)]
        replacements = []
        for groups, joins in self._clusters(copy):
            found = []
            for first in range(len(groups)):
                total = 0
                for last in range(first, len(groups)):
                    total += len(groups[last].digits)
                    if total > 10:
                        break
                    verdict = self._judge(groups[first:last + 1], joins[first:last], labels) if total >= 8 else None
                    if verdict:
                        found.append(_Candidate(first, last, *verdict))
            # A two-column layout can leave "518-20-" or "47-" dangling, the rest further on.
            tail = tuple(len(g.digits) for g in groups[-2:])
            if not found and copy[groups[-1].end:groups[-1].end + 1] == "-" and not groups[-1].money and \
                    (tail == (3, 2) and "-" in joins[-1] or tail[-1:] == (2,)) and \
                    any(0 <= groups[-len(tail) if tail == (3, 2) else -1].start - label_end <= _LABEL_BEFORE
                        for _label_start, label_end in labels):
                found.append(_Candidate(len(groups) - (2 if tail == (3, 2) else 1), len(groups) - 1, "TIN", 30, False))
            chosen: list[_Candidate] = []
            for c in sorted(found, key=lambda c: (-c.score, c.first)):
                if all(c.last < o.first or c.first > o.last for o in chosen):
                    chosen.append(c)
            for c in chosen:
                # A group a dash ties to a number (a two-column layout's "518-20-" then "1058392") goes with it.
                while c.first > 0 and "-" in joins[c.first - 1] and not groups[c.first - 1].money and \
                        all(o.last < c.first - 1 or o.first > c.first - 1 for o in chosen):
                    c.first, c.kind, c.dashed = c.first - 1, "TIN", False
                while c.last + 1 < len(groups) and "-" in joins[c.last] and not groups[c.last + 1].money and \
                        all(o.last < c.last + 1 or o.first > c.last + 1 for o in chosen):
                    c.last, c.kind, c.dashed = c.last + 1, "TIN", False
                run = groups[c.first:c.last + 1]
                source_start, source_end = starts[run[0].start], ends[run[-1].end - 1]
                replacements.append((source_start, source_end, self._placeholder(
                    c.kind, "".join(g.digits for g in run), text[source_start:source_end], c.dashed)))
        for source_start, source_end, placeholder in sorted(replacements, reverse=True):
            text = text[:source_start] + placeholder + text[source_end:]
        return text

    def restore_text(self, text: str) -> str:
        def back(m: re.Match) -> str:
            ours = self._resolve(m.group())
            return self._real[ours[0]] + ours[1] if ours else m.group()
        return self._placeholder_re.sub(back, text)

    # -- structures ---------------------------------------------------------------

    def redact(self, value: Any) -> Any:
        """``value`` with every taxpayer ID in its strings (and keys, and long whole numbers) replaced;
        dicts and lists are walked.  Read twice, so a label in one string counts for all of them."""
        self._walk(value, self.redact_text)
        return self._walk(value, self.redact_text)

    def restore(self, value: Any) -> Any:
        """``value`` with this conversation's placeholders turned back into the real numbers."""
        return self._walk(value, self.restore_text)

    def _walk(self, value: Any, fix) -> Any:
        if isinstance(value, str):
            return fix(value)
        if isinstance(value, int) and not isinstance(value, bool) and abs(value) >= 10_000_000:
            fixed = fix(str(value))
            return fixed if fixed != str(value) else value
        if isinstance(value, dict):
            return {(fix(k) if isinstance(k, str) else k): self._walk(v, fix) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._walk(v, fix) for v in value]
        return value
