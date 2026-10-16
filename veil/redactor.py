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


def _surname_like(word: str, known: set[str]) -> bool:
    """Whether ``word`` (folded) can be a surname: one listed or known, or no everyday English word."""
    first = word.split("-")[0]
    return word in _SURNAMES or word in _WORD_SURNAMES or word in known or first in _surname_list() or \
        first in _common_surnames() or word not in _common_words()


# First names that are everyday words too: a name only before a surname ("Mark Tiffany Fuentes", "Will Smith").
_WORD_GIVEN = _words("mark will grant june may rose faith hope joy dawn april summer autumn bill bob pat sue ray earl "
                     "dean frank rich sky iris ivy holly daisy pearl ruby amber crystal destiny honor lily jade")
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
_HONORIFICS = _words("mr mrs ms miss mx dr prof sir dame agent captain capt officer detective inspector sergeant "
                     "sgt lieutenant lt judge coach nurse pastor rev reverend rabbi imam professor")
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
    r"(?<!product\s)(?<!chemical\s)(?<!substance\s)(?<!instrument\s)(?<!item\s)(?<!brand\s)(?<!project\s)(?<!event\s)(?<!venue\s)(?<!vessel\s)(?<!ship\s)(?<!plan\s)(?<!program\s)(?<!course\s)(?<!trade\s)(?<!model\s)(?<!device\s)(?<!drug\s)(?<!medication\s)(?<!domain\s)(?<!host\s)(?<!server\s)(?<!street\s)(?<!city\s)(?<!country\s)(?<!state\s)(?<!branch\s)(?<!team\s)(?<!campaign\s)name"
    r"|zip\s+code|signatory|signature|regards|sincerely|cordially|respectfully"
    r"|(?:beneficial\s+)?owner|(?:account\s+)?holder|executor|executrix|administrator|guardian|conservator"
    r"|(?:partnership\s+)?representative|designated\s+individual|attorney(?:-in-fact)?|poa)"
    r"[ \t]*(?:[:.,-][ \t]*)?(?:\n[ \t]*){0,2}"
    r"|(?:named|members?|partners?|limited\s+partner|general\s+partner|investor|shareholder|stockholder"
    r"|beneficiary|trustee|custodian|grantor|spouse|client|contact(?:\s+person)?|attn|attention|dear|fbo|c/o"
    r"|for\s+the\s+benefit\s+of|(?:prepared|issued|mailed|sent|registered)\s+(?:for|to)|prepared\s+by"
    r"|registration|signed{extra})"
    r"(?:'s)?[ \t]*(?:[:.,-][ \t]*)?(?:/s/[ \t]*)?"
    r"|(?:by|to|from|re|cc|bcc)[ \t]*:[ \t]*(?:/s/[ \t]*)?"
    # a party's role, then a colon: "Shipper: Tassilo M. Hess", "Borrower: Pedro"
    r"|(?:shipper|consignee|notify\s+party|payer|payee|remitter|applicant|co-?applicant|borrower|co-?borrower"
    r"|guarantor|insured|policy\s*holder|patient|purchaser|buyer|seller|vendor|lessee|lessor|tenant|landlord"
    r"|employee|customer|claimant|sender|recipient|debtor|creditor|witness|physician|doctor|assigned\s+to"
    r"|created\s+by|modified\s+by|reported\s+by|approved\s+by|reviewed\s+by|requested\s+by|user|agent)"
    r"(?:'s)?[ \t]*:[ \t]*(?:\*\*[ \t]*)?)\Z")
