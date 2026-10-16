"""Personal information swapped for placeholders before text goes to a model.

``Redactor`` finds taxpayer IDs (``veil.tax_ids``), names, addresses, email
addresses, phone numbers, account and ID numbers, birth dates, long digit
runs and whatever your own ``patterns`` match (the README lists the forms
each takes), and gives each a placeholder: NAME_001, ADDRESS_001 ... the same
one for the same person or value all conversation.  ``restore`` puts the real
values back; a person's name comes back the way it was first known, anything
else as it was written.

Names are those you tell it of (``add_person``), however they're written, and
those it finds by word lists and cues ("Mr.", "Attn:", "Last, First").  What
the user types (``typed=True``) is read more eagerly.  A found name followed
by Fund, Capital, L.P. and the like is a business's and stays, as do names
given to ``add_business``.  The text is read through the same normalized copy
as taxpayer IDs, so odd characters hide nothing.  The word lists are in
``veil/words``.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache

from veil.profiles import Profile, word_file
from veil.tax_ids import KINDS, TAX_ID_KINDS, TaxIdRedactor, _shadow


def _words(text: str) -> frozenset[str]:
    return frozenset(text.casefold().split())


# Common first names.  Words that are ordinary words too (Will, Mark, Grant, June, Rose, Faith, Virginia ...)
# are left out: those count only as part of a name found another way.
_GIVEN = word_file("given_names")
# Common surnames that are no ordinary word.  One beside another name makes a name: "Priya Patel".
_SURNAMES = word_file("surnames")
# Surnames that are ordinary words or places too: hidden with a first name or a title, never alone, and no
# sign of a name by themselves.
_WORD_SURNAMES = word_file("word_surnames")
# Capitalized words that aren't names in any document: everyday words, months, days, places and words that
# start sentences.  A profile (veil.profiles) adds its documents' own words.
_STOP = word_file("stop_words")
# After a found name, these make it a business's: "Jordan Ridge Capital", "Hudson Yards Co-Invest".
_BUSINESS = word_file("business_words")
# A name before one of these is still a person's: "Avery Mockridge Revocable Trust", "... IRA".
_PERSONAL = _words("""
trust revocable irrevocable living family ira roth sep rollover jtwros ttee trustee custodian fbo
retirement pension foundation charitable remainder annuity marital grantor dynasty gst descendants
children heirs survivor survivors bypass qtip
""")
# A capitalized word before one of these is a family's name: "The Okonkwo Family Trust".
_FAMILY = _words("revocable irrevocable living dynasty grantor marital gst bypass qtip descendants heirs")
# Firms and the like with what looks like a person's name.
_FIRMS = word_file("firms", lines=True)
_HONORIFICS = _words("mr mrs ms miss mx dr prof sir dame")
_NAME_SUFFIXES = _words("jr sr ii iii iv md phd cpa esq")
_ROMAN = _words("i ii iii iv v vi vii viii ix x xi xii xiii xiv xv")
_PARTICLES = _words("van von de da del della der den di du la le st bin binti ibn abu al el ni nic mac dos das do "
                    "ter ten")

# Words right before a person's name: the capitalized words after one are taken for a name.  Those in the
# first group can have the name on the next line, as a form or a signature block puts it.
_CUE_PATTERN = (
    r"(?<![^\W\d_])(?i:"
    r"(?:(?:partner|investor|member|account|beneficiary|owner|holder|client|contact)(?:'s)?\s+name"
    r"|name\s+of\s+(?:the\s+)?(?:partner|investor|member|owner|holder|beneficiary)"
    r"|(?<!bank\s)(?<!fund\s)(?<!firm\s)(?<!file\s)(?<!user\s)(?<!company\s)(?<!entity\s)(?<!business\s)name"
    r"|zip\s+code|signatory|signature|regards|sincerely|cordially|respectfully"
    r"|(?:beneficial\s+)?owner|(?:account\s+)?holder|executor|executrix|administrator|guardian|conservator"
    r"|(?:partnership\s+)?representative|designated\s+individual|attorney(?:-in-fact)?|poa)"
    r"[ \t]*(?:[:.,-][ \t]*)?(?:\n[ \t]*){0,2}"
    r"|(?:named|members?|partners?|limited\s+partner|general\s+partner|investor|shareholder|stockholder"
    r"|beneficiary|trustee|custodian|grantor|spouse|client|contact(?:\s+person)?|attn|attention|dear|fbo|c/o"
    r"|for\s+the\s+benefit\s+of|(?:prepared|issued|mailed|sent|registered)\s+(?:for|to)|prepared\s+by"
    r"|registration|signed{extra})"
    r"(?:'s)?[ \t]*(?:[:.,-][ \t]*)?(?:/s/[ \t]*)?"
    r"|(?:by|to|from|re|cc|bcc)[ \t]*:[ \t]*(?:/s/[ \t]*)?)\Z")
# The last word of each of those: the label is looked for only after one of them.
_CUE_ENDS = _words("""
name code signatory signature regards sincerely cordially respectfully owner holder executor executrix administrator
guardian conservator representative individual attorney attorney-in-fact poa named member members partner partners
investor shareholder stockholder beneficiary trustee custodian grantor spouse client contact person attn attention
dear fbo o of for to registration signed by from re cc bcc s
""")
# After a name, in what the user types: what says it's a person's (a profile adds its own).
_AFTER_CUES = (r",?[ \t]+(?i:ttee|trustee|custodian|cust|executor|executrix)\b",)

# A word: letters, with apostrophes (O'Brien, but not a possessive 's) and hyphens inside.
_TOKEN = re.compile(r"[^\W\d_]+(?:'(?![sS](?![^\W\d_]))[^\W\d_]+)*(?:-[^\W\d_]+)*")
_NAME_GAP = re.compile(r"[ \t_]{1,3}")
_COMMA_GAP = re.compile(r",[ \t]{1,2}")
_LIST_GAP = re.compile(r"(?:[ \t]*\([^()\n]{1,12}\))?(?:,[ \t]{1,2}(?:(?:and|&)[ \t]+)?|[ \t]+(?:and|&)[ \t]+)",
                       re.IGNORECASE)
# What ends a business's name: "L.P.", "L.L.C.", "GmbH" ..., perhaps after a number ("II, L.P.").
_LEGAL_ENDING = re.compile(
    r"[ \t,]*(?:(?:[IVX]+|\d+)[ \t,]+)*(?:L\.[ \t]?P\.|L\.[ \t]?L\.[ \t]?[CP]\.?|P\.[ \t]?C\.|N\.[ \t]?A\.|S\.[ \t]?A\."
    r"|GmbH|B\.[ \t]?V\.|A\.[ \t]?G\.)", re.IGNORECASE)

_TLD = r"(?:com|org|net|edu|gov|io|co|us|uk|ca|de|fr|ai|biz|info|me|[a-z]{2})"
_AT = r"(?:[ \t]*@[ \t]*|[ \t]*[\[({]at[\])}][ \t]*|[ \t]+at[ \t]+)"
_DOT = r"(?:[ \t]*\.[ \t]*|[ \t]*[\[({]dot[\])}][ \t]*|[ \t]+dot[ \t]+)"
_EMAIL = re.compile(rf"(?<![\w.%+-])(?:[\w%+-]|\.(?=[\w%+\[(-])|[ \t]+\.[ \t]+(?=\w)|[\[(]dot[\])])+{_AT}"
                    rf"[\w-]+(?:{_DOT}[\w-]+)*?"
                    rf"{_DOT}{_TLD}(?![\w-])", re.IGNORECASE)
_NO = r"(?:no\b\.?|number|num\b\.?|\#)"
_ACCOUNT_LABEL = (
    r"(?:(?:bank|brokerage|checking|savings|investment|custody|custodial|custodian|beneficiary|wire|deposit|ira|dda"
    rf"|credit|sub-?)[ \t]*(?:account|acct\b\.?|a/c)(?:\s*{_NO})?"
    rf"|(?:account|acct\b\.?|a/c)\s*(?:{_NO}|ending(?:\s+in)?)"
    rf"|(?:for\s+(?:further\s+)?credit(?:\s+to)?|ffc|further\s+credit)(?:\s+(?:account|acct\b\.?|a/c))?(?:\s*{_NO})?"
    rf"|routing(?:\s*/?\s*transit)?(?:\s*{_NO})?|aba(?:\s*routing)?(?:\s*{_NO})?"
    rf"|rtn|iban|(?:credit|debit)\s*card(?:\s*{_NO})?|card\s*{_NO}"
    r"|(?:visa|mastercard|amex|american\s+express|discover|card)\s+ending(?:\s+in)?)"
    # "Account Number (last 4): 4321"
    r"(?:[ \t]*\([^()\n]{0,15}\))?")
# "account", "acct" or "a/c" alone: a number needs six digits after it, and a capital account is no account.
_BARE_ACCOUNT = r"(?<!capital\s)(?<!capital\s\s)(?:account|acct\b\.?|a/c|dda)"
_SWIFT_LABEL = r"swift(?:\s*/\s*bic)?(?:\s*code)?|bic(?:\s*code)?"
_ID_LABEL = (
    rf"driver'?s?\s*licen[cs]e(?:\s*{_NO})?|dl(?=\s*[#:])|dl\s*no\b\.?|passport(?:\s*{_NO})?"
    r"|(?:lp|gp|investor|partner|member|client|customer|policy|employee|patient|holder|medicare|medicaid|insurance"
    rf"|national|foreign(?:\s+tax)?)\s*(?:id\b\.?|i\.\s?d\.|code|identification(?:\s*{_NO})?|{_NO})"
    # a foreign tax number; a US one is the taxpayer IDs' (utils.taxpayer_ids)
    r"|foreign(?:\s+tax)?\s*tin\b"
    rf"(?:\s*{_NO})?|(?:ni|nino|national\s+insurance)(?:\s*{_NO})?|pan(?:\s*(?:card|{_NO}))?"
    rf"|aadhaa?r(?:\s*{_NO})?")
_DOB_LABEL = (r"(?:d\.?\s?o\.?\s?b\b\.?|date\s+of\s+birth|birth\s*date|birthday|born(?:\s+on)?)"
              r"(?:\s+of\s+(?:the\s+)?(?:partner|member|investor|owner|holder|spouse|beneficiary))?"
              r"(?:[ \t]*\([^()\n]{0,20}\))?")
_MONTHS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DATE = (r"\d{1,2}[/.-]\d{1,2}[/.-](?:\d{4}|\d{2})|\d{1,2}[ ]\d{1,2}[ ]\d{4}|\d{4}[/.-]\d{1,2}[/.-]\d{1,2}"
         r"|(?:19|20)\d{6}(?!\d)"
         rf"|{_MONTHS}[ \t]+\d{{1,2}}(?:st|nd|rd|th)?,?[ \t]+\d{{4}}"
         rf"|\d{{1,2}}(?:st|nd|rd|th)?[ \t/.-]*{_MONTHS},?[ \t/.-]*\d{{2,4}}")
_SEP = r"[ \t]*(?:[:#.=|\u2013-][ \t]*|is[ \t]+)?(?:\n[ \t]*){0,2}"
# An account or ID number: letters, digits, masks and dashes, in up to six groups.
_VALUE = r"[A-Za-z0-9*\u2022#][A-Za-z0-9*\u2022#/-]*(?:[ ][A-Za-z0-9*\u2022#/-]+){0,5}"
_LABELLED = re.compile(
    rf"(?<![^\W\d_])(?i:(?P<account>{_ACCOUNT_LABEL})|(?P<swift>{_SWIFT_LABEL})|(?P<id>{_ID_LABEL})"
    rf"|(?P<dob>{_DOB_LABEL})|(?P<bare>{_BARE_ACCOUNT}))(?![^\W\d_]){_SEP}"
    rf"(?P<value>(?(dob)(?i:{_DATE})|(?(swift)(?i:[A-Z]{{6}}[A-Z0-9]{{2}}(?:[A-Z0-9]{{3}})?)(?![A-Za-z0-9])"
    rf"|{_VALUE})))")
_PHONE_LABEL = (rf"(?<![^\W\d_])(?i:(?:phone|tel(?:ephone)?|mobile|cell(?:ular)?|fax|ph)\b\.?(?:[ \t]*{_NO})?"
                r"[ \t]*[:.#-]?|(?:direct|office|work|home|main)[ \t]*:)")
_EXTENSION = r"(?:[ \t]*(?:x|ext\b\.?|extension)[ \t]*\d{1,6})?"
_END = r"(?![\d]|[.,]\d)"
_PHONES = [
    # 415-555-0134, (415) 555-0134, 415.555.0134, 415 555-0134, 415/555-0134, 1-415-555-0134, with any extension
    re.compile(r"(?<![\w$.,+/-])(?:\+?1[ .-]?)?(?:\(\s*\d{3}\s*\)[ .-]?\d{3}[ .-]|\d{3}[.-]\d{3}[ .-]|\d{3}[ /]\d{3}-"
               r"|\d{3}[ ]-[ ]\d{3}[ ]-[ ])"
               rf"\d{{4}}{_EXTENSION}{_END}"),
    # +1 415 555 0134
    re.compile(rf"(?<![\w+])\+1[ .-]?\(?[2-9]\d{{2}}\)?[ .-]?[2-9]\d{{2}}[ .-]?\d{{4}}{_EXTENSION}{_END}"),
    # anything after "Phone:", "Tel", "Fax", "Work:" ...
    re.compile(rf"{_PHONE_LABEL}[ \t]*(?P<value>\+?[\d(][\d ().-]{{6,22}}\d{_EXTENSION}){_END}"),
    # +44 20 7946 0958, 011 44 20 7946 0958
    re.compile(rf"(?<![\w+])(?:\+|011[ .-]?|00[ ])(?!1[ .(-]?[2-9])\d{{1,3}}(?:[ .-]?\(?\d{{1,5}}\)?){{2,5}}{_END}"),
]
# In what the user types: 415 555 0134, 1 415 555 0134 and 4155550134 too.
_TYPED_PHONES = [re.compile(rf"(?<![\d.,$])(?:1[ .-])?[2-9]\d{{2}} [2-9]\d{{2}} \d{{4}}{_END}"),
                 re.compile(rf"(?<![\d.,$])[2-9]\d{{2}}[2-9]\d{{6}}{_END}")]
_STREET_SUFFIX = ("Street St Avenue Ave Av Road Rd Boulevard Blvd Lane Ln Drive Dr Court Ct Place Pl Way Terrace Ter "
                  "Circle Cir Parkway Pkwy Highway Hwy Square Sq Trail Trl Plaza Plz Alley Aly Loop Row Path Pike "
                  "Crescent Cres Center Ctr Centre Expressway Expy Freeway Fwy Turnpike Tpke Causeway Mews Walk "
                  "Commons Crossing Heights Hts Route Rte Yards Wharf Pier Quay Esplanade Promenade Concourse").split()
_STATE_CODES = ("AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC "
                "ND OH OK OR PA PR RI SC SD TN TX UT VT VA VI WA WV WI WY GU").split()
_STATE_NAMES = ["Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", "Delaware",
                "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky",
                "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi",
                "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey", "New Mexico",
                "New York", "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania",
                "Rhode Island", "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont",
                "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming", "District of Columbia",
                "Puerto Rico"]
_STATE_ABBREVIATIONS = ("Ala Ariz Ark Calif Cal Colo Conn Del Fla Ga Ill Ind Kan Kans Ky La Md Mass Mich Minn Miss Mo "
                        "Mont Neb Nev Okla Ore Pa Penn Tenn Tex Vt Va Wash Wis Wyo").split()
_STATE = (rf"(?:(?:{'|'.join(_STATE_CODES)})\b\.?|(?:{'|'.join(_STATE_ABBREVIATIONS)})\.|(?:[NSRW]\.[ \t]?[A-Z]\."
          rf"|W\.[ \t]?Va\.|D\.[ \t]?C\.)|{'|'.join(_STATE_NAMES + [s.upper() for s in _STATE_NAMES])})")
_ZIP = r"\d{5}(?:-\d{4})?(?!\d)"
# Words before a state and five digits that say it's an amount, not a city: "Ordinary Income CA 45000".
_NOT_CITY = _words("""
income tax taxes paid total composite withheld withholding ordinary dividends interest gain gains loss losses
credit credits deduction deductions distribution distributions contribution contributions amount amounts
balance capital account net gross basis box line code section partner partners share estimated refund due
state local nonresident resident apportionment allocation allocated sourced source fund funds
""") | _BUSINESS
_CITY_STATE_ZIP = re.compile(rf"(?<![\w'])(?P<city>(?:[A-Z][\w'.-]*[ \t]+"
                             rf"(?:d'|(?:de|la|du|del|los|las|el)[ \t]+)?){{0,2}}"
                             rf"[A-Z][\w'.-]*),?[ \t]+{_STATE},?[ \t]+{_ZIP}")
# In what the user types: "east hampton ny 11937".
_TYPED_CITY_STATE_ZIP = re.compile(rf"(?<![\w'])(?P<city>(?:[a-z][\w'.-]*[ \t]+){{0,2}}[a-z][\w'.-]*),?[ \t]+"
                                   rf"(?i:{'|'.join(_STATE_CODES)}),?[ \t]+{_ZIP}")
# Abroad: "Bahnhofstrasse 45", "75001 Paris, France".
_COUNTRIES = ("France Germany Switzerland Austria Italy Spain Belgium Netherlands Luxembourg Sweden Denmark Norway "
              "Finland Portugal Ireland Mexico Japan Canada Brazil Israel Singapore Australia").split()
_FOREIGN = re.compile(
    r"(?<![\w])[A-Z][\w]*(?:strasse|stra\u00dfe|str\.|gasse|weg|platz|allee|ring|damm)[ \t]+\d{1,5}[a-z]?(?![\w])"
    rf"|(?<![\w-])\d{{3,5}}(?:-\d{{4}})?[ \t]+(?:[A-Z][\w'.-]*[ \t]+){{0,3}}[A-Z][\w'.-]*,[ \t]+"
    rf"(?:{'|'.join(_COUNTRIES)})\b")
# "Mailing address: 88 Kearny": the rest of the line, when it has a number.
_ADDRESS_LABEL = re.compile(r"(?<![^\W\d_])(?i:(?:mailing|street|home|residential|permanent|billing|registered|"
                            r"partner'?s?|investor'?s?)[ \t]+address|address)[ \t]*(?::|\#|[ \t]-[ \t])[ \t]*"
                            r"(?P<value>[^\n]*\d[^\n]*)")
_DIRECTION = r"(?:N|S|E|W|NE|NW|SE|SW|North|South|East|West)\.?"
_UNIT = r"(?:Suite|Ste|STE|SUITE|Apt|APT|Apartment|Unit|UNIT|Floor|FLOOR|Fl|Room|Rm|Bldg|Building|\#)"
_NUMBER_WORDS = "One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve Fifteen Twenty Fifty Hundred".split()
_STREET = re.compile(
    rf"(?<![\w$.,/-])(?:\d{{1,6}}(?:[A-Za-z]|-\d{{1,5}}|-[A-Za-z]|[ ]1/2)?|{'|'.join(_NUMBER_WORDS)})[ \t]+"
    rf"(?:{_DIRECTION}[ \t]+)?(?:"
    rf"(?:(?:[A-Z][\w'.-]*|\d+(?:st|nd|rd|th))[ \t]+){{1,4}}"
    rf"(?:{'|'.join(_STREET_SUFFIX + [s.upper() for s in _STREET_SUFFIX])})\.?(?![\w])"
    r"|(?:[a-z][\w'.-]*[ \t]+){1,3}(?:street|st|avenue|ave|road|rd|boulevard|blvd|lane|ln|drive|court|ct|place"
    r"|parkway|pkwy|highway|hwy|terrace|circle)\.?(?![\w])"
    r"|(?i:el[ \t]+camino[ \t]+real|(?:alameda|avenida|calle|camino|via|rue|avenue[ \t]+of[ \t]+the)"
    r"(?:[ \t]+[a-z][\w'.-]*){1,4})|Broadway|BROADWAY)"
    rf"(?:[ \t]+{_DIRECTION}(?![\w]))?"
    rf"(?:,?[ \t]*{_UNIT}\.?[ \t]*\#?[A-Za-z0-9-]+|,?[ \t]*\d+(?:st|nd|rd|th)[ \t]+(?:Floor|FLOOR|Fl)\.?)?"
    # the city, state and ZIP on the same line
    rf"(?:,?[ \t]+(?:[A-Z][\w'.-]*,?[ \t]+){{0,3}}{_STATE},?[ \t]+{_ZIP})?")
_BOXES = re.compile(
    r"(?<![^\W\d_])(?i:(?:p\.?[ \t]?[o0]\.?|post[ \t]+office)[ \t]*b[o0]x|pob|pmb|private[ \t]+mailbox|postfach"
    r"|apartado(?:[ \t]+postal)?|casilla|bo\u00eete[ \t]+postale)[ \t]*\#?[ \t]*\d{1,7}"
    r"(?!\d)|(?<![^\W\d_])(?i:rr|r\.r\.|rural[ \t]+route|hc|highway[ \t]+contract|psc|cmr)[ \t]*\d{1,5},?[ \t]+"
    r"(?i:box)[ \t]*\d{1,6}(?:,?[ \t]+(?:APO|FPO|DPO)[ \t]+(?:AE|AP|AA)[ \t]+\d{5})?"
    r"|(?<![^\W\d_])(?:APO|FPO|DPO)[ \t]+(?:AE|AP|AA)[ \t]+\d{5}(?!\d)"
    # "Box 1234, Jackson, WY 83001": a plain "Box" only with the city, state and ZIP after it
    rf"|(?<![^\W\d_])Box[ \t]+\d{{1,6}},[ \t]+(?:[A-Z][\w'.-]*,?[ \t]+){{0,3}}{_STATE},?[ \t]+{_ZIP}")
_UNIT_LINE = re.compile(r"(?m)^[ \t]*(?:Apt|Apartment|Suite|Ste|Unit|Floor|Fl|Room|Rm|Bldg|Building)\.?[ \t]*\#?[ \t]*"
                        r"[A-Za-z0-9-]{1,6}[ \t]*$"
                        r"|(?<![^\W\d_])(?:Suite|Ste|STE|SUITE|Apt|APT|Apartment)\.?[ \t]*\#?[ \t]*\d[\w-]{0,5}"
                        r"(?![\w])")
_POSTCODES = re.compile(r"(?<![A-Za-z0-9])(?:[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z][ ]?\d[ABCEGHJ-NPRSTV-Z]\d"
                        r"|(?:[A-Z]{1,2}\d[A-Z\d]?|GIR)[ ]\d[ABD-HJLNP-UW-Z]{2})(?![A-Za-z0-9])")
_IBAN = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]{2}\d{2}(?:[ ]?[A-Za-z0-9]{4}){2,7}(?:[ ]?[A-Za-z0-9]{1,3})?"
                   r"(?![A-Za-z0-9])")
_CARD = re.compile(r"(?<![\d.,$])(?:\d{4}([ -])\d{4}\1\d{4}\1\d{4}(?:\1\d{1,3})?|\d{4}([ -])\d{6}\2\d{5})"
                   rf"{_END}")
_LONG_NUMBER = re.compile(rf"(?<![\d.,$])\d{{11,19}}{_END}")

_APOSTROPHES = "\u2019\u2018\u02bc`\u00b4\u2032"
_SPECIAL_LETTERS = {"\u00f8": "o", "\u00d8": "O", "\u00df": "s", "\u00e6": "a", "\u00c6": "A", "\u0153": "o",
                    "\u0152": "O", "\u0111": "d", "\u0110": "D", "\u0142": "l", "\u0141": "L", "\u00fe": "t",
                    "\u00de": "T", "\u00f0": "d", "\u00d0": "D", "\u0131": "i"}


@lru_cache(maxsize=4096)
def _base(c: str) -> str:
    """One character with its accent taken off (o for o-umlaut), or ' for a curly apostrophe."""
    if c < "\x80":
        return c
    if c in _APOSTROPHES:
        return "'"
    if c in _SPECIAL_LETTERS:
        return _SPECIAL_LETTERS[c]
    plain = unicodedata.normalize("NFKD", c)[:1]
    return plain if plain.isascii() and plain.isalpha() else c


