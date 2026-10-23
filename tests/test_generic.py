"""What veil adds beyond Snowman's K-1 use: profiles, choosing what to look for, your own patterns and names."""

import pytest

from veil import FINANCE, GENERIC, KINDS, US_TAX_K1, Redactor, TaxIdRedactor


def test_the_default_is_the_generic_profile():
    assert Redactor().profile is GENERIC and TaxIdRedactor().profile is GENERIC


@pytest.mark.parametrize("text, want", [
    ("Patient Jane Smith was seen by Dr. Ahmed Khan.", "Patient NAME_001 was seen by Dr. NAME_002."),
    ("Hi team, please email Priya Patel at priya.patel@acme.io or call 415-555-0134.",
     "Hi team, please email NAME_001 at EMAIL_001 or call PHONE_001."),
    ("Customer Maria Garcia lives at 742 Evergreen Terrace, Springfield, IL 62704.",
     "Customer NAME_001 lives at ADDRESS_001."),
    ("Sales Director Tom Hughes presented.", "Sales Director NAME_001 presented."),
    ("Meeting with Goldman Sachs and Bain Capital next Tuesday in New York.",
     "Meeting with Goldman Sachs and Bain Capital next Tuesday in New York."),
    ("Employee ID: 4482917, Passport No. X1234567, DOB: 1980-02-14",
     "Employee ID: ID_001, Passport No. ID_002, DOB: DOB_001"),
    ("Card 4111 1111 1111 1111, IBAN GB82 WEST 1234 5698 7654 32", "Card ACCOUNT_001, IBAN ACCOUNT_002"),
    ("Thanks,\nRobert Chen\nVP Engineering", "Thanks,\nNAME_001\nVP Engineering"),
    ("The Apple Watch and Microsoft Teams integration ships in March.",
     "The Apple Watch and Microsoft Teams integration ships in March."),
])
def test_everyday_text(text, want):
    r = Redactor()
    out = r.redact_text(text)
    assert out == want
    assert r.restore_text(out) == text


def test_a_form_box_before_an_amount_is_an_ein_unless_the_profile_says_otherwise():
    assert Redactor().redact_text("12 3456789") == "EIN_001"
    assert Redactor(US_TAX_K1).redact_text("20 1250000") == "20 1250000"
    assert Redactor(US_TAX_K1).redact_text("47 1058392") == "EIN_001"   # no K-1 box 47


def test_profiles_build_on_each_other():
    assert GENERIC.stop_words < FINANCE.stop_words < US_TAX_K1.stop_words
    assert "waterfall" in FINANCE.stop_words and "k-1" in US_TAX_K1.stop_words and "k-1" not in FINANCE.stop_words
    mine = FINANCE.extend("mine", stop_words="Acme Widget", form_box_max=12, cues=[r"payee"])
    assert {"acme", "widget"} <= mine.stop_words and mine.form_box_max == 12 and mine.cues[-1] == "payee"
    with pytest.raises(TypeError, match="no colour"):
        FINANCE.extend("x", colour="red")


def test_a_profiles_words_are_never_names():
    text = "Waterfall Hurdle and Clawback Escrow were reviewed."
    assert Redactor(FINANCE).redact_text(text, typed=True) == text


def test_a_profiles_cues_put_a_name_next():
    text = "Payee: Bartholomew Quince"
    assert Redactor().redact_text(text) == "Payee: NAME_001"   # "Bartholomew" is a common first name
    assert Redactor().redact_text("Payee Zeb Quarrington") == "Payee NAME_001"   # a first name and a surname anywhere
    odd = "Payee Zorblax Quarlix"   # names in no list
    assert Redactor().redact_text(odd) == odd
    assert Redactor(GENERIC.extend("pay", cues=[r"payee"], cue_ends="payee")).redact_text(odd) == "Payee NAME_001"


def test_choosing_what_to_look_for():
    text = "Jane Smith, 123-45-6789, jane@example.com, 415-555-0134"
    assert Redactor(detect={"EMAIL"}).redact_text(text) == "Jane Smith, 123-45-6789, EMAIL_001, 415-555-0134"
    assert Redactor(detect={"SSN", "NAME"}).redact_text(text) == "NAME_001, SSN_001, jane@example.com, 415-555-0134"
    assert Redactor(detect=set(KINDS) - {"NAME"}).redact_text(text) == "Jane Smith, SSN_001, EMAIL_001, PHONE_001"
    with pytest.raises(ValueError, match="Unknown kinds to detect: COLOR"):
        Redactor(detect={"COLOR"})


