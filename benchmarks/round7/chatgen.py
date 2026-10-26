"""Round 10's generated conversations (round 10 in PROTOCOL.md, source A): a user's messages to an assistant, two to six
turns and under 300 words, aimed at what the tagger alone misses on PII-TRACE: phone numbers with extensions, IDs and
references of letters and digits in groups, access codes, passwords and API keys, obfuscated emails, and details that
come back in a later turn, written another way or corrected.  Beside them, in every conversation, the look-alikes that
stay visible (RULES.md): order, invoice, ticket, tracking, case and booking references, SKUs, versions, commit hashes,
UUIDs, colours, times and amounts.  English for four conversations in five; German, French, Spanish, Dutch and Italian
share the rest.

Every person is made up (Faker).  conversations(n, seed) -> [[(text, [(start, end, label)]) per user message]], labels
in the tagger's names; docs(convs, seed) gives half of them as one text (messages joined by a blank line, as
pii_trace.SEP) and half a message at a time (source D).  Split train and dev by conversation, before docs():
round7.split_docs(convs, key=lambda c: c[0][0]).  A draw is repeatable with PYTHONHASHSEED=0.

python chatgen.py [n] [seed]       print n conversations with their details marked
python chatgen.py --stats [n]      details by label, look-alikes, words a conversation"""
import random
import string
import unicodedata

from faker import Faker

SEP = "\n\n"   # pii_trace.SEP
LANGS = [("en", "en_US")] * 10 + [("en", "en_GB"), ("en", "en_CA"), ("en", "en_AU"), ("en", "en_IN"),
                                  ("en", "en_US"), ("en", "en_US")] + \
        [("de", "de_DE"), ("fr", "fr_FR"), ("es", "es_ES"), ("nl", "nl_NL"), ("it", "it_IT")]


class Msg:
    """One user message, built in pieces, the details marked as they're added."""
    def __init__(self):
        self.parts, self.n = [], 0

    def add(self, text, label=None):
        span = (self.n, self.n + len(text), label) if label and text.strip() else None
        self.parts.append((text, span))
        self.n += len(text)
        return self

    def say(self, text, label=None):
        """``text``, its first letter a capital where a sentence starts."""
        before = "".join(t for t, _ in self.parts[-2:])
        if text and (not before.strip() or before.rstrip(" ").endswith((".", "!", "?", "\n", ":"))):
            text = text[0].upper() + text[1:]
        return self.add(text, label)

    def done(self):
        return "".join(t for t, _ in self.parts), [s for _, s in self.parts if s]


_FAKERS = {}


def fk(loc, rng):
    if loc not in _FAKERS:
        _FAKERS[loc] = Faker(loc)
    f = _FAKERS[loc]
    f.seed_instance(rng.randrange(1 << 30))
    return f


def digits(rng, n):
    return "".join(rng.choice(string.digits) for _ in range(n))


def alnum(rng, n, need_digit=True):
    s = "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(n))
    return s if not need_digit or any(c.isdigit() for c in s) else s[:-1] + rng.choice("23456789")


# ---------------------------------------------------------------- the details

def phone(rng, loc):
    """A person's phone number; half of them with an extension, which is part of the span."""
    if loc in ("en_US", "en_CA") or rng.random() < 0.15:
        a, b, c = f"{rng.randint(201, 989)}", digits(rng, 3), digits(rng, 4)
        base = rng.choice([f"+1 {a} {b} {c}", f"+1 ({a}) {b}-{c}", f"({a}) {b}-{c}", f"{a}-{b}-{c}", f"{a}.{b}.{c}",
                           f"1-{a}-{b}-{c}", f"+1-{a}-{b}-{c}"])
    else:
        base = fk(loc, rng).phone_number()
    if rng.random() < 0.5:
        ext = str(rng.randint(2, 99999))
        base += rng.choice([f" ext {ext}", f" ext. {ext}", f" x{ext}", f", extension {ext}", f" #{ext}", f" (ext {ext})",
                            f", ext. {ext}", f" Durchwahl {ext}" if loc == "de_DE" else f" poste {ext}" if loc == "fr_FR"
                            else f" extension {ext}"])
    return base


