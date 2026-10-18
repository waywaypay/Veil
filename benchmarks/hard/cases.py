"""Hand-written adversarial cases for veil.  All people, numbers and addresses are fictional (555-01xx phones,
example domains, test IBANs and card numbers).

Markup, turned into offsets by ``build.py``:

    ⟦KIND|text⟧   personal detail veil should hide.  KIND is what it should be hidden as: NAME, EMAIL, PHONE,
                  ADDRESS, SSN, EIN, TIN, ACCOUNT, ID, DOB; or OUT for something personal that is outside the
                  kinds veil looks for (an IP address, a wallet), scored on its own.
    ⟪text⟫        text that looks like a detail but isn't, and should stay visible.

Each case: id, category, why (what makes it hard), text, and optionally profile ("GENERIC", "FINANCE",
"US_TAX_K1"), typed (bool), people (add_person), businesses (add_business), and beyond=True for what veil's
README makes no claim to (other scripts, numbers in words, lookalike letters), scored on its own.
A KIND may name alternatives: ⟦ID/TIN|...⟧.
"""

C = []


def case(id, category, why, text, **kw):
    C.append({"id": id, "category": category, "why": why, "text": text, **kw})


# ---------------------------------------------------------------- taxpayer IDs
T = "tax_ids"
case("tax-fullwidth", T, "SSN in full-width Unicode digits",
     "Member SSN: ⟦SSN|１２３－４５－６７８９⟧ (copied from the portal).")
case("tax-arabic-indic", T, "SSN in Arabic-Indic digits",
     "رقم الضمان الاجتماعي SSN ⟦SSN|٥٢٣-٤٥-٦٧٨٩⟧", beyond=True)
case("tax-boxes", T, "one digit per form box",
     "Social security number  ⟦SSN|5 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9⟧")
case("tax-split-line", T, "SSN split across a line break mid-number",
     "The employee's SSN is ⟦SSN|523-45-\n6781⟧ per the W-4 on file.")
case("tax-html-entity", T, "digits as HTML entities",
     "<td>SSN</td><td>⟦SSN|&#53;&#50;&#51;-&#52;&#53;-&#54;&#55;&#56;&#57;⟧</td>")
case("tax-zero-width", T, "zero-width spaces between digits",
     "ssn=⟦SSN|523\u200b-\u200b45\u200b-\u200b6789⟧")
case("tax-nbsp", T, "non-breaking spaces as separators",
     "SSN ⟦SSN|523\u00a045\u00a06789⟧")
case("tax-ocr", T, "OCR lookalikes: l for 1, O for 0, S for 5",
     "Taxpayer identification no. ⟦SSN|l23-4S-67O9⟧")
case("tax-masked", T, "SSN masked to last four",
     "We have your SSN ending ⟦SSN|***-**-4821⟧ on file.")
case("tax-no-dash-label-far", T, "nine bare digits, label several words before",
     "Please confirm the social security number that we have listed for the account holder: ⟦SSN|523456789⟧.")
case("tax-ein-prefix", T, "EIN with an unusual prefix and spaces",
     "Fund EIN ⟦EIN|98 - 7654321⟧; GP EIN ⟦EIN|13-1234567⟧.")
case("tax-itin", T, "ITIN (9xx-7x-xxxx)",
     "ITIN: ⟦TIN|912-78-3456⟧")
case("tax-url", T, "SSN %-encoded inside a URL",
     "GET /verify?name=⟦NAME|Lena%20Okafor⟧&ssn=⟦SSN|523%2D45%2D6789⟧ HTTP/1.1")
case("tax-neg-zip4", T, "ZIP+4 is not an SSN",
     "Mail to the processing center, ZIP ⟪94107-1234⟫, by ⟪04/15/2025⟫.")
case("tax-neg-part", T, "part, invoice and claim numbers shaped like IDs",
     "Replace part ⟪SKU 523-45-678⟫ and reference invoice ⟪INV-2024-000123⟫, claim ⟪#12-3456789-0⟫.")