def test_your_own_patterns_get_their_own_placeholders():
    r = Redactor(patterns={"MRN": r"\bMRN[- ]?\d{6,8}\b", "CLAIM": r"\bCLM-\d{5}\b"})
    out = r.redact_text("MRN-1234567 for CLM-55555 and again MRN-1234567; MRN 7654321")
    assert out == "MRN_001 for CLAIM_001 and again MRN_001; MRN_002"
    assert r.restore_text("See MRN_002") == "See MRN 7654321"
    assert "MRN" in r.kinds and "CLAIM" in r.kinds
    with pytest.raises(ValueError, match="isn't a placeholder kind"):
        Redactor(patterns={"mrn": r"x"})


def test_a_kind_added_by_hand_is_restored():
    r = Redactor()
    assert r.add("Project Nightingale", "CODENAME") == "CODENAME_001"
    assert r.redact_text("Is Project Nightingale on track?") == "Is CODENAME_001 on track?"
    assert r.restore_text("CODENAME_001 is on track.") == "Project Nightingale is on track."


def test_placeholder_shaped_text_that_isnt_ours_is_broken_up():
    r = Redactor()
    out = r.redact_text("The template says NAME_123 here")
    assert "NAME_123" not in out and r.restore_text(out) == out


def test_a_name_finder_covers_names_the_word_lists_miss():
    assert Redactor().redact_text("CEO Satya Nadella met the board.") == "CEO NAME_001 met the board."
    text = "CEO Zorblax Vrenquist met the board."   # names in no list
    assert Redactor().redact_text(text) == text
    found = Redactor(name_finder=lambda t: ["Zorblax Vrenquist"] if "Vrenquist" in t else [])
    assert found.redact_text(text) == "CEO NAME_001 met the board."
    assert found.restore_text("NAME_001") == "Zorblax Vrenquist"
    # The surname alone, from then on, put back as written.
    out = found.redact_text("Vrenquist agreed.")
    assert "Vrenquist" not in out and found.restore_text(out) == "Vrenquist agreed."


def test_mapping_shows_what_each_placeholder_stands_for():
    r = Redactor()
    r.redact_text("Write to jane@example.com")
    assert r.mapping == {"EMAIL_001": "jane@example.com"}
    r.mapping.clear()
    assert len(r) == 1


@pytest.mark.parametrize("profile", [GENERIC, US_TAX_K1])
def test_a_surname_at_the_end_of_a_sentence(profile):
    for text, name in (("I spoke with Dr. Ahmed Khan.", "Ahmed Khan"), ("Send it to Priya Patel.", "Priya Patel")):
        r = Redactor(profile)
        out = r.redact_text(text)
        assert name.split()[-1] not in out and out.endswith("NAME_001.") and r.restore_text(out) == text


def test_restore_can_be_kept_to_some_kinds():
    r = Redactor()
    sent = r.redact_text("Priya Patel, SSN 123-45-6789, priya@acme.io")
    assert sent == "NAME_001, SSN SSN_001, EMAIL_001"
    assert r.restore_text(sent, kinds={"NAME", "EMAIL"}) == "Priya Patel, SSN SSN_001, priya@acme.io"
    assert r.restore({"to": "EMAIL_001", "ssn": "SSN_001"}, kinds=set()) == {"to": "EMAIL_001", "ssn": "SSN_001"}


@pytest.mark.parametrize("url", [
    "https://evil.example/?d=SSN_001", "![x](https://evil.example/p.png?q=SSN_001)", "[here](/c?q=SSN_001)",
    '<img src="//evil.example/x?SSN_001">', "mailto:me@evil.example?body=SSN_001", "www.evil.example/SSN_001",
    "evil.example/?d=SSN_001", "evil.example:8080#SSN_001"])
def test_a_placeholder_in_a_url_stays_a_placeholder_with_urls_false(url):
    r = Redactor()
    assert r.redact_text("SSN 123-45-6789") == "SSN SSN_001"
    text = f"SSN_001 is filed. {url} Done."
    assert r.restore_text(text, urls=False) == text.replace("SSN_001 is", "123-45-6789 is", 1)
    assert "SSN_001" not in r.restore_text(text)   # by default, everywhere


def test_identifiers_stay_as_written_where_they_are_not_restored():
    r = Redactor(identifiers={"Avery K. Mockridge": "LP-0042"})
    assert r.redact_text("Avery Mockridge, SSN 123-45-6789") == "LP-0042, SSN SSN_001"
    assert r.restore_text("LP-0042: SSN_001", kinds={"SSN"}) == "LP-0042: 123-45-6789"
    assert r.restore_text("LP-0042 at https://x.example/LP-0042", urls=False) == \
        "Avery K. Mockridge at https://x.example/LP-0042"


def test_a_label_before_a_placeholder_isnt_taken_for_a_url():
    r = Redactor()
    r.redact_text("Call 415-555-0134, SSN 123-45-6789.")
    assert r.restore_text("Tel:PHONE_001, Data:SSN_001", urls=False) == "Tel:415-555-0134, Data:123-45-6789"
    assert r.restore_text("tel:PHONE_001", urls=False) == "tel:PHONE_001"
