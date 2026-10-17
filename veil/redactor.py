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

import gzip
import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources

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


@lru_cache(maxsize=None)
def _name_list(name: str) -> dict[str, float]:
    """A packaged list of names (``veil/data``), each with how common it is as an English word (a Zipf
    frequency: 0 for no word at all, 3 for a word used about once in a million)."""
    with resources.files("veil").joinpath(f"data/{name}.txt.gz").open("rb") as raw, \
            gzip.open(raw, "rt", encoding="utf-8") as f:
        return {w: float(z) for w, z, *_ in (line.rstrip("\n").split("\t") for line in f if not line.startswith("#"))}


@lru_cache(maxsize=None)
def _dictionary_names(name: str) -> frozenset[str]:
    """The names on a packaged list that are dictionary words too ("rose", "stale")."""
    with resources.files("veil").joinpath(f"data/{name}.txt.gz").open("rb") as raw, \
            gzip.open(raw, "rt", encoding="utf-8") as f:
        return frozenset(parts[0] for parts in (line.rstrip("\n").split("\t") for line in f if not line.startswith("#"))
                         if len(parts) > 2 and parts[2] == "1")


def _wordlike(word: str) -> bool:
    """Whether a listed name is also a word, or a place, or common enough in English to be one ("Stale",
    "Virginia")."""
    return word in _dictionary_names("given_names") or word in _dictionary_names("surnames") or \
        word in _PLACE_NAMES or max(_given_names().get(word, 0), _surname_list().get(word, 0)) >= 4.5


def _given_names() -> dict[str, float]:
    """First names from Wikidata, from every country, that are no common English word."""
    return _name_list("given_names")


def _surname_list() -> dict[str, float]:
    """Surnames from Wikidata and the 2010 US Census that are no common English word."""
    return _name_list("surnames")


@lru_cache(maxsize=None)
def _common_words() -> frozenset[str]:
    """English words in everyday use ("crude", "owner", "oil"): no sign of a name by themselves."""
    with resources.files("veil").joinpath("data/common_words.txt.gz").open("rb") as raw, \
            gzip.open(raw, "rt", encoding="utf-8") as f:
        return frozenset(line.strip() for line in f if not line.startswith("#"))


@lru_cache(maxsize=None)
def _common_surnames() -> frozenset[str]:
    """Surnames common in the US that are everyday words too: Young, King, Doe."""
    with resources.files("veil").joinpath("data/common_surnames.txt.gz").open("rb") as raw, \
            gzip.open(raw, "rt", encoding="utf-8") as f:
        return frozenset(line.strip() for line in f if not line.startswith("#"))


def _name_listed(word: str, known: set[str]) -> bool:
    """Whether ``word`` (folded) is on a list of names, or a name already known.  Of the surnames that are
    everyday words, only those listed here count ("Young", not "Driver")."""
    return word in _GIVEN or word in _SURNAMES or word in known or word in _WORD_SURNAMES or word in _WORD_GIVEN or \
        word in _given_names() or word in _surname_list()


@lru_cache(maxsize=None)
def _top_surnames() -> frozenset[str]:
    """The 1,000 commonest US surnames, everyday words or not: Carter, Wood, Mills."""
    with resources.files("veil").joinpath("data/top_surnames.txt.gz").open("rb") as raw, \
            gzip.open(raw, "rt", encoding="utf-8") as f:
        return frozenset(line.strip() for line in f if not line.startswith("#"))


def _surname_like(word: str, known: set[str]) -> bool:
    """Whether ``word`` (folded) can be a surname: one listed or known, or no everyday English word."""
    first = word.split("-")[0]
    return word in _SURNAMES or word in _WORD_SURNAMES or word in known or first in _surname_list() or \
        first in _common_surnames() or word not in _common_words()


# First names that are everyday words too: a name only before a surname ("Mark Tiffany Fuentes", "Will Smith").
_WORD_GIVEN = _words("mark will grant june may rose faith hope joy dawn april summer autumn bill bob pat sue ray earl "
                     "dean frank rich sky iris ivy holly daisy pearl ruby amber crystal destiny honor lily jade "
                     "valentine grace robin hazel olive heather violet ginger sandy gene guy art lee don glen angel penny "
                     "brandy max faye flora wade homer rex earnest jewel laurel aurora candy merle clay toby charity "
                     "heath sterling rocky gale dolly dee chuck chase august rod eve rusty cliff ward reed cole basil "
                     "mack saul ed al geneva devon marshall burton maxwell coral nova pier luna")
# Words a first name alone may follow: "Hello Sarah", "Thanks Kai".
_GREETINGS = _words("hello hi hey dear thanks thank welcome congratulations congrats goodbye bye morning afternoon "
                    "evening sorry yes no ok okay great cheers")
# First names that are places too: never taken for a name alone.
_PLACE_NAMES = _words("""
austin dallas houston orlando jordan sydney florence victoria georgia carolina madison lincoln hudson charlotte
savannah phoenix denver aurora chester camden brooklyn paris london berlin vienna china india israel kenya
chad cuba lima regina adelaide alexandria augusta beverly cleveland dakota douglas eugene hamilton helena
jackson laramie lansing lorain marion montgomery nelson orange quincy raleigh salem sharon tyler warren
wellington york
""")
_PLACES = _PLACE_NAMES | word_file("places")
_HONORIFICS = _words("mr mrs ms miss mx dr prof sir dame agent captain capt officer detective inspector sergeant "
                     "sgt lieutenant lt judge coach nurse pastor rev reverend rabbi imam professor mister mistress "
                     "madam madame mayor mayoress monsieur mademoiselle herr frau senor senora signor signora")
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
    r"|(?<!bank\s)(?<!fund\s)(?<!firm\s)(?<!file\s)(?<!user\s)(?<!company\s)(?<!entity\s)(?<!business\s)"
    r"(?<!product\s)(?<!chemical\s)(?<!substance\s)(?<!instrument\s)(?<!item\s)(?<!brand\s)(?<!project\s)(?<!event\s)(?<!venue\s)(?<!vessel\s)(?<!ship\s)(?<!plan\s)(?<!program\s)(?<!course\s)(?<!trade\s)(?<!model\s)(?<!device\s)(?<!drug\s)(?<!medication\s)(?<!domain\s)(?<!host\s)(?<!server\s)(?<!street\s)(?<!city\s)(?<!country\s)(?<!state\s)(?<!branch\s)(?<!team\s)(?<!campaign\s)name(?:(?:(?<=my\sname)|(?<=last\sname)|(?<=first\sname)|(?<=full\sname)|(?<=surname))[ \t]+is)?"
    r"|zip\s+code|signatory|signature|regards|sincerely|cordially|respectfully|(?<![^\n>])best(?=,)|cheers(?=,)"
    r"|(?:beneficial\s+)?owner|(?:account\s+)?holder|executor|executrix|administrator|guardian|conservator"
    r"|(?:partnership\s+)?representative|(?:designated|named)\s+individual|attorney(?:-in-fact)?|poa)"
    r"[ \t]*(?:\*{1,2}[ \t]*)?(?:[:.,-][ \t]*)?(?:\*{1,2}[ \t]*)?(?:\n[ \t]*){0,2}"
    r"|(?:named|members?|partners?|limited\s+partner|general\s+partner|investor|shareholder|stockholder"
    r"|beneficiary|trustee|custodian|grantor|spouse|client|contact(?:\s+person)?|attn|attention|dear|fbo|c/o"
    r"|for\s+the\s+benefit\s+of|(?:prepared|issued|mailed|sent|registered)\s+(?:for|to)|prepared\s+by"
    r"|registration|signed|i'm|i[ \t]+am|this[ \t]+is{extra})"
    r"(?:'s)?[ \t]*(?:[:.,-][ \t]*)?(?:/s/[ \t]*)?(?:(?<=:)(?:\n[ \t]*){1,2})?"
    r"|(?:by|to|from|re|cc|bcc)[ \t]*:[ \t]*(?:/s/[ \t]*)?(?:\n[ \t]*)?"
    # a party's role, then a colon: "Shipper: Tassilo M. Hess", "Borrower: Pedro"
    r"|(?:shipper|consignee|notify\s+party|payer|payee|remitter|applicant|co-?applicant|borrower|co-?borrower"
    r"|guarantor|insured|policy\s*holder|patient|purchaser|buyer|seller|vendor|lessee|lessor|tenant|landlord"
    r"|employee|customer|claimant|sender|recipient|debtor|creditor|witness|physician|doctor|assigned\s+to"
    r"|created\s+by|modified\s+by|reported\s+by|approved\s+by|reviewed\s+by|requested\s+by|user|agent)"
    r"(?:'s)?[ \t]*:[ \t]*(?:\*\*[ \t]*)?(?:\n[ \t]*){0,2})\Z")
# The last word of each of those: the label is looked for only after one of them.
_CUE_ENDS = _words("""
name is i'm am best cheers code signatory signature regards sincerely cordially respectfully owner holder executor executrix administrator
guardian conservator representative individual attorney attorney-in-fact poa named member members partner partners
investor shareholder stockholder beneficiary trustee custodian grantor spouse client contact person attn attention
dear fbo o of for to registration signed by from re cc bcc s
shipper consignee party payer payee remitter applicant co-applicant coapplicant borrower co-borrower coborrower
guarantor insured holder policyholder patient purchaser buyer seller vendor lessee lessor tenant landlord employee
customer claimant sender recipient debtor creditor witness physician doctor user agent
""")
# After a name, in what the user types: what says it's a person's (a profile adds its own).
_AFTER_CUES = (r",?[ \t]+(?i:ttee|trustee|custodian|cust|executor|executrix)\b",
               # "Leone Toselli, an individual", "Carolyn S. Day, residing at", "Jane Doe (Spouse)"
               r",[ \t]+(?i:an[ \t]+individual|who[ \t]+resides|resident[ \t]+of|born[ \t]+on)\b",
               r",?[ \t]+(?i:residing|who[ \t]+lives)[ \t]+at\b",
               r"[ \t]+\((?i:spouse|husband|wife|son|daughter|child|mother|father|parent|sibling|brother|sister)\)")

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
                    rf"(?:{_DOT}{_TLD}(?:\.[a-z]{{2}})?|\.[a-z]{{3,12}})(?![\w-])", re.IGNORECASE)
# Spelled out ("jane at example dot com"), the domain must end in a known suffix.
_SPELLED_EMAIL = re.compile(rf"(?:[\w%+-]|\.(?=[\w%+\[(-])|[ \t]+\.[ \t]+(?=\w)|[\[(]dot[\])])+{_AT}[\w-]+"
                            rf"(?:{_DOT}[\w-]+)*?{_DOT}{_TLD}", re.IGNORECASE)
_NO = r"(?:no\b\.?|number|num\b\.?|nr\b\.?|\#)"
_ACCOUNT_LABEL = (
    r"(?:(?:bank|brokerage|checking|savings|investment|custody|custodial|custodian|beneficiary|wire|deposit|ira|dda"
    rf"|credit|sub-?)[ \t]*(?:account|acct\b\.?|a/c)(?:\s*{_NO})?"
    rf"|(?:account|acct\b\.?|a/c)\s*(?:{_NO}|ending(?:\s+in)?)"
    rf"|(?:for\s+(?:further\s+)?credit(?:\s+to)?|ffc|further\s+credit)(?:\s+(?:account|acct\b\.?|a/c))?(?:\s*{_NO})?"
    rf"|routing(?:\s*/?\s*transit)?(?:\s*{_NO})?|aba(?:\s*routing)?(?:\s*{_NO})?"
    rf"|rtn|iban|bban|(?:credit|debit)\s*card(?:\s*{_NO})?|card\s*{_NO}"
    r"|(?:visa|mastercard|amex|american\s+express|discover|card)\s+ending(?:\s+in)?)"
    # "Account Number (last 4): 4321"
    r"(?:[ \t]*\([^()\n]{0,40}\))?")