def email(rng, loc):
    f = fk(loc, rng)
    user = rng.choice([f"{f.first_name()}.{f.last_name()}", f"{f.first_name()[0]}{f.last_name()}{rng.randint(1, 99)}",
                       f"{f.last_name()}_{f.first_name()}", f"{f.user_name()}"]).lower().replace(" ", "").replace("'", "")
    user = unicodedata.normalize("NFKD", user).encode("ascii", "ignore").decode()
    dom = rng.choice([f.free_email_domain(), f.domain_name(), "example.com", "example.org"])
    k = rng.random()
    if k < 0.6:
        return f"{user}@{dom}"
    host, _, tld = dom.rpartition(".")
    return rng.choice([f"{user} at {host} dot {tld}", f"{user} [at] {host} [dot] {tld}", f"{user}(at){host}(dot){tld}",
                       f"{user} @ {dom}", f"{user} AT {host} DOT {tld}"])


def grouped_id(rng, prefix=None):
    """An ID or reference of letters and digits: two to five groups, separated by -, a space, /, . or nothing."""
    groups = [prefix or "".join(rng.choice(string.ascii_uppercase) for _ in range(rng.randint(1, 3)))] \
        if rng.random() < 0.7 else []
    groups += [alnum(rng, rng.randint(3, 5)) for _ in range(rng.randint(2, 4) if groups else rng.randint(2, 5))]
    s = rng.choice(["-", "-", " ", "/", ".", ""]).join(groups)
    return s.lower() if rng.random() < 0.1 else s


def code(rng):
    """An access, security or recovery code: four to twelve digits, alone or in groups of three or four."""
    n = rng.choice([4, 6, 6, 8, 9, 9, 9, 12])
    d = digits(rng, n)
    if n >= 8 and rng.random() < 0.6:
        size = 3 if n % 3 == 0 else 4
        d = rng.choice(["-", " ", "."]).join(d[i:i + size] for i in range(0, n, size))
    return d


def password(rng, loc):
    f = fk(loc, rng)
    w = rng.choice([f.word(), f.first_name(), f.city()]).replace(" ", "")
    return rng.choice([f"{w.capitalize()}{rng.randint(1, 2026)}{rng.choice('!#$%&*?')}",
                       f"{w.lower()}_{w[::-1].lower()}{digits(rng, 2)}",
                       "".join(rng.choice(string.ascii_letters + string.digits + "!@#$%^&*") for _ in range(rng.randint(10, 18))),
                       f"{f.word()}-{f.word()}-{f.word()}-{rng.randint(1, 99)}"])


def recovery(rng):
    return rng.choice(["-".join(alnum(rng, 4, False).lower() for _ in range(rng.randint(2, 4))),
                       f"{alnum(rng, 5, False)}-{alnum(rng, 5, False)}"])


def api_key(rng):
    tok = lambda n, chars=string.ascii_letters + string.digits: "".join(rng.choice(chars) for _ in range(n))  # noqa: E731
    return rng.choice([f"sk-{tok(rng.choice([32, 48]))}", f"sk_live_{tok(24)}", f"sk_test_{tok(24)}", f"pk_live_{tok(24)}",
                       f"ghp_{tok(36)}", f"github_pat_{tok(22)}_{tok(30)}", f"AKIA{tok(16, string.ascii_uppercase + string.digits)}",
                       f"xoxb-{digits(rng, 11)}-{digits(rng, 12)}-{tok(24)}", f"AIza{tok(35)}", f"glpat-{tok(20)}",
                       f"eyJhbGciOiJIUzI1NiJ9.{tok(36)}.{tok(43)}", tok(40, string.ascii_lowercase + string.digits)])


