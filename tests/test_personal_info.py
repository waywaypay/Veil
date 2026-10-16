"""Personal information swapped for placeholders: what's hidden, what isn't, and what comes back."""

import json
import os
import time

import pytest

from veil import US_TAX_K1, Redactor  # noqa: E402


def PersonalInfoRedactor():
    return Redactor(US_TAX_K1)

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "k1_specimens.json")


def hidden(text, *known, typed=False):
    """What ``text`` loses: the values its placeholders stand for, in order."""
    r = PersonalInfoRedactor()
    for name in known:
        r.add_person(name)
    out = r.redact_text(text, typed=typed)
    assert r.restore_text(out) != text or out == text or r._real   # sanity
    return [r._real[p] for p in sorted(r._real, key=out.find) if p in out]


# -- each kind ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("Partner: Avery F. Mockridge", ["Avery F. Mockridge"]),
    ("JORDAN T. EXEMPLAR", ["JORDAN T. EXEMPLAR"]),
    ("Prepared for: Dagny Adeyemi", ["Dagny Adeyemi"]),
    ("Name Fennel Mere Income LP Name Olu Z. Quarrington", ["Olu Z. Quarrington"]),
    ("F Partner's name, address, city, state, and ZIP code\nZeb B. Kowalczyk", ["Zeb B. Kowalczyk"]),
    ("Investor: Priya Patel", ["Priya Patel"]),
    ("Wei Zhang and Siobhan Nakamura", ["Wei Zhang", "Siobhan Nakamura"]),   # a common surname; a first name
    ("Members: Olu Adeyemi, Kwesi Mensah and Tal Barak", ["Olu Adeyemi", "Kwesi Mensah", "Tal Barak"]),
    ("Mockridge, Avery K.", ["Avery K. Mockridge"]),
    ("Dear Dr. Rowan Exemplar and Ms. Testwell", ["Rowan Exemplar", "Ms. Testwell"]),
    ("Attn: Maria de la Cruz", ["Maria de la Cruz"]),
    ("Sean O'Brien's K-1", ["Sean O'Brien"]),
    ("Jane Doe Revocable Trust", ["Jane Doe"]),
])
def test_names_it_finds(text, expected):
    assert hidden(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("6224 Mockingbird Ct\nAnytown, WA 00490", ["6224 Mockingbird Ct\nAnytown, WA 00490"]),
    ("4702 Placeholder Rd, Ste 323", ["4702 Placeholder Rd, Ste 323"]),
    ("345 Park Avenue, 30th Floor, New York, NY 10154-0004", ["345 Park Avenue, 30th Floor, New York, NY 10154-0004"]),
    ("2800 Sand Hill Road Suite 101 Menlo Park California 94025",
     ["2800 Sand Hill Road Suite 101 Menlo Park California 94025"]),
    ("123 Main St Palo Alto CA 94301", ["123 Main St Palo Alto CA 94301"]),
    ("100 W 41st St", ["100 W 41st St"]),
    ("1585 Broadway", ["1585 Broadway"]),
    ("P.O. Box 4471", ["P.O. Box 4471"]),
    ("PALO ALTO, CA 94301", ["PALO ALTO, CA 94301"]),
])
def test_addresses(text, expected):
    assert hidden(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("avery.mockridge@example.com", ["avery.mockridge@example.com"]),
    ("write to avery [at] example [dot] com", ["avery [at] example [dot] com"]),
    ("(415) 555-0134 ext. 12", ["(415) 555-0134 ext. 12"]),
    ("Call 415-555-0134 or 415.555.0199", ["415-555-0134", "415.555.0199"]),
    ("+1 415 555 0134", ["+1 415 555 0134"]),
    ("Tel: 415 555 0134", ["415 555 0134"]),
    ("Fax 4155550134", ["4155550134"]),
    ("cell 4155550134", ["4155550134"]),
    ("+44 20 7946 0958", ["+44 20 7946 0958"]),
])
def test_emails_and_phones(text, expected):
    assert hidden(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("Wire to Account No. 123456789012", ["123456789012"]),
    ("Acct #: 0042-7781-11", ["0042-7781-11"]),
    ("Account ending in 4321", ["4321"]),
    ("Bank account number: ****6789", ["****6789"]),
    ("ABA Routing Number 021000021", ["021000021"]),
    ("SWIFT/BIC: CHASUS33", ["CHASUS33"]),
    ("IBAN GB82 WEST 1234 5698 7654 32", ["GB82 WEST 1234 5698 7654 32"]),
    ("GB82WEST12345698765432", ["GB82WEST12345698765432"]),            # an IBAN that checks out, unlabelled
    ("card 4111 1111 1111 1111", ["4111 1111 1111 1111"]),
    ("Passport No. X12345678", ["X12345678"]),
    ("Investor ID: INV-20391", ["INV-20391"]),
    ("Driver's License D1234567", ["D1234567"]),
    ("DOB: 04/12/1975", ["04/12/1975"]),
    ("Date of birth March 4, 1975", ["March 4, 1975"]),
    ("reference 20240315123456", ["20240315123456"]),                    # 11 to 19 digits
])
def test_accounts_ids_and_birth_dates(text, expected):
    assert hidden(text) == expected


