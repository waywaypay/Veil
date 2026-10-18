"""Synthetic everyday documents with personal details written the ways they are in many countries: forms (key: value,
dotted leaders, tables, HTML, boxes split per field), letters, emails with quoted replies and signatures, record
exports (CSV, JSON, XML, YAML, SQL), logs and file paths, bank and pay statements, patient notes, passport data pages
with their MRZ, chat transcripts, shipping labels.  Among them the things that must stay: amounts, dates that aren't
a birth date, order, invoice, tracking and case numbers, IPs, versions, companies, places alone, public figures and
fictional characters.  Labels are (start, end, label) in the tagger's label names; a street address is one span with
the town, region and postcode written with it.  Every person is made up (Faker)."""
import contextlib
import io
import random
import string

from faker import Faker

# locale, weight, language of the form's field names
LOCALES = [("en_US", 14, "en"), ("en_GB", 6, "en"), ("en_CA", 3, "en"), ("en_AU", 3, "en"), ("en_IN", 4, "en"),
           ("en_IE", 1, "en"), ("en_NZ", 1, "en"), ("en_PH", 2, "en"), ("de_DE", 4, "de"), ("de_AT", 1, "de"),
           ("de_CH", 1, "de"), ("fr_FR", 4, "fr"), ("fr_CA", 1, "fr"), ("es_ES", 3, "es"), ("es_MX", 3, "es"),
           ("it_IT", 3, "it"), ("nl_NL", 2, "nl"), ("nl_BE", 1, "nl"), ("pt_BR", 3, "pt"), ("pt_PT", 1, "pt"),
           ("pl_PL", 2, "pl"), ("sv_SE", 1, "sv"), ("da_DK", 1, "en"), ("no_NO", 1, "en"), ("fi_FI", 1, "en"),
           ("cs_CZ", 1, "en"), ("tr_TR", 1, "en"), ("ro_RO", 1, "en"), ("hu_HU", 1, "en"), ("el_GR", 1, "en"),
           ("ja_JP", 1, "en"), ("zh_CN", 1, "en"), ("ko_KR", 1, "en"), ("ru_RU", 1, "en"), ("vi_VN", 1, "en"),
           ("id_ID", 1, "en"), ("th_TH", 1, "en"), ("he_IL", 1, "en")]
COUNTRY = {"en_US": "USA", "en_GB": "United Kingdom", "en_CA": "Canada", "en_AU": "Australia", "en_IN": "India",
           "en_IE": "Ireland", "en_NZ": "New Zealand", "en_PH": "Philippines", "de_DE": "Deutschland", "de_AT": "Österreich",
           "de_CH": "Schweiz", "fr_FR": "France", "fr_CA": "Canada", "es_ES": "España", "es_MX": "México", "it_IT": "Italia",
           "nl_NL": "Nederland", "nl_BE": "België", "pt_BR": "Brasil", "pt_PT": "Portugal", "pl_PL": "Polska",
           "sv_SE": "Sverige", "da_DK": "Danmark", "no_NO": "Norge", "fi_FI": "Suomi", "cs_CZ": "Česká republika",
           "tr_TR": "Türkiye", "ro_RO": "România", "hu_HU": "Magyarország", "el_GR": "Greece", "ja_JP": "Japan",
           "zh_CN": "China", "ko_KR": "Korea", "ru_RU": "Russia", "vi_VN": "Vietnam", "id_ID": "Indonesia",
           "th_TH": "Thailand", "he_IL": "Israel"}
# the locales whose Faker ssn() is a real national number (others fall back to a US-looking one)
REAL_SSN = {"en_US": "SSN", "en_GB": "National Insurance No.", "en_CA": "SIN", "de_AT": "SV-Nummer",
            "de_CH": "AHV-Nr.", "fr_FR": "N° de sécurité sociale", "it_IT": "Codice fiscale", "nl_NL": "BSN",
            "nl_BE": "Rijksregisternummer", "pl_PL": "PESEL", "sv_SE": "Personnummer", "no_NO": "Fødselsnummer",
            "fi_FI": "Henkilötunnus", "tr_TR": "T.C. Kimlik No", "zh_CN": "身份证号", "ko_KR": "주민등록번호",
            "th_TH": "เลขประจำตัวประชาชน", "ro_RO": "CNP", "es_MX": "NSS", "ru_RU": "ИНН", "en_PH": "SSS No."}