def dob(rng, lang):
    y, m, d = rng.randint(1940, 2006), rng.randint(1, 12), rng.randint(1, 28)
    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
              "November", "December"]
    if lang == "en":
        return rng.choice([f"{m:02d}/{d:02d}/{y}", f"{d} {months[m - 1]} {y}", f"{months[m - 1]} {d}, {y}", f"{y}-{m:02d}-{d:02d}"])
    return rng.choice([f"{d:02d}.{m:02d}.{y}", f"{d:02d}/{m:02d}/{y}", f"{y}-{m:02d}-{d:02d}"])


def address(rng, loc):
    return fk(loc, rng).address().replace("\n", ", ")


def respelled(value, label, rng):
    """The same value as a later turn might write it: other separators, other case, without the country code."""
    if label == "phone number":
        v = value.replace("+1 ", "", 1) if value.startswith("+1 ") and rng.random() < 0.5 else value
        return v.replace(" ", "-", 2) if "-" not in v[:8] else v.replace("-", " ")
    if label == "email address":
        return value.upper() if rng.random() < 0.3 else value
    seps = [c for c in "- /." if c in value]
    if seps:
        return value.replace(seps[0], rng.choice([s for s in ["-", " ", "", "."] if s != seps[0]]))
    return value.lower() if value.upper() == value and any(c.isalpha() for c in value) else value


# ---------------------------------------------------------------- what each detail is called, by language

# kind -> (tagger label, maker, {lang: [cues]})
KINDS = {
    "phone": ("phone number", lambda rng, loc, lang: phone(rng, loc), {
        "en": ["my number is", "you can reach me on", "call me at", "my cell is", "my phone:", "my work line is"],
        "de": ["meine Nummer ist", "Sie erreichen mich unter", "Telefon:"],
        "fr": ["mon numéro est le", "vous pouvez me joindre au", "téléphone :"],
        "es": ["mi número es el", "pueden llamarme al", "teléfono:"],
        "nl": ["mijn nummer is", "u kunt mij bereiken op", "telefoon:"],
        "it": ["il mio numero è", "potete chiamarmi al", "telefono:"]}),
    "email": ("email address", lambda rng, loc, lang: email(rng, loc), {
        "en": ["my email is", "email me at", "write to", "my address for this is"],
        "de": ["meine E-Mail ist", "schreiben Sie an"], "fr": ["mon e-mail est", "écrivez-moi à"],
        "es": ["mi correo es", "escríbanme a"], "nl": ["mijn e-mail is", "mail naar"], "it": ["la mia email è", "scrivetemi a"]}),
    "member": ("customer id", lambda rng, loc, lang: grouped_id(rng), {
        "en": ["my member ID is", "membership number:", "customer number", "my patient ID is", "loyalty card no.",
               "policyholder ID", "my client reference is"],
        "de": ["meine Mitgliedsnummer ist", "Kundennummer:", "Versichertennummer"],
        "fr": ["mon numéro d'adhérent est", "numéro client :", "mon identifiant patient est"],
        "es": ["mi número de socio es", "número de cliente:", "mi ID de paciente es"],
        "nl": ["mijn lidnummer is", "klantnummer:", "mijn patiëntnummer is"],
        "it": ["il mio numero di socio è", "codice cliente:", "il mio ID paziente è"]}),
    "account": ("account number", lambda rng, loc, lang: grouped_id(rng, rng.choice(["AC", "PR", "LN", "POL", None])), {
        "en": ["my policy number is", "the loan reference is", "account ref:", "my account number is", "policy no.",
               "reference number for my account:"],
        "de": ["meine Policennummer ist", "Darlehensnummer:", "Kontoreferenz"],
        "fr": ["mon numéro de police est", "référence du prêt :", "mon numéro de compte est"],
        "es": ["mi número de póliza es", "referencia del préstamo:", "mi número de cuenta es"],
        "nl": ["mijn polisnummer is", "leningnummer:", "mijn rekeningreferentie is"],
        "it": ["il mio numero di polizza è", "riferimento del prestito:", "il mio numero di conto è"]}),
    "code": ("password or access code", lambda rng, loc, lang: code(rng), {
        "en": ["the access code is", "my security code is", "the door code is", "my PIN is", "verification code:",
               "my one-time code was", "passcode:"],
        "de": ["der Zugangscode ist", "meine PIN ist", "Sicherheitscode:"],
        "fr": ["le code d'accès est", "mon code PIN est", "code de sécurité :"],
        "es": ["el código de acceso es", "mi PIN es", "código de seguridad:"],
        "nl": ["de toegangscode is", "mijn pincode is", "beveiligingscode:"],
        "it": ["il codice di accesso è", "il mio PIN è", "codice di sicurezza:"]}),
    "password": ("password or access code", lambda rng, loc, lang: password(rng, loc), {
        "en": ["my password is", "the Wi-Fi password is", "I set the password to", "login password:"],
        "de": ["mein Passwort ist", "das WLAN-Passwort ist"], "fr": ["mon mot de passe est", "le mot de passe Wi-Fi est"],
        "es": ["mi contraseña es", "la contraseña del wifi es"], "nl": ["mijn wachtwoord is", "het wifi-wachtwoord is"],
        "it": ["la mia password è", "la password del wifi è"]}),
    "recovery": ("password or access code", lambda rng, loc, lang: recovery(rng), {
        "en": ["my recovery code is", "backup code:", "the reset code they gave me is"],
        "de": ["mein Wiederherstellungscode ist"], "fr": ["mon code de récupération est"],
        "es": ["mi código de recuperación es"], "nl": ["mijn herstelcode is"], "it": ["il mio codice di recupero è"]}),
    "key": ("api key", lambda rng, loc, lang: api_key(rng), {
        "en": ["my API key is", "here's the token:", "the key I'm using is", "secret key:"],
        "de": ["mein API-Schlüssel ist"], "fr": ["ma clé API est"], "es": ["mi clave de API es"],
        "nl": ["mijn API-sleutel is"], "it": ["la mia chiave API è"]}),
    "dob": ("date of birth", lambda rng, loc, lang: dob(rng, lang), {
        "en": ["my date of birth is", "DOB:", "I was born on"], "de": ["geboren am", "Geburtsdatum:"],
        "fr": ["je suis né le", "date de naissance :"], "es": ["nací el", "fecha de nacimiento:"],
        "nl": ["geboren op", "geboortedatum:"], "it": ["sono nato il", "data di nascita:"]}),
    "address": ("street address", lambda rng, loc, lang: address(rng, loc), {
        "en": ["I live at", "my address is", "please send it to", "home address:"],
        "de": ["ich wohne in der", "meine Adresse ist"], "fr": ["j'habite au", "mon adresse est"],
        "es": ["vivo en", "mi dirección es"], "nl": ["ik woon op", "mijn adres is"], "it": ["abito in", "il mio indirizzo è"]}),
}
WEIGHTS = {"phone": 4, "member": 4, "account": 4, "code": 4, "password": 2, "recovery": 1, "key": 2, "email": 3, "dob": 1,
           "address": 1}

