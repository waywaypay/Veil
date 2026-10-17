# Audit of the held-out results

The Gretel labels are synthetic and noisy in both directions: roles and company names are
labelled as people ("Secondee", "Defaulting Party", "Boman Enterprises"), template text as
addresses ("1234 Street Name, City, Province"), while many real personal details carry no label
at all (dates of birth in CSV rows, SSNs, account and policy numbers, people's addresses beyond
the labelled span). The rule-based adjudication in `gretel.py` (`is_noise`) removes the obvious
cases; this audit judges the rest by hand.

## Method

`audit_sample.py` drew, from veil's output on the held-out Gretel test split (2,962 English
documents, never used for tuning), 100 adjudicated misses at random and 100 over-redacted runs
at random weighted by their words (as the over-redaction rate counts words), with seed 777
(`audit_sample.jsonl`). Each was judged by its context:

* a miss is **personal** when the span is a detail of a person a careful redactor should hide,
  and **not personal** otherwise (a role, a company, a product code, a template, a bank's code,
  a label word the gold span included);
* an over-redacted run is **ordinary** when it is ordinary text wrongly hidden, a **business
  contact** when it is a company's address or phone, and **personal or sensitive** when it is a
  person's detail the labels missed (a date of birth, an SSN, an account number, the city and
  ZIP of a labelled street).

An earlier sample (seed 2026) informed some fixes, so it is not used here. Six of the
over-redacted runs in this sample came from three bugs found by it, fixed since (a row of zeros
read as taxpayer IDs, "I've" taken into a name, an address label taking its sentence).

## Results