def _ascii(text: str) -> str:
    """``text`` with accents taken off, character for character, so offsets still line up."""
    return "".join(map(_base, text))


def _luhn(digits: str) -> bool:
    total = 0
    for i, c in enumerate(reversed(digits)):
        d = int(c) * (2 if i % 2 else 1)
        total += d - 9 if d > 9 else d
    return total % 10 == 0


def _iban_ok(text: str) -> bool:
    s = text.replace(" ", "").upper()
    return 15 <= len(s) <= 34 and int("".join(str(int(c, 36)) for c in s[4:] + s[:4])) % 97 == 1


def _fold(text: str) -> str:
    return " ".join(text.casefold().split())


def _name_words(text: str) -> list[str]:
    return re.findall(r"[^\W_]+(?:'[^\W_]+)*(?:-[^\W_]+)*", _ascii(text))


@dataclass
class _Tok:
    start: int
    end: int
    word: str
    fold: str
    case: str        # "title", "caps", "initial" (one capital letter) or "lower"
    dot: bool        # a period right after it


def _tokens(fold: str) -> list[_Tok]:
    toks = []
    for m in _TOKEN.finditer(fold):
        w = m.group()
        if len(w) == 1:
            case = "initial" if w.isupper() else "lower"
        else:
            case = "caps" if w.isupper() else "title" if w[0].isupper() else "lower"
        toks.append(_Tok(m.start(), m.end(), w, w.casefold(), case, fold[m.end():m.end() + 1] == "."))
    return toks