# The last word of each of those: the label is looked for only after one of them.
_CUE_ENDS = _words("""
name code signatory signature regards sincerely cordially respectfully owner holder executor executrix administrator
guardian conservator representative individual attorney attorney-in-fact poa named member members partner partners
investor shareholder stockholder beneficiary trustee custodian grantor spouse client contact person attn attention
dear fbo o of for to registration signed by from re cc bcc s
shipper consignee party payer payee remitter applicant co-applicant coapplicant borrower co-borrower coborrower
guarantor insured holder policyholder patient purchaser buyer seller vendor lessee lessor tenant landlord employee
customer claimant sender recipient debtor creditor witness physician doctor user agent
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
    rf"|rtn|iban|(?:credit|debit)\s*card(?:\s*{_NO})?|card\s*{_NO}"
    r"|(?:visa|mastercard|amex|american\s+express|discover|card)\s+ending(?:\s+in)?)"
    # "Account Number (last 4): 4321"
    r"(?:[ \t]*\([^()\n]{0,15}\))?")
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
    rf"|aadhaa?r(?:\s*{_NO})?")
_DOB_LABEL = (r"(?:d\.?\s?o\.?\s?b\b\.?|date[\s_\\]*of[\s_\\]*birth|birth[\s_\\]*date|birthday|born(?:\s+on)?)"
              r"(?:\s+of\s+(?:the\s+)?(?:partner|member|investor|owner|holder|spouse|beneficiary))?"
              r"(?:[ \t]*\([^()\n]{0,20}\))?")
_MONTHS = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DATE = (r"\d{1,2}[/.-]\d{1,2}[/.-](?:\d{4}|\d{2})|\d{1,2}[ ]\d{1,2}[ ]\d{4}|\d{4}[/.-]\d{1,2}[/.-]\d{1,2}"
         r"|(?:19|20)\d{6}(?!\d)"
         rf"|{_MONTHS}[ \t]+\d{{1,2}}(?:st|nd|rd|th)?,?[ \t]+\d{{4}}"
         rf"|\d{{1,2}}(?:st|nd|rd|th)?[ \t/.-]*{_MONTHS},?[ \t/.-]*\d{{2,4}}")
_SEP = (r"[\"'*\\_]*[ \t]*(?:\([^()\n]{0,20}\)[ \t]*)?"
        r"(?:[:#.=|\u2013-][ \t]*|is[ \t]+|of[ \t]+|was[ \t]+|\((?:e\.g\.,?|i\.e\.,?)?[ \t]*)?(?:\*\*(?=\s))?[\"']*[ \t]*"
        r"(?:\n[ \t]*){0,2}")
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
    re.compile(rf"{_PHONE_LABEL}[ \t]*\**[ \t]*(?P<value>\+?[\d(][\d ().-]{{6,22}}\d{_EXTENSION}){_END}"),
    # A national number with its trunk 0, as the UK and Europe write them: 0800 123 4567, 020-7946-0958
    re.compile(rf"(?<![\w$.,+/:-])0\d{{1,4}}(?:[ -]\d{{2,4}}){{2,4}}{_EXTENSION}{_END}"),
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
                       "Rise Parade Yard Embankment Grange Rue").split()
_ADDRESS_END = (r"(?=[ \t]*(?:[,;|*\n\"'<>()/:\\?!}+]|$|\.(?!\w)|(?:Suite|Ste|Apt|Apartment|Unit|Floor|\#)\b)"
                r"|[ \t]+(?:and|was|is|in|for|to|with|as|has|have|had|where|which|on|at|from|since|by)\b)")
# A street name of one word with its kind in it, before or after the number: "Xaviweg 5", "36 Ringtorget".
_EURO_STREET = (r"[A-Z\u00c0-\u024f][\w\u00c0-\u024f'-]*(?i:strasse|stra\u00dfe|str\.|gasse|weg|platz|allee|ring|damm"
                r"|straat|laan|gracht|plein|kade|singel|dijk|steeg|dreef|boulevard|markt|hof|gata|gatan|vagen|v\u00e4gen"
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
    r"|Camino|Cuesta|Alameda|Avinguda|Passatge|Pra\u00e7a|Pra\u00e7a|Borgo|Viale|Salita|Vico)(?:[ \t]+(?:de|del|della|di|da|do|dos|la|las"
    r"|los|le|les|du|des)?[ \t]*[A-Z\u00c0-\u024f][\w\u00c0-\u024f'.-]*){1,4},?[ \t]+\d{1,5}[a-z]?(?![\w])"
    rf"|(?<![\w-])\d{{3,5}}(?:-\d{{4}})?[ \t]+(?:[A-Z][\w'.-]*[ \t]+){{0,3}}[A-Z][\w'.-]*,[ \t]+"
    rf"(?:{'|'.join(_COUNTRIES)})\b")
# "Mailing address: 88 Kearny": the rest of the line, when it has a number.
_ADDRESS_LABEL = re.compile(r"(?<![^\W\d_])(?<!ip\s)(?<!ipv4\s)(?<!ipv6\s)(?<!mac\s)(?<!email\s)(?<!e-mail\s)"
                            r"(?<!web\s)(?<!wallet\s)(?<!bitcoin\s)(?<!crypto\s)(?<!server\s)(?<!network\s)"
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
    rf"(?:(?<![\w$.,/-])|(?<=[A-Za-z\"],)|(?<=Floor, )|(?<=FLOOR, )|(?<=Floor )|(?<=Fl\. ))(?:\d{{1,6}}(?:[A-Za-z]|-\d{{1,5}}|-[A-Za-z]|[ ]1/2)?"
    rf"|{'|'.join(_NUMBER_WORDS)}),?[ \t]+"
    rf"(?:{_DIRECTION}[ \t]+)?(?:"
    rf"(?:(?:[A-Z][\w'.-]*|\d+(?:st|nd|rd|th))[ \t]+){{1,4}}"
    rf"(?:(?:{'|'.join(_STREET_SUFFIX + [s.upper() for s in _STREET_SUFFIX])})\.?(?![\w])"
    rf"|(?:{'|'.join(_STREET_SUFFIX_MORE + [s.upper() for s in _STREET_SUFFIX_MORE])})(?![\w]){_ADDRESS_END})"
    r"|(?:[a-z][\w'.-]*[ \t]+){1,3}(?:street|st|avenue|ave|road|rd|boulevard|blvd|lane|ln|drive|court|ct|place"
    r"|parkway|pkwy|highway|hwy|terrace|circle)\.?(?![\w])"
    r"|(?i:el[ \t]+camino[ \t]+real|(?:alameda|avenida|calle|camino|via|rue|avenue[ \t]+of[ \t]+the|boulevard|bd"
    r"|chemin|all\u00e9e|allee|impasse|place|quai|cours|pasaje|paseo|plaza|carrer|ronda|rambla|traves\u00eda|viale"
    r"|piazza|corso|vicolo|strada|largo|rua|avenue|contrada|travessa|glorieta|rotonda|stretto|callej\u00f3n|callejon"
    r"|cuesta|ronda|rambla|avinguda|passatge|borgo|salita|vico|traves\u00eda)"
    r"(?:[ \t]+[a-z][\w'.-]*){1,4})|Broadway|BROADWAY)"
    rf"(?:[ \t]+{_DIRECTION}(?![\w]))?"
    rf"(?:,?[ \t]*{_UNIT}\.?[ \t]*\#?[A-Za-z0-9-]+|,?[ \t]*\d+(?:st|nd|rd|th)[ \t]+(?:Floor|FLOOR|Fl)\.?)?"
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
_CITY_WORDS = r"(?:[A-Z][\w'\u00c0-\u024f.-]*[ \t]+){0,2}[A-Z][\w'\u00c0-\u024f.-]*"
_POSTAL = (r"(?:\d{3}[ ]\d{2}(?![\d])|\d{4,6}(?:-\d{3,4})?|[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z][ ]?\d[ABCEGHJ-NPRSTV-Z]\d"
           r"|(?:[A-Z]{1,2}\d[A-Z\d]?|GIR)[ ]\d[ABD-HJLNP-UW-Z]{2})")
# What may follow a street, piece by piece: ", 19821", ", New Shrewsbury", ", London, EC4M 2JR, UK", and lines
# under it that are the rest of the address ("Toronto, ON M3H 2T6", "Canada").
_TAIL_PIECE = re.compile(
    rf",?[ \t]*{_UNIT}\.?[ \t]*\#?[\w-]{{1,8}}(?![\w-])"
    rf"|,[ \t]*(?:{_POSTAL}(?:[ \t]+{_CITY_WORDS})?|{_STATE}[ \t]*{_ZIP}"
    rf"|(?!{_UNIT}\b){_CITY_WORDS}(?:,?[ \t]+{_STATE})?(?:,?[ \t]+{_POSTAL})?)"
    rf"(?=[ \t]*(?:[,;|*\n\"'<>()/:?!}}+]|$|\.(?!\w)|[ \t]+(?:and|as|was|is|for|to|with|in|on)\b))"
    rf"|[ \t]*\n[ \t]*(?:{_UNIT}\.?[ \t]*\#?[\w-]{{1,8}}"
    rf"|{_CITY_WORDS},?[ \t]+(?:{_STATE}|[A-Z][\w'.-]+(?:[ \t]+[A-Z][\w'.-]+)?),?[ \t]+{_POSTAL}"
    rf"|{_CITY_WORDS},?[ \t]+{_POSTAL}|{_POSTAL}[ \t]+{_CITY_WORDS}|(?:{_COUNTRY_NAMES})"
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
                       rf"|(?:{_PERSON_ROLES})(?:[ _-]?(?:name|full[ _-]?name))?|first|last|surname|forename|given")
# Keys with "name" in them that name no person.
_NOT_PERSON_KEY = re.compile(r"(?i)user[ _-]?name|login|company|business|bank|product|file|instrument|org|firm|fund"
                             r"|entity|brand|item|project|event|venue|vessel|ship(?!per)|plan\b|program|course|trade"
                             r"|model|device|drug|medic|host|server|domain|street|city|country|state|branch|team|account[ _-]?name"
                             r"|campaign|group|dept|department|unit|category|type|code|tag|field|column|table|key|app"
                             r"|service|insurer|issuer|carrier|vendor|supplier|merchant|provider|partner|agency|office"
                             r"|institution|school|hospital|facility|site|store|shop|location|property|building|asset")
# Fields that hold a street address, by their key: "street_address", "StreetAddress", "Mailing Address".
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
    r"(?:(?!\.\s)[^\n;()\[\]{}<>\"]){0,40}?[ \t:(\",]"
    r"(?P<value>(?=[A-Za-z0-9-]*\d)[A-Za-z0-9]+(?:-[A-Za-z0-9]+){0,3})(?![\w-])")
# An ID by its shape alone: one to four capital letters and six to ten digits (EMP286818, G4830770), not an amount
# in a currency (USD52482349) and not an ISIN (US1234567890).
_SHAPED_ID = re.compile(r"(?<![\w$.\-/])(?P<letters>[A-Z]{1,4})(?P<digits>\d{6,10})(?![\w-])")
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


def _address_tail(copy: str, end: int) -> int:
    """Where an address that has its street end at ``end`` ends, with its city, postcode, country and the
    lines under it."""
    while (m := _TAIL_PIECE.match(copy, end)) is not None and m.end() > end:
        end = m.end()
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
        if n == 5 or re.search(r"[()\n:;<>|=\"]", rest[:m.start()]) or (n and "," in rest[:m.start()]):
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
        scan(_EMAIL, lambda m: ("@" in m.group() or (_SPELLED_EMAIL.fullmatch(m.group()) is not None and
                                                       not re.search(r"(?i)\bwww\b|^(?:website|site|web|us|online|"
                                                                     r"page|portal|home|link|webpage)\b", m.group())))
             and
             take(m.start(), m.end(), "EMAIL"))
        scan(_LABELLED, lambda m: self._labelled(m, take, fold))
        scan(_IBAN, lambda m: _iban_ok(m.group()) and (m.group().isupper() or sum(c.isdigit() for c in m.group()) >= 8)
             and
             take(m.start(), m.end(), "ACCOUNT", "ACCOUNT:" + m.group().replace(" ", "").upper()))
        scan(_BIC, lambda m: m.group("country") in _ISO_COUNTRIES and any(c.isdigit() for c in m.group()[6:]) and
             take(m.start(), m.end(), "ACCOUNT", "ACCOUNT:" + m.group()))
        scan(_CARD, lambda m: ((m.group(1) == "-" and len(re.sub(r"\D", "", m.group())) != 15) or
                               _luhn(re.sub(r"\D", "", m.group()))) and
             take(m.start(), m.end(), "ACCOUNT", "ACCOUNT:" + re.sub(r"\D", "", m.group())))
        for pattern in _PHONES + (_TYPED_PHONES if typed else []):
            scan(pattern, lambda m: self._phone(m, take))
        scan(_ADDRESS_LABEL, lambda m: take(m.start("value"), m.end("value"), "ADDRESS"))
        scan(_STREET, lambda m: not _business_after(fold, m.end(), self._v) and
             take(m.start(), _address_tail(copy, m.end()), "ADDRESS"))
        scan(_BOXES, lambda m: take(m.start(), m.end(), "ADDRESS"))
        scan(_CITY_STATE_ZIP, lambda m: not set(_fold(m.group("city")).split()) & _NOT_CITY and
             take(m.start(), m.end(), "ADDRESS"))
        if typed:
            scan(_TYPED_CITY_STATE_ZIP, lambda m: not set(_fold(m.group("city")).split()) & _NOT_CITY and
                 take(m.start(), m.end(), "ADDRESS"))
        scan(_FOREIGN, lambda m: take(m.start(), _address_tail(copy, m.end()), "ADDRESS"))
        for pattern in (_UNIT_LINE, _POSTCODES):
            scan(pattern, lambda m: take(m.start(), m.end(), "ADDRESS"))
        if "ID" in self._detect:
            scan(_CONTEXT_ID, lambda m: (sum(c.isdigit() for c in m.group("value")) >= 7 or
                                         (sum(c.isdigit() for c in m.group("value")) >= 4 and
                                          any(c.isalpha() for c in m.group("value")))) and
                 not re.fullmatch(_DATE, m.group("value"), re.IGNORECASE) and
                 take(m.start("value"), m.end("value"), "ID", "ID:" + m.group("value").replace("-", "").upper()))
            scan(_SHAPED_ID, lambda m: m.group("letters") not in _CURRENCIES and
                 not (m.group("letters") in _ISO_COUNTRIES and len(m.group("digits")) == 10) and
                 take(m.start(), m.end(), "ID", "ID:" + m.group()))
        if "NAME" in self._detect:
            self._field_names(copy, fold, take)
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

    def _name_value(self, value: str) -> bool:
        """Whether a field's ``value`` reads as a person's name: one to five words, capitalized, none a
        business's word, and not only everyday words."""
        words = value.split()
        if not 1 <= len(words) <= 5 or not re.fullmatch(r"[^\W\d_][\w'.,\u2019-]*(?:[ \t]+[^\W\d_][\w'.,\u2019-]*)*",
                                                        value.strip()):
            return False
        folds = [w.strip(".,").casefold() for w in _name_words(value)]
        if not folds or not any(w[:1].isupper() for w in words) or _LEGAL_ENDING.search(value) or \
                re.fullmatch(r"[A-Z]{2,4}", value.strip()):   # a code: GBP, USD
            return False
        if any(f in self._v.business or f in self._v.stop or f in _PERSONAL for f in folds if len(f) > 1) or \
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
            if _DOB_KEY.fullmatch(key):
                return "DOB"
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
            elif kind == "ADDRESS":
                if re.search(r"\d", value) and re.search(r"[^\W\d_]{2}", value) and len(value) <= 160:
                    take(start + lead, start + lead + len(value), "ADDRESS")
            elif kind == "ID":
                if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 /-]{2,30}", value) and sum(c.isdigit() for c in value) >= 3:
                    take(start + lead, start + lead + len(value), "ID",
                         "ID:" + re.sub(r"[^0-9A-Za-z]", "", value).upper())
            elif self._name_value(value):
                take(start + lead, start + lead + len(value), "NAME")
                if len(value.split()) >= 2:
                    self.add_person(value)

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
    def _phone(m: re.Match, take) -> bool:
        start = m.start("value") if "value" in m.re.groupindex else m.start()
        digits = re.sub(r"\D", "", m.group()[start - m.start():])
        if m.group()[:1] == "0" and m.re is _PHONES[3] and not 10 <= len(digits) <= 11:
            return False
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
                    t.fold in _PLACE_NAMES or (t.case == "caps" and not cued):
                return None
            if cued:
                if (t.fold in _common_words() or _wordlike(t.fold)) and t.fold not in _GIVEN and \
                        t.fold not in _SURNAMES:
                    return None
            elif t.case != "title" or t.fold in _WORD_SURNAMES or \
                    not (t.fold in _GIVEN or (t.fold in _given_names() and not _wordlike(t.fold))):
                return None
            if re.match(r"[ \t]*(?:&|and[ \t])", fold[t.end:t.end + 5]):
                return None
            if i > 0 and toks[i - 1].case in ("title", "caps") and near(i - 1) and not cued and \
                    toks[i - 1].fold not in _GREETINGS and not (toks[i - 1].dot and toks[i - 1].case != "initial"):
                # "Provided Rahel with": an everyday word starting the line before it
                p = toks[i - 1]
                line_start = re.search(r"(?:^|\n)[ \t]*(?:[-*\u2022]|\d{1,2}[.)])?[ \t]*\Z", fold[:p.start])
                if not (line_start and p.fold in _common_words() and not _name_listed(p.fold, surnames) and
                        f"{p.fold} {t.fold}" not in _FIRMS):
                    return None
            if i + 1 < len(toks) and toks[i + 1].case in ("title", "caps") and near(i) and not t.dot:
                return None
            return _Found(i, i, None, None, None) if ok(i, i) else None

        # Mark Tiffany Fuentes: a first name that's an everyday word, before a name
        if t.fold in _WORD_GIVEN and t.case in ("title", "caps") and not t.dot and near(i) and \
                toks[i + 1].case == t.case and not toks[i + 1].dot and \
                (toks[i + 1].fold in _GIVEN or toks[i + 1].fold in _given_names() or
                 toks[i + 1].fold in _SURNAMES or toks[i + 1].fold in surnames or
                 (toks[i + 1].fold not in _common_words() and _surname_like(toks[i + 1].fold, surnames))):
            more = rest(i + 1, t.case, True, lambda k: _surname_like(toks[k].fold, surnames), True)
            if more and ok(i, more[1]):
                return found(i, more[1], t.word, more[0], toks[more[1]].word, True)
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
                            toks[k].fold not in _WORD_SURNAMES and
                            (toks[k].fold not in _common_words() or (toks[k].fold in _common_surnames() and not wordy)),
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
            # Sarah K.: a first name and an initial
            if n.case == "initial" and n.dot and listed and (t.fold in _given_names() or t.fold in _GIVEN) and \
                    not (i + 2 < len(toks) and near(i + 1) and toks[i + 2].case in ("title", "caps")) and ok(i, i + 1):
                return _Found(i, i + 1, None, None, None)
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
        if i + 1 < len(toks) and _COMMA_GAP.fullmatch(_gap(fold, toks, i)) and name_word(i):
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