case("tax-neg-money", T, "nine-digit dollar amounts",
     "Total commitments were ⟪$523,456,789⟫ and distributions ⟪523456789.00⟫ USD.")
case("tax-neg-phone-time", T, "phone, time and IP shaped like IDs",
     "Ring ⟦PHONE|523-456-7890⟧ at ⟪12:45:30⟫ from ⟦OUT|10.123.45.67⟧.")
case("tax-neg-sample", T, "a K-1 box number before an amount", "20  ⟪1250000⟫\n20 Z  ⟪987654321⟫", profile="US_TAX_K1")
case("tax-two-in-row", T, "two SSNs glued by a slash",
     "Joint filers: ⟦SSN|523-45-6789⟧/⟦SSN|524-56-7890⟧")

# ---------------------------------------------------------------- names: shapes
N = "names_shape"
case("name-apostrophe", N, "apostrophes, straight and curly",
     "Signed by ⟦NAME|Siobhán O'Callaghan⟧ and witnessed by ⟦NAME|D’Angelo Russo⟧.")
case("name-particles", N, "lower-case particles",
     "Beneficiaries: ⟦NAME|Ludwig van der Berg⟧, ⟦NAME|María de la Cruz⟧ and ⟦NAME|Faisal bin Abdullah⟧.")
case("name-hyphen", N, "double-barrelled surnames",
     "Account opened for ⟦NAME|Anne-Sophie Lefèvre-Durand⟧ on ⟪March 3⟫.")
case("name-diacritics", N, "diacritics and non-English letters",
     "Contacts: ⟦NAME|Bjørn Ødegård⟧, ⟦NAME|Zoë Kowalczyk⟧, ⟦NAME|Đặng Thị Hương⟧.")
case("name-cjk", N, "Chinese name in Han characters",
     "客户姓名：⟦NAME|王小明⟧，电话 ⟦PHONE|+86 138 0013 8000⟧", beyond=True)
case("name-cyrillic", N, "Russian name in Cyrillic",
     "Клиент: ⟦NAME|Владимир Петрович Соколов⟧, паспорт ⟦ID|45 08 123456⟧", beyond=True)
case("name-arabic", N, "Arabic name in Arabic script",
     "الاسم: ⟦NAME|محمد عبد الله⟧", beyond=True)
case("name-suffix", N, "suffixes and post-nominals",
     "Trustee: ⟦NAME|Robert L. Hayes Jr.⟧; Advisor: ⟦NAME|Priscilla Nakamura-Holt⟧, CFA, PhD.")
case("name-nickname", N, "nickname in quotes in the middle",
     "Our contact is ⟦NAME|Robert \"Bobby\" Tablesworth⟧ in procurement.")
case("name-initials", N, "initials only, with and without periods",
     "Approved: ⟦NAME|J.R. Whitlock⟧; reviewed: ⟦NAME|K M Osei⟧.")
case("name-reverse-caps", N, "LAST, FIRST MIDDLE in capitals",
     "PAYEE ⟦NAME|OKONKWO-BELL, ADAEZE N⟧  AMOUNT ⟪$4,250.00⟫")
case("name-possessive", N, "possessive with curly apostrophe",
     "We reviewed ⟦NAME|Thandiwe Mokoena⟧’s allocation and ⟦NAME|Thandiwe⟧’s side letter.")
case("name-mononym", N, "single-name person with a label",
     "Name: ⟦NAME|Sukarno⟧\nNationality: ⟪Indonesian⟫")
case("name-mixed-case", N, "mixed and odd capitalisation",
     "cc: ⟦NAME|mcDONALD, kEVIN⟧ and ⟦NAME|DeShawn MacInnes⟧")
case("name-email-local", N, "name only in an email address",
     "Forward to ⟦EMAIL|priya.raghunathan@example.com⟧ please.")
