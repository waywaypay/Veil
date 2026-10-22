"""Round 9's targeted training documents, aimed at what the rules and round 7's model still miss (round 9 in
PROTOCOL.md): addresses as other countries and scripts write them (Arabic, Persian, Cyrillic, Thai, Korean, Japanese,
Chinese, Greek, Hebrew, Irish house names, Argentine and Italian forms), forms with one box or space per letter,
scanned (misread) copies, names written in parts (particles, initials, suffixes, nicknames, surname-first in
capitals), Japanese, Chinese, Korean and Arabic names with their honorifics and readings, a first name alone after a
role, and staff numbers in payroll registers and timesheets.  Among them what must stay: company names and their
office addresses, departments and job titles, honorifics alone, amounts, dates, order and invoice numbers.

Every person is made up (Faker).  docs(n, seed) -> [(text, [(start, end, label)])], labels in the tagger's names.
A draw is repeatable with PYTHONHASHSEED=0."""
import random

import augment
from faker import Faker


class Doc:
    def __init__(self):
        self.parts, self.n = [], 0

    def add(self, text, label=None):
        span = None
        if label and text.strip():
            lead = len(text) - len(text.lstrip())
            span = (self.n + lead, self.n + len(text.rstrip()), label)
        self.parts.append((text, span))
        self.n += len(text)
        return self

    def done(self):
        return "".join(t for t, _ in self.parts), [s for _, s in self.parts if s]


_FAKERS = {}


def fk(loc, rng):
    if loc not in _FAKERS:
        _FAKERS[loc] = Faker(loc)
    f = _FAKERS[loc]
    f.seed_instance(rng.randrange(1 << 30))
    return f


def num(rng, a, b):
    return str(rng.randint(a, b))


def money(rng):
    return f"{rng.randint(10, 9999):,}.{rng.randint(0, 99):02d}"


def date(rng):
    return f"{rng.randint(1, 28):02d}/{rng.randint(1, 12):02d}/20{rng.randint(18, 26)}"


# ---------------------------------------------------------------- addresses as other countries write them

def addr_ar(rng):
    f = fk("ar_SA", rng)
    city = rng.choice(["دبي", "أبوظبي", "الرياض", "جدة", "الدوحة", "الكويت", "مسقط", "عمّان", "القاهرة"])
    area = rng.choice(["النهدة الثانية", "البرشاء", "الملقا", "العليا", "الروضة", "السالمية", "الخوير", "جبل عمّان"])
    return rng.choice([
        f"شقة {num(rng, 1, 2400)}، بناية {f.last_name()} {num(rng, 1, 30)}، شارع {num(rng, 1, 90)}، {area}، {city}",
        f"فيلا {num(rng, 1, 400)}، شارع {f.first_name_male()}، حي {area}، {city} {num(rng, 10000, 99999)}",
        f"{city}، {area}، شارع {num(rng, 1, 90)}، مبنى {num(rng, 1, 999)}، الطابق {num(rng, 1, 30)}"])


def addr_fa(rng):
    f = fk("fa_IR", rng)
    city = rng.choice(["تهران", "اصفهان", "شیراز", "مشهد", "تبریز", "کرج"])
    return (f"{city}، خیابان {f.last_name()}، کوچه {f.first_name()}، پلاک {num(rng, 1, 120)}، واحد {num(rng, 1, 20)}، "
            f"کد پستی {num(rng, 1000000000, 9999999999)}")


def addr_cyr(rng):
    if rng.random() < 0.5:
        return fk("uk_UA", rng).address().replace("\n", ", ")
    return fk("ru_RU", rng).address().replace("\n", ", ")


def addr_other(rng):
    loc = rng.choice(["th_TH", "ko_KR", "ja_JP", "zh_CN", "zh_TW", "el_GR", "he_IL", "pl_PL", "pt_BR", "nl_NL",
                      "it_IT", "es_AR", "de_DE", "fr_FR", "es_ES", "uk_UA"])
    return fk(loc, rng).address()


