"""Your own identifiers in place of placeholders (Redactor(identifiers=...), add_identifier)."""

import pytest

from veil import US_TAX_K1, Redactor


def test_a_person_and_a_taxpayer_id_show_as_their_identifiers_however_written():
    r = Redactor(US_TAX_K1, identifiers={"Avery K. Mockridge": "LP-0042", "123-45-6789": "INV-17"})
    sent = r.redact_text("MOCKRIDGE, AVERY K (SSN 123 45 6789) wired to Priya Raman; A. Mockridge confirmed.")
    assert sent == "LP-0042 (SSN INV-17) wired to NAME_002; LP-0042 confirmed."
    # Back as the real values, a person as the table names them
    assert r.restore_text(sent) == ("Avery K. Mockridge (SSN 123-45-6789) wired to Priya Raman; "
                                    "Avery K. Mockridge confirmed.")
    assert r.identifiers == {"LP-0042": "Avery K. Mockridge", "INV-17": "123-45-6789"}


def test_an_identifier_already_in_the_text_stays_and_comes_back_as_its_value():
    r = Redactor(US_TAX_K1)
    r.add_identifier("Avery K. Mockridge", "LP-0042")
    # Typed, or redacted a second time: it isn't taken for an ID number and hidden again
    assert r.redact_text("Is LP-0042 the partner? Investor ID LP-0042", typed=True) == \
        "Is LP-0042 the partner? Investor ID LP-0042"
    assert r.redact_text(r.redact_text("Avery Mockridge")) == "LP-0042"
    assert r.restore({"name": "LP-0042", "note": "LP-0042's K-1"}) == \
        {"name": "Avery K. Mockridge", "note": "Avery K. Mockridge's K-1"}


def test_other_values_take_their_kind_and_a_placeholder_is_left_where_no_identifier_is_given():
    r = Redactor(US_TAX_K1)
    r.add_identifier("000123456789", "ACCT-A", kind="ACCOUNT")
    sent = r.redact_text("Wired to account 000123456789 and 000987654321.")
    assert sent.startswith("Wired to account ACCT-A and ") and "987654321" not in sent and "_001" in sent


def test_identifiers_that_would_be_mistaken_are_refused():
    r = Redactor()
    r.add_identifier("Avery Mockridge", "LP-0042")
    with pytest.raises(ValueError, match="looks like a placeholder"):
        r.add_identifier("Priya Raman", "NAME_007")
    with pytest.raises(ValueError, match="already the identifier"):
        r.add_identifier("Priya Raman", "LP-0042")
    with pytest.raises(ValueError, match="needed"):
        r.add_identifier("Priya Raman", " ")


def test_a_value_hidden_by_hand_is_hidden_as_a_whole_word_only():
    r = Redactor()
    placeholder = r.add("Will", "NAME")
    assert r.redact_text("Will and the Willow fund") == f"{placeholder} and the Willow fund"