case("name-linkedin", N, "name in a profile URL",
     "See ⟦OUT|linkedin.com/in/tomasz-wieczorek-4b21a⟧ for background.", beyond=True)
case("name-path", N, "username in a file path",
     "Saved to C:\\Users\\⟦ID|mkowalski⟧\\Documents\\K1_2023.pdf")
case("name-long-hispanic", N, "two given names and two surnames",
     "Titular: ⟦NAME|José Manuel García Fernández⟧")
case("name-sign-off", N, "first name alone in a sign-off",
     "Thanks so much for the quick turnaround!\n\nCheers,\n⟦NAME|Marguerite⟧")
case("name-greeting", N, "first name alone after Hi",
     "Hi ⟦NAME|Oluwaseun⟧,\nAttached is the subscription doc.")
case("name-homoglyph", N, "Cyrillic а and о inside a Latin-looking name",
     "Wire approved by ⟦NAME|Nаtаlie Bоwen⟧.", beyond=True)
case("name-soft-hyphen", N, "soft hyphen inside the name",
     "Signed: ⟦NAME|Christo\u00adpher Lindqvist⟧")
case("name-spaced-letters", N, "letters spaced out for emphasis",
     "N A M E :  ⟦NAME|J A N E   D O E⟧", beyond=True)
case("name-html-split", N, "name split by inline HTML tags",
     "<p>Dear ⟦NAME|<b>Hel</b>ena Vasquez⟧,</p>")

# ---------------------------------------------------------------- names that are words / places / brands
W = "names_ambiguous"
case("amb-word-names", W, "names that are everyday words",
     "Meeting with ⟦NAME|Hope Faith⟧ and ⟦NAME|Will Summers⟧ about the ⟪summer⟫ ⟪will⟫ provisions.")
case("amb-word-names-2", W, "names that are verbs",
     "⟦NAME|Grant Bill⟧ asked us to ⟪bill⟫ the fund and ⟪grant⟫ the waiver; ⟦NAME|Mark Rich⟧ will ⟪mark⟫ it paid.")
case("amb-month-names", W, "names that are months",
     "Ms. ⟦NAME|April June⟧ was born in ⟪May⟫; ⟦NAME|August Rush⟧ joined in ⟪August⟫.")
case("amb-place-names", W, "people named like places",
     "⟦NAME|Paris Brooklyn⟧ moved from ⟪Paris⟫ to ⟪Brooklyn⟫; ⟦NAME|Austin Georgia⟧ lives in ⟪Austin⟫, ⟪Georgia⟫.")
case("amb-sentence-start-verbs", W, "capitalised words at sentence start are not names",
     "⟪Will⟫ you sign? ⟪Grant⟫ access to the folder. ⟪Mark⟫ the invoice as paid. ⟪Frank⟫ feedback welcome.")
case("amb-places", W, "places named after people",
     "We toured ⟪Victoria Falls⟫, the ⟪Lincoln Memorial⟫, ⟪Jordan River⟫ and ⟪Martin Luther King Jr. Blvd⟫ shops.")
case("amb-brands", W, "brands and firms that are surnames",
     "Holdings include ⟪Johnson & Johnson⟫, ⟪Morgan Stanley⟫, ⟪Wells Fargo⟫, ⟪Charles Schwab⟫ and ⟪Ernst & Young⟫ fees.")
case("amb-products", W, "products named like people",
     "Order ⟪Dr Pepper⟫, ⟪Jack Daniel's⟫ and ⟪Ben & Jerry's⟫ for the ⟪Tom Ford⟫ launch.")
case("amb-diseases", W, "eponymous diseases and laws",
     "History of ⟪Parkinson's disease⟫ and ⟪Hodgkin lymphoma⟫; tested with ⟪Bayesian⟫ methods per ⟪Newton⟫'s method.")
