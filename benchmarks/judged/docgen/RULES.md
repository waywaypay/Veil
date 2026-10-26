# Writing labelled documents for a PII redaction model

You are writing realistic, varied documents of the kinds people really handle, so a model can learn to find the
personal details in them. Every person, number and address you write is made up: never use a real private person's
details. Public figures and fictional characters may appear by name, as they would in real text.

## Mark every private person's detail inline

Write each detail as `⟦label|text⟧`, the text exactly as it appears in the document. Labels:

| label | what |
|---|---|
| `name` | a private person's name: full name, first name alone, surname alone, initials with a surname, a nickname, written any way (all caps, "Last, First", with a middle initial) |
| `email address` | a person's email address, also obfuscated ("jane at example dot com") |
| `phone number` | a person's phone or fax number, any format, any country, with its extension in the span ("+1 202 555 0137 ext 204") |
| `street address` | a person's street address: the street line, and the town, region, postcode and country written with it, as one span (span lines if it's written over lines) |
| `ssn` | a US Social Security number, also masked ("XXX-XX-1234") |
| `tax id` | an EIN, ITIN, or another country's tax or national identity number (UK National Insurance number, Canadian SIN, Indian Aadhaar or PAN, German Steuer-ID, Italian codice fiscale, Spanish DNI/NIE...) |
| `account number` | a bank account or routing number, a UK sort code with its account, a policy or loan number |
| `credit card number` | a card number, also masked ("**** **** **** 4242") |
| `iban` | an IBAN |
| `swift code` | a SWIFT/BIC code (only when it identifies a person's account in context; a bank's code in a header isn't personal) |
| `date of birth` | a person's date of birth (not other dates: visit dates, invoice dates, deadlines stay unmarked) |
| `customer id` | a customer, member, patient, policyholder, account holder or loyalty number |
| `employee id` | an employee, staff or student number |
| `username` | a person's username, login, handle (@handle), or a username inside a file path or URL |
| `passport number` | a passport number |
| `driver license number` | a driver's licence number |
| `password or access code` | a person's password, PIN, passcode, door or alarm code, verification or one-time code, recovery or backup code, Wi-Fi password, or answer to a security question (from round 10 on) |
| `api key` | an API key, access token or private key, the secret value only: not the setting's name, the host or the username beside it (from round 10 on) |

Never mark: companies, shops, banks, hospitals, schools, government bodies, products, brands; a town, region or
country named alone; public figures (politicians, celebrities, authors, historical people); fictional characters;
job titles and roles ("the tenant", "Dr."); dates that aren't a birth date; amounts, prices, percentages, order or
invoice numbers, case and ticket numbers, booking references and reservation codes, form and line numbers, tracking
numbers, SKUs, version and build numbers, commit hashes, request and error IDs, IP addresses; a company's own phone
number, email or address. A code of letters and digits is marked by what it is in context, not by how it looks: a
member number is marked, an order number written the same way isn't. A title or
honorific before a name (Mr., Dr., Herr, Mme) stays outside the span: `Dr. ⟦name|Okafor⟧`.

## What to write

* Make each document look like the real thing: its layout (key: value fields, tables, columns, headers and footers,
  checkboxes, signatures, quoted email replies), its length (from a few lines to a page or two), its clutter.
* Vary everything: the people's origins and how their names are written (family name first, particles like van der,
  de la, bin, al-, O', Mc, hyphenated, apostrophes, initials, nicknames, names that are ordinary words like Rose
  Hunter or Will Baker), the countries and their formats (addresses, phones, IDs, dates), the writing (formal, typed
  in a hurry, all lower case, all caps, typos, OCR misreadings like l for 1 and O for 0 in a scanned form).
* Put in the hard cases on purpose, a few in every document: a detail split across lines, a phone written bare in a
  sentence, a name with no title or label before it, a public figure next to a private person, an email in a
  signature, a username in a file path, a masked number, a second mention of a person by first name only.
* Some documents should have few or no personal details, and plenty of things that look like them but aren't
  (amounts, dates, codes, company names, places).

## Output

Write a JSON Lines file (one JSON object a line) to the path you're given, each object
`{"type": "...", "locale": "...", "text": "..."}`, `text` holding the document with its markup. Check with Python
that every line parses, that every `⟦` has a matching `⟧` with a known label and a `|`, and report how many documents
you wrote and of which types.