# "account", "acct" or "a/c" alone: a number needs six digits after it, and a capital account is no account.
_BARE_ACCOUNT = r"(?<!capital\s)(?<!capital\s\s)(?:account|acct\b\.?|a/c|dda)"
_SWIFT_LABEL = r"swift(?:\s*/\s*bic)?(?:\s*code)?|bic(?:\s*code)?"
_ID_LABEL = (
    rf"driver'?s?[\s_\\]*licen[cs]e(?:[\s_\\]*{_NO})?|dl(?=\s*[#:])|dl\s*no\b\.?|passport(?:[\s_\\]*{_NO})?"
    r"|(?:lp|gp|investor|partner|member|client|customer|policy|employee|patient|holder|medicare|medicaid|insurance"
    r"|national|user|corporate|e-?wallet|wallet|staff|student|subscriber|loyalty"
    rf"|foreign(?:\s+tax)?)[\s_\\]*(?:id\b\.?|i\.\s?d\.|code|identification(?:[\s_\\]*{_NO})?|{_NO})"
    # a foreign tax number; a US one is the taxpayer IDs' (utils.taxpayer_ids)
    r"|foreign(?:\s+tax)?\s*tin\b"
    rf"(?:\s*{_NO})?|(?:ni|nino|national\s+insurance)(?:\s*{_NO})?|pan(?:\s*(?:card|{_NO}))?"
    rf"|aadhaa?r(?:\s*{_NO})?"
    rf"|tax[\s_\\]*(?:id(?:entification)?\b\.?|identification)(?:[\s_\\]*{_NO})?|national[\s_\\]*id(?:entity)?(?:[\s_\\]*card)?(?:[\s_\\]*{_NO})?"
    rf"|(?:certificate|licen[cs]e|permit)(?:[\s_\\]+licen[cs]e)?[\s_\\]*{_NO}"
    r"|cuit|cuil|npwp|nif|nie|cif|rfc|cpf|curp|dni|nric|pesel|bsn|tfn|sin\b(?=\s*[:#])"
    rf"|id(?=\s*[:#]\s*[A-Z]{{1,4}}\d)|social[\s_]+(?:number|no\b\.?)|(?<!employer\s)(?<!employer\s\s)identification[\s_]+(?:code|{_NO})")
_DOB_LABEL = (r"(?:d\.?\s?o\.?\s?b\b\.?|date[\s_.\\]*of[\s_.\\]*birth|birth[\s_\\]*date|birthday|born(?:\s+on)?)"
              r"(?:\s+of\s+(?:the\s+)?(?:partner|member|investor|owner|holder|spouse|beneficiary))?"
              r"(?:[ \t]*\([^()\n]{0,20}\))?")
_MONTHS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DATE = (r"\d{1,2}[/.-]\d{1,2}[/.-](?:\d{4}|\d{2})|\d{1,2}[ ]\d{1,2}[ ]\d{4}|\d{4}[/.-]\d{1,2}[/.-]\d{1,2}"
         r"|(?:19|20)\d{6}(?!\d)"
         rf"|{_MONTHS}[ \t]+\d{{1,2}}(?:st|nd|rd|th)?(?:,[ \t]*|[ \t]+)\d{{4}}"
         rf"|\d{{1,2}}(?:st|nd|rd|th)?[ \t/.-]*{_MONTHS},?[ \t/.-]*\d{{2,4}}")
_SEP = (r"[\"'*\\_]*[ \t]*(?:\([^()\n]{0,20}\)[ \t]*)?"
        r"(?:[:#.=|,\u2013-]{1,2}[ \t]*|is[ \t]+|of[ \t]+|was[ \t]+|\((?:e\.g\.,?|i\.e\.,?)?[ \t]*)?(?:\*\*(?=\s))?[\"']*[ \t]*"
        r"(?:\n[ \t]*){0,2}")
# An account or ID number: letters, digits, masks and dashes, in up to six groups.
_VALUE = r"[A-Za-z0-9*\u2022#](?:[A-Za-z0-9*\u2022#/-]|\.(?=[A-Za-z0-9]))*(?:[ ](?:[A-Za-z0-9*\u2022#/-]|\.(?=[A-Za-z0-9]))+){0,9}"
_LABELLED = re.compile(
    rf"(?<![^\W\d_])(?i:(?P<account>{_ACCOUNT_LABEL})|(?P<swift>{_SWIFT_LABEL})|(?P<id>{_ID_LABEL})"
    rf"|(?P<dob>{_DOB_LABEL})|(?P<bare>{_BARE_ACCOUNT}))(?![^\W\d_]){_SEP}"
    rf"(?P<value>(?(dob)(?i:{_DATE})|(?(swift)(?i:[A-Z]{{4}}[A-Z0-9]{{4,8}})(?![A-Za-z0-9])"
    rf"|{_VALUE})))")
# The first date after a birth date's label in the same sentence: "date of birth must be October 28, 1994",
# "[Date of Birth]\n01/01/1999".
_DOB_NEAR = re.compile(rf"(?<![^\W\d_])(?i:{_DOB_LABEL})(?P<gap>(?:(?!\.\s|\d)[^\n]|\n(?![ \t]*\n)){{0,45}}?)"
                       rf"(?<![\w/.-])(?P<value>(?i:{_DATE}))(?![\w/-])")
# A UK National Insurance number: two letters, three pairs of digits, a letter.
_NI_NUMBER = re.compile(r"(?<![A-Za-z0-9])[A-Z]{2}[ ]?\d{2}[ ]?\d{2}[ ]?\d{2}[ ]?[A-Z](?![A-Za-z0-9])")
# An SSN with all but its last four digits masked: ***-**-1234
# A Swedish or Danish personal number: the birth date, a dash or a plus, four digits (811217-8701)
_PERSONNUMMER = re.compile(r"(?<![\w-])(?:19|20)?\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])[-+]\d{4}(?![\w-])")
_MASKED_SSN = re.compile(r"(?<![\w*])(?:\*{3,4}|X{3}|x{3})-(?:\*{2}|X{2}|x{2})-\d{4}(?!\d)")
# A card or account number a few words after its label: "the credit card number on file is 3495-4026-3400-406"
_ACCOUNT_NEAR = re.compile(
    r"(?<![^\W\d_])(?i:(?:credit|debit)?[ \t]*card[ \t]+(?:number|no\b\.?|#)s?|account[ \t]+(?:number|no\b\.?)|iban|bban)"
    r"(?:(?!\.\s)[^\n\d]){0,40}?(?<![\w-])(?P<value>\d{4}(?:[ -]\d{3,6}){2,4}|\d{12,24})(?![\w-])")
# A username: after its label ("Username: mnewman", "User ID: JSMITH"), or an @handle.
_USERNAME = re.compile(
    r"(?<![^\W\d_])(?i:user[ \t_-]?name|login(?:[ \t_-]?(?:id|name))?|user[ \t_-]?id|screen[ \t_-]?name|handle)"
    r"(?![^\W\d_])[\"'*]*[ \t]*(?:[:=]|,?[ \t]+(?:which[ \t]+)?is|[ \t]+to)[ \t]*[\"'*]*[ \t]*"
    r"(?P<value>@?[A-Za-z0-9][\w.\-]{2,40}?)(?=[\"'*]*(?:[\s,;:)]|\.(?:\s|$)|$))(?![\w@])"
    r"|(?<![\w@.])(?P<handle>@[A-Za-z][\w.]{2,30})(?![\w@])")
_PHONE_LABEL = (rf"(?<![^\W\d_])(?i:(?:phone|tel(?:ephone)?|mobile|cell(?:ular)?|fax|ph)\b\.?(?:[ \t]*{_NO})?"
                r"(?:[ \t]+is)?[ \t]*\**[ \t]*[:.#-]?|contact[ \t]*(?:number|no\b\.?|\#)?[ \t]*\**[ \t]*:|(?:direct|office|work|home|main)[ \t]*:"
                r"|(?:call|text|phone|ring|fax|reach|reached|contact|contacting)(?:[ \t]+(?:us|me|him|her|them))?[ \t]+(?:at|on)"
                r"|(?:by|via)[ \t]+(?:phone|telephone|fax)(?:[ \t]+(?:at|on))?)")
_EXTENSION = r"(?:[ \t]*(?:x|ext\b\.?|extension)[ \t]*\d{1,6})?"
_END = r"(?![\d]|[.,]\d)"
# anything after "Phone:", "Tel", "Fax", "Work:", "call us at" ...
# (0131) 4960506, (028) 9018 0669: a national number with its area code's trunk 0 in brackets
_BRACKETED_TRUNK_PHONE = re.compile(rf"(?<![\w(])\(0\d{{1,4}}\)[ ]?\d{{3,4}}[ -]?\d{{3,4}}{_END}")
_LABELLED_PHONE = re.compile(rf"{_PHONE_LABEL}[ \t]*\**[ \t]*(?P<value>(?:\(\+\d{{1,3}}\)[ ]?)?\+?[\d(][\d ().-]{{6,22}}\d{_EXTENSION}){_END}")
# A national number with its trunk 0, as the UK and Europe write them: 0800 123 4567, 020-7946-0958
_TRUNK_PHONE = re.compile(rf"(?<![\w$.,+/:-])0\d{{1,4}}(?:[ -]\d{{2,4}}){{2,4}}{_EXTENSION}{_END}")
_PHONES = [
    # +1 415 555 0134, (+1) 800 111 2222: with its country code, any number of the shape
    re.compile(rf"(?<![\w+(])(?:\+1|\(\+1\))[ .-]?\(?\d{{3}}\)?[ .-]?\d{{3}}[ .-]?\d{{4}}{_EXTENSION}{_END}"),
    # +44 20 7946 0958, (+44) 151-123-4567, 011 44 20 7946 0958
    re.compile(rf"(?<![\w+(])(?:\+|\(\+(?=\d{{1,3}}\))|011[ .-]?|00[ ])(?!1[ .(-]?[2-9])\d{{1,3}}\)?"
               rf"(?:[ .-]?\(?\d{{1,5}}\)?){{2,5}}{_END}"),
    # 415-555-0134, (415) 555-0134, 415.555.0134, 415 555-0134, 415/555-0134, 1-415-555-0134, with any extension
    re.compile(r"(?<![\w$.,+/-])(?:\+?1[ .-]?|\(\+?1\)[ ]?)?(?:\(\s*\d{3}\s*\)[ .-]?\d{3}[ .-]|\d{3}[.-]\d{3}[ .-]|\d{3}[ /]\d{3}-"
               r"|\d{3}[ ]-[ ]\d{3}[ ]-[ ])"
               rf"\d{{4}}{_EXTENSION}{_END}"),

    _LABELLED_PHONE,
    _TRUNK_PHONE,
    _BRACKETED_TRUNK_PHONE,
    # 001-873-829-0395: a North American number with the international prefix 00
    re.compile(rf"(?<![\w+])001[ .-]\d{{3}}[ .-]\d{{3}}[ .-]\d{{4}}{_EXTENSION}{_END}"),
    # 07728712027: a UK mobile, written whole
    re.compile(rf"(?<![\w$.,+/:-])07\d{{9}}{_END}"),
]
# In what the user types: 415 555 0134, 1 415 555 0134 and 4155550134 too.
_TYPED_PHONES = [re.compile(rf"(?<![\d.,$])(?:1[ .-])?[2-9]\d{{2}} [2-9]\d{{2}} \d{{4}}{_END}"),
                 re.compile(rf"(?<![\d.,$])[2-9]\d{{2}}[2-9]\d{{6}}{_END}")]
_STREET_SUFFIX = ("Street St Avenue Ave Av Road Rd Boulevard Blvd Lane Ln Drive Dr Court Ct Place Pl Way Terrace Ter "
                  "Circle Cir Parkway Pkwy Highway Hwy Square Sq Trail Trl Plaza Plz Alley Aly Loop Row Path Pike "
                  "Crescent Cres Center Ctr Centre Expressway Expy Freeway Fwy Turnpike Tpke Causeway Mews Walk "
                  "Commons Crossing Heights Hts Route Rte Yards Wharf Pier Quay Esplanade Promenade Concourse").split()
# The rest of the USPS street suffixes.  Many are ordinary words too ("Points", "Key", "Union"), so a street
# ending in one needs the end of the address after it: a comma, a unit, the end of a line or a field.
_STREET_SUFFIX_MORE = ("Alley Anex Annex Arcade Bayou Beach Bend Bluff Bluffs Bottom Branch Bridge Bridges Brook Brooks "
                       "Burg Burgs Bypass Camp Canyon Cape Centers Circles Cliff Cliffs Club Common Corner Corners Course "
                       "Courts Cove Coves Creek Crest Crossroad Crossroads Curve Dale Dam Divide Drives Estate Estates "
                       "Extension Extensions Fall Falls Ferry Field Fields Flat Flats Ford Fords Forest Forge Forges Fork "
                       "Forks Fort Garden Gardens Gateway Glen Glens Green Greens Grove Groves Harbor Harbors Haven Hill "
                       "Hills Hollow Inlet Island Islands Isle Junction Junctions Key Keys Knoll Knolls Lake Lakes Land "
                       "Landing Light Lights Loaf Lock Locks Lodge Mall Manor Manors Meadow Meadows Mill Mills Mission "
                       "Motorway Mount Mountain Mountains Neck Orchard Oval Overpass Park Parks Parkways Pass Passage Pine "
                       "Pines Plain Plains Point Points Port Ports Prairie Radial Ramp Ranch Rapid Rapids Rest Ridge "
                       "Ridges River Roads Run Shoal Shoals Shore Shores Skyway Spring Springs Spur Spurs Squares Station "
                       "Stravenue Stream Streets Summit Throughway Trace Track Trafficway Tunnel Underpass Union Unions "
                       "Valley Valleys Viaduct View Views Village Villages Ville Vista Walks Wall Ways Well Wells Cross Gate Close "
                       "Rise Parade Yard Embankment Grange Rue Via Nagar Chowk Marg Zila Colony Layout Enclave Vihar Bagh Ganj").split()