def _gap(fold: str, toks: list[_Tok], i: int) -> str:
    """What separates token ``i`` (and a period right after it) from the next."""
    if i + 1 >= len(toks):
        return "\n"
    return fold[toks[i].end + toks[i].dot:toks[i + 1].start]


def _business_after(fold: str, end: int, v: _Vocab, typed: bool = False) -> bool:
    """Whether the words right after ``end`` make what's before it a business's name: "... Capital",
    "..., L.P.", "... II, L.P.", "... Ridge Partners", "... & Co.".  In what the user types, a profile's
    member-interest word ("LLC") alone after a name is a member's interest ("add Jane Doe LLC")."""
    if _LEGAL_ENDING.match(fold, end):
        return True
    rest = fold[end:end + 80]
    for n, m in enumerate(_TOKEN.finditer(rest)):
        if n == 5 or re.search(r"[()\n:;]", rest[:m.start()]):
            return False
        word = m.group().casefold()
        if word in _PERSONAL:
            return False
        if word in v.business:
            return not (typed and n == 0 and word in v.member_interest and
                        re.match(r"[ \t]*(?:$|[.,;)]|and\b|members?\b|interest)", rest[m.end():], re.IGNORECASE))
        if word not in _ROMAN and word not in ("and", "of", "the") and not m.group()[0].isupper():
            return False
    return False


