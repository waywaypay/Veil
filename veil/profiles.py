"""Profiles: the vocabulary that tells a document's own words from people's names.

The detectors in ``veil.redactor`` know English, common first names and
surnames, places, months and the words around names ("Attn:", "Sincerely,",
"c/o").  A profile adds what a kind of document says that looks like a name
but isn't (a K-1's "Guaranteed Payments", a fund report's "Capital Account"),
the labels that put a name next, and a few switches.

Three come with veil, each building on the one before:

- ``GENERIC``: nothing added.  The default.
- ``FINANCE``: fund, investing and accounting words; "as an LP", "Jane's
  share" and the like say the words before them are a person's name.
- ``US_TAX_K1``: Schedule K-1 vocabulary, and box numbers before amounts
  ("20 1250000") aren't taken for an EIN.

Make your own with ``Profile(...)`` or ``FINANCE.extend("mine", stop_words=...)``.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace


def words(text: str) -> frozenset[str]:
    """A set of lower-case words from whitespace-separated ``text``."""
    return frozenset(text.casefold().split())


@dataclass(frozen=True)
class Profile:
    name: str
    # Capitalized words that are never a person's name in these documents.
    stop_words: frozenset[str] = frozenset()
    # Words that, after a name, make it a business's: "Jordan Ridge Capital".
    business_words: frozenset[str] = frozenset()
    # Regex alternatives for words right before a person's name ("k-?1s?\\s+for"); case-insensitive.
    cues: tuple[str, ...] = ()
    # The last word of each of those cues, lower case: a cue is looked for only after one.
    cue_ends: frozenset[str] = frozenset()
    # Regex alternatives right after a name that make it a person's, in what a user types ("'s[ \\t]+share").
    after_cues: tuple[str, ...] = ()
    # In what a user types, these right after a name are a member's interest, not a business: "Jane Doe LLC".
    member_interest_words: frozenset[str] = frozenset()
    # Two digits then seven, split only by a space, is a form's box number and an amount, not an EIN,
    # when the box number is at most this.  None: always an EIN.
    form_box_max: int | None = None

    def extend(self, name: str, **more) -> "Profile":
        """This profile with ``more`` added: sets are joined, tuples appended, anything else replaced."""
        changes = {"name": name}
        for f in fields(self):
            if f.name not in more or f.name == "name":
                continue
            value, mine = more[f.name], getattr(self, f.name)
            if isinstance(mine, frozenset):
                changes[f.name] = mine | (words(value) if isinstance(value, str) else frozenset(value))
            elif isinstance(mine, tuple):
                changes[f.name] = mine + tuple(value)
            else:
                changes[f.name] = value
        unknown = set(more) - {f.name for f in fields(self)}
        if unknown:
            raise TypeError(f"Profile has no {', '.join(sorted(unknown))}")
        return replace(self, **changes)


GENERIC = Profile("generic")

FINANCE = GENERIC.extend(
    "finance",
    stop_words=words("""
account accounting accounts adjustment agreement alternative amount amounts analysis annual appendix approve
assets audit audited auditor auditors balance balances bank begin book call called calls cap capital carried
carta cash catch cents clawback close closes closing closings commitment commitments committee compliance
contribution contributions county credit credits decrease desk detail details distribution distributions
dividend dividends division dollars dpi draft drive dropbox earnings end ending entries entry equity escrow
estate estimated estimates exchange exempt exhibit expense expenses fair fee fees final finals finance
financing flow flows fund funded funds gain gains google gp gross group hold holds hurdle income increase
instruction instructions interest investment investments investor investors irr journal ledger legal letter
letters liabilities llc loss losses lp management market minimum moic monthly multiple multiples nav net
notice notices office opening operations ownership partner partners partnership partnerships payment payments
pct percent period plan portfolio preferred proceeds profit promote quarter quarterly quickbooks rate rates
real record recorded relations rental report reporting reports reserve reserves return revenue room royalties
royalty rvpi schedule schedules service share shares side stock summary support table tax taxes team total
true tvpi unfunded up usd valuation valuations value values vintage waterfall wire wires withdrawals year-end
yearly
"""),
    after_cues=(
        r"\((?i:llc|lpi|lp|gp)\)",
        r",?[ \t]+(?i:(?:as|is)[ \t]+)?(?i:an?[ \t]+)?(?i:(?:llc|lpi|limited|general)[ \t]+)?(?i:member|partner)\b",
        r",?[ \t]+(?i:as|is)[ \t]+(?i:an?[ \t]+)?(?i:lp|gp|llc|lpi)\b",
        r"'s[ \t]+(?i:share|capital|allocation)",
    ),
)

US_TAX_K1 = FINANCE.extend(
    "us_tax_k1",
    stop_words=words("""
active activities activity adjusted allocation allocations amazon amended amendment amortization anthropic
apportionment aws bedrock bonus box boxes carry certificate claude collectibles composite delaware depletion
depreciation domestic drilling election elections employer employment excel extension extensions federal
foreign gaap guaranteed harbor intangible interests internal irs k-1 k-1s k1 like-kind lpi nonrecourse
nonresident ordinary passive pdf pdfs proc qualified recapture recourse reg regulation regulations resident
rev ruling rulings safe section self splits statutory term treas treasury treaty underlying unrecaptured
unrelated upload withheld withholding
"""),
    cues=(r"k-?1s?\s+(?:for|of)",),
    cue_ends=words("k-1 k1 k-1s"),
    after_cues=(r"'s[ \t]+(?i:k-?1)",),
    member_interest_words=words("llc lpi"),
    form_box_max=23,
)

PROFILES = {p.name: p for p in (GENERIC, FINANCE, US_TAX_K1)}