def addr_tr(rng):
    f = fk("tr_TR", rng)
    mah = rng.choice(["Caferağa", "Moda", "Bostancı", "Kızılay", "Alsancak", "Çankaya", "Beşiktaş"])
    return rng.choice([
        f"{mah} Mahallesi, {f.last_name()} Caddesi No: {num(rng, 1, 300)} Daire: {num(rng, 1, 40)}\n"
        f"{num(rng, 10000, 81999)} {rng.choice(['Kadıköy', 'Çankaya', 'Konak', 'Beşiktaş'])}/"
        f"{rng.choice(['İSTANBUL', 'ANKARA', 'İZMİR'])}",
        f"{mah} Mah. {f.last_name()} Sok. No:{num(rng, 1, 90)} D:{num(rng, 1, 20)} "
        f"{rng.choice(['Kadıköy', 'Çankaya'])}/{rng.choice(['İstanbul', 'Ankara'])}"])


def addr_ie(rng):
    f = fk("en_IE", rng)
    house = rng.choice(["Cnoc na Gaoithe", "Cois Abhann", "Teach na Coille", "Ard na Gréine", "Rose Cottage",
                        "The Old Rectory", "Glenview House", "Tigh na Mara"])
    town = rng.choice(["Ballyvaughan", "Salthill", "Clifden", "Dingle", "Kinsale", "Westport", "Lahinch"])
    county = rng.choice(["Clare", "Galway", "Kerry", "Cork", "Mayo", "Donegal"])
    eir = f"{rng.choice('ACDEFHKNPRTVWXY')}{num(rng, 10, 99)} {rng.choice('ACDEFHKNPRTVWXY')}{num(rng, 1, 9)}" \
          f"{rng.choice('ACDEFHKNPRTVWXY')}{num(rng, 1, 9)}"
    sep = rng.choice(["\n", ", "])
    return sep.join([house, f"{f.last_name()} Road" if rng.random() < 0.4 else f"{town} South", town,
                     f"Co. {county}", eir])


def addr_ar_es(rng):
    f = fk("es_AR", rng)
    return (f"{f.street_name()} {num(rng, 100, 4000)}, {rng.choice(['PB', '1°', '2°', '3°'])} \"{rng.choice('ABCD')}\", "
            f"({rng.choice('BCS')}{num(rng, 1000, 9999)}) {f.city()}, Pcia. de Buenos Aires")


def addr_it(rng):
    f = fk("it_IT", rng)
    prov = rng.choice(["VR", "MI", "TO", "BO", "FI", "NA", "TA", "MB"])
    return rng.choice([f"{f.city()} ({prov}), Via {f.last_name()} n. {num(rng, 1, 200)}/{rng.choice('ABC')}, "
                       f"{num(rng, 10000, 99999)}",
                       f"VIA {f.last_name().upper()} {num(rng, 1, 200)}\n{num(rng, 10000, 99999)}  {f.city().upper()}  "
                       f"({prov})"])


def addr_de(rng):
    f = fk("de_DE", rng)
    return rng.choice([f"{f.street_address()}, Hinterhaus, {num(rng, 1, 5)}. OG {rng.choice(['li.', 're.'])}",
                       f"{num(rng, 10000, 99999)} {f.city()} - {rng.choice(['Volkmarsdorf', 'Gohlis', 'Plagwitz', 'Altona'])}",
                       f"{f.last_name().upper()}STR. {num(rng, 1, 120)}\n{num(rng, 10000, 99999)} {f.city().upper()}"])


ADDRESS_MAKERS = [addr_ar, addr_fa, addr_cyr, addr_other, addr_other, addr_tr, addr_ie, addr_ar_es, addr_it, addr_de]


def person_of(loc, rng):
    return fk(loc, rng).name()


ADDR_LOC = {addr_ar: "ar_SA", addr_fa: "fa_IR", addr_cyr: "ru_RU", addr_tr: "tr_TR", addr_ie: "en_IE",
            addr_ar_es: "es_AR", addr_it: "it_IT", addr_de: "de_DE"}