# -- names the app knows -------------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Avery K. Mockridge", "Avery Mockridge", "AVERY K MOCKRIDGE", "Mockridge, Avery K.", "MOCKRIDGE AVERY",
    "A. Mockridge", "avery mockridge", "K-1_Avery_Mockridge_2024.pdf", "Avery\nMockridge",
])
def test_a_known_person_however_written_gets_one_placeholder_and_comes_back_as_known(text):
    r = PersonalInfoRedactor()
    r.add_person("Avery K. Mockridge")
    out = r.redact_text(text)
    assert "ockridge" not in out.casefold() and "NAME_001" in out
    assert r.restore_text("NAME_001") == "Avery K. Mockridge"


def test_a_known_surname_alone_or_after_a_title_is_hidden_and_comes_back_as_written():
    r = PersonalInfoRedactor()
    r.add_person("Avery K. Mockridge")
    out = r.redact_text("Mockridge signed; Mr. Mockridge's K-1. The mockingbird sang.")
    assert out == "NAME_001 signed; NAME_002's K-1. The mockingbird sang."
    assert r.restore_text(out) == "Mockridge signed; Mr. Mockridge's K-1. The mockingbird sang."
    # A surname that's an ordinary word, or a first name, isn't hidden alone; with the first name it is.
    r = PersonalInfoRedactor()
    r.add_person("Jane Price")
    r.add_person("Morgan Taylor")
    assert r.redact_text("Purchase price; Price per unit; Taylor rule") == "Purchase price; Price per unit; Taylor rule"
    assert r.redact_text("Jane Price and Mr. Taylor") == "NAME_001 and NAME_002"


def test_trusts_joint_accounts_and_custodial_titles():
    r = PersonalInfoRedactor()
    r.add_person("Pershing LLC FBO Avery Mockridge IRA")
    r.add_person("John & Jane Doe JTWROS")
    r.add_person("Dummerton Retirement Trust")
    r.add_person("Placeholder Holdings, Inc.")
    out = r.redact_text("Pershing LLC FBO Avery Mockridge IRA; Avery Mockridge; John & Jane Doe JTWROS; John Doe; "
                        "Jane Doe; Dummerton Retirement Trust; Dummerton; Placeholder Holdings, Inc.; Pershing LLC")
    assert out == ("NAME_001; NAME_002; NAME_003; NAME_004; NAME_005; NAME_006; NAME_007; NAME_008; Pershing LLC")
    assert r.restore_text("NAME_008") == "Placeholder Holdings, Inc."


def test_a_known_name_in_a_business_s_name_comes_back_exactly():
    r = PersonalInfoRedactor()
    r.add_person("Avery K. Mockridge")
    out = r.redact_text("Avery Mockridge Holdings, LLC")
    assert out == "NAME_001 Holdings, LLC" and r.restore_text(out) == "Avery Mockridge Holdings, LLC"


def test_a_name_suffix_is_kept_when_the_app_knows_it():
    r = PersonalInfoRedactor()
    r.add_person("John Smith Jr.")
    for text in ("John Smith Jr.", "John Smith", "Smith Jr., John"):
        out = r.redact_text(text)
        assert out == "NAME_001", (text, out)
    assert r.restore_text("NAME_001 signed.") == "John Smith Jr. signed."


def test_found_names_are_remembered():
    r = PersonalInfoRedactor()
    r.redact_text("Attn: Kwesi Mensah")
    assert r.redact_text("Kwesi Mensah's K-1; KWESI MENSAH; Mensah, Kwesi") == "NAME_001's K-1; NAME_001; NAME_001"