case("amb-tech", W, "software named like people",
     "Deploy via ⟪Jenkins⟫ to the ⟪Cassandra⟫ cluster; ⟪Julia⟫ and ⟪Ruby⟫ jobs run on ⟪Kafka⟫.")
case("amb-person-like-firm", W, "a person whose name is also a firm",
     "Our partner ⟦NAME|Morgan Stanley⟧ (no relation to the bank) called about the ⟪Morgan Stanley⟫ account.")
case("amb-name-in-fund", W, "a person's name inside a fund's name",
     "Commitment from ⟪Mockridge Capital Partners, LP⟫ signed by ⟦NAME|Avery Mockridge⟧.", profile="FINANCE")
case("amb-name-in-trust", W, "a person's name inside a trust's name",
     "Investor: The ⟦NAME|Avery K. Mockridge⟧ Revocable Trust dtd ⟪1/4/2011⟫", profile="FINANCE")
case("amb-roles", W, "roles that look like capitalised names",
     "The ⟪General Partner⟫ notified the ⟪Limited Partner⟫ and the ⟪Defaulting Party⟫.", profile="FINANCE")
case("amb-k1-terms", W, "K-1 vocabulary",
     "⟪Guaranteed Payments⟫ ⟪Section 1231⟫ gain; ⟪Capital Account⟫ analysis; ⟪Ordinary Business Income⟫.",
     profile="US_TAX_K1")
case("amb-famous", W, "historical figures as topic, not personal data, but still names",
     "The memo compares ⟦NAME|Warren Buffett⟧'s letters with ⟦NAME|Benjamin Graham⟧'s book.")
case("amb-honorific-only", W, "a title and surname that is a common word",
     "Please route to ⟦NAME|Dr. Strong⟧ and ⟦NAME|Mrs. Baker⟧.")

# ---------------------------------------------------------------- emails
E = "email"
case("email-plus", E, "plus addressing and subdomain",
     "Send to ⟦EMAIL|avery.mockridge+k1@mail.example.co.uk⟧.")
case("email-angle", E, "display name and angle brackets",
     "From: \"⟦NAME|Lena Okafor⟧\" <⟦EMAIL|lena.okafor@example.org⟧>")
case("email-obfuscated", E, "obfuscated with brackets",
     "reach me: ⟦EMAIL|jdoe [at] example [dot] com⟧")
case("email-obfuscated-2", E, "obfuscated with parentheses, no spaces",
     "email ⟦EMAIL|jdoe(at)example(dot)net⟧")
case("email-mailto", E, "mailto link with subject",
     "<a href=\"mailto:⟦EMAIL|h.vasquez@example.com⟧?subject=K-1\">email</a>")
case("email-caps-trail", E, "upper case, trailing period",
     "CONTACT: ⟦EMAIL|R.HAYES@EXAMPLE.COM⟧.")
case("email-idn", E, "internationalised domain",
     "Kontakt: ⟦EMAIL|jürgen@müller-example.de⟧")
case("email-quoted-local", E, "quoted local part",
     "Odd but valid: ⟦EMAIL|\"john smith\"@example.com⟧", beyond=True)
case("email-neg", E, "things with @ that aren't emails",
     "Use ⟪@dataclass⟫, install ⟪@types/node⟫, pin ⟪lodash@4.17.21⟫, clone ⟪git@github.com:acme/repo.git⟫.")
case("email-handle", E, "social handle",
     "Follow ⟦ID|@lena_okafor⟧ for updates.")

# ---------------------------------------------------------------- phones
P = "phone"
case("phone-intl-uk", P, "UK number with spaces", "Call ⟦PHONE|+44 20 7946 0958⟧ after 3pm.")
case("phone-ext", P, "US number with extension", "Tel ⟦PHONE|(415) 555-0134 ext. 221⟧")
case("phone-dots", P, "dotted US number", "Cell: ⟦PHONE|415.555.0134⟧")
case("phone-india", P, "Indian mobile", "WhatsApp ⟦PHONE|+91 98765 43210⟧")
case("phone-france", P, "French pairs", "Portable : ⟦PHONE|06 12 34 56 78⟧")
case("phone-vanity", P, "letters in a number", "Hotline ⟦PHONE|1-800-FLOWERS⟧ is a business line.")
case("phone-spelled", P, "number spelled out in words",
     "my number is ⟦PHONE|four one five, five five five, zero one three four⟧", typed=True, beyond=True)