# look-alikes that stay visible: kind -> (maker, {lang: [cues]})
LOOKALIKES = {
    "order": (lambda rng: rng.choice([f"#{digits(rng, rng.randint(6, 9))}", grouped_id(rng, "ORD"), f"{digits(rng, 3)}-{digits(rng, 7)}-{digits(rng, 7)}"]),
              {"en": ["order", "my order number is", "order no."], "de": ["Bestellung", "Bestellnummer"],
               "fr": ["commande", "numéro de commande"], "es": ["pedido", "número de pedido"],
               "nl": ["bestelling", "bestelnummer"], "it": ["ordine", "numero d'ordine"]}),
    "invoice": (lambda rng: rng.choice([f"INV-{rng.randint(2023, 2026)}-{digits(rng, 5)}", grouped_id(rng, "INV"), digits(rng, 8)]),
                {"en": ["invoice", "invoice no."], "de": ["Rechnung"], "fr": ["facture"], "es": ["factura"],
                 "nl": ["factuur"], "it": ["fattura"]}),
    "ticket": (lambda rng: rng.choice([f"INC{digits(rng, 7)}", f"#{digits(rng, 5)}", grouped_id(rng, "TKT"), f"CS-{digits(rng, 6)}"]),
               {"en": ["ticket", "support ticket", "case number"], "de": ["Ticket", "Vorgangsnummer"],
                "fr": ["ticket", "numéro de dossier"], "es": ["incidencia", "número de caso"],
                "nl": ["ticket", "zaaknummer"], "it": ["ticket", "numero pratica"]}),
    "tracking": (lambda rng: rng.choice([f"1Z{alnum(rng, 16, False)}", f"{alnum(rng, 2, False)}{digits(rng, 9)}GB", digits(rng, 12)]),
                 {"en": ["tracking number", "the parcel's tracking is"], "de": ["Sendungsnummer"], "fr": ["numéro de suivi"],
                  "es": ["número de seguimiento"], "nl": ["trackingnummer"], "it": ["numero di tracciamento"]}),
    "booking": (lambda rng: rng.choice([alnum(rng, 6, False), grouped_id(rng, "BK"), f"{alnum(rng, 3, False)}{digits(rng, 5)}"]),
                {"en": ["booking reference", "reservation code", "the PNR is", "confirmation number"],
                 "de": ["Buchungsnummer"], "fr": ["référence de réservation"], "es": ["localizador"],
                 "nl": ["boekingsnummer"], "it": ["codice di prenotazione"]}),
    "sku": (lambda rng: f"{alnum(rng, 2, False)}-{digits(rng, 3)}-{rng.choice(['BLK', 'WHT', 'XL', 'M', 'RED'])}",
            {"en": ["item", "SKU"], "de": ["Artikel"], "fr": ["article"], "es": ["artículo"], "nl": ["artikel"], "it": ["articolo"]}),
    "version": (lambda rng: rng.choice([f"v{rng.randint(1, 14)}.{rng.randint(0, 30)}.{rng.randint(0, 9)}", f"build {digits(rng, 4)}",
                                        f"{rng.randint(1, 9)}.{rng.randint(0, 9)}.{digits(rng, 4)}"]),
                {"en": ["I'm on version", "the app says"], "de": ["Version"], "fr": ["version"], "es": ["versión"],
                 "nl": ["versie"], "it": ["versione"]}),
    "hash": (lambda rng: "".join(rng.choice("0123456789abcdef") for _ in range(rng.choice([7, 8, 12, 40]))),
             {"en": ["it broke after commit", "the hash is"], "de": ["Commit"], "fr": ["commit"], "es": ["commit"],
              "nl": ["commit"], "it": ["commit"]}),
    "uuid": (lambda rng: "-".join("".join(rng.choice("0123456789abcdef") for _ in range(n)) for n in (8, 4, 4, 4, 12)),
             {"en": ["the request ID in the log is", "error id"], "de": ["Fehler-ID"], "fr": ["identifiant d'erreur"],
              "es": ["ID de error"], "nl": ["fout-ID"], "it": ["ID errore"]}),
    "amount": (lambda rng: rng.choice([f"${rng.randint(5, 9999):,}.{digits(rng, 2)}", f"€{rng.randint(5, 9999)},{digits(rng, 2)}",
                                       f"£{rng.randint(5, 999)}.{digits(rng, 2)}"]),
               {"en": ["they charged me", "the total was"], "de": ["Betrag"], "fr": ["montant"], "es": ["importe"],
                "nl": ["bedrag"], "it": ["importo"]}),
    "time": (lambda rng: rng.choice([f"{rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}",
                                     f"2026-{rng.randint(1, 12):02d}-{rng.randint(1, 28):02d} {rng.randint(0, 23):02d}:{rng.randint(0, 59):02d}"]),
             {"en": ["it happened at", "they called me at"], "de": ["es passierte um"], "fr": ["c'est arrivé à"],
              "es": ["pasó a las"], "nl": ["het gebeurde om"], "it": ["è successo alle"]}),
}