# -- what the user types ------------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("Fill out Dagny Adeyemi's K-1.", ["Dagny Adeyemi"]),
    ("Please add Siobhan Okonkwo (LLC) and Thandiwe Ferreira (LPI).", ["Siobhan Okonkwo", "Thandiwe Ferreira"]),
    ("Is Zeb Quarrington a member?", ["Zeb Quarrington"]),
    ("Thanks Claude, use the Members & Ownership page.", []),
    ("Split it 60/40 between LLC and LPI for Fund III.", []),
    ("Where's the Halcyon Mere Energy Partners K-1? Box 20 Code Z is blank.", []),
    ("What did Pinecrest Gate Real Estate Fund III, LP report on 19A in 2024?", []),
    ("Record Schedule K-1 Box 11 Other Income as Section 1256 contracts.", []),
])
def test_what_the_user_types(text, expected):
    assert hidden(text, typed=True) == expected


# -- what stays ----------------------------------------------------------------------------------------

NOT_PERSONAL = [
    "Pinecrest Gate Real Estate Fund III, LP", "Morgan Stanley Smith Barney LLC", "Grant Thornton LLP",
    "Charles Schwab & Co., Inc.", "Jordan Ridge Capital Fund II, LP", "Edward Jones", "Raymond James Financial",
    "Halcyon Mere Energy Partners, LLC", "Marlow Vane Growth Fund, LP", "Eastmere Holdings, LP",
    "Beginning capital account $ 1,614,150", "Ending capital account 290226", "Current year net income (loss)",
    "Partner's share of profit, loss, and capital", "Qualified nonrecourse $ 66,700",
    "1 Ordinary business income (loss) (1,083,246)", "6a Ordinary dividends 204,725",
    "9c Unrecaptured section 1250 gain",
    "20 Z Section 199A information", "13 ZZ Other deductions 12,500", "19A Distributions 125,000",
    "For calendar year 2023, or tax year beginning 01/01/2023 ending 12/31/2023", "OMB No. 1545-0123",
    "Department of the Treasury Internal Revenue Service", "IRS center where partnership filed return: E-file",
    "General partner or LLC member-manager", "Limited partner or other LLC member", "Domestic partner",
    "Did the partner contribute property with a built-in gain or loss? No", "Profit 5.8042 % 5.8042 %",
    "Members & Ownership page", "Upload K-1s", "Statement A - Codes reported in Part III",
    "Capital contributed during the year $ 148,350", "Withdrawals & distributions $ 0",
    "Net section 1231 gain (loss) 1,250,000", "Total 12,345,678.90", "Tax year 2024", "Fund III LP 2024 K-1.pdf",
    "Distribution dated 03/15/2024 of $250,000", "Box 20 code AH: 1,250", "Units held 125,000.0000",
    "Account analysis", "Capital account (tax basis method)", "Account: Capital", "Section 704(c) gain",
    "Wire date 2024-03-15", "Fund ID 4521", "Partner number of units 1,250", "Real Estate Fund",
]


@pytest.mark.parametrize("text", NOT_PERSONAL)
def test_fund_names_k1_vocabulary_and_amounts_stay(text):
    r = PersonalInfoRedactor()
    assert r.redact_text(text) == text


def test_specimen_k1s_lose_only_the_partner_and_the_addresses():
    """Fictional K-1 specimens, as Snowman's PDF reader read them."""
    with open(FIXTURES) as f:
        specimens = json.load(f)
    for specimen in specimens:
        path, data, partner = specimen["file"], specimen["data"], specimen["partner_name"]
        r = PersonalInfoRedactor()
        r.add_person(partner)
        out = r.redact(data)
        assert (out["partnership"], out["rows"], out["warnings"]) == \
            (data["partnership"], data["rows"], data["warnings"]), path
        kinds = {p.rsplit("_", 1)[0] for p in r._real}
        assert kinds <= {"NAME", "ADDRESS", "SSN", "EIN", "TIN"}, (path, r._real)
        # The partner, and their surname alone ("Specimen" is one, so the SPECIMEN watermark goes too).
        names = {v for p, v in r._real.items() if p.startswith("NAME")}
        assert partner in names and names <= {partner} | {
            w.upper() for w in partner.split()} | set(partner.split()), (path, names)
        assert partner not in json.dumps(out)
        if data["partner"].get("entity_type") == "Individual":
            assert partner.split()[-1] not in json.dumps(out)


