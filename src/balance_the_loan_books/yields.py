"""Expected-yield arithmetic.

All math is done in :class:`~decimal.Decimal`; the only rounding happens in :func:`round_cents`,
which rounds half away from zero (``ROUND_HALF_UP``) to a whole number of cents.
"""

from decimal import ROUND_HALF_UP, Decimal

from balance_the_loan_books.models import Cents, Loan

_ONE = Decimal(1)


def expected_yield(loan: Loan, facility_interest_rate: Decimal) -> Decimal:
    """Expected yield, in (fractional) cents, of funding ``loan`` from a facility.

    ``(1 - dl) * loan_rate * amount - dl * amount - facility_rate * amount``
    """
    amount = Decimal(loan.amount)
    dl = loan.default_likelihood
    return (_ONE - dl) * loan.interest_rate * amount - dl * amount - facility_interest_rate * amount


def round_cents(value: Decimal) -> Cents:
    """Round to the nearest whole cent, halves away from zero."""
    return int(value.quantize(_ONE, rounding=ROUND_HALF_UP))