FIELDS = {
    "en": dict(name="Name", full="Full name", first="First name", last="Last name", dob="Date of birth",
               address="Address", phone="Phone", mobile="Mobile", email="Email", iban="IBAN", account="Account number",
               card="Card number", passport="Passport No.", licence="Driver's licence no.", customer="Customer ID",
               employee="Employee ID", username="Username", date="Date", amount="Amount", ref="Reference",
               company="Employer", nationality="Nationality", birthplace="Place of birth", sign="Signature"),
    "de": dict(name="Name", full="Vor- und Nachname", first="Vorname", last="Nachname", dob="Geburtsdatum",
               address="Anschrift", phone="Telefon", mobile="Mobil", email="E-Mail", iban="IBAN", account="Kontonummer",
               card="Kartennummer", passport="Reisepass-Nr.", licence="Führerschein-Nr.", customer="Kundennummer",
               employee="Personalnummer", username="Benutzername", date="Datum", amount="Betrag", ref="Aktenzeichen",
               company="Arbeitgeber", nationality="Staatsangehörigkeit", birthplace="Geburtsort", sign="Unterschrift"),
    "fr": dict(name="Nom", full="Nom et prénom", first="Prénom", last="Nom de famille", dob="Date de naissance",
               address="Adresse", phone="Téléphone", mobile="Portable", email="Courriel", iban="IBAN",
               account="N° de compte", card="N° de carte", passport="N° de passeport", licence="N° de permis",
               customer="N° client", employee="Matricule", username="Identifiant", date="Date", amount="Montant",
               ref="Référence", company="Employeur", nationality="Nationalité", birthplace="Lieu de naissance",
               sign="Signature"),
    "es": dict(name="Nombre", full="Nombre completo", first="Nombre", last="Apellidos", dob="Fecha de nacimiento",
               address="Domicilio", phone="Teléfono", mobile="Móvil", email="Correo electrónico", iban="IBAN",
               account="Número de cuenta", card="Número de tarjeta", passport="N.º de pasaporte",
               licence="N.º de licencia", customer="N.º de cliente", employee="N.º de empleado", username="Usuario",
               date="Fecha", amount="Importe", ref="Referencia", company="Empresa", nationality="Nacionalidad",
               birthplace="Lugar de nacimiento", sign="Firma"),
    "it": dict(name="Nome", full="Nome e cognome", first="Nome", last="Cognome", dob="Data di nascita",
               address="Indirizzo", phone="Telefono", mobile="Cellulare", email="E-mail", iban="IBAN",
               account="Numero di conto", card="Numero carta", passport="N. passaporto", licence="N. patente",
               customer="Codice cliente", employee="Matricola", username="Nome utente", date="Data", amount="Importo",
               ref="Riferimento", company="Datore di lavoro", nationality="Cittadinanza", birthplace="Luogo di nascita",
               sign="Firma"),
    "nl": dict(name="Naam", full="Volledige naam", first="Voornaam", last="Achternaam", dob="Geboortedatum",
               address="Adres", phone="Telefoon", mobile="Mobiel", email="E-mailadres", iban="IBAN",
               account="Rekeningnummer", card="Kaartnummer", passport="Paspoortnummer", licence="Rijbewijsnummer",
               customer="Klantnummer", employee="Personeelsnummer", username="Gebruikersnaam", date="Datum",
               amount="Bedrag", ref="Kenmerk", company="Werkgever", nationality="Nationaliteit",
               birthplace="Geboorteplaats", sign="Handtekening"),
    "pt": dict(name="Nome", full="Nome completo", first="Nome", last="Sobrenome", dob="Data de nascimento",
               address="Endereço", phone="Telefone", mobile="Celular", email="E-mail", iban="IBAN",
               account="Número da conta", card="Número do cartão", passport="N.º do passaporte", licence="N.º da CNH",
               customer="Código do cliente", employee="Matrícula", username="Usuário", date="Data", amount="Valor",
               ref="Referência", company="Empregador", nationality="Nacionalidade", birthplace="Naturalidade",
               sign="Assinatura"),
    "pl": dict(name="Imię i nazwisko", full="Imię i nazwisko", first="Imię", last="Nazwisko", dob="Data urodzenia",
               address="Adres", phone="Telefon", mobile="Tel. kom.", email="E-mail", iban="IBAN",
               account="Numer rachunku", card="Numer karty", passport="Nr paszportu", licence="Nr prawa jazdy",
               customer="Nr klienta", employee="Nr pracownika", username="Login", date="Data", amount="Kwota",
               ref="Sygnatura", company="Pracodawca", nationality="Obywatelstwo", birthplace="Miejsce urodzenia",
               sign="Podpis"),
    "sv": dict(name="Namn", full="Fullständigt namn", first="Förnamn", last="Efternamn", dob="Födelsedatum",
               address="Adress", phone="Telefon", mobile="Mobil", email="E-post", iban="IBAN", account="Kontonummer",
               card="Kortnummer", passport="Passnummer", licence="Körkortsnummer", customer="Kundnummer",
               employee="Anställningsnummer", username="Användarnamn", date="Datum", amount="Belopp", ref="Referens",
               company="Arbetsgivare", nationality="Medborgarskap", birthplace="Födelseort", sign="Underskrift"),
}
PUBLIC = ["Taylor Swift", "Elon Musk", "Angela Merkel", "Barack Obama", "Emmanuel Macron", "Narendra Modi",
          "Serena Williams", "Lionel Messi", "Oprah Winfrey", "Warren Buffett", "Jeff Bezos", "Greta Thunberg",
          "Shakespeare", "Albert Einstein", "Marie Curie", "Sherlock Holmes", "Harry Potter", "Hermione Granger",
          "Gandalf", "Darth Vader", "Mickey Mouse", "Jane Austen", "Beyoncé", "Cristiano Ronaldo", "Keir Starmer",
          "Olaf Scholz", "Frida Kahlo", "Tom Hanks", "Lewis Hamilton", "Rafael Nadal", "Dr. Seuss", "Santa Claus"]