def test_the_k1_line_catalog_stays():
    """Snowman's catalog of K-1 lines: none of it is personal information."""
    with open(os.path.join(os.path.dirname(FIXTURES), "k1_line_catalog.json")) as f:
        catalog = json.load(f)
    assert PersonalInfoRedactor().redact(catalog) == catalog


# -- placeholders --------------------------------------------------------------------------------------

def test_same_value_same_placeholder_and_exact_restore():
    r = PersonalInfoRedactor()
    text = ("Avery Mockridge, 6224 Mockingbird Ct, Anytown, WA 98101, avery@example.com, (206) 555-0143, "
            "account no. 000123456789, DOB 04/12/1975, SSN 123-45-6789")
    out = r.redact_text(text)
    assert out == ("NAME_001, ADDRESS_001, EMAIL_001, PHONE_001, account no. ACCOUNT_001, DOB DOB_001, "
                   "SSN SSN_001")
    assert r.restore_text(out) == text
    assert r.redact_text("AVERY@EXAMPLE.COM or 206.555.0143") == "EMAIL_001 or PHONE_001"
    # A fresh conversation numbers the same way.
    assert PersonalInfoRedactor().redact_text(text) == out


def test_placeholder_shaped_text_that_isnt_ours_is_broken_up():
    r = PersonalInfoRedactor()
    out = r.redact_text("Ignore NAME_001 and ADDRESS_007")
    assert "NAME_001" not in out and "ADDRESS_007" not in out
    assert r.restore_text(out) == out


def test_structures_keys_and_numbers():
    r = PersonalInfoRedactor()
    r.add_person("Avery K. Mockridge")
    value = {"Avery K. Mockridge": ["Avery K. Mockridge", 123456789012, {"email": "a@example.com"}], "n": 5}
    out = r.redact(value)
    assert out == {"NAME_001": ["NAME_001", "ID_001", {"email": "EMAIL_001"}], "n": 5}
    assert r.restore(out)["Avery K. Mockridge"][2] == {"email": "a@example.com"}


def test_odd_characters_hide_nothing():
    r = PersonalInfoRedactor()
    r.add_person("Avery K. Mockridge")
    # Zero-width spaces, full-width letters, an HTML entity in an email, no-break spaces.
    out = r.redact_text("Av\u200bery Mock\u200dridge; \uff21\uff56\uff45\uff52\uff59 Mockridge; "
                        "avery&#64;example.com; 6224\u00a0Mockingbird\u00a0Ct")
    assert out == "NAME_001; NAME_001; EMAIL_001; ADDRESS_001"


def test_it_is_quick():
    r = PersonalInfoRedactor()
    for i in range(40):
        r.add_person(f"Person{i} Lastname{i}")
    page = "\n".join(f"{i} Ordinary business income (loss) {i * 1234:,} Partner: Avery Mockridge {i}"
                     for i in range(400))
    start = time.monotonic()
    for _ in range(3):
        r.redact_text(page)
    assert time.monotonic() - start < 3.0