# ---------------------------------------------------------------- how a user writes to an assistant

ASKS = {
    "en": ["Can you help me write an email to support about this?", "Can you draft a complaint for me?",
           "Help me fill in this form.", "What should I tell them?", "Can you put this in a short letter?",
           "Can you check I've got everything they asked for?", "Please write this up as a message to my bank.",
           "can u make this sound more formal", "Turn this into a reply to the landlord."],
    "de": ["Kannst du mir eine E-Mail an den Support schreiben?", "Hilf mir bitte, das Formular auszufüllen.",
           "Formuliere das bitte als Beschwerde."],
    "fr": ["Peux-tu m'aider à écrire un e-mail au service client ?", "Aide-moi à remplir ce formulaire.",
           "Rédige une réclamation, s'il te plaît."],
    "es": ["¿Me ayudas a escribir un correo al soporte?", "Ayúdame a rellenar este formulario.",
           "Redacta una reclamación, por favor."],
    "nl": ["Kun je me helpen een e-mail naar de klantenservice te schrijven?", "Help me dit formulier in te vullen.",
           "Schrijf hier een klacht van."],
    "it": ["Mi aiuti a scrivere un'email all'assistenza?", "Aiutami a compilare questo modulo.",
           "Scrivi un reclamo, per favore."]}