@dataclass
class _Person:
    key: str                  # NAME:<first last>: the placeholder's
    display: str              # what the placeholder is put back as
    first: str = ""
    middles: list[str] = field(default_factory=list)
    last: str = ""
    particles: list[str] = field(default_factory=list)   # "de la" of "de la Cruz"
    suffix: str = ""          # Jr., III ...
    whole: list[str] = field(default_factory=list)   # a business's, trust's or joint account's name, word by word
    bare: bool = False        # hide the surname alone too


@dataclass
class _Found:
    first_tok: int            # its first and last token
    last_tok: int
    key: str | None           # the placeholder's key; None to put it back as written
    display: str | None
    person: _Person | None    # to remember, so it's hidden wherever it appears from now on


@dataclass(frozen=True)
class _Vocab:
    """The word lists and patterns for one profile."""
    stop: frozenset[str]
    business: frozenset[str]
    not_surnames: frozenset[str]
    not_names: frozenset[str]
    cue: re.Pattern
    cue_ends: frozenset[str]
    after_cue: re.Pattern
    member_interest: frozenset[str]


@lru_cache(maxsize=32)
def _vocab(profile: Profile, kinds: frozenset[str]) -> _Vocab:
    stop = _STOP | profile.stop_words
    business = _BUSINESS | profile.business_words
    extra = "".join("|" + c for c in profile.cues)
    return _Vocab(
        stop=stop, business=business,
        not_surnames=stop | business | _HONORIFICS | kinds | _PERSONAL | _NAME_SUFFIXES,
        not_names=business | _PERSONAL | stop | _NAME_SUFFIXES,
        cue=re.compile(_CUE_PATTERN.replace("{extra}", extra)),
        cue_ends=_CUE_ENDS | profile.cue_ends,
        after_cue=re.compile(r"[ \t]*(?:" + "|".join(_AFTER_CUES + profile.after_cues) + ")"),
        member_interest=profile.member_interest_words)