case("phone-bare-typed", P, "ten bare digits typed in chat", "call me at ⟦PHONE|4155550134⟧ tmrw", typed=True)
case("phone-neg-dates", P, "dates and versions shaped like phones",
     "Build ⟪10.0.19045.3693⟫ released ⟪2024.03.15⟫; ⟪911⟫ was not called; page ⟪555⟫.")
case("phone-neg-coords", P, "coordinates", "Site at ⟪37.7749, -122.4194⟫.")

# ---------------------------------------------------------------- addresses
A = "address"
case("addr-us-full", A, "US address with directional and suite",
     "Ship to ⟦ADDRESS|1600 Pennsylvania Ave NW, Suite 400, Washington, DC 20500⟧.")
case("addr-fraction", A, "fractional house number", "Lives at ⟦ADDRESS|123 1/2 Elm St, Apt 2R, Bend, OR 97701⟧")
case("addr-spelled", A, "house number spelled out", "Office: ⟦ADDRESS|One Market Plaza, San Francisco, CA 94105⟧")
case("addr-po", A, "PO Box variants",
     "Remit to ⟦ADDRESS|P.O. Box 7781, Tulsa OK 74101⟧ or ⟦ADDRESS|PMB 12, 55 Oak Rd, Reno NV 89501⟧")
case("addr-rural", A, "rural route", "Mail: ⟦ADDRESS|RR 2 Box 152, Hartwell, GA 30643⟧")
case("addr-military", A, "military address", "⟦ADDRESS|PSC 1234, Box 5678, APO AE 09012⟧")
case("addr-uk", A, "UK address with postcode", "⟦ADDRESS|Flat 3, 27 Cranbourne Gardens, London NW11 0HP⟧")
case("addr-ca", A, "Canadian address", "⟦ADDRESS|2045 rue Saint-Denis, Montréal QC H2X 3K8⟧")
case("addr-de", A, "German address", "Anschrift: ⟦ADDRESS|Hauptstraße 5a, 10115 Berlin⟧")
case("addr-jp", A, "Japanese address", "住所：⟦ADDRESS|〒100-0001 東京都千代田区千代田1-1⟧", beyond=True)
case("addr-multiline", A, "address over three lines with no label",
     "⟦NAME|Harriet Quimby⟧\n⟦ADDRESS|48 Larkspur Ln\nUnit 7\nMarblehead, MA 01945⟧\nUSA")
case("addr-highway", A, "highway address", "Store at ⟦ADDRESS|12345 State Route 9, Lacey, WA 98516⟧")
case("addr-csv", A, "address in a CSV cell with quotes",
     "id,name,address\n7,⟦NAME|Ruth Ellery⟧,\"⟦ADDRESS|88 Beacon St, Boston, MA 02108⟧\"")
case("addr-neg", A, "street words that aren't addresses",
     "⟪Wall Street⟫ rallied; ⟪Main Street⟫ investors cheered; see ⟪Street View⟫; read ⟪Chapter 12 Main Points⟫.")
case("addr-neg-2", A, "number and street-word in prose",
     "There are ⟪3 Avenue⟫s to explore and ⟪5 Way⟫s to win; ⟪Route 66⟫ is famous.")

