"""Taxpayer IDs are swapped for placeholders before the K-1 assistant's model sees them."""



from veil import US_TAX_K1  # noqa: E402
from veil import TaxIdRedactor as _TaxIdRedactor  # noqa: E402


def TaxIdRedactor():
    return _TaxIdRedactor(US_TAX_K1)

K1_PAGE = ("E Partner's SSN or TIN (Do not use TIN of a disregarded entity. See instructions.)\n123-45-6789\n"
           "A Partnership's employer identification number\n98-7654321")


def test_ssns_and_eins_become_placeholders_and_come_back():
    r = TaxIdRedactor()
    redacted = r.redact(K1_PAGE)
    assert "123-45-6789" not in redacted and "98-7654321" not in redacted
    assert redacted.endswith("instructions.)\nSSN_001\nA Partnership's employer identification number\nEIN_001")
    assert r.restore(redacted) == K1_PAGE
    assert r.redact(redacted) == redacted


def test_the_same_number_keeps_its_placeholder_however_it_is_written():
    r = TaxIdRedactor()
    assert r.redact("SSN 123-45-6789") == "SSN SSN_001"
    # An en dash (OCR), spaces after a label, no separators at all: the same number each time.
    assert r.redact("Partner 123\u201345\u20136789, TIN 123 45 6789, on file as 123456789") == \
        "Partner SSN_001, TIN SSN_001, on file as SSN_001"
    assert r.redact("and another 987-65-4321") == "and another SSN_002"
    assert r.restore("SSN_001 and SSN_002") == "123-45-6789 and 987-65-4321"
    # Put back as written, or in the usual dashed form once the document writes it that way.
    r = TaxIdRedactor()
    assert r.redact("l23 45 6789, then EIN 98\u20137654321") == "SSN_001, then EIN EIN_001"
    assert r.restore("SSN_001 / EIN_001") == "l23 45 6789 / 98-7654321"
    assert r.redact("Partner 123-45-6789") == "Partner SSN_001"
    assert r.restore("SSN_001") == "123-45-6789"


def test_nine_digits_in_a_row_are_hidden_unless_written_as_money():
    r = TaxIdRedactor()
    assert r.redact("Partner's identifying number:\n555443333") == "Partner's identifying number:\nTIN_001"
    assert r.redact("ref 987654321, routing 021000021") == "ref TIN_002, routing TIN_003"
    money = "Total $123456789, $ 123456789 and 123456789.00, or a round 125000000"
    assert TaxIdRedactor().redact(money) == money


def test_odd_groupings_and_a_dropped_digit_are_caught_after_a_label():
    r = TaxIdRedactor()
    assert r.redact("S.S.N. 1234 56 789") == "S.S.N. TIN_001"
    assert r.redact("Soc. Sec. No.: 123 456 780") == "Soc. Sec. No.: TIN_002"
    assert r.redact("Employer ID No. 98 765 4321") == "Employer ID No. TIN_003"
    assert r.redact("Partner TIN 123-45-678 (as read)") == "Partner TIN TIN_004 (as read)"   # OCR lost a digit
    assert r.restore("TIN_001, TIN_004") == "1234 56 789, 123-45-678"


def test_amounts_dates_and_masked_numbers_are_left_alone():
    r = TaxIdRedactor()
    text = ("Box 1 1,234,567  (123,456,789)  date 2025-12-31  12/31/2024  12.31.2024  amount -1250.00  "
            "phone 1-800-555-1234  (212) 555-1234  212.555.1234  ZIP 12345-6789  02110 1234  "
            "XXX-XX-6789  ***-**-6789  long 1234567890  line 20Z  20-Z  OMB No. 1545-0123  Cat. No. 11394R  "
            "Profit 12.3456%  Page 2 of 3  Form 1065 (2024)")
    assert r.redact(text) == text
    assert len(r) == 0


def test_placeholders_it_never_handed_out_are_left_as_written():
    r = TaxIdRedactor()
    r.redact("123-45-6789")
    assert r.restore("SSN_001 and SSN_002") == "123-45-6789 and SSN_002"


def test_dicts_and_lists_are_walked():
    r = TaxIdRedactor()
    value = {"file": "K-1 123-45-6789.pdf", "rows": [{"amount": "100.00", "note": "EIN 98-7654321"}], "pages": 2,
             "partner": None}
    redacted = r.redact(value)
    assert redacted == {"file": "K-1 SSN_001.pdf", "rows": [{"amount": "100.00", "note": "EIN EIN_001"}],
                        "pages": 2, "partner": None}
    assert r.restore(redacted) == value