ADDR_LABEL = {"ar_SA": ["العنوان", "عنوان السكن"], "fa_IR": ["نشانی", "آدرس"], "ru_RU": ["Адрес", "Адрес проживания"],
              "tr_TR": ["Adres", "İkamet adresi"], "en_IE": ["Address", "Home address"], "es_AR": ["Domicilio", "Dirección"],
              "it_IT": ["Indirizzo", "Residenza"], "de_DE": ["Anschrift", "Wohnanschrift"]}


def doc_address(rng):
    maker = rng.choice(ADDRESS_MAKERS)
    loc = ADDR_LOC.get(maker, "en_US")
    d = Doc()
    company = fk("en_US", rng).company()
    style = rng.randrange(5)
    name_loc = loc if loc != "en_US" else rng.choice(["ja_JP", "ko_KR", "zh_CN", "th_TH", "el_GR", "pl_PL", "pt_BR"])
    who = person_of(name_loc, rng)
    lab = rng.choice(ADDR_LABEL.get(loc, ["Address", "Mailing address"]))
    if style == 0:      # a form
        d.add(f"{rng.choice(['Customer record', 'Registration', 'KYC form', 'Tenant details'])}\n")
        d.add(rng.choice(["Name", "Nombre", "Name / الاسم", "Full name"]) + ": ").add(who, "name").add("\n")
        d.add(lab + ": ").add(maker(rng), "street address").add("\n")
        d.add(f"Ref: {rng.choice('ABCDEFGH')}{num(rng, 100000, 999999)}   Date: {date(rng)}\n")
    elif style == 1:    # a letter head with the company's office (not marked) and the person's home (marked)
        d.add(f"{company}\n{fk('en_US', rng).street_address()}, {fk('en_US', rng).city()}\n\n")
        d.add(f"{date(rng)}\n\n").add(who, "name").add("\n").add(maker(rng), "street address").add("\n\n")
        d.add(f"Re: account {num(rng, 10000, 99999)}\n\nDear customer,\nPlease find enclosed your statement.\n")
    elif style == 2:    # a chat or an email body
        d.add(rng.choice(["hi, my new address is ", "Please ship to: ", "Lieferadresse: ", "Mi dirección es ", "住所："]))
        d.add(maker(rng), "street address").add(rng.choice([" thanks!", "\n", ". Danke.", " gracias", "\n"]))
        d.add(f"\nOrder #{num(rng, 100000, 999999)}, total {money(rng)}\n")
    elif style == 3:    # a table row
        d.add("| Name | Address | Since |\n|---|---|---|\n| ").add(who, "name").add(" | ")
        d.add(maker(rng).replace("\n", ", "), "street address").add(f" | {date(rng)} |\n")
        d.add(f"| {company} (office) | {fk('en_US', rng).street_address()} | {date(rng)} |\n")
    else:               # a shipping label
        d.add("SHIP TO:\n").add(who.upper(), "name").add("\n").add(maker(rng), "street address")
        d.add(f"\n\nFROM: {company}, Warehouse {num(rng, 1, 9)}\nTRACKING {rng.choice(['1Z', 'JD', 'LX'])}"
              f"{num(rng, 10000000, 99999999)}\n")
    return d.done()


# ---------------------------------------------------------------- one box or space per letter

def boxed(s, rng, style):
    if style == 0:
        return "".join(f"[{c}]" if c != " " else "[ ]" for c in s)
    if style == 1:
        return " | ".join(c if c != " " else " " for c in s)
    return " ".join(s)