# ---------------------------------------------------------------- accounts
B = "account"
case("acct-iban-spaced", B, "IBAN in groups", "IBAN ⟦ACCOUNT|GB82 WEST 1234 5698 7654 32⟧")
case("acct-iban-lower", B, "IBAN lower case without label", "pls wire to ⟦ACCOUNT|de89370400440532013000⟧", typed=True)
case("acct-card-dash", B, "Visa with dashes", "Card: ⟦ACCOUNT|4111-1111-1111-1111⟧ exp ⟪12/27⟫")
case("acct-amex", B, "Amex 4-6-5", "AMEX ⟦ACCOUNT|3782 822463 10005⟧")
case("acct-card-bare", B, "card number in prose with no label",
     "I paid with ⟦ACCOUNT|5555555555554444⟧ but it bounced.")
case("acct-routing", B, "ABA routing and account",
     "Routing ⟦ACCOUNT|021000021⟧, account ⟦ACCOUNT|000123456789⟧")
case("acct-swift", B, "SWIFT/BIC with branch", "BIC: ⟦ACCOUNT|DEUTDEFF500⟧")
case("acct-last4", B, "account given as last four", "Your account ending in ⟦ACCOUNT|4821⟧ was debited.")
case("acct-neg-isbn", B, "ISBN-13 and UPS tracking", "Book ⟪978-0-306-40615-7⟫ shipped as ⟪1Z999AA10123456784⟫.")
case("acct-neg-ts", B, "timestamps and hashes",
     "ts=⟪1700000000123⟫ sha=⟪e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855⟫")
case("acct-crypto", B, "crypto wallet (outside veil's kinds)",
     "Send BTC to ⟦OUT|bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh⟧", beyond=True)

# ---------------------------------------------------------------- IDs and DOBs
D = "ids_dob"
case("id-passport", D, "passport with label", "Passport No. ⟦ID|X12345678⟧, issued ⟪2019-02-11⟫")
case("id-dl", D, "driver's licence", "DL# ⟦ID|D1234567⟧ (CA)")
case("id-nhs", D, "NHS number", "NHS number: ⟦ID|943 476 5919⟧")
case("id-ni", D, "UK National Insurance number with spaces", "NI ⟦ID|QQ 12 34 56 C⟧")
case("id-sin", D, "Canadian SIN", "SIN ⟦ID/TIN|046 454 286⟧")
case("id-mbi", D, "Medicare MBI", "Medicare ID ⟦ID|1EG4-TE5-MK73⟧")
case("dob-prose", D, "DOB in prose", "He was born on the ⟦DOB|4th of July, 1976⟧ in Ohio.")
case("dob-short", D, "two-digit year", "D.O.B. ⟦DOB|07/04/76⟧")
case("dob-label-next-line", D, "label and value on separate lines", "Date of Birth\n⟦DOB|1976-07-04⟧")
case("dob-json", D, "DOB in JSON", "{\"dob\": \"⟦DOB|1988-11-30⟧\", \"created\": \"⟪2024-01-02⟫\"}")
case("dob-neg", D, "dates that are not birth dates",
     "Invoice date ⟪07/04/2024⟫; effective ⟪January 1, 2025⟫; as of ⟪12/31/2023⟫.")
case("dob-age-only", D, "age is not a DOB", "Applicant is ⟪42⟫ years old.")

# ---------------------------------------------------------------- structured formats
S = "structured"
case("json-nested", S, "nested JSON with name keys",
     "{\"investor\": {\"first_name\": \"⟦NAME|Quentin⟧\", \"last_name\": \"⟦NAME|Abernathy⟧\", "
     "\"tax\": {\"ssn\": \"⟦SSN|523-45-6789⟧\"}, \"fund\": \"⟪Northgate Opportunity Fund II⟫\"}}")
case("json-array-names", S, "names as bare array items",
     "{\"signers\": [\"⟦NAME|Imogen Thrale⟧\", \"⟦NAME|Cassius Obi⟧\"], \"status\": \"⟪Approved⟫\"}")
case("json-escaped", S, "JSON with escaped unicode",
     "{\"name\": \"⟦NAME|Jos\\u00e9 N\\u00fa\\u00f1ez⟧\"}")