OPENERS = {"en": ["Hi,", "Hey,", "Hello!", "ok so", "Quick one:", "Right,", ""],
           "de": ["Hallo,", "Also,", ""], "fr": ["Bonjour,", "Alors,", ""], "es": ["Hola,", "Vale,", ""],
           "nl": ["Hoi,", "Oké,", ""], "it": ["Ciao,", "Allora,", ""]}
LATER = {"en": ["Thanks. Also,", "One more thing:", "ok and", "They replied.", "Update:", ""],
         "de": ["Danke. Noch was:", "Nachtrag:", ""], "fr": ["Merci. Autre chose :", "Mise à jour :", ""],
         "es": ["Gracias. Otra cosa:", "Actualización:", ""], "nl": ["Bedankt. Nog iets:", "Update:", ""],
         "it": ["Grazie. Un'altra cosa:", "Aggiornamento:", ""]}
AGAIN = {"en": ["Just to confirm, it's", "Use", "Again, that's", "They asked again, so:"],
         "de": ["Zur Sicherheit noch mal:", "Also:"], "fr": ["Pour confirmer, c'est", "Donc :"],
         "es": ["Para confirmar, es", "O sea:"], "nl": ["Ter bevestiging:", "Dus:"], "it": ["Per conferma, è", "Quindi:"]}
CORRECT = {"en": ["Sorry, {old} is the old one. The new one is", "Correction: not {old}, it's", "{old} was replaced, it's now"],
           "de": ["Moment, {old} ist veraltet. Neu ist", "Korrektur: nicht {old}, sondern"],
           "fr": ["Pardon, {old} est l'ancien. Le nouveau est", "Correction : pas {old}, mais"],
           "es": ["Perdón, {old} es el antiguo. El nuevo es", "Corrijo: no es {old}, es"],
           "nl": ["Sorry, {old} is de oude. De nieuwe is", "Correctie: niet {old} maar"],
           "it": ["Scusa, {old} è il vecchio. Il nuovo è", "Correzione: non {old}, ma"]}
RELATION = {"en": ["my wife", "my husband", "my son", "my daughter", "my partner", "my brother"],
            "de": ["meine Frau", "mein Mann", "mein Sohn"], "fr": ["ma femme", "mon mari", "mon fils"],
            "es": ["mi mujer", "mi marido", "mi hijo"], "nl": ["mijn vrouw", "mijn man", "mijn zoon"],
            "it": ["mia moglie", "mio marito", "mio figlio"]}
NAME_IS = {"en": ["I'm", "my name is", "this is"], "de": ["ich bin", "mein Name ist"], "fr": ["je suis", "je m'appelle"],
           "es": ["soy", "me llamo"], "nl": ["ik ben", "mijn naam is"], "it": ["sono", "mi chiamo"]}
AND_IS = {"en": " and {rel} is ", "de": " und {rel} ist ", "fr": " et {rel} est ", "es": " y {rel} es ", "nl": " en {rel} is ",
          "it": " e {rel} è "}