def doc_boxed(rng):
    f = fk(rng.choice(["en_US", "en_US", "en_GB", "es_MX", "en_CA"]), rng)
    style = rng.randrange(3)
    d = Doc()
    d.add(rng.choice(["e  EMPLOYEE'S NAME", "Applicant (BLOCK CAPITALS, one letter per box)", "1. Surname",
                      "NAME OF CLAIMANT"]) + "\n   ")
    d.add(boxed(f.last_name().upper(), rng, style), "name").add("\n   ")
    d.add(boxed(f.first_name().upper(), rng, style), "name").add("\n")
    d.add(rng.choice(["f  EMPLOYEE'S ADDRESS", "Address", "2. Home address"]) + "\n   ")
    d.add(boxed(f.street_address().upper(), rng, style), "street address").add("\n   ")
    d.add(boxed(f"{f.city().upper()} {f.state_abbr() if hasattr(f, 'state_abbr') else ''} {f.postcode()}".replace("  ", " "),
                rng, style), "street address").add("\n")
    if rng.random() < 0.6:
        d.add(rng.choice(["a  SSN", "Social security number", "National Insurance No."]) + "  ")
        ssn = f"{num(rng, 100, 899)}-{num(rng, 10, 99)}-{num(rng, 1000, 9999)}"
        d.add(boxed(ssn, rng, style), "ssn").add("\n")
    if rng.random() < 0.5:
        d.add("d  CONTROL NUMBER   ").add(boxed(f"{rng.choice('ABCDEFGHJKLM')}{rng.choice('ABCDEFGHJKLM')}-{num(rng, 10000, 99999)}",
                                               rng, style), "employee id").add("\n")
    d.add(f"Wages {money(rng)}   Tax {money(rng)}   Year 20{num(rng, 20, 26)}\n")
    doc = d.done()
    return augment.ocr(doc, rng, 0.08) if rng.random() < 0.3 else doc


# ---------------------------------------------------------------- names written in parts

PARTICLES = [("DE", "it_IT"), ("DI", "it_IT"), ("D'", "it_IT"), ("DE LA", "es_ES"), ("DEL", "es_ES"), ("VAN DER", "nl_NL"),
             ("VAN", "nl_NL"), ("BIN", "id_ID"), ("BINTI", "id_ID"), ("AL", "ar_SA"), ("VON", "de_DE"), ("DOS", "pt_BR")]


def part_name(rng):
    """(text, is it all a name) in one of the ways a name is written in parts."""
    loc = rng.choice(["en_US", "en_GB", "it_IT", "es_ES", "nl_NL", "de_DE", "pt_BR", "fr_FR"])
    f = fk(loc, rng)
    first, last = f.first_name(), f.last_name()
    k = rng.randrange(9)
    if k == 0:
        p, ploc = rng.choice(PARTICLES)
        sur = fk("en_US" if ploc in ("ar_SA", "id_ID") else ploc, rng).last_name().upper()
        return f"{p}{'' if p.endswith(chr(39)) else ' '}{sur} {first}"
    if k == 1:
        return f"{rng.choice('ABCDEFGHJKLMNPRSTW')}.{rng.choice('ABCDEFGHJKLMNPRSTW')}. {last.upper()}"
    if k == 2:
        return f"{first.upper()} {last.upper()} {rng.choice(['JR.', 'SR.', 'II', 'III'])}"
    if k == 3:
        return f"{first} ({rng.choice(['Sasha', 'Bea', 'Teo', 'Kiki', 'Ben', 'Lulu', 'Rafa'])}) {last}"
    if k == 4:
        return f"{last.upper()}, {first[0]}."
    if k == 5:
        return f"{first} {rng.choice(['de la', 'van der', 'von', 'da', 'dos'])} {last}"
    if k == 6:
        return f"{first} {last} (née {fk(loc, rng).last_name()})"
    if k == 7:
        return f"{rng.choice(['v. d.', 'vd.'])} {last}, {first}"
    return f"{first[0]}. {last}-{fk(loc, rng).last_name()}"


