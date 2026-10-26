"""Money amounts: visible by default, hidden when they're a person's (amounts="personal") or always ("all")."""

import pytest

from veil import FINANCE, Redactor
from veil.tagged import TaggedRedactor

STATEMENT = ("Statement for Avery Mockridge, account no. 4410028871\n"
             "Opening balance $12,400.00\nDeposit 1,250.00\nClosing balance $13,650.00\n")
PAYROLL = ("employee_id,first_name,last_name,title,pay_date,gross_pay\n"
           "E10442,Yusuf,Adebayo,Payroll Analyst,2026-10-15,6,250.00\n")


def hidden(text, amounts, **kwargs):
    """The amounts ``text`` loses, in order."""
    r = Redactor(FINANCE, amounts=amounts, **kwargs)
    out = r.redact_text(text)
    return [r.mapping[p] for p in sorted(r.mapping, key=out.find) if p.startswith("AMOUNT_") and p in out]


# -- show, the default ---------------------------------------------------------------------------------

def test_amounts_stay_visible_by_default():
    out = Redactor(FINANCE).redact_text(STATEMENT)
    assert "$12,400.00" in out and "1,250.00" in out and "$13,650.00" in out and "AMOUNT" not in out
    assert Redactor(FINANCE).redact_text(STATEMENT) == Redactor(FINANCE, amounts="show").redact_text(STATEMENT)


def test_amounts_hide_nothing_else():
    """Whatever the setting, what else is hidden is what the default hides."""
    for text in (STATEMENT, PAYROLL, "Base salary: $142,000 for Jordan T. Exemplar, SSN 123-45-6789"):
        plain = Redactor(FINANCE).redact_text(text)
        for amounts in ("personal", "all"):
            r = Redactor(FINANCE, amounts=amounts)
            assert r.restore_text(r.redact_text(text), kinds={"AMOUNT"}) == plain


# -- personal ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("Base salary: $142,000", ["$142,000"]),
    (PAYROLL, ["6,250.00"]),
    ("Her bonus for 2025 was $18,500.", ["$18,500"]),
    ("LP commitment of $5,000,000 (Fund II)", ["$5,000,000"]),
    ("Net pay ........ 4,812.33", ["4,812.33"]),
    ("Amount owed: EUR 3,200.00", ["EUR 3,200.00"]),
    ("Avery Mockridge | Partner | $310,000.00", ["$310,000.00"]),   # a person on the row
    ("Avery Mockridge\t2026-01-31\t($12,400.00)", ["($12,400.00)"]),
    ("The capital call of $250,000 is due", []),
    ("Fund II closed at $400,000,000 in March.", []),
    ("Office rent is $8,500.00 a month.", []),
])
def test_personal_hides_amounts_tied_to_a_person(text, expected):
    assert hidden(text, "personal") == expected


def test_personal_hides_a_tied_amount_wherever_it_is_written_the_same_way():
    r = Redactor(FINANCE, amounts="personal")
    out = r.redact_text("Base salary: $142,000\nThe band's midpoint is $142,000; the cap is $150,000.")
    assert out == "Base salary: AMOUNT_001\nThe band's midpoint is AMOUNT_001; the cap is $150,000."
    assert r.redact_text("Is $142,000 enough?") == "Is AMOUNT_001 enough?"


# -- all -----------------------------------------------------------------------------------------------

def test_all_hides_every_amount_written_as_money():
    text = ("Wire $1,339,032.49 and EUR 2,500 to the fund; fees of £1,200 and ¥5000, a refund of -$45.10, "
            "a loss of ($12,400.00), 900 USD, US$15, $1.2M and ₹2,50,000. Total 6,250.00.")
    assert hidden(text, "all") == ["$1,339,032.49", "EUR 2,500", "£1,200", "¥5000", "-$45.10", "($12,400.00)",
                                   "900 USD", "US$15", "$1.2M", "₹2,50,000", "6,250.00"]


@pytest.mark.parametrize("text", [
    "The fee is 12.5% of profits.",
    "Tax year 2026",
    "Due 10/14/2026 at 10:30",
    "See Box 14 and line 20.",
    "EIN 12-3456789",
    "1,200 shares and 2,400 employees",
    "Population 1,234,567; version 3.14",
    "Rate booked: USD/AED 3.6735",
    "Invoice No. 12,345",
    "Server 192.168.0.12",
])
def test_all_leaves_what_isnt_money(text):
    assert hidden(text, "all") == []


def test_all_keeps_ein_and_percent_beside_amounts():
    r = Redactor(FINANCE, amounts="all")
    out = r.redact_text("EIN 12-3456789, Box 14: 12.5% of $40,000 on 10/14/2026 (tax year 2026)")
    assert out == "EIN EIN_001, Box 14: 12.5% of AMOUNT_001 on 10/14/2026 (tax year 2026)"