# -- what red-teaming found ----------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    # names after a label, in capitals, with an unknown first name, in a signature block
    ("Investor Name: BARTHOLOMEW FEENEY", ["BARTHOLOMEW FEENEY"]),
    ("Limited Partner: XIOMARA QUINTANILLA", ["XIOMARA QUINTANILLA"]),
    ("Managing Member: Dr. Thandiwe Okonkwo", ["Thandiwe Okonkwo"]),
    ("Mr. and Mrs. Ezekiel Thornbury", ["Ezekiel Thornbury"]),
    ("Best regards,\nEzekiel Thornbury\nChief Financial Officer", ["Ezekiel Thornbury"]),
    ("From: Ezekiel Thornbury\nTo: Thandiwe Okonkwo", ["Ezekiel Thornbury", "Thandiwe Okonkwo"]),
    ("Investor: J. Ezekiel Thornbury", ["J. Ezekiel Thornbury"]),
    ("Subject: K-1 for Thandiwe Okonkwo", ["Thandiwe Okonkwo"]),
    ("Member: Thandiwe Okonkwo (LLC), Ezekiel Thornbury (LPI)", ["Thandiwe Okonkwo", "Ezekiel Thornbury"]),
    # a name found once, everywhere else in the text; a family's other members
    ("Investor: Thandiwe Okonkwo\nThe 2024 allocation to Okonkwo is 2.5%.", ["Thandiwe Okonkwo", "Okonkwo"]),
    ("Thandiwe Okonkwo and Kwame Okonkwo, JTWROS", ["Thandiwe Okonkwo", "Kwame Okonkwo"]),
    ("John & Jane Doe JTWROS", ["John Doe", "Jane Doe"]),
    ("Thandiwe Okonkwo Revocable Trust u/a/d 3/1/2015", ["Thandiwe Okonkwo"]),
    ("The Okonkwo Family Trust", ["Okonkwo"]),
    ("Ezekiel Thornbury, Trustee", ["Ezekiel Thornbury"]),
    # accents, curly apostrophes, surname first, more names than two
    ("José García received a distribution of $25,000.", ["José García"]),
    ("Siobhan O’Brien", ["Siobhan O’Brien"]),
    ("ZHANG WEI", ["WEI ZHANG"]),
    ("Priya PATEL", ["Priya PATEL"]),
    ("Juan Carlos Garcia Lopez", ["Juan Carlos Garcia Lopez"]),
])
def test_names_red_teaming_found(text, expected):
    assert hidden(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("add jane smith as an LPI member", ["jane smith"]),
    ("add thandiwe okonkwo as a member", ["thandiwe okonkwo"]),
    ("Is EZEKIEL THORNBURY a member?", ["EZEKIEL THORNBURY"]),
    ("Add J.R. Thornbury", ["J.R. Thornbury"]),
    ("Move 5% from Okonkwo, Thandiwe to Feeney, Bartholomew", ["Thandiwe Okonkwo", "Bartholomew Feeney"]),
    ("call me at 415 555 0134", ["415 555 0134"]),
])
def test_typed_names_and_numbers_red_teaming_found(text, expected):
    assert hidden(text, typed=True) == expected


@pytest.mark.parametrize("text, expected", [
    ("123 Main St Palo Alto CA 94301", ["123 Main St Palo Alto CA 94301"]),
    ("1420 Alameda de las Pulgas", ["1420 Alameda de las Pulgas"]),
    ("3000 El Camino Real", ["3000 El Camino Real"]),
    ("One Market Plaza", ["One Market Plaza"]),
    ("123-B Elm St", ["123-B Elm St"]),
    ("RR 2 Box 152", ["RR 2 Box 152"]),
    ("PSC 1234 Box 5678, APO AE 09012", ["PSC 1234 Box 5678, APO AE 09012"]),
    ("POB 4567", ["POB 4567"]),
    ("Box 1234, Jackson, WY 83001", ["Box 1234, Jackson, WY 83001"]),
    ("Palo Alto, Calif. 94301", ["Palo Alto, Calif. 94301"]),
    ("Coeur d'Alene, ID 83814", ["Coeur d'Alene, ID 83814"]),
    ("Mailing address: 88 Kearny", ["88 Kearny"]),
    ("Toronto, ON M5V 2T6", ["M5V 2T6"]),
    ("Bahnhofstrasse 45, 8001 Zurich, Switzerland", ["Bahnhofstrasse 45, 8001 Zurich, Switzerland"]),
    ("Account: 3302114471", ["3302114471"]),
    ("Acct 12345678", ["12345678"]),
    ("for credit to account 1029384756", ["1029384756"]),
    ("FFC: 123-45678", ["123-45678"]),
    ("Account Number (last 4): 4321", ["4321"]),
    ("Visa ending 4242", ["4242"]),
    ("4111-1111-1111-1112", ["4111-1111-1111-1112"]),
    ("Swift code chasus33xxx", ["chasus33xxx"]),
    ("415 555-0134; 415/555-0135; 415 - 555 - 0136", ["415 555-0134", "415/555-0135", "415 - 555 - 0136"]),
    ("Work: 415 555 0134; Mobile: 07700 900123", ["415 555 0134", "07700 900123"]),
    ("011 44 20 7946 0958", ["011 44 20 7946 0958"]),
    ("jane.doe at gmail dot com; jane[dot]doe[at]gmail[dot]com",
     ["jane.doe at gmail dot com", "jane[dot]doe[at]gmail[dot]com"]),
    ("DOB 14-Mar-1975; DOB: 1975/03/14; Date of birth (MM/DD/YYYY): 03/14/1975; Birthday: May 2, 1980",
     ["14-Mar-1975", "1975/03/14", "03/14/1975", "May 2, 1980"]),
    ("DL# D1234567; LP ID: 004512; Investor Code: CR-0045; Foreign TIN: AB123456C",
     ["D1234567", "004512", "CR-0045", "AB123456C"]),
])
def test_addresses_accounts_and_numbers_red_teaming_found(text, expected):
    assert hidden(text) == expected