case("csv-no-header-hint", S, "CSV whose header is ambiguous",
     "who,amt,when\n⟦NAME|Delphine Arceneaux⟧,⟪1200⟫,⟪2024-02-01⟫\n⟦NAME|Kwame Mensah⟧,⟪800⟫,⟪2024-02-03⟫")
case("tsv-names", S, "tab separated with names in second column",
     "ID\tCustomer\tCity\n⟦ID|C-10291⟧\t⟦NAME|Rosalind Achterberg⟧\t⟪Denver⟫")
case("xml", S, "XML with attributes",
     "<Investor id=\"⟦ID|INV-88213⟧\"><FullName>⟦NAME|Ines Albuquerque⟧</FullName>"
     "<Phone type=\"mobile\">⟦PHONE|+351 912 345 678⟧</Phone></Investor>")
case("yaml", S, "YAML config with a contact",
     "owner:\n  name: ⟦NAME|Percival Ng⟧\n  email: ⟦EMAIL|percy.ng@example.io⟧\nservice: ⟪billing-api⟫")
case("sql", S, "SQL insert",
     "INSERT INTO lp (name, ssn, email) VALUES ('⟦NAME|Odalys Ferreira⟧', '⟦SSN|523-45-6790⟧', "
     "'⟦EMAIL|odalys@example.com⟧');")
case("markdown-table", S, "markdown table",
     "| Partner | Commitment |\n|---|---|\n| ⟦NAME|Esperanza Villalobos⟧ | ⟪$250,000⟫ |\n| ⟪Total⟫ | ⟪$250,000⟫ |")
case("log-line", S, "application log",
     "2024-05-01T12:00:03Z INFO login ok user=⟦EMAIL|t.wieczorek@example.pl⟧ ip=⟦OUT|203.0.113.42⟧ "
     "session=⟪a8f3c2⟫")
case("email-thread", S, "quoted reply header",
     "> On Tue, Mar 5, 2024 at 9:14 AM ⟦NAME|Gideon Faulkner⟧ <⟦EMAIL|gfaulkner@example.com⟧> wrote:\n"
     "> Please send ⟦NAME|Marisol⟧'s K-1.")
case("vcard", S, "vCard",
     "BEGIN:VCARD\nFN:⟦NAME|Henrietta Lacks-Moore⟧\nTEL;TYPE=cell:⟦PHONE|+1 617 555 0199⟧\n"
     "ADR;TYPE=home:;;⟦ADDRESS|12 Orchard Ln;Concord;MA;01742⟧\nEND:VCARD")
case("edi-x12", S, "X12 EDI segments",
     "N1*ST*⟦NAME|Bartholomew Crane⟧*~N3*⟦ADDRESS|456 Elm St.⟧*~N4*⟦ADDRESS|Othertown*NY*11111⟧~")
case("swift-mt", S, "SWIFT MT103 fields",
     ":50K:/⟦ACCOUNT|12345678⟧\n⟦NAME|MISTY LEE DEAN⟧\n⟦ADDRESS|22 HARBOR RD SEATTLE WA⟧\n:59:/⟦ACCOUNT|GB82WEST12345698765432⟧")

# ---------------------------------------------------------------- typed chat
Y = "typed_chat"
case("typed-lower-name", Y, "all lower case name and request",
     "add ⟦NAME|jane smith⟧ as an lp with ⟪250k⟫", typed=True, profile="FINANCE")
case("typed-ssn-no-dash", Y, "nine digits typed with 'ssn'", "her ssn is ⟦SSN|523456789⟧ btw", typed=True)
case("typed-obf-email", Y, "spoken email", "email me at ⟦EMAIL|jane dot doe at gmail dot com⟧", typed=True)
case("typed-run-on", Y, "no punctuation run-on",
     "pls update ⟦NAME|marcus okoye⟧ address to ⟦ADDRESS|14 birch hollow rd west chester pa 19382⟧ thx", typed=True)