NICK = ["Bob", "Liz", "Kate", "Mike", "Sam", "Alex", "Jo", "Danny", "Tash", "Rick", "Bea", "Chris", "Nicky"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
OCR = {"1": "l", "0": "O", "5": "S", "8": "B", "2": "Z", "l": "1", "O": "0", "I": "1", "S": "5", "B": "8", "o": "0",
       "e": "c", "m": "n", "rn": None}


class Doc:
    def __init__(self):
        self.parts, self.labels, self.n = [], [], 0

    def add(self, text, label=None):
        text = str(text)
        if label and text.strip():
            lead = len(text) - len(text.lstrip())
            self.labels.append((self.n + lead, self.n + len(text.rstrip()), label))
        self.parts.append(text)
        self.n += len(text)
        return self

    def text(self):
        return "".join(self.parts)


class Person:
    def __init__(self, r, loc):
        self.r, self.loc = r, loc
        self.f = f = Faker(loc)
        f.seed_instance(r.randrange(10 ** 9))
        self.lang = next(lang for l_, _, lang in LOCALES if l_ == loc)
        self.first, self.last = f.first_name(), f.last_name()
        if r.random() < 0.06:   # names that are ordinary words
            self.first, self.last = r.choice([("Rose", "Hunter"), ("Will", "Baker"), ("Grace", "Church"),
                                              ("Hope", "Mason"), ("Joy", "Fisher"), ("Mark", "Young"),
                                              ("Faith", "Cook"), ("Ivy", "Rich"), ("Rich", "Gardner")])
        if r.random() < 0.08:   # particles, prefixes, hyphens, apostrophes
            self.last = r.choice(["van der ", "de la ", "O'", "Mc", "al-", "bin ", "di ", "von ", "St. ", "Fitz",
                                  "dos ", "ten "]) + self.last if r.random() < 0.6 else f"{self.last}-{f.last_name()}"
        self.family_first = loc in ("ja_JP", "zh_CN", "ko_KR", "hu_HU", "vi_VN")
        self.middle = r.choice(string.ascii_uppercase) if r.random() < 0.25 and not self.family_first else ""
        self.dob = f.date_of_birth(minimum_age=18, maximum_age=90)
        addr = f.address()
        self.address_lines = [a for a in addr.split("\n") if a.strip()]
        self.country = COUNTRY[loc]
        self.city = f.city()

    def name(self, style=None):
        r, first, last = self.r, self.first, self.last
        if self.family_first and self.loc in ("ja_JP", "zh_CN", "ko_KR"):
            return f"{last}{first}" if r.random() < 0.5 else f"{last} {first}"
        style = style or r.choices(["full", "middle", "last_first", "caps", "initial", "nick", "first", "last"],
                                   [40, 10, 10, 8, 8, 3, 6, 4])[0]
        mid = f" {self.middle}." if self.middle else ""
        return {"full": f"{first} {last}", "middle": f"{first}{mid} {last}", "last_first": f"{last}, {first}",
                "caps": f"{last.upper()}, {first.upper()}" if r.random() < 0.5 else f"{first} {last}".upper(),
                "initial": f"{first[0]}. {last}", "nick": f"{first} \"{r.choice(NICK)}\" {last}", "first": first,
                "last": last}[style]

    def email(self):
        r, f = self.r, self.f
        base = "".join(c for c in Faker("en_US").first_name().lower() if c.isalpha()) if not self.first.isascii() \
            else "".join(c for c in self.first.lower() if c.isalnum())
        lastb = "".join(c for c in self.last.lower() if c.isalnum() and c.isascii()) or "x"
        user = r.choice([f"{base}.{lastb}", f"{base[0]}{lastb}", f"{base}{r.randint(1, 99)}", f"{lastb}.{base}",
                         f"{base}_{lastb}{r.randint(70, 99)}", f.user_name()])
        dom = r.choice([f.free_email_domain(), f.domain_name(), "gmail.com", "outlook.com", "yahoo.co.uk", "web.de",
                        "icloud.com", "proton.me", "hotmail.fr", "libero.it"])
        e = f"{user}@{dom}"
        if r.random() < 0.05:
            e = e.replace("@", r.choice([" at ", " [at] ", "(at)"])).replace(".", r.choice([" dot ", "[.]", "."]), 1)
        return e

    def phone(self):
        r = self.r
        try:
            with contextlib.redirect_stdout(io.StringIO()):   # en_NZ prints a notice
                p = self.f.phone_number()
        except AttributeError:   # a locale without phone formats
            p = r.choice([f"+63 9{r.randint(10, 99)} {r.randint(100, 999)} {r.randint(1000, 9999)}",
                          f"09{r.randint(10, 99)}-{r.randint(100, 999)}-{r.randint(1000, 9999)}"])
        if r.random() < 0.15:
            p = "".join(c for c in p if c.isdigit() or c == "+")
        elif r.random() < 0.1:
            p = p.replace(" ", ".").replace("-", ".")
        return p

    def address(self, one_line=None):
        lines = self.address_lines + ([self.country] if self.r.random() < 0.3 else [])
        one_line = self.r.random() < 0.4 if one_line is None else one_line
        return ", ".join(lines) if one_line else "\n".join(lines)

    def national_id(self):
        r, f = self.r, self.f
        if self.loc in REAL_SSN:
            v = f.ssn()
            kind = "ssn" if self.loc == "en_US" else "tax id"
            if kind == "ssn" and r.random() < 0.15:
                v = r.choice(["XXX-XX-", "***-**-", "xxx-xx-"]) + v[-4:]
            return REAL_SSN[self.loc], v, kind
        if self.loc == "es_ES":
            return ("DNI", f.nif(), "tax id") if r.random() < 0.7 else ("NIE", f.nie(), "tax id")
        if self.loc == "pt_BR":
            return "CPF", f.cpf(), "tax id"
        if self.loc == "en_IN":
            return ("Aadhaar", f.aadhaar_id(), "tax id") if r.random() < 0.5 else \
                ("PAN", "".join(r.choices(string.ascii_uppercase, k=5)) + f"{r.randint(0, 9999):04d}" +
                 r.choice(string.ascii_uppercase), "tax id")
        if self.loc in ("de_DE",):
            return "Steuer-ID", f"{r.randint(1, 9)}{r.randint(0, 10 ** 10 - 1):010d}", "tax id"
        if self.loc == "en_AU":
            return "TFN", f"{r.randint(100, 999)} {r.randint(100, 999)} {r.randint(100, 999)}", "tax id"
        if self.loc == "ja_JP":
            return "マイナンバー", f"{r.randint(1000, 9999)} {r.randint(1000, 9999)} {r.randint(1000, 9999)}", "tax id"
        if self.loc == "da_DK":
            return "CPR-nr.", f"{self.dob:%d%m%y}-{r.randint(0, 9999):04d}", "tax id"
        if self.loc == "fr_CA":
            return "NAS", f"{r.randint(100, 999)} {r.randint(100, 999)} {r.randint(100, 999)}", "tax id"
        return "National ID", f"{r.randint(10 ** 8, 10 ** 10)}", "tax id"

    def card(self):
        r = self.r
        n = self.f.credit_card_number()
        if r.random() < 0.3:
            return r.choice(["**** **** **** ", "XXXX-XXXX-XXXX-", "•••• ", "ending in ", "xxxx"]) + n[-4:]
        if r.random() < 0.5 and len(n) == 16:
            return " ".join(n[i:i + 4] for i in range(0, 16, 4))
        return n

    def account(self):
        r, f = self.r, self.f
        if self.loc == "en_GB" and r.random() < 0.6:
            return f"{r.randint(10, 99)}-{r.randint(10, 99)}-{r.randint(10, 99)} {r.randint(10 ** 7, 10 ** 8 - 1)}"
        if self.loc == "en_US" and r.random() < 0.5:
            return f"{r.randint(10 ** 8, 10 ** 9 - 1)}" if r.random() < 0.5 else f"{r.randint(10 ** 9, 10 ** 12)}"
        v = f.bban()
        return r.choice(["****", "XXXX", "…"]) + v[-4:] if r.random() < 0.2 else v

    def iban(self):
        v = self.f.iban()
        return " ".join(v[i:i + 4] for i in range(0, len(v), 4)) if self.r.random() < 0.5 else v

    def username(self):
        r = self.r
        u = r.choice([self.f.user_name(), f"{self.first[0].lower()}{self.last.lower()}",
                      f"{self.first.lower()}_{r.randint(1, 999)}", f"{self.last.lower()}{self.first[:2].lower()}"])
        return "".join(c for c in u if c.isalnum() or c in "._-") or self.f.user_name()

    def passport(self):
        return self.f.passport_number() if self.r.random() < 0.7 else \
            "".join(self.r.choices(string.ascii_uppercase, k=2)) + f"{self.r.randint(0, 9999999):07d}"

    def licence(self):
        r = self.r
        if self.loc == "en_US":
            return r.choice([f"{r.choice(string.ascii_uppercase)}{r.randint(0, 10 ** 12):012d}",
                             f"{r.choice(string.ascii_uppercase)}{r.randint(100, 999)}-{r.randint(100, 999)}-{r.randint(100, 999)}-{r.randint(100, 999)}",
                             f"{r.randint(10 ** 7, 10 ** 8 - 1)}", f"D{r.randint(1000000, 9999999)}"])
        if self.loc == "en_GB":
            return f"{self.last[:5].upper():9<5}{self.dob:%y}{self.dob.month:02d}{self.dob:%d}{self.first[0].upper()}9{r.choice('ABCDEFGHJK')}{r.randint(10, 99)}"
        return "".join(r.choices(string.ascii_uppercase + string.digits, k=r.randint(8, 12)))

    def customer_id(self):
        r = self.r
        return r.choice([f"C{r.randint(10 ** 5, 10 ** 7)}", f"{r.randint(10 ** 7, 10 ** 9)}",
                         f"CUST-{r.randint(1000, 99999):05d}", f"M{r.randint(10 ** 6, 10 ** 8)}-{r.randint(1, 99):02d}",
                         f"{''.join(r.choices(string.ascii_uppercase, k=3))}{r.randint(10 ** 6, 10 ** 9)}",
                         f"{r.randint(10 ** 6, 10 ** 8)}"])

    def employee_id(self):
        r = self.r
        return r.choice([f"E{r.randint(10000, 999999)}", f"{r.randint(100000, 9999999)}", f"EMP-{r.randint(100, 99999):05d}",
                         f"S{r.randint(10 ** 6, 10 ** 8)}", f"{self.last[:3].upper()}{r.randint(100, 9999)}"])

    def dob_text(self):
        d, r = self.dob, self.r
        styles = [f"{d:%d/%m/%Y}", f"{d:%m/%d/%Y}", f"{d:%Y-%m-%d}", f"{d:%d.%m.%Y}", f"{d.day} {MONTHS[d.month - 1]} {d.year}",
                  f"{MONTHS[d.month - 1]} {d.day}, {d.year}", f"{d:%d-%b-%Y}".upper(), f"{d:%d %b %Y}", f"{d:%m-%d-%y}",
                  f"{d.year}年{d.month}月{d.day}日" if self.loc in ("ja_JP", "zh_CN") else f"{d:%d/%m/%y}"]
        return styles[0] if self.loc != "en_US" and r.random() < 0.4 else \
            styles[1] if self.loc == "en_US" and r.random() < 0.5 else r.choice(styles)


def other_date(r):
    y, m, d = r.randint(2015, 2026), r.randint(1, 12), r.randint(1, 28)
    return r.choice([f"{d:02d}/{m:02d}/{y}", f"{m:02d}/{d:02d}/{y}", f"{y}-{m:02d}-{d:02d}", f"{d:02d}.{m:02d}.{y}",
                     f"{d} {MONTHS[m - 1]} {y}", f"{MONTHS[m - 1][:3]} {d}, {y}"])


def amount(r):
    v = r.randint(1, 999999) / r.choice([1, 100])
    cur = r.choice(["$", "€", "£", "", "USD ", "EUR ", "CHF ", "R$ ", "₹", "¥", "zł "])
    return r.choice([f"{cur}{v:,.2f}", f"{v:,.2f} {cur.strip() or 'EUR'}", f"{cur}{v:.2f}".replace(".", ","), f"({cur}{v:,.2f})"])


def ref(r):
    return r.choice([f"INV-{r.randint(10000, 999999)}", f"Order #{r.randint(100000, 9999999)}", f"PO {r.randint(1000, 99999)}",
                     f"Case No. {r.randint(1, 30)}-cv-{r.randint(100, 9999)}", f"1Z{''.join(r.choices(string.ascii_uppercase + string.digits, k=16))}",
                     f"Ticket {r.choice(['INC', 'REQ', 'CS'])}{r.randint(100000, 999999)}", f"Ref. {r.randint(1000, 9999)}/{r.randint(2015, 2026)}",
                     f"SKU {r.randint(100, 999)}-{r.randint(1000, 9999)}", f"v{r.randint(1, 9)}.{r.randint(0, 20)}.{r.randint(0, 99)}",
                     f"IP {r.randint(1, 223)}.{r.randint(0, 255)}.{r.randint(0, 255)}.{r.randint(1, 254)}",
                     f"Policy form {r.choice(['HO-3', 'PA-2', 'DP-1'])}", f"Batch {r.randint(1, 999)}"])


def labelled(d, p, key, r, lang=None):
    """Write one field's value (and return whether one was written)."""
    if key == "name":
        d.add(p.name(), "name")
    elif key == "first":
        d.add(p.first, "name")
    elif key == "last":
        d.add(p.last, "name")
    elif key == "dob":
        d.add(p.dob_text(), "date of birth")
    elif key == "address":
        d.add(p.address(), "street address")
    elif key in ("phone", "mobile"):
        d.add(p.phone(), "phone number")
    elif key == "email":
        d.add(p.email(), "email address")
    elif key == "iban":
        d.add(p.iban(), "iban")
    elif key == "account":
        d.add(p.account(), "account number")
    elif key == "card":
        d.add(p.card(), "credit card number")
    elif key == "passport":
        d.add(p.passport(), "passport number")
    elif key == "licence":
        d.add(p.licence(), "driver license number")
    elif key == "customer":
        d.add(p.customer_id(), "customer id")
    elif key == "employee":
        d.add(p.employee_id(), "employee id")
    elif key == "username":
        d.add(p.username(), "username")
    elif key == "id":
        _, v, kind = p.national_id()
        d.add(v, kind)
    elif key == "date":
        d.add(other_date(r))
    elif key == "amount":
        d.add(amount(r))
    elif key == "ref":
        d.add(ref(r))
    elif key == "company":
        d.add(p.f.company())
    elif key == "nationality":
        d.add(p.country)
    elif key == "birthplace":
        d.add(p.city)
    elif key == "sign":
        d.add(p.name("full"), "name") if r.random() < 0.5 else d.add("________________")


def field_name(p, key):
    if key == "id":
        return p.national_id()[0]
    return FIELDS.get(p.lang, FIELDS["en"])[key]


# -- documents -------------------------------------------------------------------------------------------------------

def form(r, p):
    d = Doc()
    title = r.choice(["APPLICATION FORM", "New customer registration", "Patient intake form", "Rental application",
                      "Know Your Customer (KYC) form", "Change of address", "Membership application", "Claim form",
                      "Antrag", "Formulaire d'inscription", "Solicitud", "Modulo di adesione", "Aanvraagformulier",
                      "Employee onboarding", "Direct debit mandate", "Beneficiary designation", "Visa application"])
    d.add(f"{title}\n" + (f"{p.f.company()}\n" if r.random() < 0.5 else "") + "\n")
    keys = ["name"] if r.random() < 0.5 else ["first", "last"]
    keys += r.sample(["dob", "address", "phone", "mobile", "email", "id", "iban", "account", "card", "passport",
                      "licence", "customer", "employee", "username"], r.randint(3, 7))
    keys += r.sample(["date", "amount", "ref", "company", "nationality", "birthplace"], r.randint(1, 4))
    head = 1 if keys[0] == "name" else 2
    rest = keys[head:]
    r.shuffle(rest)
    keys = keys[:head] + rest
    style = r.randrange(7)
    caps = r.random() < 0.2
    for i, k in enumerate(keys):
        fn = field_name(p, k)
        fn = fn.upper() if caps else fn
        if style == 0:
            d.add(f"{fn}: ")
        elif style == 1:
            d.add(f"{fn}\n")
        elif style == 2:
            d.add(f"{fn} {'.' * r.randint(3, 25)} ")
        elif style == 3:
            d.add(f"| {fn} | ")
        elif style == 4:
            d.add(f"<tr><td>{fn}</td><td>")
        elif style == 5:
            d.add(f"{i + 1}. {fn}{r.choice([':', '', ' -'])} ")
        else:
            d.add(f"[{fn}] ")
        if k == "address" and style in (3, 4):
            d.add(p.address(one_line=True), "street address")
        else:
            labelled(d, p, k, r)
        d.add({3: " |\n", 4: "</td></tr>\n"}.get(style, "\n" if style != 6 or r.random() < 0.6 else "   "))
    if r.random() < 0.5:
        d.add(r.choice(["\nMarital status: [x] Married [ ] Single [ ] Divorced\n", "\nGender: M [ ] F [X] Other [ ]\n",
                        "\n☑ I agree to the terms   ☐ Send me offers\n", "\nEmployment: (•) Full-time ( ) Part-time\n"]))
    if r.random() < 0.6:
        d.add(f"\n{field_name(p, 'sign')}: ")
        labelled(d, p, "sign", r)
        d.add(f"    {field_name(p, 'date')}: {other_date(r)}\n")
    return d


def letter(r, p):
    d, q = Doc(), Person(r, p.loc if r.random() < 0.7 else pick(r))
    if r.random() < 0.5:
        d.add(p.name("full"), "name").add("\n").add(p.address(one_line=False), "street address").add("\n\n")
    else:
        d.add(f"{p.f.company()}\n{r.choice(['Customer Service', 'Accounts Department', 'Human Resources', 'Claims'])}\n\n")
    d.add(f"{other_date(r)}\n\n")
    d.add(q.name(r.choice(["full", "middle", "caps"])), "name").add("\n").add(q.address(one_line=False), "street address")
    d.add("\n\n")
    if r.random() < 0.6:
        k = r.choice(["account", "customer", "card", "id", "ref"])
        d.add(f"Re: {field_name(q, k) if k != 'ref' else 'Your reference'} ")
        labelled(d, q, k, r)
        d.add("\n\n")
    title = r.choice(["Mr.", "Ms.", "Mrs.", "Dr.", "Mx.", ""])
    d.add(f"Dear {title} " if title else "Dear ").add(q.last if title else q.first, "name").add(",\n\n")
    bodies = [lambda: d.add(f"Thank you for your payment of {amount(r)} received on {other_date(r)}. "),
              lambda: d.add("We tried to reach you on ").add(q.phone(), "phone number").add(" but could not get through. "),
              lambda: d.add("Please confirm that your date of birth is ").add(q.dob_text(), "date of birth").add(". "),
              lambda: d.add(f"As {r.choice(PUBLIC)} once said, it's never too late. "),
              lambda: d.add(f"Your order {ref(r)} will be shipped to the address above. "),
              lambda: d.add("A copy has been sent to ").add(q.email(), "email address").add(". "),
              lambda: d.add(f"Our office in {p.city} is open until {r.randint(4, 7)} pm. "),
              lambda: d.add(f"Your new statement shows a balance of {amount(r)}. "),
              lambda: d.add("Your colleague ").add(Person(r, q.loc).name("full"), "name").add(" asked us to write. "),
              lambda: d.add("Funds will be paid into ").add(q.iban(), "iban").add(". ")]
    for b in r.sample(bodies, r.randint(2, 5)):
        b()
    d.add(f"\n\n{r.choice(['Sincerely', 'Kind regards', 'Best wishes', 'Yours faithfully', 'Mit freundlichen Grüßen', 'Cordialement'])},\n\n")
    if r.random() < 0.6:
        d.add(p.name("full"), "name").add("\n")
        if r.random() < 0.5:
            d.add(r.choice(["Tel: ", "T ", "Phone: ", "Mob. "])).add(p.phone(), "phone number").add(" | ").add(p.email(), "email address").add("\n")
    else:
        d.add(f"{r.choice(['The Claims Team', 'Customer Services', 'HR Operations'])}\n{p.f.company()}\n")
    return d


def email(r, p):
    d, q = Doc(), Person(r, p.loc if r.random() < 0.6 else pick(r))
    d.add("From: ")
    if r.random() < 0.7:
        q_ = '"' if r.random() < 0.5 else ""
        d.add(q_).add(p.name(r.choice(["full", "last_first"])), "name").add(f"{q_} <")
        d.add(p.email(), "email address").add(">\n")
    else:
        d.add(p.email(), "email address").add("\n")
    d.add("To: ").add(q.name("full"), "name").add(" <").add(q.email(), "email address").add(">\n")
    if r.random() < 0.3:
        d.add("Cc: ").add(Person(r, q.loc).email(), "email address").add("\n")
    d.add(f"Date: {r.choice(['Mon', 'Tue', 'Wed', 'Thu', 'Fri'])}, {other_date(r)} {r.randint(8, 18)}:{r.randint(0, 59):02d}\n")
    d.add(f"Subject: {r.choice(['RE: ', 'Fwd: ', ''])}{r.choice(['invoice', 'your application', 'quick question', 'Updated details', 'meeting next week', 'Account access', 'payroll change'])}\n\n")
    d.add(r.choice(["Hi ", "Hello ", "Dear ", "hey ", ""])).add(q.first, "name").add(",\n\n")
    lines = [lambda: d.add("my new number is ").add(p.phone(), "phone number").add(", the old one is gone. "),
             lambda: d.add(f"The invoice {ref(r)} for {amount(r)} is attached. "),
             lambda: d.add("can you update my bank details to ").add(p.iban(), "iban").add(" please. "),
             lambda: d.add(f"See you at the {r.choice(['Hilton', 'Marriott', 'WeWork', 'Starbucks'])} in {q.city} on {other_date(r)}. "),
             lambda: d.add("I've cc'd ").add(Person(r, p.loc).name("first"), "name").add(" who handles this. "),
             lambda: d.add("Login is ").add(p.username(), "username").add(" if you need to check. "),
             lambda: d.add(f"Did you see what {r.choice(PUBLIC)} said yesterday? "),
             lambda: d.add("My employee number is ").add(p.employee_id(), "employee id").add(". "),
             lambda: d.add("Ship it to ").add(p.address(one_line=True), "street address").add(". ")]
    for b in r.sample(lines, r.randint(2, 4)):
        b()
    d.add("\n\n")
    if r.random() < 0.5:
        d.add(f"{r.choice(['Thanks', 'Cheers', 'Best', 'BR', 'Regards'])},\n").add(p.name(r.choice(["first", "full"])), "name").add("\n")
    if r.random() < 0.5:
        d.add("--\n").add(p.name("full"), "name").add(f"\n{p.f.job()}, {p.f.company()}\n")
        d.add(r.choice(["M: ", "Mobile: ", "Tel. ", "☎ "])).add(p.phone(), "phone number").add("\n")
    if r.random() < 0.4:
        d.add(f"\nOn {other_date(r)}, ").add(q.name("full"), "name").add(" <").add(q.email(), "email address").add("> wrote:\n> ")
        d.add(r.choice(["Please send me the signed copy.", "Can you confirm the amount?", "Thanks, see below."]))
        d.add("\n> ").add(q.first, "name").add("\n")
    return d


def records(r, p):
    d = Doc()
    people = [p] + [Person(r, p.loc if r.random() < 0.7 else pick(r)) for _ in range(r.randint(1, 5))]
    cols = ["name"] + r.sample(["email", "phone", "dob", "address", "customer", "account", "username", "id", "card"],
                               r.randint(2, 4)) + r.sample(["date", "amount", "ref"], r.randint(1, 2))
    names = {"name": "name", "email": "email", "phone": "phone", "dob": "dob", "address": "address",
             "customer": "customer_id", "account": "account_no", "username": "username", "id": "national_id",
             "card": "card_number", "date": "created_at", "amount": "amount", "ref": "order_ref"}
    fmt = r.choice(["csv", "tsv", "json", "xml", "yaml", "sql", "md"])

    def cell(q, c):
        if c == "address":
            d.add(q.address(one_line=True), "street address")
        else:
            labelled(d, q, c, r)

    if fmt in ("csv", "tsv", "md"):
        sep = {"csv": ",", "tsv": "\t", "md": " | "}[fmt]
        d.add(sep.join(names[c] for c in cols) + "\n")
        if fmt == "md":
            d.add(" | ".join("---" for _ in cols) + "\n")
        for q in people:
            for i, c in enumerate(cols):
                quote = fmt == "csv" and c in ("name", "address") and r.random() < 0.7
                d.add(('"' if quote else "") if i == 0 else sep + ('"' if quote else ""))
                cell(q, c)
                d.add('"' if quote else "")
            d.add("\n")
    elif fmt == "json":
        d.add("[\n")
        for qi, q in enumerate(people):
            d.add("  {")
            for i, c in enumerate(cols):
                d.add(f'{", " if i else ""}"{names[c]}": "')
                cell(q, c)
                d.add('"')
            d.add("}" + ("," if qi < len(people) - 1 else "") + "\n")
        d.add("]\n")
    elif fmt == "xml":
        d.add("<customers>\n")
        for q in people:
            d.add("  <customer>")
            for c in cols:
                d.add(f"<{names[c]}>")
                cell(q, c)
                d.add(f"</{names[c]}>")
            d.add("</customer>\n")
        d.add("</customers>\n")
    elif fmt == "yaml":
        for q in people:
            for i, c in enumerate(cols):
                d.add(f"{'- ' if i == 0 else '  '}{names[c]}: ")
                cell(q, c)
                d.add("\n")
    else:
        for q in people:
            d.add(f"INSERT INTO customers ({', '.join(names[c] for c in cols)}) VALUES (")
            for i, c in enumerate(cols):
                d.add(("'" if i == 0 else ", '"))
                cell(q, c)
                d.add("'")
            d.add(");\n")
    return d


def logs(r, p):
    d = Doc()
    for _ in range(r.randint(3, 8)):
        ts = f"{r.randint(2022, 2026)}-{r.randint(1, 12):02d}-{r.randint(1, 28):02d}T{r.randint(0, 23):02d}:{r.randint(0, 59):02d}:{r.randint(0, 59):02d}Z"
        lvl = r.choice(["INFO", "WARN", "ERROR", "DEBUG"])
        ip = f"{r.randint(1, 223)}.{r.randint(0, 255)}.{r.randint(0, 255)}.{r.randint(1, 254)}"
        k = r.randrange(7)
        d.add(f"{ts} {lvl} ")
        if k == 0:
            d.add("auth: login ok user=").add(p.username(), "username").add(f" ip={ip} session={r.getrandbits(48):x}\n")
        elif k == 1:
            d.add("mailer: sent receipt to=").add(p.email(), "email address").add(f" order={ref(r)} bytes={r.randint(100, 99999)}\n")
        elif k == 2:
            d.add("fs: opened /home/").add(p.username(), "username").add(f"/{r.choice(['Documents', 'Downloads', 'projects'])}/{r.choice(['report', 'tax', 'cv', 'data'])}_{r.randint(2020, 2026)}.{r.choice(['pdf', 'xlsx', 'csv'])}\n")
        elif k == 3:
            d.add("sync: C:\\Users\\").add(p.username(), "username").add(r"\AppData\Local\Temp\cache" + f"{r.randint(1, 99)}.tmp\n")
        elif k == 4:
            d.add(f"http: GET /api/v{r.randint(1, 3)}/users?email=").add(p.email().replace("@", "%40"), "email address").add(f" 200 {r.randint(5, 900)}ms\n")
        elif k == 5:
            d.add(f"billing: charge {amount(r)} card=").add(p.card(), "credit card number").add(" status=declined\n")
        else:
            d.add(f"worker: job {r.getrandbits(32):08x} done in {r.randint(1, 9999)}ms, retries={r.randint(0, 3)}, host=web-{r.randint(1, 40)}\n")
    if r.random() < 0.3:
        d.add(f"git: commit {r.getrandbits(160):040x}\nAuthor: ").add(p.name("full"), "name").add(" <").add(p.email(), "email address").add(">\n")
    return d


def statement(r, p):
    d = Doc()
    kind = r.choice(["bank", "pay"])
    d.add(f"{p.f.company().upper() if r.random() < 0.5 else p.f.company()}\n")
    d.add("STATEMENT OF ACCOUNT\n" if kind == "bank" else r.choice(["EARNINGS STATEMENT\n", "Payslip\n", "Gehaltsabrechnung\n"]))
    d.add(p.name(r.choice(["full", "caps", "middle"])), "name").add("\n").add(p.address(one_line=False), "street address").add("\n\n")
    if kind == "bank":
        d.add(f"{field_name(p, 'account')}: ").add(p.account(), "account number").add(f"    Period: {other_date(r)} – {other_date(r)}\n")
        if r.random() < 0.5:
            d.add("IBAN: ").add(p.iban(), "iban").add("   BIC: ").add(p.f.swift(), "swift code").add("\n")
        d.add("\nDate        Description                         Amount      Balance\n")
        for _ in range(r.randint(3, 9)):
            desc = r.choice([f"CARD PURCHASE {p.f.company()[:18].upper()}", f"DIRECT DEBIT {p.f.company()[:16].upper()}",
                             "ATM WITHDRAWAL", f"TRANSFER FROM {Person(r, p.loc).name('caps')[:22]}", "INTEREST", f"SALARY {p.f.company()[:14].upper()}",
                             f"STANDING ORDER REF {r.randint(1000, 99999)}"])
            if desc.startswith("TRANSFER FROM"):
                d.add(f"{other_date(r):<12}TRANSFER FROM ").add(desc[14:], "name").add(f"{' ' * max(1, 24 - len(desc[14:]))}{amount(r):>12}  {amount(r):>12}\n")
            else:
                d.add(f"{other_date(r):<12}{desc:<36}{amount(r):>12}  {amount(r):>12}\n")
    else:
        d.add(f"{field_name(p, 'employee')}: ").add(p.employee_id(), "employee id")
        _, v, kind_ = p.national_id()
        d.add(f"   {p.national_id()[0]}: ").add(v, kind_).add(f"\nPay period: {other_date(r)} to {other_date(r)}   Pay date: {other_date(r)}\n\n")
        for item in r.sample(["Regular", "Overtime", "Bonus", "Federal tax", "State tax", "Social Security", "Medicare",
                              "401(k)", "Health ins.", "Lohnsteuer", "Solidaritätszuschlag", "NI contribution"], r.randint(4, 8)):
            d.add(f"{item:<20}{r.randint(1, 80):>4}.00  {amount(r):>14}  YTD {amount(r):>14}\n")
        d.add(f"\nNet pay {amount(r)} deposited to account ").add(p.account(), "account number").add("\n")
    return d


def medical(r, p):
    d = Doc()
    doc_ = Person(r, p.loc)
    d.add(f"{r.choice(['St. Mary’s Hospital', 'City Medical Centre', 'Riverside Clinic', 'Klinikum Nord', 'Hôpital Saint-Louis'])}\n")
    d.add(r.choice(["PATIENT: ", "Patient name: ", "Pt: ", "Name: "])).add(p.name(r.choice(["caps", "last_first", "full"])), "name")
    d.add(r.choice(["   DOB: ", "  D.O.B. ", "\nDate of birth: ", "  Born "])).add(p.dob_text(), "date of birth")
    d.add(r.choice(["   MRN: ", "\nMRN ", "  Patient ID: ", "  Hospital no. "])).add(p.customer_id(), "customer id").add("\n")
    if r.random() < 0.6:
        d.add(f"Insurance: {r.choice(['Aetna', 'BUPA', 'AOK', 'Blue Cross', 'Medicare', 'NHS'])}  Member ID: ").add(p.customer_id(), "customer id").add("\n")
    d.add(f"Visit: {other_date(r)}   Attending: Dr. ").add(doc_.last, "name").add("\n\n")
    d.add(f"S: {r.randint(18, 90)}yo presents with {r.choice(['chest pain', 'cough x3 days', 'lower back pain', 'headache', 'rash'])}. ")
    d.add(f"BP {r.randint(100, 160)}/{r.randint(60, 100)}, HR {r.randint(50, 110)}, T {r.randint(360, 395) / 10}°C, SpO2 {r.randint(90, 100)}%.\n")
    d.add(f"A: {r.choice(['J06.9', 'M54.5', 'R07.4', 'L30.9', 'I10'])} – {r.choice(['URTI', 'lumbago', 'chest pain, unspecified', 'dermatitis', 'hypertension'])}\n")
    d.add(f"P: {r.choice(['Amoxicillin 500 mg TDS x7d', 'Ibuprofen 400 mg PRN', 'Lisinopril 10 mg OD', 'review in 2/52'])}\n")
    if r.random() < 0.5:
        d.add("NOK: ").add(Person(r, p.loc).name("full"), "name").add(f" ({r.choice(['wife', 'husband', 'mother', 'son', 'partner'])}) ").add(p.phone(), "phone number").add("\n")
    return d


def passport(r, p):
    d = Doc()
    code = {"United Kingdom": "GBR", "USA": "USA", "Deutschland": "D<<", "France": "FRA", "Italia": "ITA",
            "España": "ESP", "India": "IND", "Canada": "CAN", "Australia": "AUS"}.get(p.country, "UTO")
    num = "".join(r.choices(string.ascii_uppercase + string.digits, k=9))
    last = "".join(c for c in p.last.upper() if c.isalpha() and c.isascii()) or "DOE"
    first = "".join(c for c in p.first.upper() if c.isalpha() and c.isascii()) or "JANE"
    d.add(f"PASSPORT / PASSEPORT\nType P   Code {code}   Passport No. ").add(num, "passport number").add("\n")
    d.add("Surname / Nom\n").add(p.last.upper(), "name").add("\nGiven names / Prénoms\n").add(p.first.upper(), "name")
    d.add(f"\nNationality {p.country.upper()}\nDate of birth\n").add(f"{p.dob:%d %b %Y}".upper(), "date of birth")
    d.add(f"\nPlace of birth {p.city.upper()}\nDate of issue {other_date(r)}   Date of expiry {other_date(r)}\n\n")
    mrz_name = f"{last}<<{first}"
    d.add(f"P<{code}").add(mrz_name, "name").add("<" * max(1, 39 - len(mrz_name)) + "\n")
    d.add(num, "passport number").add(f"{r.randint(0, 9)}{code}").add(f"{p.dob:%y%m%d}", "date of birth")
    d.add(f"{r.randint(0, 9)}{r.choice('MF')}{r.randint(25, 35)}{r.randint(1, 12):02d}{r.randint(1, 28):02d}{r.randint(0, 9)}<<<<<<<<<<<<<<0{r.randint(0, 9)}\n")
    return d


def chat(r, p):
    d = Doc()
    q = Person(r, p.loc)
    speakers = [(p.first, p), (q.first, q)]
    for _ in range(r.randint(4, 9)):
        nm, who = r.choice(speakers)
        d.add(f"[{r.randint(0, 23):02d}:{r.randint(0, 59):02d}] " if r.random() < 0.7 else "").add(nm, "name").add(": ")
        k = r.randrange(9)
        if k == 0:
            d.add("call me on ").add(who.phone(), "phone number")
        elif k == 1:
            d.add(f"lol did u see {r.choice(PUBLIC)} last night")
        elif k == 2:
            d.add("send it to ").add(who.email(), "email address")
        elif k == 3:
            d.add(f"ok {amount(r)} it is, transfer to ").add(who.iban() if r.random() < 0.5 else who.account(),
                                                           "iban" if r.random() < 0.5 else "account number")
        elif k == 4:
            d.add("my address is ").add(who.address(one_line=True), "street address")
        elif k == 5:
            d.add(f"running late, see you at {r.randint(1, 11)}")
        elif k == 6:
            d.add("tell ").add(Person(r, p.loc).first, "name").add(" I said hi")
        elif k == 7:
            d.add("my insta is @").add(who.username(), "username")
        else:
            d.add(f"order {ref(r)} arrived 👍")
        d.add("\n")
    return d


def shipping(r, p):
    d = Doc()
    d.add(f"{r.choice(['DHL EXPRESS', 'UPS', 'FedEx', 'Royal Mail Tracked 24', 'DPD', 'La Poste Colissimo', 'PostNL'])}\n")
    d.add(f"FROM: {p.f.company()}\n")
    d.add(r.choice(["SHIP TO:\n", "DELIVER TO:\n", "To:\n", "Empfänger:\n"])).add(p.name(r.choice(["caps", "full"])), "name")
    d.add("\n").add(p.address(one_line=False).upper() if r.random() < 0.5 else p.address(one_line=False), "street address")
    d.add("\n" + r.choice(["TEL: ", "Phone: ", "☎ "])).add(p.phone(), "phone number").add("\n")
    track = r.choice([f"1Z{''.join(r.choices(string.ascii_uppercase + string.digits, k=16))}", f"{r.randint(10 ** 11, 10 ** 12)}",
                      f"JD{r.randint(10 ** 15, 10 ** 16)}", f"{''.join(r.choices(string.ascii_uppercase, k=2))}{r.randint(10 ** 8, 10 ** 9)}GB"])
    d.add(f"Tracking: {track}\nWeight: {r.randint(1, 300) / 10} kg   Pieces: {r.randint(1, 4)}\nOrder: {ref(r)}   Date: {other_date(r)}\n")
    if r.random() < 0.3:
        d.add(f"Contents: {r.choice(['Books', 'Clothing', 'Electronics', 'Documents'])}  Value: {amount(r)}\n")
    return d


def plain(r, p):
    """A page with nothing personal in it: amounts, dates, references, companies, places, public figures."""
    d = Doc()
    for _ in range(r.randint(3, 8)):
        d.add(r.choice([f"{p.f.company()} reported revenue of {amount(r)} for the quarter ending {other_date(r)}.",
                        f"{ref(r)}  {amount(r)}  {other_date(r)}", f"Meeting in {p.f.city()} with the {p.f.company()} team.",
                        f"{r.choice(PUBLIC)} visited {p.f.city()} on {other_date(r)}.", f"Version {ref(r)} released.",
                        f"Total due: {amount(r)} by {other_date(r)}.", f"{p.f.catch_phrase()}.",
                        f"See {p.f.url()} for details.",
                        f"{p.f.street_name()} will be closed for roadworks until {other_date(r)}."]) + "\n")
    return d


KINDS = [(form, 22), (letter, 12), (email, 14), (records, 10), (logs, 6), (statement, 9), (medical, 7),
         (passport, 4), (chat, 8), (shipping, 6), (plain, 6)]


def pick(r):
    return r.choices([l_ for l_, _, _ in LOCALES], [w for _, w, _ in LOCALES])[0]


def noisy(r, text, labels):
    """Offset-keeping noise over the whole page: all caps, all lower case, OCR misreads."""
    k = r.random()
    if k < 0.08:
        text = "".join(c.upper() if len(c.upper()) == 1 else c for c in text)
    elif k < 0.14:
        text = "".join(c.lower() if len(c.lower()) == 1 else c for c in text)
    if r.random() < 0.1:
        chars = list(text)
        for i in r.sample(range(len(chars)), max(1, len(chars) // r.randint(30, 80))):
            if chars[i] in OCR and OCR[chars[i]]:
                chars[i] = OCR[chars[i]]
        text = "".join(chars)
    return text, labels


def doc(r):
    p = Person(r, pick(r))
    fn = r.choices([k for k, _ in KINDS], [w for _, w in KINDS])[0]
    d = fn(r, p)
    return noisy(r, d.text(), d.labels)


def docs(n, seed):
    r = random.Random(seed)
    return [doc(r) for _ in range(n)]


if __name__ == "__main__":
    import sys
    for t, labels in docs(int(sys.argv[1]) if sys.argv[1:] else 8, int(sys.argv[2]) if sys.argv[2:] else 1):
        print("----\n" + t)
        print([(t[s:e], lab) for s, e, lab in labels])