@pytest.mark.parametrize("text", [
    "B Partnership's name, address, city, state, and ZIP code\nCalder Ridge II, L.P.",
    "Name: Calder Ridge, L.P.", "General Partner: Calder Ridge GP", "Account Name: Calder Ridge II",
    "Investor: Stanford University", "Moss Adams LLP", "Elliott Davis, LLC", "Robert W. Baird & Co.",
    "Bank Name: Wells Fargo", "Hudson Yards Co-Invest", "Austin Office Portfolio", "Orlando Multifamily",
    "Attn: Investor Relations", "Dear Valued Investor,", "Ordinary Income CA 45000", "Composite Tax Paid NY 34567",
    "Investment in 100 Pine Street Holdings LLC", "Rev. Proc. 2019-11", "Added Calder Ridge K-1",
    "EIN 00-0602997", "Spencer Stuart", "Alliance Bernstein", "Total 2345678901", "+1 250 000 000",
    "Partner TIN: 000-36-8219",
])
def test_what_red_teaming_found_hidden_by_mistake(text):
    r = PersonalInfoRedactor()
    out = r.redact_text(text)
    assert not any(p.startswith(("NAME", "ADDRESS", "PHONE", "ACCOUNT", "ID_")) for p in r._real), (text, out)


@pytest.mark.parametrize("text", ["Passive Activity", "Bonus Depreciation", "Hurdle Rate", "Wire Instructions",
                                  "Palo Alto", "San Francisco", "Side Letter", "Investment Committee"])
def test_finance_words_and_places_typed_stay(text):
    assert hidden(f"What about the {text}?", typed=True) == []


def test_a_fund_the_app_knows_is_no_name_however_its_shortened():
    r = PersonalInfoRedactor()
    r.add_business("Calder Ridge Ventures II, L.P.")
    r.add_business("Lark Hollow Fund, L.P.")
    for text in ("What did Calder Ridge report on 19A?", "Compare Calder Ridge and Lark Hollow on box 1"):
        assert r.redact_text(text, typed=True) == text
    assert r.redact_text("Calder Ridge Ventures II, L.P.") == "Calder Ridge Ventures II, L.P."


def test_a_name_typed_without_evidence_hides_only_there():
    """Two capitalized words the user typed are hidden in that message, but not remembered: a fund's
    short name mustn't spread to the K-1 pages."""
    r = PersonalInfoRedactor()
    assert r.redact_text("Compare Calder Ridge and Lark Hollow on box 1", typed=True) == \
        "Compare NAME_001 and NAME_002 on box 1"
    page = "Lark Hollow Fund, L.P. and Calder Ridge Ventures II, L.P. both report 19A."
    assert r.redact_text(page) == page



@pytest.mark.parametrize("verb", ["Call", "Text", "Message", "Invite", "Meet", "Pay", "Remind", "Contact",
                                  "Introduce", "Welcome", "Notify", "Cc", "Schedule", "Book", "Email", "Phone"])
@pytest.mark.parametrize("typed", [False, True])
def test_a_verb_before_a_name_isnt_part_of_it(verb, typed):
    r = Redactor()
    assert r.redact_text(f"{verb} Priya Patel at 415-555-0134", typed=typed) == f"{verb} NAME_001 at PHONE_001"
    assert r.restore_text("NAME_001") == "Priya Patel"


def test_a_name_that_is_also_a_verb_is_still_hidden():
    # Ping is a first name too: as a stop word, "Ping Zhang" would go out as it is.
    assert hidden("Ping Zhang called") == ["Ping Zhang"]
    assert hidden("Investor: Ping Zhang") == ["Ping Zhang"]


def test_a_placeholder_before_digits_comes_back():
    r = PersonalInfoRedactor()
    r.add_person("Avery K. Mockridge")
    for text in ("K1_Mockridge2024.pdf", "Investor: Thandiwe Okonkwo2", "DOB: 03/14/1975 and DOB: 03/14/1975123"):
        out = r.redact(text)
        assert r.restore(out) == text, (text, out)
    # And the taxpayer IDs never take a placeholder's digits for part of a number.
    r = PersonalInfoRedactor()
    out = r.redact_text("ABC 12345678901(415) 555-0134")
    assert out.startswith("ABC ID_001") and r.restore_text(out) == "ABC 12345678901(415) 555-0134"


