# Hard cases

151 hand-written cases built to break veil: personal details in odd formats, scripts and encodings, names
that are everyday words, and words, brands and places that look like names. Every person, number and address
is fictional.

* `cases.py`: the cases, marked up inline. `⟦KIND|text⟧` is a detail to hide, `⟪text⟫` is a look-alike to
  keep, and `beyond=True` marks what veil's README makes no claim to handle.
* `hard.jsonl`: the same cases with character offsets, built by `python benchmarks/hard/hard.py build`.
* `hard.py score [-v]`: runs veil and prints what it found and kept; `-v` adds every failure, with the input
  and veil's output.

Each row of `hard.jsonl` has `id`, `category`, `why`, `text`, `spans` (`start`, `end`, `kind`, `text`; the
`KEEP` kind is a look-alike), and `profile`, `typed`, `people`, `businesses` and `beyond` when a case sets them.

## What is in it

| Category | Cases | Examples |
|---|---|---|
| tax_ids | 19 | full-width and Arabic-Indic digits, one digit per box, a split across lines, HTML entities, zero-width spaces, NBSP, OCR lookalikes, %-encoding; SKU, ZIP+4, money and K-1 amounts to keep |
| names_shape | 24 | O'Callaghan, D’Angelo, van der Berg, Lefèvre-Durand, Jr./PhD, "Bobby" nicknames, initials, LAST, FIRST, homoglyphs, soft hyphen, a name split by `<b>` tags, Han, Cyrillic and Arabic script |
| names_ambiguous | 17 | Hope Faith, Grant Bill, April June, Paris Brooklyn; Jordan River, Dr Pepper, Parkinson's, Jenkins, Morgan Stanley (both the bank and a person) |
| email | 10 | plus addressing, `[at]`/`(at)`, mailto, IDN, quoted local part; `@dataclass`, `lodash@4.17.21`, `git@github.com:` to keep |
| phone | 10 | UK, India and France numbers, extensions, vanity, spelled out; versions, dates and coordinates to keep |
| address | 15 | fractional and spelled-out house numbers, rural routes, APO, UK, Canada, Germany, Japan, highways, EDI; Wall Street and Main Street to keep |
| account | 11 | spaced or lower-case IBANs, Amex, routing, SWIFT, last four; ISBN, UPS tracking, timestamps and hashes to keep |
| ids_dob | 12 | NHS, NI, SIN, MBI, DOB in prose and on the next line; invoice dates and ages to keep |
| structured | 14 | nested JSON, TSV, XML attributes, YAML, SQL, Markdown, logs, quoted email, vCard, X12, SWIFT MT103 |
| typed_chat | 7 | all lower case, run-ons, spoken emails, emoji |
| known_people | 4 | `add_person` variants, a misspelling, the surname inside a place name |
| roundtrip | 3 | text that already contains `NAME_001`; one SSN written two ways |
| mixed | 5 | coreference, a firm named after its founder, all capitals, K-1 boxes, a founding date next to "born" |

## Results (veil at `caa8eed`)

Within what veil claims to handle (139 cases, 172 details, 121 look-alikes):

| | |
|---|---|
| details found | **84.9%** (146 of 172); 83.1% hidden as the right kind |
| partly hidden (part of the detail left visible) | 10 |
| look-alikes kept | **81.0%** (98 of 121) |
| other words hidden | 0.5% |
| round trip exact | 127 of 139; **damaged** text outside a detail in 4 |

Beyond its claims (other scripts, numbers in words, lookalike letters): 3 of 12 found.

By comparison, `wider.md` reports 91% found on Nemotron and 0.1% to 1.2% of other words hidden. This set
is harder on purpose.

## What it shows

Hiding too much, and changing text on the way back:

* **A literal `NAME_001` or `SSN_001` in the input comes back as `NAME‐001`** (with a Unicode hyphen). veil
  escapes it so it can't be confused with a placeholder, but `restore_text` doesn't undo the escape
  (`rt-literal-placeholder`).
* **Restoring can reorder or merge text that isn't personal.** `Dr Pepper, Jack Daniel's` comes back as
  `Dr Jack Daniel Pepper's`. The `AMOUNT` column in `PAYEE OKONKWO-BELL, ADAEZE N  AMOUNT` is absorbed into
  the name. In a TSV the tab before `Denver` turns into a space.
* Brands, places and software named like people are hidden: Jordan River, Martin Luther King Jr. Blvd, Dr
  Pepper, Tom Ford, Ben & Jerry's, Jenkins, Cassandra, Google Sheets (typed), the Georgia in "Austin, Georgia".
* Strings with `@` that aren't emails are hidden: `@dataclass` and `@types/node` as IDs, and
  `git@github.com:` as an email.
* ID-shaped numbers are hidden: `SKU 523-45-678` as an SSN, a claim number `#12-3456789-0` and a K-1 Box 20
  amount as TINs, a UPS tracking number and a millisecond timestamp as IDs, `Chapter 12 Main Points` as an
  address, and "born out of a June 3, 1998 spinout" as a DOB.

* **One known person gets three placeholders.** After `add_person("Avery K. Mockridge")`, `MOCKRIDGE, AVERY K`
  and `A. Mockridge` become `NAME_001`, but `Ms. Mockridge` becomes `NAME_002` and `Avery` `NAME_003`, so the
  model sees three people (`known-variants`).

Missing, or leaving part of a detail visible:

* Name parts left visible: `Jr.` (`Robert L. Hayes Jr.`), initials (`J.R. Whitlock`, `K M Osei`), the
  surname after a quoted nickname, `DEAN` in `MISTY LEE DEAN`, the `.co.uk` of an email, the house number
  of a highway address, `Flat 3,` before a UK address, and the rest of a name after `<b>Hel</b>`.
* Names that are words: `Hope Faith`, `Grant Bill`, `Paris Brooklyn`, and a person named `Morgan Stanley`.
* A surname alone after the full name earlier (`Vance`), a sign-off name (`Cheers,\nMarguerite`),
  `mcDONALD, kEVIN`, and a known person written `avery` or `AKM`.
* A username in a Windows path, `C-10291` in a TSV's ID column, a DOB in prose ("4th of July, 1976"), the
  city, state and ZIP of an X12 `N4` segment, the account in a SWIFT `:50K:` field, `1-800-FLOWERS`, and an
  email spoken aloud in a chat (`jane dot doe at gmail dot com`).
* Kinds: a full-width-digit SSN, an OCR-misread SSN and a bare nine-digit SSN after a distant label are
  hidden, but as `ID` rather than `SSN`.

veil isn't built to find IP addresses, wallets or profile URLs; they are scored on their own (`OUT`) and
don't count above.

## Caveats

Some labels are judgement calls. `Morgan Stanley` as a person and the famous names in `amb-famous` are
examples, as is whether a Canadian SIN is an `ID` or a `TIN` (either counts). Words are aligned the way
`gretel.py` aligns them, so an ordinary word repeated nearby can occasionally be counted as kept.