ALSO = {"en": [" will call them too. ", " may answer instead of me. ", " is on the account too. "],
        "de": [" ruft vielleicht auch an. ", " ist auch auf dem Konto. "], "fr": [" appellera peut-être aussi. ", " est aussi sur le compte. "],
        "es": [" puede que llame también. ", " también está en la cuenta. "], "nl": [" belt misschien ook. ", " staat ook op de rekening. "],
        "it": [" potrebbe chiamare anche lui. ", " è anche sul conto. "]}
AGAIN_ME = {"en": [" here again. ", " again. "], "de": [" noch mal. "], "fr": [" à nouveau. "], "es": [" otra vez. "],
            "nl": [" weer. "], "it": [" di nuovo. "]}


def env_file(m, rng):
    """A developer pasting a config: keys and a password among harmless settings."""
    m.add(rng.choice(["here's my .env, why won't it connect?\n\n", "Config below, what's wrong?\n\n",
                      "I pasted my settings:\n\n"]))
    lines = [("DEBUG=", rng.choice(["true", "false"]), None), ("PORT=", str(rng.choice([3000, 5432, 8080])), None),
             ("LOG_LEVEL=", rng.choice(["info", "debug"]), None), ("APP_VERSION=", LOOKALIKES["version"][0](rng), None),
             (rng.choice(["STRIPE_SECRET_KEY=", "OPENAI_API_KEY=", "GITHUB_TOKEN=", "AWS_ACCESS_KEY_ID="]), api_key(rng), "api key"),
             ("THEME_COLOR=#", "".join(rng.choice("0123456789ABCDEF") for _ in range(6)), None)]
    rng.shuffle(lines)
    for k, v, lab in lines:
        m.add(k).add(v, lab).add("\n")
    m.add("DATABASE_URL=postgres://").add(fk("en_US", rng).user_name()).add(":")
    m.add(password(rng, "en_US"), "password or access code").add(f"@db.internal:5432/{rng.choice(['app', 'prod', 'main'])}\n")


def sentence(m, lang, cue, value, label, rng):
    m.say(f"{cue} ").add(value, label).add(rng.choice([". ", ". ", ", ", " - ", ".\n", " "]))


# ---------------------------------------------------------------- a conversation