_ADDRESS_END = (r"(?=[ \t]*(?:[,;|*\n\"'<>()/:\\?!}+\]]|$|\.(?!\w)|(?:Suite|Ste|Apt|Apartment|Unit|Floor|\#)\b)"
                r"|[ \t]+(?:and|was|is|in|for|to|with|as|has|have|had|where|which|on|at|from|since|by)\b)")
# A street name of one word with its kind in it, before or after the number: "Xaviweg 5", "36 Ringtorget".
_EURO_STREET = (r"[A-Z\u00c0-\u024f][\w\u00c0-\u024f'-]*(?i:strasse|stra\u00dfe|str\.|gasse|weg|platz|allee|ring|damm"
                r"|straat|laan|baan|pad|gracht|plein|kade|singel|dijk|steeg|dreef|boulevard|markt|hof|gata|gatan|vagen|v\u00e4gen"
                r"|v\u00e4g|vej|gade|torget|torg|stigen|gr\u00e4nd|grand|backe|veien|vegen|tie|katu|polku)")
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
    rf"(?<![\w])(?:{_EURO_STREET}[ \t]+\d{{1,5}}[a-z]?|(?:\d{{1,5}}/)?\d{{1,5}}[a-z]?,?[ \t]+{_EURO_STREET})(?![\w])"
    # Ronda Macario Merino 88, Via Roma 12
    r"|(?<![\w])(?:Ronda|Calle|Avenida|Paseo|Plaza|Pasaje|Carrer|Rua|Via|Viale|Piazza|Corso|Contrada|Strada|Vicolo"
    r"|Largo|Rue|Avenue|Boulevard|Chemin|Place|Quai|Travessa|Traves\u00eda|Glorieta|Rotonda|Stretto|Callej\u00f3n|Callejon"
    r"|Camino|Cuesta|Alameda|Avinguda|Passatge|Pra\u00e7a|Rambla|Acceso|Borgo|Viale|Salita|Vico|Ulitsa|Ulica|Ul\.|Utca"
    r"|Prospekt|Pereulok|Sharia|Shari|Sharaa|Jalan|Jl\.|Thanon|Soi|Calea|Strada|Rruga|Odos|Sokak|Caddesi|Cad\.)"
    r"(?:[ \t]+(?:(?:de|del|della|di|da|do|das|dos|la|las|los|le|les|du|des|el|al|Al)[ \t]+){0,2}"
    r"[A-Z\u00c0-\u024f][\w\u00c0-\u024f'.-]*){1,4},?[ \t]+(?:No\.?[ \t]*)?\d{1,5}[a-z]?(?![\w])"
    # Herzl Street 42, Al Wajba Street, 34, King Fahd Road, Bldg 45: the number after an English kind
    r"|(?<![\w])(?:[A-Z][\w'-]+[ \t]+){1,3}(?:Street|Road|Avenue|Lane|Boulevard|St\.|Rd\.)"
    r",?[ \t]+(?:No\.?[ \t]*|Bldg\.?[ \t]*|Building[ \t]+|House[ \t]+)?(?!(?:19|20)\d\d\b)\d{1,4}[A-Za-z]?(?![\w.,]\d|\w)"
    r"(?![ \t]+[A-Z][a-z])"
    # No. 23, Jalan Ampang; 75 Yulgok-ro; 617 W 183 St
    r"|(?<![\w])No\.?[ \t]*\d{1,5},?[ \t]+(?:Jalan|Jl\.|Lorong|Road|Street|Lane)(?:[ \t]+[A-Z][\w'-]*){1,3}"
    r"|(?<![\w-])\d{1,5}(?:-\d{1,4})?[ \t]+[A-Z][a-z]+(?:-[a-z]+)?-(?:ro|gil|daero|dong)\b"
    r"|(?<![\w-])\d{1,6}[ \t]+[NSEW]\.?[ \t]+\d{1,3}(?:st|nd|rd|th)?[ \t]+(?:St|Street|Ave|Avenue|Rd|Road|Pl|Place|Blvd)\b\.?"
    # rue de Bonnet, chemin Germain: a French street's kind in lower case, then its name
    r"|(?<![\w])(?:rue|chemin|impasse|all\u00e9e|boulevard|avenue)[ \t]+(?:(?:de|du|des|la|d')[ \t]*){0,2}"
    r"[A-Z\u00c0-\u024f][\w\u00c0-\u024f'-]*(?:[ \t]+[A-Z\u00c0-\u024f][\w\u00c0-\u024f'-]*){0,3}(?=[ \t]*(?:[,.;:)\n]|$))"
    rf"|(?<![\w-])\d{{3,5}}(?:-\d{{4}})?[ \t]+(?:[A-Z][\w'.-]*[ \t]+){{0,3}}[A-Z][\w'.-]*,[ \t]+"
    rf"(?:{'|'.join(_COUNTRIES)})\b")
# "Mailing address: 88 Kearny": the rest of the line, when it has a number.  Not an IP, MAC, email, web,
# wallet or server address, however it's capitalized.
_ADDRESS_LABEL = re.compile(r"(?<![^\W\d_])(?i:(?<!ip\s)(?<!ipv4\s)(?<!ipv6\s)(?<!mac\s)(?<!email\s)(?<!e-mail\s)"
                            r"(?<!web\s)(?<!wallet\s)(?<!bitcoin\s)(?<!crypto\s)(?<!server\s)(?<!network\s))"
                            r"(?i:(?:mailing|street|home|residential|permanent|billing|registered|"
                            r"partner'?s?|investor'?s?)[ \t]+address|address)[ \t]*(?::|\#|[ \t]-[ \t])[ \t]*\**[ \t]*"
                            r"(?P<value>(?:(?!\.[ \t]+[A-Z]|[ \t]\(|;)[^\n]){0,120}?\d"
                            r"(?:(?!\.[ \t]+[A-Z]|[ \t]\(|;)[^\n]){0,120}?)(?=\.?[ \t]*(?:$|\n)|\.[ \t]+[A-Z]|[ \t]\(|;)",
                            re.MULTILINE)
_DIRECTION = r"(?:N|S|E|W|NE|NW|SE|SW|North|South|East|West)\.?"
_UNIT = (r"(?:Suite|Ste|STE|SUITE|Apartment|Apartamento|Appartamento|Apt|APT|Unit|UNIT|Floor|FLOOR|Flat|FLAT|Fl|Room|Rm"
         r"|Building|Bldg|Piso|Puerta|Planta|Interno|Scala|Piano|Etage|\#)(?![a-z])")
_NUMBER_WORDS = "One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve Fifteen Twenty Fifty Hundred".split()
_STREET = re.compile(
    rf"(?:\d{{1,3}}(?:st|nd|rd|th)[ \t]+(?:Floor|FLOOR|Fl)\.?,?[ \t]+)?"
    rf"(?:(?<![\w$.,/-])|(?<=[a-z])(?=\d{{3,6}}[ \t]+[A-Z])|(?<=[A-Za-z\"],)|(?<=[A-Za-z:]/)|(?<=\d,)(?!\d{{3}}(?!\d))|(?<=Floor, )|(?<=FLOOR, )"
    rf"|(?<=Floor )|(?<=Fl\. ))(?:(?:H\.[ ]?No\.?[ \t]*)?\d{{1,6}}(?:[A-Za-z]|-\d{{1,5}}|-[A-Za-z]|[ ]1/2|/\d{{1,4}})?"
    rf"|{'|'.join(_NUMBER_WORDS)}),?[ \t]+"
    rf"(?:{_DIRECTION}[ \t]+)?(?:"
    rf"(?:(?:[A-Z][\w'.-]*|\d+(?:st|nd|rd|th))[ \t]+){{1,4}}"
    rf"(?:(?:{'|'.join(_STREET_SUFFIX + [s.upper() for s in _STREET_SUFFIX])})\.?(?![\w])"
    rf"|(?:{'|'.join(_STREET_SUFFIX_MORE + [s.upper() for s in _STREET_SUFFIX_MORE])})(?:s|S)?(?![\w]){_ADDRESS_END})"
    r"|(?:[a-z][\w'.-]*[ \t]+){1,3}(?:street|st|avenue|ave|road|rd|boulevard|blvd|lane|ln|drive|court|ct|place"
    r"|parkway|pkwy|highway|hwy|terrace|circle)\.?(?![\w])"
    # 93 Incrocio Cecilia, 2 Plaza de Roxana Paniagua: the street's kind first, then its name in capitals
    r"|(?:(?:Incrocio|Ca\u00f1ada|Vial|Acceso|Calle|Viale|Piazza|Strada|Contrada|Rotonda|Vicolo|Borgo|Ronda|Rambla"
    r"|Paseo|Pasaje|Avenida|Rua|Travessa|Chemin|All\u00e9e|Impasse|Salita|Glorieta)"
    r"(?:[ \t]+(?:de|del|della|di|da|do|dos|la|las|los|le|les|du|des|el))*"
    r"|(?:Plaza|Via|Rue|Camino|Corso|Largo|Quai)(?:[ \t]+(?:de|del|della|di|da|do|dos|la|las|los|le|les|du|des|el))+)"
    r"(?:[ \t]+(?:(?:de|del|della|di|da|do|dos|la|las|los|le|les|du|des|el)[ \t]+){0,2}"
    r"[A-Z\u00c0-\u00de][\w\u00c0-\u024f'-]*){1,4}(?=[ \t]*(?:[,;|\n\"'<)/]|$|\.(?!\w)))"
    r"|(?i:el[ \t]+camino[ \t]+real|(?:alameda|avenida|calle|camino|via|rue|avenue[ \t]+of[ \t]+the|boulevard|bd"
    r"|chemin|all\u00e9e|allee|impasse|place|quai|cours|pasaje|paseo|plaza|carrer|ronda|rambla|traves\u00eda|viale"
    r"|piazza|corso|vicolo|strada|largo|rua|avenue|contrada|travessa|glorieta|rotonda|stretto|callej\u00f3n|callejon"
    r"|cuesta|ronda|rambla|avinguda|passatge|borgo|salita|vico|canale|traves\u00eda)"
    r"(?:[ \t]+[a-z][\w'.-]*){1,4})|Broadway|BROADWAY)"
    rf"(?:[ \t]+{_DIRECTION}(?![\w]))?"
    rf"(?:[,;.]?[ \t]*{_UNIT}(?:[.:,]|[ \t]+[.:,]){{0,3}}(?:[ \t]|\n[ \t]*\n?)*\#?[A-Za-z0-9-]+|,?[ \t]*\d+(?:st|nd|rd|th)[ \t]+(?:Floor|FLOOR|Fl)\.?)?"
    # the city, state and ZIP on the same line; or the city alone, ending the address
    rf"(?:,?[ \t]+(?:[A-Z][\w'.-]*,?[ \t]+){{0,3}}{_STATE},?[ \t]+{_ZIP}"
    rf"|,[ \t]*(?:[A-Z][\w'\u00c0-\u024f-]*[ \t]+){{0,2}}[A-Z][\w'\u00c0-\u024f-]+(?=[ \t]*(?:[;|*\n\"<)/]|$|\.(?:\s|$))))?")
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
_COUNTRY_NAMES = ("USA|U\\.S\\.A\\.|US|United States(?: of America)?|UK|U\\.K\\.|United Kingdom|Great Britain|England"
                  "|Scotland|Wales|Ireland|Canada|Australia|New Zealand|" + "|".join(_COUNTRIES))
_COUNTRY_WORDS = frozenset(w.casefold() for w in re.findall(r"[A-Za-z]+", _COUNTRY_NAMES) if len(w) > 2) | \
    frozenset("india china japan brazil mexico russia nigeria egypt kenya pakistan bangladesh indonesia malaysia "
              "thailand vietnam philippines singapore israel turkey iran iraq argentina chile peru colombia".split())
# a town's words; a period only after a short one ("St. Louis"), so "Israel. Please" is no town
_CITY_WORDS = (r"(?:(?:[A-Z][a-z]{0,2}\.|[A-Z\u00c0-\u00de][\w'\u00c0-\u024f-]*)[ \t]+){0,2}"
               r"[A-Z\u00c0-\u00de][\w'\u00c0-\u024f-]*\.?")
_POSTAL = (r"(?:\d{3}[ ]\d{2}(?![\d])|\d{4,6}(?:-\d{3,4})?|[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z][ ]?\d[ABCEGHJ-NPRSTV-Z]\d"
           r"|(?:[A-Z]{1,2}\d[A-Z\d]?|GIR)[ ]\d[ABD-HJLNP-UW-Z]{2})")
