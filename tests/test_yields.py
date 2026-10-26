from decimal import Decimal

import pytest

from balance_the_loan_books.models import Loan
from balance_the_loan_books.yields import expected_yield, round_cents
from helpers import make_loan

# Worked example (docs/worked-example.md), unrounded values.
WORKED = [
    # loan, facility rate, expected
    (make_loan(amount=10552, interest_rate="0.15", default_likelihood="0.02"), "0.06", "706.984"),
    (make_loan(amount=51157, interest_rate="0.15", default_likelihood="0.01"), "0.07", "3504.2545"),
    (make_loan(amount=74965, interest_rate="0.35", default_likelihood="0.06"), "0.06", "15667.685"),
]


@pytest.mark.parametrize(("loan", "rate", "expected"), WORKED)
def test_formula_matches_hand_computed_worked_example(loan: Loan, rate: str, expected: str) -> None:
    assert expected_yield(loan, Decimal(rate)) == Decimal(expected)


def test_zero_default_likelihood_is_plain_spread() -> None:
    loan = make_loan(amount=10_000, interest_rate="0.10", default_likelihood="0")
    assert expected_yield(loan, Decimal("0.04")) == Decimal("600")


def test_certain_default_loses_principal_and_funding_cost() -> None:
    loan = make_loan(amount=10_000, interest_rate="0.10", default_likelihood="1")
    # (1-1)*0.10*10000 - 1*10000 - 0.04*10000
    assert expected_yield(loan, Decimal("0.04")) == Decimal("-10400")


def test_decimal_math_is_exact_for_binary_unfriendly_inputs() -> None:
    # With floats 0.1 + 0.2 != 0.3; the Decimal pipeline must be exact.
    loan = make_loan(amount=10, interest_rate="0.1", default_likelihood="0.2")
    assert expected_yield(loan, Decimal("0.3")) == Decimal("0.8") * Decimal("0.1") * 10 - 2 - 3
    assert expected_yield(loan, Decimal("0.3")) == Decimal("-4.2")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0", 0),
        ("0.49", 0),
        ("0.5", 1),
        ("1.5", 2),
        ("2.5", 3),  # half up, not banker's rounding
        ("2.4999999", 2),
        ("16374.669", 16375),
        ("3504.2545", 3504),
    ],
)
def test_round_cents_positive(value: str, expected: int) -> None:
    assert round_cents(Decimal(value)) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("-0.4", 0),
        ("-0.5", -1),  # ROUND_HALF_UP in decimal rounds halves away from zero
        ("-1.5", -2),
        ("-2.5", -3),
        ("-2.4999", -2),
    ],
)
def test_round_cents_negative_halves_go_away_from_zero(value: str, expected: int) -> None:
    assert round_cents(Decimal(value)) == expected


def test_round_cents_never_yields_negative_zero() -> None:
    assert str(round_cents(Decimal("-0.1"))) == "0"