| | raw (adjudicated) | audited |
|---|---|---|
| Plain text, 2,962 documents: personal details found | 95.6% (366 of 8,342 missed) | **97.9%** (47 of 100 misses personal: ~172 missed; 95% interval 97.4–98.3%) |
| Plain text: words hidden by mistake | 1.10% | **0.26%** ordinary words (22 of the 94 runs not since fixed); 0.69% counting companies' contact details |
| Clean OCR, 300 documents: found | 94.4% | **96.6%** (OCR's own 11 misses all counted personal) |
| Degraded scans, 300 documents: found | 93.0% | **95.1%** (OCR's own 23 misses all counted personal) |
| OCR: words hidden by mistake | 1.02–1.05% | ~0.25% |

What the personal misses are: names and addresses run together with other fields in SWIFT,
FIX and EDI messages (`:60F:Curt J. Löwer`, `PatrickTurner`, `350 Payne Green` glued to an
account number); customer and employee IDs with no label near them (`Fu27362-S`,
`C23-74-740`); names in space-separated tables; and addresses whose street kind is written in
lower case (`6 Graham lane`). Below 99% the remaining gap is mostly these: values with no
context but their shape, which a rule can only catch by guessing the generator's formats.

## The judged sample

| # | kind | label | span | judged |
|---|---|---|---|---|
| 0 | miss | name | `Mason` | personal |
| 1 | miss | name | `Alex" "Smith` | personal |
| 2 | miss | street address | `6 Graham lane` | personal |
| 3 | miss | street address | `Toronto, Canada` | not personal |
| 4 | miss | name | `Curt J. Löwer` | personal |
| 5 | miss | bank / card / IBAN / SWIFT | `BBAN` | not personal |
| 6 | miss | customer / employee ID | `Fd-12035` | not personal |
| 7 | miss | name | `Defaulting Party` | not personal |
| 8 | miss | street address | `N3*456 Elm St.` | not personal |
| 9 | miss | street address | `6 Graham lane` | personal |
| 10 | miss | street address | `0008 Kent Springs⏎Aimeeside` | personal |
| 11 | miss | name | `Barker-Hughes` | personal |
| 12 | miss | name | `Non-Defaulting Party` | not personal |
| 13 | miss | customer / employee ID | `Cx-33520` | not personal |
| 14 | miss | bank / card / IBAN / SWIFT | `177736309` | not personal |
| 15 | miss | customer / employee ID | `Zy-20538` | personal |
| 16 | miss | customer / employee ID | `Zh-71984` | not personal |
| 17 | miss | customer / employee ID | `Zh-71984` | not personal |
| 18 | miss | name | `Gordon Ramsay's` | not personal |
| 19 | miss | street address | `75426 Bailey Island` | personal |
| 20 | miss | street address | `Toronto, Canada` | not personal |
| 21 | miss | street address | `1234 Street Name, City, Province, Postal Code` | not personal |
| 22 | miss | name | `PAUL BURG` | not personal |
| 23 | miss | street address | `7 boulevard Gérard Dupuis⏎59901⏎Le Roux⏎France` | personal |
| 24 | miss | name | `LAURENCE T. MORENO` | personal |
| 25 | miss | customer / employee ID | `Fu27362-S` | personal |
| 26 | miss | customer / employee ID | `Ek-82579` | not personal |
| 27 | miss | bank / card / IBAN / SWIFT | `BBAN` | not personal |
| 28 | miss | date of birth | `1910-08-16` | not personal |
| 29 | miss | name | `Mitchell G. Gibbs` | personal |
| 30 | miss | phone | `9847884667` | personal |
| 31 | miss | phone | `(0131) 4960150` | personal |
| 32 | miss | name | `targetsystem` | not personal |
| 33 | miss | name | `Confirmor` | not personal |
| 34 | miss | customer / employee ID | `Ia3440-R` | personal |
| 35 | miss | name | `jim\_brown789` | personal |
| 36 | miss | street address | `43989 April Falls, Apt. 822` | personal |
| 37 | miss | name | `Hague` | not personal |
| 38 | miss | name | `Markberg` | not personal |
| 39 | miss | customer / employee ID | `C23-74-740` | personal |
| 40 | miss | name | `John` | not personal |
| 41 | miss | email | `scott24@randall` | personal |
| 42 | miss | street address | `4 Smith forge, Apt. 797` | personal |
| 43 | miss | name | `Defaulting Party` | not personal |
| 44 | miss | street address | `71823 Victoria Station⏎71102, South Willie` | personal |
| 45 | miss | bank / card / IBAN / SWIFT | `BBAN` | not personal |
| 46 | miss | name | `targetsystem` | not personal |
| 47 | miss | customer / employee ID | `Hf-50315` | not personal |
| 48 | miss | street address | `66208 Spence Bypass` | personal |
| 49 | miss | name | `Ethan" "Williams` | personal |
| 50 | miss | name | `Berthelot` | not personal |
| 51 | miss | street address | `5678 Main Street, Anytown, UK AB1 2CD` | personal |
| 52 | miss | bank / card / IBAN / SWIFT | `344502819198156` | personal |
| 53 | miss | street address | `Thomas Heights Apt.` | personal |
| 54 | miss | name | `Andreachester` | not personal |
| 55 | miss | bank / card / IBAN / SWIFT | `MXOOUSHO591` | not personal |
| 56 | miss | name | `ABC123` | not personal |
| 57 | miss | customer / employee ID | `Hf-50315` | not personal |
| 58 | miss | name | `Livia F. d' Heripon` | personal |
| 59 | miss | name | `DianeRDaniel` | personal |
| 60 | miss | customer / employee ID | `Al-501` | personal |
| 61 | miss | street address | `Westminster, London, SW1A 2JR` | not personal |
| 62 | miss | name | `Non-Defaulting Party` | not personal |
| 63 | miss | customer / employee ID | `O-700343-O` | not personal |
| 64 | miss | name | `AI Chatbot` | not personal |
| 65 | miss | street address | `8 Clark estate, Flat 10P` | personal |
| 66 | miss | bank / card / IBAN / SWIFT | `472329181` | personal |
| 67 | miss | street address | `321 Orchard Road,Glasgow,Glasgow City` | personal |
| 68 | miss | SSN / passport / license | `G527-5319-475-0` | personal |
| 69 | miss | street address | `242 Lyons Estate Suite 143` | personal |
| 70 | miss | phone | `1-8` | not personal |
| 71 | miss | street address | `806 Aronsteeg, 2631PY, Lauwersoog` | personal |
| 72 | miss | SSN / passport / license | `16-045597-08` | not personal |
| 73 | miss | email | `[Consignee's Email Address` | not personal |
| 74 | miss | street address | `350 Payne Green Apt. 471` | personal |
| 75 | miss | bank / card / IBAN / SWIFT | `BBAN` | not personal |
| 76 | miss | name | `J Smith` | personal |
| 77 | miss | name | `Markberg` | not personal |
| 78 | miss | name | `Louis 778` | personal |
| 79 | miss | street address | `41 Pasadizo Sancho Valbuena, Alicante` | personal |
| 80 | miss | name | `Barker-Hughes` | personal |
| 81 | miss | customer / employee ID | `Vo-73752` | personal |
| 82 | miss | street address | `Manchester, UK` | not personal |
| 83 | miss | name | `Defaulting Party` | not personal |
| 84 | miss | phone | `1-800-EXAMPLE` | not personal |
| 85 | miss | street address | `7608 Lindsey Ramp` | personal |
| 86 | miss | street address | `123 Ocean Way⏎San Francisco, CA, USA` | not personal |
| 87 | miss | name | `Emily" "Davis` | personal |
| 88 | miss | name | `Ricky` | personal |
| 89 | miss | name | `CEO` | not personal |
| 90 | miss | customer / employee ID | `G-681154-H` | not personal |
| 91 | miss | street address | `North Patriciaburgh, 11933, USA` | not personal |
| 92 | miss | street address | `New Alejandra, UK` | not personal |
| 93 | miss | name | `Robert Mark Riggs` | personal |
| 94 | miss | name | `Smith Barney` | not personal |
| 95 | miss | street address | `094 Oconnor Mission, Apt.  SD, CA 92104, USA` | personal |
| 96 | miss | name | `Jane Smith, Esq.` | not personal |
| 97 | miss | customer / employee ID | `Xw-35442` | not personal |
| 98 | miss | street address | `N4*Other City, Other State Zip` | not personal |
| 99 | miss | bank / card / IBAN / SWIFT | `IBAN: GB43SFAO77222063071972` | not personal |
| 100 | over (3 words) | | `1991-12-30` | personal or sensitive |
| 101 | over (9 words) | | `112 Rue du Faubourg Saint-Honoré, 75008 Paris, France` | business contact |
| 102 | over (2 words) | | `I've` | ordinary (fixed since) |
| 103 | over (6 words) | | `was also verified during the assessment` | ordinary (fixed since) |
| 104 | over (2 words) | | `Pierangelo C` | personal or sensitive |
| 105 | over (2 words) | | `London, UK` | business contact |
| 106 | over (2 words) | | `523487654321/12345678901` | ordinary |
| 107 | over (5 words) | | `example.com", "555-123-4567` | personal or sensitive |
| 108 | over (8 words) | | `1234 Wheat Fields Lane, Kansas City, MO 64116` | business contact |
| 109 | over (1 words) | | `123456789` | business contact |
| 110 | over (7 words) | | `123 MAIN STREET/CITY, STATE, ZIP/US` | business contact |
| 111 | over (2 words) | | `34=123459` | ordinary |
| 112 | over (2 words) | | `038/093022CAD523456` | ordinary |
| 113 | over (216 words) | | `0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,` | ordinary (fixed since) |
| 114 | over (2 words) | | `EC3V 3QY` | business contact |
| 115 | over (9 words) | | `1234 Main Street, Suite 500⏎Washington D.C., USA` | business contact |
| 116 | over (3 words) | | `Linus","Van Pelt` | personal or sensitive |
| 117 | over (1 words) | | `0x23A3f09422233d340090fDe23222222222222223` | personal or sensitive |
| 118 | over (2 words) | | `34=123456` | ordinary |
| 119 | over (9 words) | | `34, King's Cross Lane,⏎London, EC1R 5EA, UK` | business contact |
| 120 | over (216 words) | | `0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,` | ordinary (fixed since) |
| 121 | over (2 words) | | `email.com` | personal or sensitive |
| 122 | over (2 words) | | `London, UK` | business contact |
| 123 | over (4 words) | | `54321:Jensen:AGNES LENA` | personal or sensitive |
| 124 | over (216 words) | | `0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,` | ordinary (fixed since) |
| 125 | over (2 words) | | `EDI MSDS` | ordinary |
| 126 | over (10 words) | | `123 Main Street, Suite 500⏎New York, NY 10001⏎USA` | business contact |
| 127 | over (1 words) | | `1234567890` | personal or sensitive |
| 128 | over (3 words) | | `123 Main Street` | business contact |
| 129 | over (10 words) | | `223 E 4th St, Ste 900, New York, NY 10009` | business contact |
| 130 | over (5 words) | | `05634 TIFFANY PORT, APT. 468` | personal or sensitive |
| 131 | over (1 words) | | `Germany` | personal or sensitive |
| 132 | over (4 words) | | `44 20 7992 1234` | business contact |
| 133 | over (6 words) | | `123 Main St.⏎Anytown, USA⏎12345` | business contact |
| 134 | over (3 words) | | `45, Kingfisher Drive` | personal or sensitive |
| 135 | over (2 words) | | `London, UK` | business contact |
| 136 | over (2 words) | | `Olive Grove` | ordinary |
| 137 | over (4 words) | | `Los Angeles, CA 90017` | personal or sensitive |
| 138 | over (1 words) | | `12345678901234567890` | ordinary |
| 139 | over (2 words) | | `Amsterdam, Netherlands` | business contact |
| 140 | over (1 words) | | `123456789` | personal or sensitive |
| 141 | over (1 words) | | `ABBYGB2L` | business contact |
| 142 | over (3 words) | | `123-456-789` | ordinary |
| 143 | over (1 words) | | `CLV` | ordinary |
| 144 | over (3 words) | | `456 Oak St` | personal or sensitive |
| 145 | over (1 words) | | `098765432109` | ordinary |
| 146 | over (1 words) | | `123456789012` | ordinary |
| 147 | over (3 words) | | `123-456-7890` | personal or sensitive |
| 148 | over (2 words) | | `MORABITOMIELCAREKSTR. 55` | personal or sensitive |
| 149 | over (216 words) | | `0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,` | ordinary (fixed since) |
| 150 | over (3 words) | | `1985-05-15` | personal or sensitive |
| 151 | over (7 words) | | `456 Beta Boulevard⏎New York, NY⏎10001` | business contact |
| 152 | over (3 words) | | `1978-12-23` | personal or sensitive |
| 153 | over (1 words) | | `0312222345US7654321000000000` | ordinary |
| 154 | over (6 words) | | `123 Main Street,City,State,12345` | business contact |
| 155 | over (2 words) | | `34=123456` | ordinary |
| 156 | over (5 words) | | `2345 Optical Ave, Suite 101` | business contact |
| 157 | over (1 words) | | `CHASUS33` | business contact |
| 158 | over (1 words) | | `123456789` | business contact |
| 159 | over (3 words) | | `456 Imaginary Lane` | business contact |
| 160 | over (2 words) | | `London, UK` | ordinary |
| 161 | over (7 words) | | `123 Main Street⏎Anytown, CA 12345⏎USA` | business contact |
| 162 | over (3 words) | | `Maple Glazed Salmon` | ordinary |
| 163 | over (2 words) | | `NW3 2LA` | personal or sensitive |
| 164 | over (10 words) | | `2784 West Bay Road, Grand Cayman, KY1-1203, Cayman Islands` | business contact |
| 165 | over (6 words) | | `555-555-5560","234 Cedar St` | personal or sensitive |
| 166 | over (2 words) | | `1901011234567890/1901011234567890` | ordinary |
| 167 | over (3 words) | | `Toronto, Ontario, Canada` | business contact |
| 168 | over (3 words) | | `1990-09-08` | personal or sensitive |
| 169 | over (3 words) | | `53 STACEY CORNERS` | personal or sensitive |
| 170 | over (10 words) | | `7675 TORRES MALL, SUITE 000, SAN FRANCISCO, CA, 94109, USA` | personal or sensitive |
| 171 | over (3 words) | | `43 High Street` | business contact |
| 172 | over (4 words) | | `Southampton, SO14 3ZA⏎UK` | personal or sensitive |
| 173 | over (3 words) | | `ADÈLE A. LÉGER` | personal or sensitive |
| 174 | over (4 words) | | `M1 2WD⏎Ui15755-T` | personal or sensitive |
| 175 | over (1 words) | | `123456789` | ordinary |
| 176 | over (5 words) | | `example.com", "555-567-8901` | personal or sensitive |
| 177 | over (10 words) | | `065 ELIZABETH PLAINS, APT. 84659/CITY/CA/91010-1234/US` | personal or sensitive |
| 178 | over (1 words) | | `CAD000000600` | ordinary |
| 179 | over (2 words) | | `123456789012*132456789012` | ordinary |
| 180 | over (3 words) | | `JEREMY LEON LONG` | personal or sensitive |
| 181 | over (1 words) | | `150134567891GBP10000` | ordinary |
| 182 | over (3 words) | | `7808 Brown Mission` | personal or sensitive |
| 183 | over (3 words) | | `Brighton, BN1 2CD` | personal or sensitive |
| 184 | over (9 words) | | `100 King Street West, Toronto, Ontario, M5X 1A1, Canada` | business contact |
| 185 | over (9 words) | | `456 West 48th Street, New York, NY 10036, USA` | business contact |
| 186 | over (7 words) | | `2311 Summerfield Rd, San Diego, CA 92104` | business contact |
| 187 | over (9 words) | | `225 Park Avenue South⏎New York, NY 10003⏎USA` | business contact |
| 188 | over (2 words) | | `V6B 1G1` | business contact |
| 189 | over (3 words) | | `5678 Elm St` | business contact |
| 190 | over (1 words) | | `20220315143000` | ordinary |
| 191 | over (1 words) | | `123456789` | personal or sensitive |
| 192 | over (2 words) | | `Toronto, Canada` | ordinary |
| 193 | over (2 words) | | `V6V 1G8` | business contact |
| 194 | over (1 words) | | `1234` | personal or sensitive |
| 195 | over (4 words) | | `Springfield, IL 62703, USA` | personal or sensitive |
| 196 | over (1 words) | | `CHASUS33` | business contact |
| 197 | over (8 words) | | `1234 Prepaid Way, Prepaid City, CA 90210, USA` | business contact |
| 198 | over (1 words) | | `GB22ABBY012345678901` | personal or sensitive |
| 199 | over (1 words) | | `987654321` | business contact |