@pytest.mark.parametrize("text, expected", [
    # what the benchmark on Gretel's synthetic financial documents found
    ("Call Priya Patel at 415-555-0134", ["Priya Patel", "415-555-0134"]),
    ("Dear Gudula Scheuermann,", ["Gudula Scheuermann"]),
    ("Applicant Name: Mark Tiffany Fuentes", ["Mark Tiffany Fuentes"]),
    ("Shipper: Tassilo M. Heß", ["Tassilo M. Heß"]),
    ("Hello Sarah, thanks for writing.", ["Sarah"]),
    ('{"first_name": "Inna", "last_name": "Patberg"}', ["Inna", "Patberg"]),
    ("<fpml:name>Moreno</fpml:name>", ["Moreno"]),
    ('"ID","First Name","Last Name"\n"1","Bob","Johnson"', ["Bob", "Johnson"]),
    ("Lives at 8563 Wilson Forks and works", ["8563 Wilson Forks"]),
    ("3091 Paul Hill, Port Briannaport\nSan Teresa", ["3091 Paul Hill, Port Briannaport"]),
    ("Shipper:\nGustav Jakobsson\n5 Xaviweg\nLondon, UK", ["Gustav Jakobsson", "5 Xaviweg\nLondon, UK"]),
    ("located at 45, Baker Street, London, NW1 6XE.", ["45, Baker Street, London, NW1 6XE"]),
    ("Email: john.thompson@atlanticshipping.co.uk", ["john.thompson@atlanticshipping.co.uk"]),
    ("Call us at 0800 123 4567.", ["0800 123 4567"]),
    ('"driver_license_number": "C057-8449-728-8"', ["C057-8449-728-8"]),
    ("date of birth (e.g. 1994-08-29)", ["1994-08-29"]),
    ("At WCRMGBPJ669 we lend.", ["WCRMGBPJ669"]),
])
def test_what_the_gretel_benchmark_found(text, expected):
    assert hidden(text) == expected


@pytest.mark.parametrize("text", [
    "<InstrumentName>Brent Crude Oil</InstrumentName>", "goods, Premium Organic Olive Oil, have been inspected",
    "Hazardous substance name: Hazardous Substance", "IV. ADDITIONAL LIVING EXPENSES", "STALE BILL OF LADING",
    "A. Named Driver Exclusion: none",
    "visit our website at www.example.com", "<creationTime>2022-02-15T10:30:00</creationTime>",
    '"2021-01-01",15000,8000', "Sender:", "Skin contact: Wash off with soap",
])
def test_what_the_gretel_benchmark_found_hidden_by_mistake(text):
    assert hidden(text) == []


def test_an_ip_address_label_takes_no_sentence_with_it():
    assert hidden("IP address: 14.47.149.44. This information is confidential.") == ["14.47.149.44"]


def test_an_amount_with_the_digits_of_a_number_caught_stays_an_amount():
    r = PersonalInfoRedactor()
    text = "TIN 123456789; CashLetterAmount=\"1234567.89\""
    out = r.redact_text(text)
    assert "1234567.89" in out and r.restore_text(out) == text


@pytest.mark.parametrize("text, expected", [
    ("<us-gaap:DateOfBirth>1940-07-20</us-gaap:DateOfBirth>", ["1940-07-20"]),
    ("first,last,date_of_birth\nInna,Patberg,1935-12-01", ["Inna", "Patberg", "1935-12-01"]),
    ('<n1:CustomerID>M9089Y551</n1:CustomerID>', ["M9089Y551"]),
    ("The employee ID for Heinz Kabus is Nq-92647.", ["Heinz Kabus", "Nq-92647"]),
    ("we noted that her passport number, R87712693, did not match", ["R87712693"]),
    ("such as James Aguilar (EMP286818), have been", ["James Aguilar", "EMP286818"]),
])
def test_ids_and_birth_dates_by_their_field_or_context(text, expected):
    assert hidden(text) == expected


@pytest.mark.parametrize("text", ["Balance USD52482349 at close", "ISIN US1234567890 traded", "employee benefits since 2019"])
def test_amounts_isins_and_years_are_no_ids(text):
    assert hidden(text) == []
