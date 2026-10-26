"""Immutable domain types shared by the rest of the package.

Rates and likelihoods are :class:`decimal.Decimal` values parsed from the CSV text so that no
binary floating-point error enters the money math. Amounts are whole cents held as ``int``.
"""

from dataclasses import dataclass
from decimal import Decimal

type Cents = int
"""A whole number of cents."""

type FacilityId = int
type LoanId = int
type BankId = int


@dataclass(frozen=True, slots=True, kw_only=True)
class Loan:
    id: LoanId
    interest_rate: Decimal
    amount: Cents
    default_likelihood: Decimal
    state: str


@dataclass(frozen=True, slots=True, kw_only=True)
class Facility:
    id: FacilityId
    bank_id: BankId
    interest_rate: Decimal
    amount: Cents
    """Total capacity of the facility."""


@dataclass(frozen=True, slots=True, kw_only=True)
class Bank:
    id: BankId
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CovenantRow:
    """One row of ``covenants.csv``, before it is turned into concrete covenants.

    ``facility_id`` ``None`` means the row applies to every facility of ``bank_id``. A row may
    carry several restrictions (for example both a maximum default likelihood and a banned
    state); each one becomes its own covenant.
    """

    bank_id: BankId
    facility_id: FacilityId | None = None
    max_default_likelihood: Decimal | None = None
    banned_state: str | None = None