# -- placeholders and restoring -----------------------------------------------------------------------

def test_the_same_amount_twice_gets_one_placeholder():
    r = Redactor(FINANCE, amounts="all")
    out = r.redact_text("Paid $4,500.00 on Monday and $4,500.00 on Friday; $4,600.00 later.")
    assert out == "Paid AMOUNT_001 on Monday and AMOUNT_001 on Friday; AMOUNT_002 later."
    assert r.redact_text("Was it $4,500.00?") == "Was it AMOUNT_001?"


def test_a_reply_and_a_tool_call_get_the_exact_amounts_back():
    r = Redactor(FINANCE, amounts="all")
    out = r.redact_text("Refund ($12,400.00) and wire €1.234,56 to Avery Mockridge.")
    assert "AMOUNT_001" in out and "AMOUNT_002" in out
    assert r.restore_text("Refunding AMOUNT_001, then AMOUNT_002.") == "Refunding ($12,400.00), then €1.234,56."
    call = {"name": "send_wire", "input": {"amount": "AMOUNT_002", "memo": "refund AMOUNT_001"}}
    assert r.restore(call) == {"name": "send_wire", "input": {"amount": "€1.234,56", "memo": "refund ($12,400.00)"}}


def test_a_tool_call_through_the_wrapper_gets_the_exact_amount_back():
    pytest.importorskip("anthropic")
    from test_anthropic import FakeClient, _message

    from veil.anthropic import wrap
    fake = FakeClient([_message("Paying AMOUNT_001.", ("t1", "pay", {"amount": "AMOUNT_001"}))])
    client = wrap(fake, Redactor(FINANCE, amounts="all", reveal={"AMOUNT": "round"}))
    reply = client.messages.create(model="m", max_tokens=100,
                                   messages=[{"role": "user", "content": "Pay invoice 7 for $1,339,032.49"}])
    assert "1,339,032" not in str(fake.requests) and "AMOUNT_001 (about $1.3M)" in str(fake.requests)
    assert reply.content[0].text == "Paying $1,339,032.49."
    assert next(b for b in reply.content if b.type == "tool_use").input == {"amount": "$1,339,032.49"}


def test_reveal_round_shows_about_how_much():
    r = Redactor(FINANCE, amounts="all", reveal={"AMOUNT": "round"})
    out = r.redact_text("Distribution: $1,339,032.49; fees $250,000, (EUR 12,400.00) and 6,250.00 in total")
    assert out == ("Distribution: AMOUNT_001 (about $1.3M); fees AMOUNT_002 (about $250K), "
                   "AMOUNT_003 (about -EUR 12K) and AMOUNT_004 (about 6.3K) in total")
    assert r.restore_text("You got AMOUNT_001 (about $1.3M), AMOUNT_002 net.") == "You got $1,339,032.49, $250,000 net."
    assert r.redact_text(out) == out   # sent again with the next turn: the note isn't read as an amount


def test_reveal_round_works_with_a_birth_year_too():
    r = Redactor(FINANCE, amounts="personal", reveal={"AMOUNT": "round", "DOB": "year"})
    out = r.redact_text("Salary: $142,000\nDOB: 14/03/1990")
    assert out == "Salary: AMOUNT_001 (about $140K)\nDOB: DOB_001 (born 1990)"
    assert r.restore_text(out) == "Salary: $142,000\nDOB: 14/03/1990"


def test_the_tagged_redactor_passes_amounts_through():
    class Model:   # marks nothing: the rules do the rest
        without_torch = True

        def batch_predict_entities(self, pieces, labels, threshold):
            return [[] for _ in pieces]

    tagged = TaggedRedactor()
    tagged._model = Model()
    r = tagged.redactor(reveal={"AMOUNT": "round"}, amounts="personal")
    out = r.redact_text("Base salary: $142,000. The capital call of $250,000 is due.")
    assert out == "Base salary: AMOUNT_001 (about $140K). The capital call of $250,000 is due."
    assert r.restore_text(out) == "Base salary: $142,000. The capital call of $250,000 is due."


# -- checked -------------------------------------------------------------------------------------------

def test_invalid_settings_raise():
    with pytest.raises(ValueError, match="'show', 'personal', 'all'"):
        Redactor(amounts="some")
    with pytest.raises(ValueError, match="AMOUNT"):
        Redactor(amounts="all", reveal={"AMOUNT": "exact"})
    with pytest.raises(ValueError, match="amounts='show'"):
        Redactor(reveal={"AMOUNT": "round"})
    with pytest.raises(ValueError, match="amounts='show'"):
        TaggedRedactor(system="veil").redactor(reveal={"AMOUNT": "round"})