class Redactor(TaxIdRedactor):
    """One conversation's placeholders for taxpayer IDs and personal information.

    ``profile``: the vocabulary of the documents it reads (``veil.profiles``); GENERIC by default.
    ``detect``: the kinds to look for (``KINDS``: "SSN", "NAME", "EMAIL" ...); all of them by default.
    Taxpayer IDs are looked for when any of "SSN", "EIN" or "TIN" is.
    ``patterns``: more to look for, as {kind: regex}, e.g. {"MRN": r"\\bMRN[- ]?\\d{6,8}\\b"}.  Each kind gets
    its own placeholders (MRN_001) and is looked for before the built-in ones.
    ``name_finder``: a function from text to the people's names in it, such as a wrapper around an NER model
    (spaCy, Presidio, a cloud service); each name it returns is added with ``add_person`` before the text is
    read.  The built-in name finding works from word lists, so it misses names it has no word for in prose
    that has no label or title before them ("CEO Satya Nadella").
    """

    def __init__(self, profile: Profile | None = None, detect=None, patterns=None, name_finder=None):
        super().__init__(profile)
        self._name_finder = name_finder
        self._detect = frozenset(KINDS if detect is None else detect)
        unknown = self._detect - set(KINDS)
        if unknown:
            raise ValueError(f"Unknown kinds to detect: {', '.join(sorted(unknown))}. Use some of {', '.join(KINDS)}.")
        self._custom: list[tuple[str, re.Pattern]] = []
        for kind, pattern in (patterns or {}).items():
            self.register_kind(kind)
            self._custom.append((kind, pattern if isinstance(pattern, re.Pattern) else re.compile(pattern)))
        self._people: dict[str, _Person] = {}
        self._patterns: list[tuple[re.Pattern, _Person | None]] | None = None
        self._businesses: set[tuple[str, ...]] = set()   # every run of two to five words of a fund's name
        self._kinds_changed()

    def _kinds_changed(self) -> None:
        self._v = _vocab(self.profile, frozenset(k.casefold() for k in self.kinds))

    # -- what the app knows ----------------------------------------------------

    def add_business(self, name: str) -> None:
        """A fund's or company's name: the words in it are never taken for a person's, so it stays."""
        words = [w.casefold() for w in _name_words(name or "")]
        for n in range(2, 6):
            self._businesses.update(tuple(words[i:i + n]) for i in range(len(words) - n + 1))

    def add_person(self, name: str) -> None:
        """Hide ``name`` (someone the app already knows of) from now on, however it's written:
        "Avery K. Mockridge", "MOCKRIDGE, AVERY K", "A. Mockridge", "Mr. Mockridge" ..."""
        name = " ".join(str(name or "").split())
        words = _name_words(name)
        if len(name) < 3 or not any(len(w) > 1 and not w.isdigit() for w in words) or \
                all(w.casefold() in self._v.not_names or w.isdigit() for w in words):
            return
        plain = [w for w in words if w.casefold() not in _NAME_SUFFIXES]
        if any(w.casefold() in self._v.business or w.casefold() in _PERSONAL for w in words) or \
                re.search(r"&|\band\b|/|\+", name, re.IGNORECASE) or len(plain) > 5:
            self._remember(_Person("NAME:" + " ".join(w.casefold() for w in words), name, whole=words))
            if any(w.casefold() in _PERSONAL for w in words) or re.search(r"&|\band\b|/|\+", name, re.IGNORECASE):
                parts = [_name_words(p) for p in re.split(r"&|\band\b|/|\+", name, flags=re.IGNORECASE)]
                for k, part in enumerate(parts):
                    self._people_in(part, parts[k + 1] if k + 1 < len(parts) else [])
            return
        suffix = next((w for w in words if w.casefold() in _NAME_SUFFIXES), "")
        if "," in name:   # "Mockridge, Avery K."
            last, _, rest = name.partition(",")
            plain = [w for w in _name_words(rest) + _name_words(last) if w.casefold() not in _NAME_SUFFIXES]
        if len(plain) == 1:
            self._remember(_Person(f"NAME:{plain[0].casefold()}", name, last=plain[0], bare=True))
        elif plain:
            self._remember(self._person(plain, name, suffix=suffix, bare=True))

    @staticmethod
    def _person(words: list[str], display: str, suffix: str = "", bare: bool = False) -> _Person:
        first, *middles, last = words
        particles = []
        while middles and middles[-1].casefold() in _PARTICLES:   # "Maria Jose de la Cruz"
            particles.insert(0, middles.pop())
        return _Person(f"NAME:{first.casefold()} {last.casefold()}", display, first, middles, last, particles,
                       suffix, bare=bare)

    def _people_in(self, words: list[str], next_part: list[str]) -> None:
        """The people in a trust's or joint account's name: "Avery Mockridge Revocable Trust",
        "Pershing LLC FBO Avery Mockridge IRA", "John & Jane Doe JTWROS", "Mockridge Family Trust"."""
        def breaks(w: str) -> bool:
            f = w.casefold()
            return f in self._v.business or f in _PERSONAL or f in self._v.stop or f in _NAME_SUFFIXES or f in ("c", "o") or \
                any(c.isdigit() for c in w)

        runs, i = [], 0
        while i < len(words):
            if breaks(words[i]):
                i += 1
                continue
            j = i
            while j < len(words) and not breaks(words[j]):
                j += 1
            runs.append((i, j))
            i = j
        for a, b in runs:
            run, after = words[a:b], words[b].casefold() if b < len(words) else ""
            if after in self._v.business:   # "Pershing" of "Pershing LLC FBO ..."
                continue
            if len(run) >= 2:
                self._remember(self._person(run, " ".join(run), bare=True))
            elif len(words) == 1 and next_part:   # "John" of "John & Jane Doe"
                plain = [w for w in next_part if not breaks(w)]
                if len(plain) >= 2:
                    self._remember(self._person([run[0], plain[-1]], f"{run[0]} {plain[-1]}"))
            elif len(run[0]) > 2:
                self._remember(_Person(f"NAME:{run[0].casefold()}", run[0], last=run[0], bare=True))

    def _remember(self, person: _Person) -> None:
        known = self._people.get(person.key)
        if known is not None and (known.bare or not person.bare) and (known.whole or not person.whole):
            return
        if known is not None:   # put back as it first was
            person.display = known.display
        self._people[person.key] = person
        self._patterns = None

    def _surnames(self) -> set[str]:
        """The surnames of the people known and found so far that are no ordinary word."""
        return {p.last.casefold() for p in self._people.values()
                if p.last and (p.first or p.bare) and p.last.casefold() not in _WORD_SURNAMES | self._v.not_surnames}

    def _compiled(self) -> list[tuple[re.Pattern, _Person | None]]:
        """Each known person's ways of being written; a None person is put back as written."""
        if self._patterns is not None:
            return self._patterns
        gap = r"(?:[ \t_-]+|[ \t]*\n[ \t]*|[ \t]*[.][ \t]*|(?-i:(?<=[a-z])(?=[A-Z])))"
        surnames: dict[str, int] = {}
        for p in self._people.values():
            if p.last and p.first:
                surnames[p.last.casefold()] = surnames.get(p.last.casefold(), 0) + 1

        def word(w: str) -> str:
            return r"[-\s]?".join(re.escape(part) for part in w.split("-")).replace("'", r"['\s]?")

        patterns: list[tuple[re.Pattern, _Person | None]] = []
        alone: list[tuple[re.Pattern, _Person | None]] = []
        for p in sorted(self._people.values(), key=lambda p: -len(p.display)):
            forms = []
            if p.whole:
                forms.append(r"[\W_]{1,4}".join(word(w) for w in p.whole) +
                             (r"\." if p.display.endswith(".") else ""))
            if p.first and p.last:
                # a middle name: one it knows, an initial, or any capitalized word
                middle = "|".join([word(m) for m in p.middles] + [r"[^\W\d_]", r"(?-i:[A-Z][A-Za-z'-]+)"])
                first = word(p.first)
                last = "".join(rf"(?:{word(x)}{gap})?" for x in p.particles) + word(p.last)
                suffix = rf"(?:,?[ \t]+{word(p.suffix)}\.?)?" if p.suffix else ""
                forms += [rf"{first}(?:{gap}(?:{middle})\.?){{0,2}}{gap}{last}{suffix}",
                          rf"{last}{suffix}[ \t]*,?{gap}{first}(?:{gap}(?:{middle})(?![^\W\d_])\.?){{0,2}}"]
                if surnames.get(p.last.casefold()) == 1:   # A. Mockridge: a capital, so not "a Smith family"
                    forms.append(rf"(?-i:{re.escape(p.first[0].upper())})\.?{gap}(?:(?-i:[A-Z])\.?{gap})?"
                                 rf"{last}{suffix}")
            if forms:
                patterns.append((re.compile(rf"(?<![^\W\d_])(?:{'|'.join(forms)})(?![^\W\d_])", re.IGNORECASE), p))
            if p.last and len(p.last) > 2 and p.last.casefold() not in self._v.stop:
                # Mr. Mockridge; and Mockridge alone, when that's no ordinary word.  Put back as written.
                optional = "?" if p.bare and p.last.casefold() not in _GIVEN | _WORD_SURNAMES else ""
                particles = "".join(rf"(?:{word(x)}[ \t]+)?" for x in p.particles)
                alone.append((re.compile(rf"(?<![^\W\d_])(?:(?:{'|'.join(_HONORIFICS)})\.?[ \t]+){optional}"
                                         rf"{particles}{word(p.last)}(?![^\W\d_])", re.IGNORECASE), None))
            first = p.first.casefold()
            if p.first and p.bare and len(first) > 3 and first not in _GIVEN | _WORD_SURNAMES | self._v.not_names:
                # Thandiwe alone: a first name that's no common one or ordinary word
                alone.append((re.compile(rf"(?<![^\W\d_]){word(p.first)}(?![^\W\d_])", re.IGNORECASE), None))
        self._patterns = patterns + alone
        return self._patterns

    # -- finding it ------------------------------------------------------------

    def redact_text(self, text: str, typed: bool = False) -> str:
        """``text`` with taxpayer IDs and personal information replaced.  ``typed``: the user typed it, so any
        two or three capitalized words (that aren't the profile's words, or a business's) are taken for
        a name, and so are a common first name and surname in lower case."""
        if self._name_finder is not None and "NAME" in self._detect and text and not text.isspace():
            for name in self._name_finder(text) or ():
                self.add_person(name)
        text = self._redact_personal(self._prepare(text), typed)
        return self._redact_ids(text) if self._detect & set(TAX_ID_KINDS) else text

    def redact(self, value, typed: bool = False):
        if not typed:
            return super().redact(value)
        self._walk(value, lambda text: self.redact_text(text, True))
        return self._walk(value, lambda text: self.redact_text(text, True))

    def _redact_personal(self, text: str, typed: bool = False) -> str:
        if not text or text.isspace():
            return text
        copy, starts, ends = _shadow(text)
        if not copy:
            return text
        fold = _ascii(copy)
        covered = bytearray(len(copy))
        for start, end in self._placeholder_spans(copy):
            covered[start:end] = b"\x01" * (end - start)
        found: list[tuple[int, int, str, str, str | None]] = []   # start, end, kind, key, put back as

        def take(start: int, end: int, kind: str, key: str | None = None, real: str | None = None) -> bool:
            if start >= end or any(covered[start:end]) or (kind in KINDS and kind not in self._detect):
                return False
            covered[start:end] = b"\x01" * (end - start)
            found.append((start, end, kind, key or f"{kind}:{_fold(copy[start:end])}", real))
            return True

        def scan(pattern: re.Pattern, on, source: str = copy) -> None:
            """Each match of ``pattern``; where ``on(match)`` takes nothing, it looks again a character on."""
            pos = 0
            while (m := pattern.search(source, pos)) is not None:
                pos = m.end() if on(m) else m.start() + 1

        for kind, pattern in self._custom:
            scan(pattern, lambda m, kind=kind: take(m.start(), m.end(), kind))
        scan(_EMAIL, lambda m: take(m.start(), m.end(), "EMAIL"))
        scan(_LABELLED, lambda m: self._labelled(m, take, fold))
        scan(_IBAN, lambda m: _iban_ok(m.group()) and (m.group().isupper() or sum(c.isdigit() for c in m.group()) >= 8)
             and
             take(m.start(), m.end(), "ACCOUNT", "ACCOUNT:" + m.group().replace(" ", "").upper()))
        scan(_CARD, lambda m: (m.group(1) == "-" or _luhn(re.sub(r"\D", "", m.group()))) and
             take(m.start(), m.end(), "ACCOUNT", "ACCOUNT:" + re.sub(r"\D", "", m.group())))
        for pattern in _PHONES + (_TYPED_PHONES if typed else []):
            scan(pattern, lambda m: self._phone(m, take))
        scan(_ADDRESS_LABEL, lambda m: take(m.start("value"), m.end("value"), "ADDRESS"))
        scan(_STREET, lambda m: not _business_after(fold, m.end(), self._v) and take(m.start(), m.end(), "ADDRESS"))
        scan(_BOXES, lambda m: take(m.start(), m.end(), "ADDRESS"))
        scan(_CITY_STATE_ZIP, lambda m: not set(_fold(m.group("city")).split()) & _NOT_CITY and
             take(m.start(), m.end(), "ADDRESS"))
        if typed:
            scan(_TYPED_CITY_STATE_ZIP, lambda m: not set(_fold(m.group("city")).split()) & _NOT_CITY and
                 take(m.start(), m.end(), "ADDRESS"))
        for pattern in (_UNIT_LINE, _POSTCODES, _FOREIGN):
            scan(pattern, lambda m: take(m.start(), m.end(), "ADDRESS"))
        known = len(self._people)
        for _ in range(2 if "NAME" in self._detect else 0):   # names found in this text are hidden wherever else it says them
            self._known_names(fold, take, typed)
            self._found_names(copy, fold, take, typed)
            if len(self._people) == known:
                break
            known = len(self._people)
        scan(_LONG_NUMBER, lambda m: take(m.start(), m.end(),
                                          *(("ACCOUNT", f"ACCOUNT:{m.group()}") if len(m.group()) >= 13 and
                                            _luhn(m.group()) else ("ID", f"ID:{m.group()}"))))
        if not found:
            return text
        # Numbered in reading order, replaced from the end so the offsets hold.
        placed = []
        for start, end, kind, key, real in sorted(found):
            source_start, source_end = starts[start], ends[end - 1]
            placed.append((source_start, source_end,
                           self._placeholder(kind, key, real or text[source_start:source_end], False)))
        for source_start, source_end, placeholder in reversed(placed):
            text = text[:source_start] + placeholder + text[source_end:]
        return text

    @staticmethod
    def _phone(m: re.Match, take) -> bool:
        start = m.start("value") if "value" in m.re.groupindex else m.start()
        digits = re.sub(r"\D", "", m.group()[start - m.start():])
        return 9 <= len(digits) <= 22 and take(start, m.end(), "PHONE", "PHONE:" + digits)

    @staticmethod
    def _labelled(m: re.Match, take, fold: str) -> bool:
        value, start = m.group("value"), m.start("value")
        if m.group("dob"):
            return take(start, start + len(value), "DOB")
        if m.group("swift"):   # all capitals, or with a digit: "SWIFT transfer" isn't one
            return (value.isupper() or any(c.isdigit() for c in value)) and \
                take(start, start + len(value), "ACCOUNT", "ACCOUNT:" + value.upper())
        # The number, and nothing after it: "12345678 at Routing number ..." is 12345678.  One short
        # capitalized word may come first ("FBO 12345678"); "of units 12345" is no account number.
        groups = value.split(" ")
        if not re.search(r"[\d*\u2022]", groups[0]):
            if len(groups) < 2 or not (groups[0].isupper() and len(groups[0]) <= 4) or \
                    not re.search(r"[\d*\u2022]", groups[1]):
                return False
            start += len(groups[0]) + 1
            groups = groups[1:]
        kept = []
        for group in groups:
            if not re.search(r"[\d*\u2022]", group):
                break
            kept.append(group)
        groups = kept
        value = " ".join(groups)
        digits = sum(c.isdigit() for c in value)
        need = 6 if m.group("bare") else 4 if m.group("account") else 3
        if digits >= 2 and digits + sum(c in "*\u2022Xx" for c in value) >= need:
            kind = "ID" if m.group("id") else "ACCOUNT"
            return take(start, start + len(value), kind, f"{kind}:{re.sub(r'[^0-9A-Za-z]', '', value).upper()}")
        return False

    def _known_names(self, fold: str, take, typed: bool) -> None:
        for pattern, person in self._compiled():
            pos = 0
            while (m := pattern.search(fold, pos)) is not None:
                pos = m.end()
                if person is not None:
                    if not person.whole and _business_after(fold, m.end(), self._v, typed):
                        take(m.start(), m.end(), "NAME")   # "Avery Mockridge Holdings": put back as written
                    else:
                        take(m.start(), m.end(), "NAME", person.key, person.display)
                    continue
                # "Mr. Mockridge", or "Mockridge" alone: put back as written.  Not in a business's name
                # ("Summit Partners"), and not after another name ("Kwame Okonkwo"), which the found names take.
                written = m.group()
                if _business_after(fold, m.end(), self._v, typed):
                    continue
                if not re.match(r"(?i:" + "|".join(_HONORIFICS) + r")\b", written):
                    before = re.search(r"([^\W\d_]+)[ \t]+\Z", fold[max(0, m.start() - 40):m.start()])
                    if before and before.group(1)[0].isupper() and before.group(1).casefold() not in self._v.not_names:
                        continue
                    if not written[0].isupper() and (len(written) < 4 or written.casefold() in _WORD_SURNAMES):
                        continue
                take(m.start(), m.end(), "NAME")

    # -- names it finds --------------------------------------------------------

    def _found_names(self, copy: str, fold: str, take, typed: bool) -> None:
        toks = _tokens(fold)
        surnames = self._surnames()
        # listed: the token after a name and ", " or " and ", where another may start; it counts as after a
        # label when the name before it was found by one.
        i, listed, listed_cued = 0, -1, False
        while i < len(toks):
            cued = (i == listed and listed_cued) or (i > 0 and toks[i - 1].fold in self._v.cue_ends and
                                                       self._v.cue.search(fold, max(0, toks[i].start - 60), toks[i].start))
            found = self._name_at(copy, fold, toks, i, cued, typed, surnames)
            if found is None:
                i += 1
                continue
            start, stop = toks[found.first_tok].start, toks[found.last_tok].end
            if toks[found.last_tok].case == "initial" and toks[found.last_tok].dot:
                stop += 1
            if take(start, stop, "NAME", found.key, found.display) and found.person is not None:
                self._remember(found.person)
                surnames = self._surnames()
                self._shared_surname(copy, fold, toks, found, take)
            end = found.last_tok
            after = end + 2 if end + 2 < len(toks) and toks[end + 1].fold == "and" else end + 1
            gap = fold[toks[end].end + toks[end].dot:toks[after].start] if after < len(toks) else ""
            listed, listed_cued = (after if _LIST_GAP.fullmatch(gap) else -1), found.person is not None
            i = end + 1

    @staticmethod
    def _shared_surname(copy: str, fold: str, toks: list[_Tok], found: _Found, take) -> None:
        """The first name before "& Jane Doe" or "and Jane Doe": John of "John & Jane Doe"."""
        f = found.first_tok
        if found.person is None or not found.person.first or f == 0:
            return
        q = None
        if re.fullmatch(r"[ \t]*&[ \t]*", fold[toks[f - 1].end:toks[f].start]):
            q = f - 1
        elif f >= 2 and toks[f - 1].fold == "and" and re.fullmatch(r"[ \t]+", fold[toks[f - 2].end:toks[f - 1].start]):
            q = f - 2
        if q is not None and toks[q].fold in _GIVEN and toks[q].case in ("title", "caps") and not toks[q].dot:
            last = toks[found.last_tok]
            take(toks[q].start, toks[q].end, "NAME", f"NAME:{toks[q].fold} {last.fold}",
                 f"{copy[toks[q].start:toks[q].end]} {copy[last.start:last.end]}")

    def _name_at(self, copy: str, fold: str, toks: list[_Tok], i: int, cued: bool, typed: bool,
                 surnames: set[str]) -> _Found | None:
        """The name starting at token ``i``, if there is one."""
        t = toks[i]

        def w(k: int) -> str:   # token k as written, accents and all
            return copy[toks[k].start:toks[k].end]

        def near(a: int) -> bool:
            if a + 1 >= len(toks):
                return False
            gap = _gap(fold, toks, a)
            return _NAME_GAP.fullmatch(gap) is not None or (gap == "" and toks[a].case == "initial" and toks[a].dot)

        def name_word(j: int, case: str | None = None) -> bool:
            s = toks[j]
            return (s.case == case if case else s.case in ("title", "caps")) and len(s.word) > 1 and \
                s.fold not in self._v.not_surnames

        def rest(j: int, case: str, mixed: bool, test, longer: bool):
            """After a first name at token j - 1: middles (initials or names) and particles, then a surname
            that passes ``test``; ``longer``: any more names after it ("Juan Carlos Garcia Lopez")."""
            def fits(k: int) -> bool:
                return name_word(k, None if mixed else case) and test(k)

            ends = []
            k = j
            for _ in range(3):
                while k + 1 < len(toks) and toks[k].fold in _PARTICLES and near(k):
                    k += 1
                if k >= len(toks):
                    break
                # a surname may end a sentence ("Dr. Ahmed Khan."); an initial with a period is a middle
                if fits(k) and (not toks[k].dot or (toks[k].case != "initial" and len(toks[k].word) > 2)):
                    ends.append(k)
                if not (toks[k].case == "initial" or name_word(k, None if mixed else case)) or not near(k):
                    break
                k += 1
            if not ends:
                return None
            end = ends[-1] if longer else ends[0]
            return [toks[m].word for m in range(j, end) if toks[m].fold not in _PARTICLES], end

        def ok(a: int, b: int) -> bool:
            words = [toks[k].fold for k in range(a, b + 1)]
            if any(f"{x} {y}" in _FIRMS for x, y in zip(words, words[1:])) or tuple(words) in self._businesses:
                return False
            return not _business_after(fold, toks[b].end + (1 if toks[b].dot and toks[b].case == "initial" else 0),
                                       self._v, typed)

        def found(a: int, b: int, first: str, middles: list[str], last: str, remember: bool,
                  display: str | None = None) -> _Found:
            key = f"NAME:{first.casefold()} {last.casefold()}"
            display = display or copy[toks[a].start:toks[b].end]
            return _Found(a, b, key, display,
                          _Person(key, display, first, middles, last, bare=True) if remember else None)

        # Dr. Avery Mockridge: the name, the title left as it is.  Mr. Mockridge: both.
        if t.fold in _HONORIFICS and t.case in ("title", "caps") and near(i):
            j = i + 1
            if toks[j].case == "initial" and near(j):
                j += 1
            if j < len(toks) and name_word(j):
                more = rest(j + 1, toks[j].case, True, lambda k: True, True) if near(j) else None
                if more and ok(j, more[1]):
                    return found(j, more[1], toks[j].word, more[0], toks[more[1]].word, True)
                if ok(j, j):
                    return _Found(i, j, None, None, None)
            return None
        # The Okonkwo Family Trust; Thandiwe Okonkwo Revocable Trust; Dummerton Retirement Trust; ... IRA
        j = i
        while j - i < 4 and j + 1 < len(toks) and (name_word(j) or (j > i and toks[j].case == "initial")) and \
                not (toks[j].dot and toks[j].case != "initial") and near(j):
            nxt = toks[j + 1]
            if nxt.fold in _FAMILY or nxt.fold == "ira" or (nxt.fold in ("family", "retirement") and j + 2 < len(toks)
                                                             and toks[j + 2].fold in ("trust", "foundation", "plan")):
                if j > i:
                    return found(i, j, t.word, [toks[m].word for m in range(i + 1, j)], toks[j].word, True)
                if t.fold not in _GIVEN:
                    return _Found(i, i, None, None, _Person(f"NAME:{t.fold}", w(i), last=t.word, bare=True))
                break
            j += 1
        if t.case == "lower":
            # In what the user types: jane smith, or anyone "as a member"
            if typed and near(i) and t.fold in _GIVEN and toks[i + 1].case == "lower" and toks[i + 1].fold in \
                    _SURNAMES and not toks[i + 1].dot:
                return found(i, i + 1, t.word, [], toks[i + 1].word, True)
            if typed and near(i) and t.fold not in self._v.not_names and toks[i + 1].case == "lower" and \
                    toks[i + 1].fold not in self._v.not_names and len(t.word) > 1 and len(toks[i + 1].word) > 1 and \
                    self._v.after_cue.match(fold, toks[i + 1].end) and \
                    (i == 0 or toks[i - 1].fold in ("add", "adding", "added", "make", "and", "include", "with")):
                return found(i, i + 1, t.word, [], toks[i + 1].word, True)
            return None
        if t.fold in self._v.not_surnames or (t.dot and t.case != "initial"):
            return None
        if t.case == "initial":
            # J. Ezekiel Thornbury, after a label or in what the user types
            if (cued or typed) and near(i):
                more = rest(i + 1, "title", True, lambda k: True, True)
                if more and ok(i, more[1]):
                    return found(i, more[1], t.word, more[0], toks[more[1]].word, True)
            return None
        if near(i):
            def named(more, remember: bool) -> _Found | None:
                if more and ok(i, more[1]):
                    return found(i, more[1], t.word, more[0], toks[more[1]].word, remember)
                return None

            # Avery K. Mockridge: a common first name
            if t.fold in _GIVEN or t.fold.split("-")[0] in _GIVEN:
                if (name := named(rest(i + 1, t.case, True, lambda k: True, True), True)) is not None:
                    return name
            # Priya Patel; Thandiwe Okonkwo once an Okonkwo is known: a common or known surname
            name = named(rest(i + 1, t.case, True, lambda k: toks[k].fold in _SURNAMES or toks[k].fold in surnames,
                              True), True)
            if name is not None:
                return name
            # After a label or cue, before "as an LLC member", or in what the user typed: any capitalized words
            if t.case == "title" or cued or typed:
                more = rest(i + 1, t.case, False, lambda k: True, True)
                after = more is not None and self._v.after_cue.match(fold, toks[more[1]].end) is not None
                # "Calder Ridge II": a fund, numbered
                numbered = more is not None and more[1] + 1 < len(toks) and near(more[1]) and \
                    toks[more[1] + 1].fold in _ROMAN and toks[more[1] + 1].case in ("caps", "initial") and \
                    not any(toks[k].case == "initial" for k in range(i + 1, more[1]))
                if (cued or after or (typed and t.case == "title")) and not numbered:
                    if (name := named(more, cued or after)) is not None:
                        return name
            # Zhang Wei, TANAKA HIROSHI: a common surname, then a first name
            n = toks[i + 1]
            if t.fold in _SURNAMES and n.fold in _GIVEN and n.case in ("title", "caps") and not n.dot:
                end = i + 2 if i + 2 < len(toks) and near(i + 1) and toks[i + 2].fold in _GIVEN and \
                    toks[i + 2].case == n.case else i + 1
                if ok(i, end):
                    return found(i, end, n.word, [toks[k].word for k in range(i + 2, end + 1)], t.word, True,
                                 " ".join([w(k) for k in range(i + 1, end + 1)] + [w(i)]))
        # Mockridge, Avery K.
        if i + 1 < len(toks) and _COMMA_GAP.fullmatch(_gap(fold, toks, i)) and name_word(i):
            n = toks[i + 1]
            if name_word(i + 1) and not n.dot and \
                    (n.fold in _GIVEN or t.fold in _SURNAMES or t.fold in surnames or cued or typed):
                end, middles = i + 1, []
                while end + 1 < len(toks) and near(end) and (toks[end + 1].case == "initial" or
                                                             name_word(end + 1, n.case)) and len(middles) < 2:
                    end += 1
                    middles.append(w(end) + ("." if toks[end].case == "initial" else ""))
                if ok(i, end):
                    return found(i, end, n.word, middles, t.word, not typed or n.fold in _GIVEN,
                                 " ".join([w(i + 1), *middles, w(i)]))
        return None


# The name it had in Snowman.
PersonalInfoRedactor = Redactor