# What may follow a street, piece by piece: ", 19821", ", New Shrewsbury", ", London, EC4M 2JR, UK", and lines
# under it that are the rest of the address ("Toronto, ON M3H 2T6", "Canada").
_TAIL_PIECE = re.compile(
    rf"[,;]?[ \t]*{_UNIT}(?:[.:,]|[ \t]+[.:,]){{0,3}}[ \t]*\#?[\w-]{{1,8}}(?![\w-])"
    rf"|(?:[,;:][.,;:]?[ \t]*(?:\n[ \t]*)?|/(?=[A-Z0-9]))(?:{_POSTAL}(?:[ \t]+{_CITY_WORDS})?|{_STATE}[ \t]*{_ZIP}"
    rf"|(?!{_UNIT}\b){_CITY_WORDS}(?:,?[ \t]+{_STATE})?(?:,?[ \t]+{_POSTAL})?)"
    rf"(?=[ \t]*(?:[,;|*\n\"'<>()/:?!}}+\\\]]|\[|$|\.(?!\w)|[ \t]+(?:and|as|was|is|for|to|with|in|on|has|had|have|may|will|shall|can|could|would"
    rf"|should|must|are|were|or|but|at|from|by|if|which|where|that|within|until|before|after|so)\b))"
    rf"|[ \t]*\n(?:[ \t]*\n)?[ \t]*(?:{_UNIT}\.?[ \t]*\#?[\w-]{{1,8}}"
    rf"|{_CITY_WORDS},?[ \t]+(?:{_STATE}|[A-Z][\w'.-]+(?:[ \t]+[A-Z][\w'.-]+)?),?[ \t]+{_POSTAL}"
    rf"|{_CITY_WORDS},?[ \t]+(?:{_POSTAL}|[A-Z]{{1,2}}\d[A-Z\d]?[ ]\d[A-Z]{{2}})|{_POSTAL}[ \t]+{_CITY_WORDS}"
    rf"|(?:{_COUNTRY_NAMES})"
    rf"|{_CITY_WORDS},?[ \t]+(?:{_STATE}|{_COUNTRY_NAMES})|\d{{5,6}}(?:-\d{{4}})?"
    rf"|[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z][ ]?\d[ABCEGHJ-NPRSTV-Z]\d|(?:[A-Z]{{1,2}}\d[A-Z\d]?)[ ]\d[ABD-HJLNP-UW-Z]{{2}})"
    rf"[ \t]*(?=\n|$)")
# Fields that hold a person's name, by their key: "first_name", "LastName", "Customer Name", "payee" ...
_PERSON_ROLES = ("payer|payee|shipper|consignee|applicant|co-?applicant|borrower|co-?borrower|customer|client|insured"
                 "|policy-?holder|patient|beneficiary|sender|recipient|remitter|debtor|creditor|employee|tenant|landlord"
                 "|buyer|seller|guarantor|contact|cardholder|card-?holder|account-?holder|holder|owner|member|investor"
                 "|subscriber|claimant|insurer|physician|doctor|signatory|witness|traveler|traveller|passenger|driver"
                 "|student|candidate|requester|requestor|reporter|assignee|author|attendee|participant|person|individual"
                 "|spouse|dependent|nominee|trustee|grantor|lessee|lessor|agent|representative")
_NAME_KEY = re.compile(rf"(?i)(?:(?:first|last|full|middle|given|family|sur|maiden|nick|legal|display|contact|customer"
                       rf"|client|employee|patient|holder|account|beneficiary|applicant|insured|payer|payee|sender"
                       rf"|recipient|person|party|member|owner|signer|driver|agent|cardholder|card)[ _-]?)?name"
                       rf"|(?:{_PERSON_ROLES})(?:[ _-]?(?:name|full[ _-]?name))?|first|last|surname|forename|given"
                       rf"|name[ _-]?(?:first|last|full|given|middle|family)")
# Keys with "name" in them that name no person.
_NOT_PERSON_KEY = re.compile(r"(?i)user[ _-]?name|login|company|business|bank|product|file|instrument|org|firm|fund"
                             r"|entity|brand|item|project|event|venue|vessel|ship(?!per)|plan\b|program|course|trade"
                             r"|model|device|drug|medic|host|server|domain|street|city|country|state|branch|team|account[ _-]?name"
                             r"|campaign|group|dept|department|unit|category|type|code|tag|field|column|table|key|app"
                             r"|service|insurer|issuer|carrier|vendor|supplier|merchant|provider|partner|agency|office"
                             r"|institution|school|hospital|facility|site|store|shop|location|property|building|asset")
# Fields that hold a street address, by their key: "street_address", "StreetAddress", "Mailing Address".
# Fields that hold the town or the postcode of an address: "City: Tulsa", "| Postcode | 32824 |"
_PLACE_KEY = re.compile(r"(?i)(?:(?:origin|destination|home|mailing|billing|shipping|residence|residential)[ _-]?)?"
                        r"(?:city|town|post[ _-]?code|postal[ _-]?code|zip(?:[ _-]?code)?)")
_ADDRESS_KEY = re.compile(r"(?i)(?:(?:street|mailing|home|residential|billing|shipping|delivery|postal|contact|customer"
                          r"|permanent|current|correspondence|property|primary)[ _-]?)?(?:address|addr)(?:[ _-]?(?:line)?"
                          r"[ _-]?[12])?|street")
# Fields that hold a birth date or a person's ID number, by their key: "date_of_birth", "EmployeeID".
_DOB_KEY = re.compile(r"(?i)(?:\w+[ _-]?)?(?:date[ _-]?of[ _-]?birth|birth[ _-]?date|dob|birthday)")
_ID_KEY = re.compile(r"(?i)(?:customer|client|employee|emp|user|member|patient|account[ _-]?holder|card[ _-]?holder"
                     r"|passport|driver'?s?[ _-]?licen[cs]e|national|staff|student|policy[ _-]?holder|insured|subscriber"
                     r"|person|personal|party|identity|citizen|voter|nhs|medicare|medicaid|loyalty|wallet|e-?wallet)"
                     r"[ _-]?(?:id|identifier|number|no|num|nr|code|ref)?")
# An ID number after a word that says whose it is, in the same sentence: "Employee ID for Jo Kabus is Nq-92647",
# "her passport number, R87712693".  The value has letters and digits, or seven digits at least.
_CONTEXT_ID = re.compile(
    r"(?<![^\W\d_])(?i:employee|customer|client|member|user|patient|passport|driver'?s?[ \t]+licen[cs]e"
    r"|licen[cs]e[ \t]+(?:number|no\b)|account[ \t]+holder|staff|student|policy[ \t]*holder)(?:'s)?(?![^\W\d_])"
    r"(?:(?!\.\s)[^\n;()\[\]{}<>\"]|\n(?![ \t]*\n)){0,40}?[ \t:(\",/*]"
    r"(?P<value>(?=[A-Za-z0-9-]*\d)[A-Za-z0-9]+(?:-[A-Za-z0-9]+){0,3})(?![\w-])")
# An ID by its shape alone: one to four capital letters and six to ten digits (EMP286818, G4830770), not an amount
# in a currency (USD52482349) and not an ISIN (US1234567890).
_SHAPED_ID = re.compile(r"(?<![\w$.\-])(?P<letters>[A-Z]{1,4})(?P<digits>\d{6,30})(?![\w-])")
_CURRENCIES = frozenset("USD EUR GBP CAD AUD NZD CHF JPY CNY HKD SGD INR MXN BRL ZAR SEK NOK DKK PLN CZK HUF RUB TRY KRW "
                        "AED SAR ILS THB MYR IDR PHP TWD".split())
# A field's value that starts with one of these is no one's name: "Agent Smith", "Support Team".
_ROLE_WORDS = _words("agent officer support representative rep manager team staff customer client user admin system "
                     "bot assistant operator advisor adviser specialist consultant service desk department unknown none "
                     "n/a na null test sample example anonymous redacted")
# "first_name": "John", 'last_name': ['Smith', 'Davis'], first_name=John, <FirstName>John</FirstName>
_KEYED_VALUE = re.compile(
    r"(?P<q0>[\"']?)(?P<key>[A-Za-z][\w \\-]{0,30}?)(?P=q0)[ \t]*[:=][ \t]*(?P<list>\[[ \t]*)?(?P<q>[\"'])"
    r"(?P<value>[^\"'\n]{1,80})(?P=q)"
    r"|<(?:[\w-]+:)?(?P<tag>[\w-]{1,40})(?:[ \t][^<>\n]{0,80})?>(?P<tvalue>[^<>\n]{1,80})</")
_LIST_ITEM = re.compile(r"[ \t]*,[ \t]*(?P<q>[\"'])(?P<value>[^\"'\n]{1,80})(?P=q)")
_ISO_COUNTRIES = frozenset("""AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ
BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET
FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR
IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN
MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY
QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR
TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS XK YE YT ZA ZM ZW""".split())
# A SWIFT/BIC code with no label (ISO 9362): bank, country, location and branch, with a digit in the location or
# branch, so a capitalized word isn't one.
_BIC = re.compile(r"(?<![A-Za-z0-9])[A-Z]{4}(?P<country>[A-Z]{2})[A-Z0-9]{2}(?:[A-Z0-9]{3})?(?![A-Za-z0-9])")
_IBAN = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]{2}\d{2}(?:[ ]?[A-Za-z0-9]{4}){2,7}(?:[ ]?[A-Za-z0-9]{1,3})?"
                   r"(?![A-Za-z0-9])")
_CARD = re.compile(r"(?<![\d.,$])(?:\d{4}([ -])\d{4}\1\d{4}\1\d{3,4}(?:\1\d{1,3})?|\d{4}([ -])\d{6}\2\d{5})"
                   rf"{_END}")
# A date and a time written as one number, as a SWIFT field has it (":32A:20210311120000"): no ID
_TIMESTAMP = re.compile(r"(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])(?:[01]\d|2[0-3])[0-5]\d(?:[0-5]\d(?:\d{1,6})?)?")
_LONG_NUMBER = re.compile(rf"(?<![\d.,$])\d{{11,24}}{_END}")

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


def _address_tail(copy: str, end: int) -> int:
    """Where an address that has its street end at ``end`` ends, with its city, postcode, country and the
    lines under it."""
    while (m := _TAIL_PIECE.match(copy, end)) is not None and m.end() > end:
        end = m.end()
    # "887 Simon Cliff, 28346" then "Clineville" alone on the next line: a town no everyday word
    if re.search(r"\d{4,6}[ \t]*\Z", copy[max(0, end - 8):end]) and \
            (m := re.match(r"[ \t]*\n[ \t]*((?:[A-Z][\w'\u00c0-\u024f-]+[ \t]+){0,2}[A-Z][\w'\u00c0-\u024f-]+)[ \t]*(?=\n|$)",
                           copy[end:])) and \
            not any(w.casefold() in _common_words() for w in m.group(1).split()):
        end += m.end()
    return end


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


def _tokens(fold: str, copy: str = "") -> list[_Tok]:
    toks = []
    for m in _TOKEN.finditer(fold):
        w = m.group()
        # Heß is looked up as Hess: the fold keeps one letter for each, so its ß is an s
        folded = _ascii(copy[m.start():m.end()].replace("\u00df", "ss")).casefold() if "\u00df" in copy[m.start():m.end()] \
            else w.casefold()
        if len(w) == 1:
            case = "initial" if w.isupper() else "lower"
        else:
            case = "caps" if w.isupper() else "title" if w[0].isupper() else "lower"
        toks.append(_Tok(m.start(), m.end(), w, folded, case, fold[m.end():m.end() + 1] == "."))
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
    if re.search(r"[a-z]{4,}\.\Z", fold[max(0, end - 12):end]):
        return False   # "874 Morrison Highway. Financial institutions": the sentence ended
    rest = fold[end:end + 80]
    for n, m in enumerate(_TOKEN.finditer(rest)):
        if n == 5 or re.search(r"[()\n:;<>|=\"!?]|(?:^|[a-z0-9]{2})\.\s", rest[:m.start()]) or (n and "," in rest[:m.start()]):
            return False   # a business's word only before any comma, or right after it ("..., Inc.")
        word = m.group().casefold()
        if word in _PERSONAL:
            return False
        if word in v.business:
            return not (typed and n == 0 and word in v.member_interest and
                        re.match(r"[ \t]*(?:$|[.,;)]|and\b|members?\b|interest)", rest[m.end():], re.IGNORECASE))
        if word not in _ROMAN and word not in ("and", "of", "the") and not m.group()[0].isupper():
            return False
    return False


def _mostly_lower(text: str) -> bool:
    """Whether a text is written in lower case: hardly a word capitalized, of enough words to tell."""
    words = re.findall(r"[^\W\d_]{2,}", text)
    return len(words) >= 8 and sum(w[0].isupper() for w in words) < 0.03 * len(words)


_LOWER_SUFFIXES = None