def conversation(rng):
    lang, loc = rng.choice(LANGS)
    f = fk(loc, rng)
    pool = [k for k, w in WEIGHTS.items() for _ in range(w)]
    planted = [rng.choice(pool) for _ in range(rng.randint(3, 8))]
    looks = [rng.choice(list(LOOKALIKES)) for _ in range(rng.randint(2, 4))]
    turns = rng.randint(2, 6)
    plan = [[] for _ in range(turns)]
    for item in [("detail", k) for k in planted] + [("look", k) for k in looks]:
        plan[rng.randrange(turns)].append(item)
    me_first, me_last = f.first_name(), f.last_name()
    other = None
    if rng.random() < 0.3:
        other = (rng.choice(RELATION[lang]), f.first_name())
    said = []   # (value, label, cue) said so far, to come back to
    msgs, words = [], 0
    for t in range(turns):
        m = Msg()
        m.add((rng.choice(OPENERS[lang] if t == 0 else LATER[lang]) + " ").lstrip())
        corrected = False
        if t == 0:
            m.say(rng.choice(NAME_IS[lang]) + " ").add(f"{me_first} {me_last}", "name")
            if other:
                m.add(AND_IS[lang].format(rel=other[0])).add(f"{other[1]} {me_last}", "name")
            m.add(". ")
            if rng.random() < 0.1 and lang == "en":
                env_file(m, rng)
        elif other and rng.random() < 0.4:
            m.say(f"{other[1]}", "name").add(rng.choice(ALSO[lang]))
        elif rng.random() < 0.2:
            m.say(me_first, "name").add(rng.choice(AGAIN_ME[lang]))
        for kind, k in plan[t]:
            if kind == "detail":
                label, make, cues = KINDS[k]
                cue, value = rng.choice(cues.get(lang, cues["en"])), make(rng, loc, lang)
                fresh = [x for x in said if x[3] == k and not x[4]]
                if fresh and not corrected and rng.random() < 0.3:   # a correction: the old value and the new, both marked
                    old = rng.choice(fresh)
                    said[said.index(old)] = old[:4] + (True,)
                    pre, post = rng.choice(CORRECT[lang]).split("{old}")
                    if pre:
                        m.say(pre)
                    m.add(old[0], label) if pre else m.say(old[0], label)
                    m.add(post + " ").add(value, label).add(". ")
                    said.append((value, label, cue, k, False))
                    corrected = True
                    continue
                sentence(m, lang, cue, value, label, rng)
                said.append((value, label, cue, k, False))
            else:
                make, cues = LOOKALIKES[k]
                m.say(f"{rng.choice(cues.get(lang, cues['en']))} {make(rng)}" + rng.choice([". ", ". ", ".\n"]))
        if t > 0 and said and rng.random() < 0.5:   # a detail again, half the time written another way
            value, label = rng.choice(said)[:2]
            m.say(rng.choice(AGAIN[lang]) + " ").add(respelled(value, label, rng) if rng.random() < 0.5 else value, label)
            m.add(". ")
        if t == 0 or rng.random() < 0.4:
            m.say(rng.choice(ASKS[lang]))
        text, spans = m.done()
        text = text.rstrip()
        spans = [(a, min(b, len(text)), lab) for a, b, lab in spans if a < len(text)]
        n = len(text.split())
        if not n:
            continue
        if msgs and words + n > 300:
            break
        msgs.append((text, spans))
        words += n
    return msgs


def conversations(n, seed):
    rng = random.Random(seed)
    return [conversation(rng) for _ in range(n)]


def joined(conv):
    """A conversation's user messages as one text, joined as pii_trace.py joins them."""
    text, spans, off = "", [], 0
    for i, (t, s) in enumerate(conv):
        if i:
            text += SEP
            off = len(text)
        spans += [(a + off, b + off, lab) for a, b, lab in s]
        text += t
    return text, spans


def docs(convs, seed):
    """Half the conversations as one text, half a message at a time (round 10's source D)."""
    rng = random.Random(seed)
    out = []
    for c in convs:
        out += [joined(c)] if rng.random() < 0.5 else list(c)
    return out


def check(convs):
    """Every span holds text, without spaces at its edges, and spans don't overlap."""
    for c in convs:
        for t, s in c:
            last = 0
            for a, b, lab in sorted(s):
                v = t[a:b]
                assert v and v == v.strip() and a >= last, (lab, repr(v), t)
                last = b


if __name__ == "__main__":
    import os
    import sys
    from collections import Counter
    if os.environ.get("PYTHONHASHSEED") != "0":
        os.execve(sys.executable, [sys.executable, *sys.argv], {**os.environ, "PYTHONHASHSEED": "0"})
    args = [a for a in sys.argv[1:] if a != "--stats"]
    n, seed = int(args[0]) if args else (2000 if "--stats" in sys.argv else 4), int(args[1]) if len(args) > 1 else 1
    convs = conversations(n, seed)
    check(convs)
    if "--stats" in sys.argv:
        labels = Counter(lab for c in convs for _, s in c for _, _, lab in s)
        words = sorted(sum(len(t.split()) for t, _ in c) for c in convs)
        turns = Counter(len(c) for c in convs)
        print(f"{n} conversations; turns {dict(sorted(turns.items()))}; words median {words[n // 2]}, max {words[-1]}")
        for lab, k in labels.most_common():
            print(f"  {lab}: {k}")
        sys.exit()
    for c in convs:
        for i, (t, s) in enumerate(c):
            out = list(t)
            for a, b, lab in sorted(s, reverse=True):
                out[a:b] = list(f"⟦{lab}|{t[a:b]}⟧")
            print(f"[{i + 1}] " + "".join(out))
        print("-" * 60)