case("typed-neg-caps", Y, "capitalised product and team names typed",
     "can ⟪Data Team⟫ fix the ⟪Quarterly Report⟫ in ⟪Google Sheets⟫?", typed=True)
case("typed-neg-lower-words", Y, "lower-case words that are also names",
     "i ⟪will⟫ ⟪mark⟫ it and ⟪bill⟫ them in ⟪may⟫, ⟪hope⟫ that's ok", typed=True)
case("typed-emoji", Y, "name next to emojis",
     "🎉 congrats ⟦NAME|Priya⟧!! 🎉 call ⟦PHONE|415-555-0177⟧", typed=True)

# ---------------------------------------------------------------- known people
K = "known_people"
KP = ["Avery K. Mockridge"]
case("known-variants", K, "a known person written six ways",
     "⟦NAME|MOCKRIDGE, AVERY K⟧ / ⟦NAME|A. Mockridge⟧ / ⟦NAME|Ms. Mockridge⟧ / ⟦NAME|avery⟧ / "
     "⟦NAME|AKM⟧ / ⟦NAME|Avery⟧", people=KP)
case("known-email", K, "known person's email", "Copy ⟦EMAIL|amockridge@example.com⟧.", people=KP)
case("known-typo", K, "a known person misspelled", "Per ⟦NAME|Avery Mockrige⟧'s note.", people=KP, beyond=True)
case("known-substring", K, "known surname inside another word stays",
     "⟪Mockridgeville⟫ ⟪Mockridge Capital Partners⟫", people=KP, businesses=["Mockridge Capital Partners"])

# ---------------------------------------------------------------- restore traps (scored on round trip)
R = "roundtrip"
case("rt-literal-placeholder", R, "text already contains placeholder-shaped tokens",
     "Template field ⟪NAME_001⟫ maps to ⟦NAME|Clementine Ashworth⟧; ⟪SSN_001⟫ is a sample token.")
case("rt-same-value-two-ways", R, "one SSN written two ways",
     "SSN ⟦SSN|523-45-6789⟧ (also written ⟦SSN|523 45 6789⟧).")
case("rt-overlap", R, "a name inside an email inside a URL",
     "https://example.com/u/⟦EMAIL|clementine.ashworth@example.com⟧?n=⟦NAME|Clementine Ashworth⟧")

# ---------------------------------------------------------------- more
M = "mixed"
case("mix-coref", M, "one person by full name, then surname, then title",
     "Memo: ⟦NAME|Cordelia Vance⟧ joined in ⟪2019⟫. Later ⟦NAME|Vance⟧ led the audit, and ⟦NAME|Ms. Vance⟧ signed off. "
     "⟦NAME|Cordelia⟧ retires in ⟪June⟫.")
case("mix-firm-from-surname", M, "a firm named for a person, and the person",
     "⟪Okafor Holdings LLC⟫ was formed by ⟦NAME|Lena Okafor⟧.", profile="FINANCE")
case("mix-all-caps", M, "a whole message in capitals",
     "PLEASE CALL ⟦NAME|DOROTHEA KLINE⟧ AT ⟦PHONE|212-555-0143⟧ RE: ⟪WIRE⟫ TO ⟪FIRST REPUBLIC⟫")
case("mix-k1-boxes", M, "K-1 box and line references",
     "Enter in ⟪Box 5⟫ and ⟪Line 14⟫, code ⟪A⟫; partner ⟦NAME|Ezekiel Thorne⟧, TIN ⟦SSN|523-45-6782⟧.",
     profile="US_TAX_K1")
case("mix-founded", M, "a date next to 'born' that is not a birth date",
     "The fund was born out of a ⟪June 3, 1998⟫ spinout; ⟦NAME|Ravi Subramanian⟧ (DOB ⟦DOB|3 Jun 1961⟧) led it.")