def _recase(text: str) -> str:
    """``text`` with the capitals a careful writer would have given its names: a listed first name, and the
    names after it ("jane smith" is "Jane Smith"); a street's name and kind after its number, and the town and
    state after it ("12 main street, springfield, il" is "12 Main Street, Springfield, IL").  Same length."""
    global _LOWER_SUFFIXES
    if _LOWER_SUFFIXES is None:
        _LOWER_SUFFIXES = "|".join(sorted({w.lower() for w in _STREET_SUFFIX + _STREET_SUFFIX_MORE}, key=len,
                                          reverse=True))
    chars = list(text)

    def cap(start: int, end: int, upper: bool = False) -> None:
        chars[start:end] = text[start:end].upper() if upper else text[start].upper() + text[start + 1:end]

    def given(w: str) -> bool:
        return w in _GIVEN or (w in _given_names() and not _wordlike(w) and w not in _common_words())

    def name(w: str) -> bool:
        return w in _GIVEN or w in _SURNAMES or w in _top_surnames() or w in _common_surnames() or \
            ((w in _given_names() or w in _surname_list()) and w not in _common_words())

    toks = list(re.finditer(r"[^\W\d_]+(?:['-][^\W\d_]+)*", text))
    k = 0
    while k < len(toks):
        w = _ascii(toks[k].group()).casefold()
        if given(w) and w not in _STOP:
            run = [k]
            while len(run) < 4 and run[-1] + 1 < len(toks) and \
                    re.fullmatch(r"[ \t]{1,2}|[ \t]*\.[ \t]*", text[toks[run[-1]].end():toks[run[-1] + 1].start()]):
                nxt = _ascii(toks[run[-1] + 1].group()).casefold()
                if not (len(nxt) == 1 or (name(nxt) and nxt not in _STOP)):
                    break
                run.append(run[-1] + 1)
            if len(run) > 1 or re.search(r"(?i)(?:name|dear|hi|hello|thanks|patient|customer|client|agent)\W{0,3}\Z",
                                         text[max(0, toks[k].start() - 12):toks[k].start()]):
                for j in run:
                    cap(toks[j].start(), toks[j].end())
            k = run[-1] + 1
            continue
        k += 1
    for m in re.finditer(rf"(?<![\w.])\d{{1,6}}[ \t]+((?:[a-z][\w'-]*[ \t]+){{1,3}}?)({_LOWER_SUFFIXES})\b\.?"
                         rf"(?:,?[ \t]+((?:[a-z][\w'-]*[ \t]+){{0,2}}[a-z][\w'-]*),?[ \t]+([a-z]{{2}})(?=[ \t]+\d{{5}}))?", text):
        for g in (1, 2, 3):
            if m.group(g):
                for w in re.finditer(r"[a-z][\w'-]*", m.group(g)):
                    cap(m.start(g) + w.start(), m.start(g) + w.end())
        if m.group(4) and m.group(4).upper() in _STATE_CODES:
            cap(m.start(4), m.end(4), upper=True)
    return "".join(chars)


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
    single: bool = False      # a name of one word, found alone: hidden wherever it's written so
    guess: bool = False       # known from the name finder alone: hidden last, only where nothing else is


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
    (spaCy, Presidio, a cloud service); each name it returns is hidden however it's written, as with
    ``add_person``, but only where nothing else is, once the rest is found: it can only add to what's hidden.
    A piece of a name ("Luigi" of "Luigi Clelia Togliatti") leaves the name found around it whole.  The built-in
    name finding works from word lists, so it misses names it has no word for in prose that has no label or
    title before them ("CEO Satya Nadella").
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
        self._patterns: list[tuple[re.Pattern, _Person | None, str, bool]] | None = None
        self._guessing = False   # what add_person is given comes from the name finder
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
        person.guess = self._guessing
        known = self._people.get(person.key)
        # The name finder's guess changes nothing the app or the word lists know; theirs replaces a guess.
        if known is not None and known.guess == person.guess:
            if (known.bare or not person.bare) and (known.whole or not person.whole):
                return
            person.display = known.display   # put back as it first was
        elif known is not None and person.guess:
            return
        self._people[person.key] = person
        self._patterns = None

    def _surnames(self) -> set[str]:
        """The surnames of the people known and found so far that are no ordinary word."""
        return {p.last.casefold() for p in self._people.values()
                if p.last and (p.first or p.bare) and not p.guess and
                p.last.casefold() not in _WORD_SURNAMES | self._v.not_surnames}

    def _lone_names(self) -> set[str]:
        """The surnames known only from a name of one word ("Rubén", "Okonkwo"), never with a first name."""
        return {p.last.casefold() for p in self._people.values() if p.last and not p.first} - \
            {p.last.casefold() for p in self._people.values() if p.last and p.first}

    def _compiled(self) -> list[tuple[re.Pattern, _Person | None, str, bool]]:
        """Each known person's ways of being written; a None person is put back as written.  Each says whether
        it's the name finder's guess."""
        if self._patterns is not None:
            return self._patterns
        gap = r"(?:[ \t_-]+|[ \t]*\n[ \t]*|[ \t]*[.][ \t]*|(?-i:(?<=[a-z])(?=[A-Z])))"
        surnames: dict[str, int] = {}
        for p in self._people.values():
            if p.last and p.first and not p.guess:
                surnames[p.last.casefold()] = surnames.get(p.last.casefold(), 0) + 1

        def word(w: str) -> str:
            return r"[-\s]?".join(re.escape(part) for part in w.split("-")).replace("'", r"['\s]?")

        # each with a word it can't match without, so a long text is searched only for the people it names
        patterns: list[tuple[re.Pattern, _Person | None, str, bool]] = []
        alone: list[tuple[re.Pattern, _Person | None, str, bool]] = []
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
                patterns.append((re.compile(rf"(?<![^\W\d_])(?:{'|'.join(forms)})(?![^\W\d_])", re.IGNORECASE), p,
                                 p.last or (p.whole[0] if p.whole else ""), p.guess))
            if p.last and len(p.last) > 2 and p.last.casefold() not in self._v.stop:
                # Mr. Mockridge; and Mockridge alone, when that's no ordinary word.  Put back as written.
                optional = "?" if p.bare and p.last.casefold() not in _GIVEN | _WORD_SURNAMES else ""
                particles = "".join(rf"(?:{word(x)}[ \t]+)?" for x in p.particles)
                # not inside a key or a tag's name: "Branch" of Erin Branch isn't in <Branch_Name>
                alone.append((re.compile(rf"(?<![^\W\d])(?:(?:{'|'.join(_HONORIFICS)})\.?[ \t]+){optional}"
                                         rf"{particles}{word(p.last)}(?![^\W\d])", re.IGNORECASE), None, p.last,
                              p.guess))
            first = p.first.casefold()
            if p.single:
                alone.append((re.compile(rf"(?<!\w)(?-i:{word(p.first)})(?!\w)"), None, p.first, p.guess))
                continue
            if p.first and p.bare and len(first) > 3 and first not in _GIVEN | _WORD_SURNAMES | self._v.not_names:
                # Thandiwe alone: a first name that's no common one or ordinary word
                alone.append((re.compile(rf"(?<![^\W\d_]){word(p.first)}(?![^\W\d_])", re.IGNORECASE), None, p.first,
                              p.guess))
        def probe(word: str) -> str:   # its longest run of letters, as the fold writes it
            runs = re.findall(r"[^\W\d_]+", _ascii(word))
            return max(runs, key=len).casefold() if runs else ""

        self._patterns = [(pattern, person, probe(word), guess) for pattern, person, word, guess in patterns + alone]
        return self._patterns

    # -- finding it ------------------------------------------------------------

    def redact_text(self, text: str, typed: bool = False) -> str:
        """``text`` with taxpayer IDs and personal information replaced.  ``typed``: the user typed it, so any
        two or three capitalized words (that aren't the profile's words, or a business's) are taken for
        a name, and so are a common first name and surname in lower case."""
        if self._name_finder is not None and "NAME" in self._detect and text and not text.isspace():
            self._guessing = True
            try:
                for name in self._name_finder(text) or ():
                    self.add_person(name)
            finally:
                self._guessing = False
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
        # A text written all in lower case, as a chat or a careless form: likely names and streets are given
        # their capitals here to be found, and put back as written.
        recased = _mostly_lower(copy)
        if recased:
            copy = _recase(copy)
        fold = _ascii(copy)
        covered = bytearray(len(copy))
        for start, end in self._placeholder_spans(copy):
            covered[start:end] = b"\x01" * (end - start)
        found: list[tuple[int, int, str, str, str | None]] = []   # start, end, kind, key, put back as
        known: dict[int, tuple[int, int, str, str, str | None]] = {}   # what the known names took, by its start

        def take(start: int, end: int, kind: str, key: str | None = None, real: str | None = None,
                 over_known: bool = False) -> bool:
            if start >= end or (kind in KINDS and kind not in self._detect):
                return False
            if any(covered[start:end]):
                # A longer name found over a known one, or a part of one: "Luigi Clelia Togliatti" with "Luigi" or
                # "Clelia Togliatti" known.  The whole is one name, with a placeholder of its own.
                if not over_known or b"\x01" in covered[start:end]:   # the known names' are marked 2
                    return False
                first = start
                while covered[first] and first not in known:
                    first -= 1
                under = [known[k] for k in range(first, end) if k in known]
                if any(f[0] <= start and end <= f[1] for f in under):
                    return False
                for f in under:
                    found.remove(f)
                    del known[f[0]]
                if under[0][0] < start or under[-1][1] > end:
                    start, end = min(start, under[0][0]), max(end, under[-1][1])
                    key = real = None   # put back as written
            if recased:
                real = None   # put back as written, not as recased
            covered[start:end] = b"\x01" * (end - start)
            found.append((start, end, kind, key or f"{kind}:{_fold(copy[start:end])}", real))
            return True

        def free(start: int, end: int) -> int:
            """Where an address's tail, from ``start``, runs into something already taken."""
            stop = covered.find(b"\x01", start, end)
            return end if stop < 0 else len(copy[start:stop].rstrip(" \t,;\n")) + start

        def scan(pattern: re.Pattern, on, source: str = copy) -> None:
            """Each match of ``pattern``; where ``on(match)`` takes nothing, it looks again a character on."""
            pos = 0
            while (m := pattern.search(source, pos)) is not None:
                pos = m.end() if on(m) else m.start() + 1

        for kind, pattern in self._custom:
            scan(pattern, lambda m, kind=kind: take(m.start(), m.end(), kind))
        scan(_EMAIL, lambda m: ("@" in m.group() or (_SPELLED_EMAIL.fullmatch(m.group()) is not None and
                                                       not re.search(r"(?i)\bwww\b|^(?:website|site|web|us|online|"
                                                                     r"page|portal|home|link|webpage)\b", m.group()) and
                                                       not re.search(r"\.[ \t]+[A-Z]", m.group()) and
                                                       re.split(r"[ \t]+at[ \t]+|[ \t]*[\[({]at", m.group())[0].casefold()
                                                       not in _common_words()))
             and
             take(m.start(), m.end(), "EMAIL"))
        if "ID" in self._detect:
            scan(_NI_NUMBER, lambda m: take(m.start(), m.end(), "ID", "ID:" + m.group().replace(" ", "")))
        scan(_MASKED_SSN, lambda m: take(m.start(), m.end(), "SSN", "SSN:" + m.group()))
        if "ID" in self._detect:
            scan(_PERSONNUMMER, lambda m: not re.search(
                r"(?i)(?:invoice|order|ref(?:erence)?|po|batch|lot|ticket|case|no|number|\#)\W{0,3}\Z",
                fold[max(0, m.start() - 14):m.start()]) and
                take(m.start(), m.end(), "ID", "ID:" + re.sub(r"\D", "", m.group())))
        scan(_LABELLED, lambda m: self._labelled(m, take, fold))
        scan(_DOB_NEAR, lambda m: take(m.start("value"), m.end("value"), "DOB"))
        if "ID" in self._detect:
            scan(_USERNAME, lambda m: self._username(m, fold, take))
        scan(_ACCOUNT_NEAR, lambda m: take(m.start("value"), m.end("value"), "ACCOUNT",
                                           "ACCOUNT:" + re.sub(r"\D", "", m.group("value"))))

        scan(_IBAN, lambda m: _iban_ok(m.group()) and (m.group().isupper() or sum(c.isdigit() for c in m.group()) >= 8)
             and
             take(m.start(), m.end(), "ACCOUNT", "ACCOUNT:" + m.group().replace(" ", "").upper()))
        scan(_BIC, lambda m: m.group("country") in _ISO_COUNTRIES and any(c.isdigit() for c in m.group()[6:]) and
             take(m.start(), m.end(), "ACCOUNT", "ACCOUNT:" + m.group()))
        scan(_CARD, lambda m: (re.fullmatch(r"\d{4}([ -])\d{4}\1\d{4}\1\d{3,4}|\d{4}([ -])\d{6}\2\d{5}", m.group()) or
                               _luhn(re.sub(r"\D", "", m.group()))) and
             take(m.start(), m.end(), "ACCOUNT", "ACCOUNT:" + re.sub(r"\D", "", m.group())))
        for pattern in _PHONES + (_TYPED_PHONES if typed else []):
            scan(pattern, lambda m: self._phone(m, take))
        # not a sentence that talks of an address ("Address: The updated system will be deployed to ...")
        # and up to a comma before words in lower case ("..., Apt. 42875, was also verified")
        scan(_ADDRESS_LABEL, lambda m: len(re.findall(r"(?<![\w'])[a-z]+\b", re.split(r"\d", m.group("value"))[0])) < 4 and
             take(m.start("value"), m.start("value") + len(re.sub(
                 r"(?:,?[ \t]*[\[<][^\]>\n]*[\]>])+[ \t]*$", "",
                 re.split(r"(?<=\d),[ \t]+(?=[a-z]{2,}[ \t]+[a-z])", m.group("value"))[0])), "ADDRESS"))
        # "the 2010 ISDA Credit Support Annex": a year and a title, after "the"
        scan(_STREET, lambda m: not _business_after(fold, m.end(), self._v) and
             not (re.match(r"(?:19|20)\d{2}\b", m.group()) and
                  re.search(r"(?i)\bthe[ \t]+\Z", fold[max(0, m.start() - 6):m.start()])) and
             take(m.start(), free(m.end(), _address_tail(copy, m.end())), "ADDRESS"))
        scan(_BOXES, lambda m: take(m.start(), m.end(), "ADDRESS"))
        scan(_CITY_STATE_ZIP, lambda m: not set(_fold(m.group("city")).split()) & _NOT_CITY and
             take(m.start(), m.end(), "ADDRESS"))
        if typed:
            scan(_TYPED_CITY_STATE_ZIP, lambda m: not set(_fold(m.group("city")).split()) & _NOT_CITY and
                 take(m.start(), m.end(), "ADDRESS"))
        scan(_FOREIGN, lambda m: take(m.start(), free(m.end(), _address_tail(copy, m.end())), "ADDRESS"))
        for pattern in (_UNIT_LINE, _POSTCODES):
            scan(pattern, lambda m: take(m.start(), m.end(), "ADDRESS"))
        if "ID" in self._detect:
            scan(_CONTEXT_ID, lambda m: (sum(c.isdigit() for c in m.group("value")) >= 7 or
                                         (sum(c.isdigit() for c in m.group("value")) >= 5 and
                                          re.search(r"(?i)\b(?:id|number|no)\b", m.group()[:m.start("value") - m.start()])) or
                                         (sum(c.isdigit() for c in m.group("value")) >= 4 and
                                          any(c.isalpha() for c in m.group("value")))) and
                 not re.fullmatch(_DATE, m.group("value"), re.IGNORECASE) and
                 take(m.start("value"), m.end("value"), "ID", "ID:" + m.group("value").replace("-", "").upper()))
            scan(_SHAPED_ID, lambda m: m.group("letters") not in _CURRENCIES and
                 not (m.group("letters") in _ISO_COUNTRIES and len(m.group("digits")) == 10) and
                 take(m.start(), m.end(), "ID", "ID:" + m.group()))
        if "NAME" in self._detect:
            self._field_names(copy, fold, take)

        def take_known(start: int, end: int, kind: str, key: str | None = None, real: str | None = None) -> bool:
            if not take(start, end, kind, key, real):
                return False
            covered[start:end] = b"\x02" * (end - start)
            known[start] = found[-1]
            return True

        def sure() -> int:   # the people known but for the name finder's guesses
            return sum(not p.guess for p in self._people.values())

        people = sure()
        for _ in range(2 if "NAME" in self._detect else 0):   # names found in this text are hidden wherever else it says them
            self._known_names(fold, take_known, typed)
            self._found_names(copy, fold, take, typed)
            if sure() == people:
                break
            people = sure()
        if "NAME" in self._detect:
            # The name finder's guesses last, where nothing else is: what it says hides no less than without
            # it ("Luigi" of "Luigi Clelia Togliatti" leaves the name found whole).  Guesses side by side are
            # one name: "Zorblax", "Qwib" and "Vrenquist" of "Zorblax Qwib Vrenquist".
            first = len(found)
            self._known_names(fold, take, typed, guesses=True)
            guessed = sorted(found[first:])
            del found[first:]
            for start, end, kind, key, real in guessed:
                if found[first:] and re.fullmatch(r"[ \t]+", copy[found[-1][1]:start]):
                    start = found.pop()[0]
                    key, real = f"NAME:{_fold(copy[start:end])}", None
                found.append((start, end, kind, key, real))
        scan(_LONG_NUMBER, lambda m: not (_TIMESTAMP.fullmatch(m.group()) and
                                          re.search(r":\d{2}[A-Z]?:\Z", copy[max(0, m.start() - 6):m.start()])) and
             take(m.start(), m.end(),
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

    def _name_value(self, value: str) -> bool:
        """Whether a field's ``value`` reads as a person's name: one to five words, capitalized, none a
        business's word, and not only everyday words."""
        words = value.split()
        if not 1 <= len(words) <= 5 or not re.fullmatch(r"[^\W\d_][\w'.,\u2019-]*(?:[ \t]+[^\W\d_][\w'.,\u2019-]*)*",
                                                        value.strip()):
            return False
        folds = [w.strip(".,").casefold() for w in _name_words(value)]
        if not folds or not any(w[:1].isupper() for w in words) or _LEGAL_ENDING.search(value) or \
                re.fullmatch(r"[A-Z]{2,4}", value.strip()) or re.search(r"[A-Z]{2,}-[A-Z]{2,}|\d", value) or \
                any(re.search(r"[a-z][A-Z]", w) and not re.match(r"(?:Mc|Mac|De|Di|Da|Du|La|Le|Van|Von|Fitz)[A-Z]", w)
                    for w in words):   # a code: GBP, MemberA, CPI-US
            return False
        if any(f in self._v.business or f in _PERSONAL for f in folds if len(f) > 1) or \
                (any(f in self._v.stop for f in folds) and not any(f in _GIVEN or f in _given_names() for f in folds)) or \
                folds[0] in _ROLE_WORDS or any(f"{x} {y}" in _FIRMS for x, y in zip(folds, folds[1:])):
            return False
        return any(f in _GIVEN or f in _SURNAMES or f in _given_names() or f in _surname_list() or
                   f in _common_surnames() or f not in _common_words() for f in folds if len(f) > 1)

    def _field_names(self, copy: str, fold: str, take) -> None:
        """Names in a field whose key or column says it holds one: JSON, XML, key=value, and tables (CSV, pipe
        and tab separated) under a header such as "First Name" or "Customer"."""
        def key_kind(key: str) -> str | None:
            key = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", key.strip().replace("\\_", "_"))   # camelCase: FirstName
            if _ADDRESS_KEY.fullmatch(key):
                return "ADDRESS"
            if _PLACE_KEY.fullmatch(key):
                return "PLACE"
            if _DOB_KEY.fullmatch(key):
                return "DOB"
            if re.fullmatch(r"(?i)user[ _-]?name|login(?:[ _-]?(?:id|name))?|user[ _-]?id|screen[ _-]?name|handle", key):
                return "USERNAME"
            if re.fullmatch(r"(?i)(?:(?:home|work|mobile|cell|contact|business|office|primary)[ _-]?)?(?:phone|telephone|tel"
                            r"|mobile|cell|fax)(?:[ _-]?(?:number|no|num|nr))?", key):
                return "PHONE"
            if _ID_KEY.fullmatch(key) and re.search(r"(?i)(?:id|identifier|number|no|num|nr|code|ref|passport)$", key):
                return "ID"
            if _NAME_KEY.fullmatch(key) is not None and not _NOT_PERSON_KEY.search(key):
                return "NAME"
            return None

        def put(start: int, value: str, kind: str = "NAME") -> None:
            lead = len(value) - len(value.lstrip())
            value = value.strip()
            if kind == "DOB":
                if re.fullmatch(_DATE, value, re.IGNORECASE):
                    take(start + lead, start + lead + len(value), "DOB")
            elif kind == "PLACE":   # a town's name, or a postcode: not a placeholder ("[City]", "N/A")
                if re.fullmatch(r"(?:[A-Z\u00c0-\u00de][\w'\u00c0-\u024f.-]*[ ]?){1,4}|[A-Z0-9]{2,5}[ -]?[A-Z0-9]{2,5}", value) and \
                        re.search(r"\d", value) or (re.fullmatch(r"(?:[A-Z\u00c0-\u00de][\w'\u00c0-\u024f.-]*[ ]?){1,4}", value)
                                                    and value.casefold() not in ("n/a", "city", "town", "none", "unknown")):
                    take(start + lead, start + lead + len(value), "ADDRESS")
            elif kind == "ADDRESS":
                if re.search(r"\d", value) and re.search(r"[^\W\d_]{2}", value) and len(value) <= 160:
                    take(start + lead, start + lead + len(value), "ADDRESS")
            elif kind == "PHONE":
                digits = re.sub(r"\D", "", value)
                if 7 <= len(digits) <= 16 and re.fullmatch(r"\+?[\d ().\-]+(?:[ ]?(?:x|ext\.?)[ ]?\d{1,6})?", value):
                    take(start + lead, start + lead + len(value), "PHONE", "PHONE:" + digits)
            elif kind == "USERNAME":
                if re.fullmatch(r"@?[A-Za-z0-9][\w.\-]{2,40}", value):
                    take(start + lead, start + lead + len(value), "ID", "ID:" + value.casefold())
            elif kind == "ID":
                if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 /-]{2,30}", value) and sum(c.isdigit() for c in value) >= 3:
                    take(start + lead, start + lead + len(value), "ID",
                         "ID:" + re.sub(r"[^0-9A-Za-z]", "", value).upper())
            elif self._name_value(value):
                take(start + lead, start + lead + len(value), "NAME")
                if len(value.split()) >= 2:
                    self.add_person(value)
                elif len(value) > 3 and value.casefold() not in _common_words():
                    # one word, as a table's or a form's field has it: hidden wherever else it's written so
                    self._remember(_Person(f"NAME:{_fold(value)}", value, first=value, single=True))

        for m in _KEYED_VALUE.finditer(fold):
            if m.group("tag") is not None:
                if kind := key_kind(m.group("tag")):
                    put(m.start("tvalue"), copy[m.start("tvalue"):m.end("tvalue")], kind)
                continue
            if not (kind := key_kind(m.group("key"))):
                continue
            put(m.start("value"), copy[m.start("value"):m.end("value")], kind)
            if m.group("list"):
                pos = m.end()
                while (item := _LIST_ITEM.match(fold, pos)) is not None:
                    put(item.start("value"), copy[item.start("value"):item.end("value")], kind)
                    pos = item.end()
        # A key and its value on a line of their own: "- **City**: Indore", "| First Name | Fazila |"
        for m in re.finditer(r"(?m)^[ \t]*(?:[-*\u2022>]+[ \t]+)?(?:\|[ \t]*)?[*_]{0,2}(?P<key>[A-Za-z][\w ]{1,30}?)[*_]{0,2}"
                             r"[ \t]*(?::[*_]{0,2}|[*_]{0,2}:|\|)[ \t]*[*_]{0,2}(?P<value>[^|\n*]{1,80}?)[*_]{0,2}[ \t]*\|?[ \t]*$", fold):
            kind = key_kind(m.group("key"))
            value = m.group("value")
            if re.match(r"\n[ \t]*\|?[ \t]*:?-{3,}", fold[m.end():m.end() + 12]):
                continue   # a table's header: "| City | Population |" over "|---|---|"
            if kind == "NAME" and (len(value.split()) > 4 or re.search(r"[,.!?;:](?:\s|$)", value)):
                continue   # a line someone said ("Agent: Thank you, Dean."), not a name
            if kind in ("NAME", "PLACE", "DOB", "PHONE", "ID"):
                put(m.start("value"), copy[m.start("value"):m.end("value")], kind)
        # A form two or more fields to a row: "| First Name | Jane | Last Name | Doe |"
        for m in re.finditer(r"(?m)^[ \t]*\|(?:[^|\n]*\|){4,}[ \t]*$", fold):
            cells, at = [], m.start() + m.group().index("|") + 1
            for cell in m.group().strip().strip("|").split("|"):
                cells.append((at, cell))
                at += len(cell) + 1
            if len(cells) % 2:
                continue
            for (k_at, key), (v_at, value) in zip(cells[::2], cells[1::2]):
                kind = key_kind(key.strip().strip("*_: ")) if key.strip() else None
                inner = value.strip()
                if kind in ("NAME", "PLACE", "DOB", "PHONE", "ID", "ADDRESS") and inner:
                    lead = value.index(inner)
                    put(v_at + lead, copy[v_at + lead:v_at + lead + len(inner)], kind)
        # Tables: a header line names the columns; each line after it with as many cells is a row.
        lines, pos = [], 0
        for line in fold.split("\n"):
            lines.append((pos, line))
            pos += len(line) + 1
        n = 0
        while n < len(lines):
            start, line = lines[n]
            n += 1
            for sep in ("|", "\t", ",", ";"):
                if line.count(sep) < (1 if sep != "," else 2):
                    continue
                cells = line.split(sep)
                kinds = {k: key_kind(c.strip().strip("\"'*_ ").replace("\\_", "_")) for k, c in enumerate(cells)}
                columns = [k for k, kind in kinds.items() if kind]
                if not any(kinds[k] in ("NAME", "ADDRESS", "PHONE", "DOB") for k in columns):
                    columns = [k for k in columns if kinds[k] != "PLACE"]   # a table of towns, not of people
                if not columns:
                    continue
                while n < len(lines):
                    row_start, row = lines[n]
                    if row.count(sep) < line.count(sep) or (sep != "," and row.count(sep) != line.count(sep)):
                        if re.fullmatch(r"[\s|:+-]*", row) and row.strip():   # a markdown table's rule
                            n += 1
                            continue
                        break
                    offsets, at = [], row_start
                    for cell in row.split(sep):
                        offsets.append((at, cell))
                        at += len(cell) + len(sep)
                    for k in columns:
                        at, cell = offsets[k]
                        quote = cell.strip()[:1]
                        inner = cell.strip()
                        lead = cell.index(inner) if inner else 0
                        if quote in "\"'" and len(inner) > 1 and inner[-1] == quote:
                            inner, lead = inner[1:-1], lead + 1
                        put(at + lead, copy[at + lead:at + lead + len(inner)], kinds[k])
                    n += 1
                break

    @staticmethod
    def _username(m: re.Match, fold: str, take) -> bool:
        group = "handle" if m.group("handle") else "value"
        value, start = m.group(group), m.start(group)
        # "User Name: John Smith" is a person's name, for the names to find
        if group == "value" and value[:1].isupper() and value[1:].islower() and \
                re.match(r"[ \t]+[A-Z][a-z]", fold[m.end(group):m.end(group) + 3]):
            return False
        if group == "value" and value.casefold() in _common_words() and not any(c.isdigit() for c in value):
            return False   # "the username is required", "Username: The ..."
        return take(start, start + len(value), "ID", "ID:" + value)

    @staticmethod
    def _phone(m: re.Match, take) -> bool:
        start = m.start("value") if "value" in m.re.groupindex else m.start()
        digits = re.sub(r"\D", "", m.group()[start - m.start():])
        if m.group()[:1] == "0" and m.re is _TRUNK_PHONE and not 10 <= len(digits) <= 11:
            return False
        least = 7 if m.re is _LABELLED_PHONE else 9   # 8277-3622 after "Phone Number:", as Singapore's are
        return least <= len(digits) <= 22 and take(start, m.end(), "PHONE", "PHONE:" + digits)

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

    def _known_names(self, fold: str, take, typed: bool, guesses: bool = False) -> None:
        """Where the people known are written; ``guesses``: the name finder's guesses, and only them."""
        low = fold.casefold()

        def matches(pattern: re.Pattern, word: str):
            """The pattern's matches, looked for only around where its word is written."""
            if not word:
                yield from pattern.finditer(fold)
                return
            pos = 0
            at = low.find(word)
            while at >= 0:
                start, end = max(pos, at - 80), min(len(fold), at + len(word) + 80)
                while start < end and (m := pattern.search(fold, start, end)) is not None:
                    if m.end() > m.start():
                        yield m
                    start = pos = max(m.end(), m.start() + 1)
                at = low.find(word, max(at + 1, pos))

        for pattern, person, word, guess in self._compiled():
            if guess != guesses or (word and word not in low):
                continue
            for m in matches(pattern, word):
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
                    if before and before.group(1)[0].isupper() and before.group(1).casefold() not in self._v.not_names \
                            and not guesses:   # the found names have had their turn
                        continue
                    if not written[0].isupper() and (len(written) < 4 or written.casefold() in _WORD_SURNAMES):
                        continue
                # "Priya" known, then "Priya Natarajan": the surname after it goes with it
                after = re.match(r"[ \t]+([A-Z][a-z]+(?:-[A-Z][a-z]+)?)(?![\w'-])", fold[m.end():m.end() + 40])
                if after and written[0].isupper() and after.group(1).casefold() not in self._v.not_names and \
                        not _business_after(fold, m.end() + after.end(), self._v, typed) and \
                        take(m.start(), m.end() + after.end(), "NAME"):
                    continue
                take(m.start(), m.end(), "NAME")

    # -- names it finds --------------------------------------------------------

    def _found_names(self, copy: str, fold: str, take, typed: bool) -> None:
        toks = _tokens(fold, copy)
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
            # Rhys Ian Mills, CIRINO CARLA CORDOBA: a listed first name or surname right before the name found
            first = found.first_tok
            if found.key and first > 0 and first - 1 >= i - 1 and toks[first - 1].case == toks[first].case and \
                    toks[first - 1].case in ("title", "caps") and not toks[first - 1].dot and \
                    _NAME_GAP.fullmatch(_gap(fold, toks, first - 1)) and \
                    toks[first - 1].fold not in self._v.not_names and toks[first - 1].fold not in _HONORIFICS and \
                    _name_listed(toks[first - 1].fold, surnames) and not _wordlike(toks[first - 1].fold) and \
                    toks[first - 1].fold not in _common_words():
                found = _Found(first - 1, found.last_tok, found.key, copy[toks[first - 1].start:toks[found.last_tok].end],
                               found.person)
            start, stop = toks[found.first_tok].start, toks[found.last_tok].end
            if toks[found.last_tok].case == "initial" and toks[found.last_tok].dot:
                stop += 1
            if take(start, stop, "NAME", found.key, found.display, over_known=True) and found.person is not None:
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
                if not (toks[k].case == "initial" or name_word(k, None if mixed else case)) or not near(k) or \
                        (toks[k].dot and toks[k].case != "initial" and len(toks[k].word) > 2):
                    break   # no name goes on past a period ending a sentence ("María Ángeles. I've")
                k += 1
            if not ends:
                return None
            end = ends[-1] if longer else ends[0]
            return [toks[m].word for m in range(j, end) if toks[m].fold not in _PARTICLES], end

        def ok(a: int, b: int) -> bool:
            # an acronym before a word in title case is no name: "API Key", "CRM Lead"
            if b > a and toks[a].case == "caps" and len(toks[a].word) <= 4 and \
                    any(toks[k].case == "title" for k in range(a + 1, b + 1)):
                return False
            # a city before its state or ZIP: "Oakland, CA", "Leeds, LS1 4AP"
            if re.match(rf"[ \t]*,[ \t]*(?:{_STATE}(?:[ \t]+{_ZIP}|,[ \t]*(?:USA|US|U\.S\.A?\.?|United States))"
                        rf"|[A-Z]{{1,2}}\d[A-Z\d]?[ ]\d[A-Z]{{2}})(?![\w])",
                        copy[toks[b].end:toks[b].end + 20]) and \
                    not re.search(r"(?i)name[ \t]*:?[ \t]*\Z", fold[max(0, toks[a].start - 20):toks[a].start]):
                return False
            words = [toks[k].fold for k in range(a, b + 1)]
            if any(f"{x} {y}" in _FIRMS for x, y in zip(words, words[1:])) or tuple(words) in self._businesses:
                return False
            # Only everyday words, none a name: "Driver Exclusion", "ADDITIONAL LIVING", "Stale Bill"
            if all(toks[k].case == "initial" or (toks[k].fold in _common_words() and not _name_listed(toks[k].fold, surnames))
                   for k in range(a, b + 1)):
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
            if j < len(toks) and (name_word(j) or (toks[j].fold in _WORD_GIVEN and toks[j].case in ("title", "caps"))):
                more = rest(j + 1, toks[j].case, True, lambda k: True, True) if near(j) else None
                if more and ok(j, more[1]):
                    return found(j, more[1], toks[j].word, more[0], toks[more[1]].word, True)
                # Mr. Alan Gross, Ms. Sarah Day: after a title and a first name, a capitalized word ending the
                # name is its surname, everyday word or not
                k = j + 1
                if k < len(toks) and near(j) and toks[k].case == toks[j].case and len(toks[k].word) > 1 and \
                        (toks[j].fold in _GIVEN or toks[j].fold in _given_names()) and \
                        toks[k].fold not in self._v.business and toks[k].fold not in _HONORIFICS and \
                        not (k + 1 < len(toks) and near(k) and toks[k + 1].case in ("title", "caps")) and ok(j, k):
                    return found(j, k, toks[j].word, [], toks[k].word, True)
                if ok(j, j):
                    return _Found(i, j, None, None, None)
            return None
        # The Okonkwo Family Trust; Thandiwe Okonkwo Revocable Trust; Dummerton Retirement Trust; ... IRA
        j = i
        while j - i < 4 and j + 1 < len(toks) and (name_word(j) or (j > i and toks[j].case == "initial")) and \
                not (toks[j].dot and toks[j].case != "initial") and near(j):
            nxt = toks[j + 1]
            if (nxt.fold in _FAMILY or nxt.fold == "ira" or (nxt.fold in ("family", "retirement") and j + 2 < len(toks)
                                                              and toks[j + 2].fold in ("trust", "foundation", "plan"))) \
                    and not all(toks[k].fold in _common_words() and not _name_listed(toks[k].fold, surnames)
                                for k in range(i, j + 1)):
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
        def alone() -> _Found | None:
            """A name of one word: a first name ("Hello Sarah,", "thank Kathy for"), or after a label any
            word that's no everyday word ("Last Name: Ritter").  Not a place's name, not in a run of
            capitalized words (a heading), and not the start of a business's name."""
            if t.case not in ("title", "caps") or len(t.word) < 2 or t.fold in self._v.not_names or \
                    t.fold in _PLACES or (t.case == "caps" and not cued) or \
                    re.search(r"'(?:re|ve|m|d|ll|t)$", t.fold) or \
                    (len(t.word) < 3 and t.fold not in _GIVEN) or \
                    (re.match(r"[^\W_]", fold[t.end:t.end + 1]) and t.start and re.match(r"[^\W_]", fold[t.start - 1])):
                return None   # a contraction (You're), a fragment of a code (5Au4), a place
            # "Last Name: Hill", "the last name is Tan": after a label that says it's a person's name, any
            # capitalized word ending the field or the sentence but a stop word
            strong = cued and t.case in ("title", "caps") and t.fold not in self._v.stop and \
                re.search(r"(?i)(?:first|last|sur|family|given|middle|maiden)[ \t_]*name[\s*_]*(?::|is|-)?[\s*_]*\Z",
                          fold[max(0, t.start - 40):t.start]) and \
                re.match(r"[ \t*_]*(?:[,.;|\n]|$)", fold[t.end:t.end + 4])
            if strong:
                pass
            elif cued:
                # a word ("Name: Total") is no name; a listed name that's a rare word too is ("Last Name: Begum")
                if (t.fold in _common_words() or (_wordlike(t.fold) and t.fold not in _given_names() and
                                                  t.fold not in _surname_list())) and \
                        t.fold not in _GIVEN and t.fold not in _SURNAMES:
                    return None
            elif t.case != "title" or t.fold in _WORD_SURNAMES or \
                    not (t.fold in _GIVEN or (t.fold in _given_names() and not _wordlike(t.fold))):
                return None
            if re.match(r"[ \t]*(?:&|and[ \t])", fold[t.end:t.end + 5]) and \
                    not ((t.fold in _GIVEN or cued) and re.match(r"[ \t]+and[ \t]+[a-z]", copy[t.end:t.end + 12])):
                return None
            if i > 0 and toks[i - 1].case in ("title", "caps") and near(i - 1) and not cued and \
                    toks[i - 1].fold not in _GREETINGS and not (toks[i - 1].dot and toks[i - 1].case != "initial"):
                # "Provided Rahel with": an everyday word starting the line before it
                p = toks[i - 1]
                line_start = re.search(r"(?:^|\n)[ \t]*(?:[-*\u2022]|\d{1,2}[.)])?[ \t]*(?:\*\*|__)?[ \t]*\Z", fold[:p.start])
                if not (line_start and p.fold in _common_words() and not _name_listed(p.fold, surnames) and
                        f"{p.fold} {t.fold}" not in _FIRMS):
                    return None
            if i + 1 < len(toks) and toks[i + 1].case in ("title", "caps") and near(i) and not t.dot:
                return None
            if not (ok(i, i) or (strong and not _business_after(fold, t.end, self._v, typed))):
                return None
            # hidden wherever else it's written, as it's written here: "Hi Margaret," ... "notify Margaret"
            single = t.case == "title" and len(t.word) > 3 and t.fold not in _common_words() and \
                not _wordlike(t.fold) and t.fold not in _WORD_GIVEN | _WORD_SURNAMES | self._v.not_names
            return _Found(i, i, None, None, _Person(f"NAME:{t.fold}", w(i), first=t.word, single=True) if single else None)

        # Mark Tiffany Fuentes: a first name that's an everyday word, before a name
        if t.fold in _WORD_GIVEN and t.case in ("title", "caps") and not t.dot and near(i) and \
                ((toks[i + 1].case == "initial" and toks[i + 1].dot) or
                 (toks[i + 1].case == t.case and
                  (toks[i + 1].fold in _GIVEN or toks[i + 1].fold in _given_names() or
                   toks[i + 1].fold in _SURNAMES or toks[i + 1].fold in surnames or toks[i + 1].fold in _top_surnames() or
                   (toks[i + 1].fold not in _common_words() and _surname_like(toks[i + 1].fold, surnames))))):
            more = rest(i + 1, t.case, True, lambda k: _surname_like(toks[k].fold, surnames), True)
            if more and ok(i, more[1]):
                return found(i, more[1], t.word, more[0], toks[more[1]].word, True)
        # "Thank you, Dean.", "No problem, Gabino.": a capitalized word after a greeting, before punctuation
        if t.case == "title" and len(t.word) > 2 and t.fold not in self._v.not_names and t.fold not in _PLACES and \
                (t.fold in _WORD_GIVEN or t.fold in _GIVEN or t.fold in _given_names() or t.fold not in _common_words()) and \
                re.match(r"[ \t]*[,.!?]", fold[t.end:t.end + 2]) and \
                re.search(r"(?i)(?:^|[^\w])(?:thank you|thanks|hello|hi|hey|dear|welcome|sorry|bye|goodbye|morning|afternoon"
                          r"|evening|congratulations|no problem|of course|sure|great|okay|ok|yes|no)[,!]?[ \t]+\Z",
                          fold[max(0, t.start - 40):t.start]) and ok(i, i):
            return _Found(i, i, None, None, None)
        # "I understand your concern, Liana.": a first name called by, after a comma, ending the sentence
        if t.case == "title" and len(t.word) > 2 and t.fold not in self._v.not_names and t.fold not in _PLACES and \
                (t.fold in _GIVEN or (t.fold in _given_names() and not _wordlike(t.fold))) and \
                re.search(r"[^\W\d_],[ \t]+\Z", fold[max(0, t.start - 3):t.start]) and \
                re.match(r"[ \t]*[.!?](?:[ \t]|$)", fold[t.end:t.end + 2]) and ok(i, i):
            return _Found(i, i, None, None, None)
        if t.fold in self._v.not_surnames:
            return None
        if t.dot and t.case != "initial":
            return alone()
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

            # Gustavo G. Cases, Carolyn S. Day: a common first name, an initial, and any capitalized word
            if (t.fold in _GIVEN or t.fold.split("-")[0] in _GIVEN) and t.case == "title" and \
                    toks[i + 1].case == "initial" and toks[i + 1].dot and i + 2 < len(toks) and near(i + 1) and \
                    toks[i + 2].case == "title" and len(toks[i + 2].word) > 2 and \
                    toks[i + 2].fold not in self._v.business and toks[i + 2].fold not in _HONORIFICS and \
                    not (i + 3 < len(toks) and near(i + 2) and toks[i + 3].case in ("title", "caps")) and ok(i, i + 2):
                return found(i, i + 2, t.word, [toks[i + 1].word], toks[i + 2].word, True)
            # Ashley Mary Good, Julius Rosalinde Killer: two first names, then any capitalized word for the surname
            def first_name(k: int) -> bool:
                f = toks[k].fold
                return toks[k].case == "title" and not toks[k].dot and f not in self._v.not_names and \
                    f not in _PLACES and (f in _GIVEN or (f in _given_names() and not _wordlike(f) and
                                                          f not in _common_words()))
            if first_name(i) and i + 2 < len(toks) and first_name(i + 1) and near(i + 1) and \
                    toks[i + 2].case == "title" and len(toks[i + 2].word) > 2 and "'" not in toks[i + 2].word and \
                    toks[i + 2].fold not in self._v.not_surnames and toks[i + 2].fold not in _PLACES and \
                    not (i + 3 < len(toks) and near(i + 2) and toks[i + 3].case in ("title", "caps")) and ok(i, i + 2):
                return found(i, i + 2, t.word, [toks[i + 1].word], toks[i + 2].word, True)
            # Avery K. Mockridge: a common first name
            if t.fold in _GIVEN or t.fold.split("-")[0] in _GIVEN:
                more = rest(i + 1, t.case, True, lambda k: _surname_like(toks[k].fold, surnames), True)
                if (name := named(more, True)) is not None:
                    return name
            # Priya Patel; Thandiwe Okonkwo once an Okonkwo is known: a common or known surname, after a word that
            # can be a first name ("Call Priya Patel" is Priya Patel)
            if not (t.fold in _common_words() and not _name_listed(t.fold, surnames) and
                    (toks[i + 1].fold in _GIVEN or toks[i + 1].fold in _given_names()) and
                    toks[i + 1].fold not in _SURNAMES):
                name = named(rest(i + 1, t.case, True, lambda k: toks[k].fold in _SURNAMES or toks[k].fold in surnames,
                                  True), True)
                if name is not None:
                    e = name.last_tok
                    if toks[e].fold not in _SURNAMES and near(e) and \
                            (toks[e + 1].case == "initial" or name_word(e + 1)) and toks[e].fold in self._lone_names():
                        # "Consuelo Rubén R. Camacho", "I'm Camille Adam" with "Rubén" or "Camille" known alone: a
                        # name of one word may be a first or a middle name, so the name may go on past it.  The
                        # longer of the names found without it, from here or from that word, if either goes on.
                        fewer = surnames - {toks[e].fold}
                        longer = [n for n in (self._name_at(copy, fold, toks, i, cued, typed, fewer),
                                              self._name_at(copy, fold, toks, e, False, typed, fewer))
                                  if n is not None and n.last_tok > e]
                        if longer:
                            return max(longer, key=lambda n: (n.last_tok, -n.first_tok))
                    return name
            # After a label or cue, before "as an LLC member", or in what the user typed: any capitalized words
            if t.case == "title" or cued or typed:
                more = rest(i + 1, t.case, False, lambda k: True, True)
                after = more is not None and self._v.after_cue.match(fold, toks[more[1]].end) is not None
                # "Calder Ridge II": a fund, numbered
                numbered = more is not None and more[1] + 1 < len(toks) and near(more[1]) and \
                    toks[more[1] + 1].fold in _ROMAN and toks[more[1] + 1].case in ("caps", "initial") and \
                    not any(toks[k].case == "initial" for k in range(i + 1, more[1]))
                # Only everyday words, none of them a name ("Gallery Owner", "Hazardous Substance"): no name
                everyday = more is not None and all(
                    toks[k].fold in _common_words() and toks[k].fold not in _GIVEN and
                    not _surname_like(toks[k].fold, surnames) for k in range(i, more[1] + 1)
                    if toks[k].case != "initial")
                if (cued or after or (typed and t.case == "title")) and not numbered and not everyday:
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
            # Amelie Lage, Heike Franz-Josef Gierschner: a first name from anywhere, then a surname from anywhere
            given = _given_names()
            if t.fold in given or t.fold.split("-")[0] in given:
                # a surname that's an everyday word or a place ("Calder Ridge") only after a common first name
                # a first name that's nearly a word ("Stale") needs a surname that's no word at all
                wordy = _wordlike(t.fold) and _wordlike(t.fold.split("-")[0])
                more = rest(i + 1, t.case, True, lambda k: _surname_like(toks[k].fold, surnames) and
                            (toks[k].fold not in _WORD_SURNAMES or (toks[k].fold in _top_surnames() and not wordy)) and
                            (toks[k].fold not in _common_words() or (toks[k].fold in _common_surnames() and not wordy) or
                             _surname_list().get(toks[k].fold, 9) < 3.5),
                            True)
                if (name := named(more, True)) is not None:
                    return name
        if near(i) and t.case in ("title", "caps") and not t.dot and t.fold not in self._v.not_names:
            n = toks[i + 1]
            listed = t.fold in _GIVEN or t.fold in _SURNAMES or (_name_listed(t.fold, surnames) and not _wordlike(t.fold))
            # Micheletto G. Ligorio, Dawn B. Neal: a capitalized word, an initial, and a surname-like word
            if n.case == "initial" and n.dot and i + 2 < len(toks) and near(i + 1) and \
                    toks[i + 2].case == t.case and not toks[i + 2].dot and len(toks[i + 2].word) > 1 and \
                    toks[i + 2].fold not in self._v.not_names and \
                    (listed or t.fold not in _common_words()) and _surname_like(toks[i + 2].fold, surnames) and \
                    not (t.fold in _common_words() and toks[i + 2].fold in _common_words()) and ok(i, i + 2):
                return found(i, i + 2, t.word, [n.word], toks[i + 2].word, True)
            # Sarah K.: a first name and an initial; "Martyn J" ending a line
            if n.case == "initial" and (n.dot or re.match(r"[ \t]*(?:\n|$)", fold[n.end:n.end + 2])) and listed and (t.fold in _given_names() or t.fold in _GIVEN) and \
                    not (i + 2 < len(toks) and near(i + 1) and toks[i + 2].case in ("title", "caps")) and ok(i, i + 1):
                return _Found(i, i + 1, None, None, None)
        # MISTY LEE DEAN, YOLANDA RIOS: capitals, a first name then a surname that's no everyday word
        if t.case == "caps" and near(i) and toks[i + 1].case == "caps" and not t.dot and \
                (t.fold in _GIVEN or t.fold in _WORD_GIVEN or (t.fold in _given_names() and not _wordlike(t.fold))):
            more = rest(i + 1, "caps", False, lambda k: _surname_like(toks[k].fold, surnames) and
                        (toks[k].fold not in _common_words() or toks[k].fold in _top_surnames()), True)
            if more and ok(i, more[1]):
                return found(i, more[1], t.word, more[0], toks[more[1]].word, True)
        # Bernardini-Vezzali, Noguera-Castrillo: a double surname alone, each half a listed surname
        if t.case == "title" and "-" in t.word and not (near(i) and toks[i + 1].case in ("title", "caps")):
            halves = t.fold.split("-")
            if len(halves) == 2 and all((h in _SURNAMES or h in _surname_list() or h in _top_surnames()) and
                                        h not in _common_words() and len(h) > 2 for h in halves) and ok(i, i):
                return _Found(i, i, None, None, None)
        # the Le Gall family, the Scholz family
        if t.case == "title" and i > 0 and toks[i - 1].fold == "the":
            j = i
            while j + 1 < len(toks) and j - i < 2 and near(j) and toks[j + 1].case == "title":
                j += 1
            if j + 1 < len(toks) and near(j) and toks[j + 1].fold == "family" and toks[j + 1].case == "lower" and \
                    all(t2.fold not in self._v.not_names and _surname_like(t2.fold, surnames) for t2 in toks[i:j + 1]) and \
                    not all(t2.fold in _common_words() for t2 in toks[i:j + 1]):
                return _Found(i, j, None, None, None)
        # Mockridge, Avery K.
        # Not a greeting or an everyday word before the comma ("Congratulations, Cory"), not a place either
        # side ("Ain, France", "Jones, NASDAQ" isn't a name turned round), and both written alike
        if i + 1 < len(toks) and _COMMA_GAP.fullmatch(_gap(fold, toks, i)) and name_word(i) and \
                t.fold not in _GREETINGS and t.fold not in _PLACES and toks[i + 1].fold not in _PLACES and \
                toks[i + 1].fold not in _COUNTRY_WORDS and toks[i + 1].case == t.case and \
                toks[i + 1].word not in _STATE_NAMES and \
                not re.match(r"[ \t]+(?i:county|parish|borough|province|state|region|district)\b",
                             fold[toks[i + 1].end:toks[i + 1].end + 12]) and \
                not (t.fold in _common_words() and t.fold not in _common_surnames() and t.fold not in _SURNAMES):
            n = toks[i + 1]
            if name_word(i + 1) and not n.dot and \
                    (n.fold in _GIVEN or t.fold in _SURNAMES or t.fold in surnames or
                     ((cued or typed) and not (t.fold in _common_words() and t.fold not in _common_surnames()) and
                      n.case != "caps") or
                     (n.fold in _given_names() and t.fold in _surname_list())):
                end, middles = i + 1, []
                while end + 1 < len(toks) and near(end) and (toks[end + 1].case == "initial" or
                                                             name_word(end + 1, n.case)) and len(middles) < 2:
                    end += 1
                    middles.append(w(end) + ("." if toks[end].case == "initial" else ""))
                if ok(i, end):
                    return found(i, end, n.word, middles, t.word, not typed or n.fold in _GIVEN,
                                 " ".join([w(i + 1), *middles, w(i)]))
        return alone()


# The name it had in Snowman.
PersonalInfoRedactor = Redactor