def doc_names(rng):
    d = Doc()
    k = rng.randrange(4)
    if k == 0:      # a register in capitals
        d.add("No.  NAME                              DATE        AMOUNT\n")
        for i in range(rng.randint(3, 7)):
            d.add(f"{i + 1:<4} ").add(part_name(rng), "name").add(f"{' ' * rng.randint(4, 12)}{date(rng)}  {money(rng)}\n")
    elif k == 1:    # minutes and letters
        for _ in range(rng.randint(2, 4)):
            d.add(rng.choice(["Present: ", "Signed: ", "Witness: ", "Attn: ", "On behalf of "]))
            d.add(part_name(rng), "name").add(rng.choice([".\n", ", Treasurer.\n", " (Chair)\n", "\n"]))
        d.add(f"Motion carried {rng.randint(3, 7)}-0. Next meeting {date(rng)}.\n")
    elif k == 2:    # a name broken at a line's end
        f = fk("en_US", rng)
        last = f.last_name().upper()
        cut = rng.randint(2, max(2, len(last) - 2))
        d.add("in qualità di genitore dell'atleta ").add(f"{last[:cut]}-\n{last[cut:]} {f.first_name().upper()}", "name")
        d.add(", chiede l'iscrizione.\n")
    else:           # first names alone after a role, and in a table beside the surname
        f = fk(rng.choice(["en_US", "en_GB", "en_IE", "en_IN"]), rng)
        d.add(f"{f.company().upper()}\nStore #{num(rng, 100, 9999)}\n")
        d.add(rng.choice(["Operator ", "Cashier: ", "Served by: ", "Your server: "])).add(f.first_name(), "name")
        d.add(f"\n{date(rng)} 18:{num(rng, 10, 59)}  #{num(rng, 1000, 9999)}\nTOTAL {money(rng)}\n\n")
        d.add("ID\tSurname\tFirst name\tDept\n")
        for _ in range(rng.randint(2, 5)):
            d.add(f"E{num(rng, 1000, 9999)}\t", None).add(f.last_name(), "name").add("\t").add(f.first_name(), "name")
            d.add(f"\t{rng.choice(['Finance', 'Ops', 'Sales', 'HR'])}\n")
    return d.done()


# ---------------------------------------------------------------- Japanese, Chinese, Korean, Arabic names

HONOR = {"ja_JP": ["様", "さん", "先生", "氏"], "ko_KR": [" 님", " 씨", " 선생님"], "zh_CN": ["先生", "女士"]}


def doc_cjk(rng):
    loc = rng.choice(["ja_JP", "ja_JP", "ko_KR", "zh_CN", "ar_SA"])
    f = fk(loc, rng)
    d = Doc()
    if loc == "ja_JP":
        if rng.random() < 0.5:
            d.add("| No. | 氏名 | ふりがな | 所属 |\n|---|---|---|---|\n")
            for i in range(rng.randint(2, 5)):
                last, first = f.last_name(), f.first_name()
                d.add(f"| A-{i + 1} | ").add(f"{last} {first}", "name").add(" | ")
                d.add(f"{f.last_kana_name()} {f.first_kana_name()}", "name")
                d.add(f" | {rng.choice(['営業部', '技術部', '総務部'])} {rng.choice(['課長', '部長', '主任'])} |\n")
        else:
            d.add("お客様各位\n\nいつもお世話になっております。")
            d.add(rng.choice(["株式会社", "有限会社"]) + f.last_name() + "製作所の")
            d.add(f.last_name(), "name").add("です。\n")
            d.add(f.last_name() + f.first_name(), "name").add(rng.choice(HONOR["ja_JP"]) + "には先日のご注文の件でご連絡いたしました。\n")
            d.add("担当：").add(f"{f.last_name()} {f.first_name()}", "name").add("（").add(f"{f.last_kana_name()} {f.first_kana_name()}", "name")
            d.add(f"）　内線 {num(rng, 100, 999)}\n")
    elif loc == "ko_KR":
        d.add("받는 사람: ").add(f.name(), "name").add(rng.choice(HONOR["ko_KR"]) + "\n\n")
        d.add(f.name(), "name").add(rng.choice(HONOR["ko_KR"]) + " 안녕하세요,\n")
        d.add(f"고객님의 주문 {num(rng, 100000, 999999)}번이 발송되었습니다.\n담당: ").add(f.name(), "name").add("\n")
    elif loc == "zh_CN":
        d.add("姓名：").add(f.name(), "name").add("　　关系：配偶\n联系人：").add(f.name(), "name")
        d.add(rng.choice(HONOR["zh_CN"]) + f"\n电话：1{num(rng, 3000000000, 9999999999)}\n")
        e = fk("en_US", rng)
        d.add("Name 姓名 : ").add(f"{e.last_name().upper()} {e.first_name()}", "name").add(" ").add(f.name(), "name").add("\n")
    else:
        d.add("نشهد بأن السيد/ ").add(f.name(), "name").add("، يعمل لدى الشركة منذ عام 2019.\n")
        d.add("الاسم بالعربي        : ").add(f.name(), "name").add("\n")
        e = fk("en_US", rng)
        d.add("Name (English)       : ").add(e.name().upper(), "name").add("\nIqama No.            : ")
        d.add(f"2{num(rng, 100000000, 999999999)}", "tax id").add("\n")
    return d.done()


# ---------------------------------------------------------------- staff numbers in registers and timesheets

def staff_id(rng):
    return rng.choice([f"{num(rng, 1, 9):0>2}-{num(rng, 1, 9999):0>4}", num(rng, 10000, 99999), f"0{num(rng, 100, 999)}",
                       f"EMP/{rng.choice(['GGN', 'BLR', 'NYC'])}/{num(rng, 1, 9999):0>4}"])


def doc_staff(rng):
    f = fk(rng.choice(["en_US", "en_GB", "en_IN", "nl_NL", "de_DE"]), rng)
    d = Doc()
    k = rng.randrange(3)
    if k == 0:
        d.add("EMP NO  NAME                        GROSS      NET       PAY\n")
        for _ in range(rng.randint(3, 6)):
            d.add(staff_id(rng), "employee id").add("  ").add(f"{f.last_name().upper()}, {f.first_name().upper()}", "name")
            d.add(f"{' ' * rng.randint(4, 10)}{money(rng)}  {money(rng)}  DD ****{num(rng, 1000, 9999)}\n")
    elif k == 1:
        d.add("Employee\tID\tDate\tJob\tIn\tOut\tHours\n")
        name, sid = f"{f.last_name()}, {f.first_name()}", num(rng, 10000, 99999)
        for _ in range(rng.randint(3, 6)):
            d.add(name, "name").add("\t").add(sid, "employee id").add(f"\t{date(rng)}\tWO-{num(rng, 100000, 999999)}\t08:00\t16:30\t8.00\n")
    else:
        d.add(rng.choice(["Salaris oktober 2026 pnr ", "Pers.-Nr. ", "Matricule : ", "EE# ", "Staff No: "]))
        d.add(num(rng, 10, 99999), "employee id").add("\n")
        d.add("Checked by: ").add(f"{f.first_name()} {f.last_name()}", "name").add(" (").add(staff_id(rng), "employee id")
        d.add(f")\nBatch {num(rng, 1000, 9999)}, total {money(rng)}\n")
    return d.done()


MAKERS = [(doc_address, 4), (doc_boxed, 2), (doc_names, 3), (doc_cjk, 2), (doc_staff, 2)]


def docs(n, seed):
    rng = random.Random(seed)
    pool = [m for m, w in MAKERS for _ in range(w)]
    out = []
    for _ in range(n):
        text, spans = rng.choice(pool)(rng)
        if rng.random() < 0.12:
            text, spans = augment.ocr((text, spans), rng, 0.08)
        out.append((text, spans))
    return out


if __name__ == "__main__":
    import os
    import sys
    if os.environ.get("PYTHONHASHSEED") != "0":
        os.execve(sys.executable, [sys.executable, *sys.argv], {**os.environ, "PYTHONHASHSEED": "0"})
    for t, s in docs(int(sys.argv[1]) if len(sys.argv) > 1 else 6, int(sys.argv[2]) if len(sys.argv) > 2 else 1):
        out = list(t)
        for a, b, lab in sorted(s, reverse=True):
            out[a:b] = list(f"⟦{lab}|{t[a:b]}⟧")
        print("".join(out), "\n" + "-" * 60)
