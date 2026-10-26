"""Assign streamed loans to the cheapest eligible debt facility."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("balance-the-loan-books")
except PackageNotFoundError:  # running from a source tree that is not installed
    __version__ = "0.0.0+unknown"

from balance_the_loan_books.allocator import Allocator
from balance_the_loan_books.covenants import (
    BannedState,
    Covenant,
    MaxDefaultLikelihood,
    build_covenants,
    covenants_for_facility,
)
from balance_the_loan_books.io import InputError
from balance_the_loan_books.models import Bank, CovenantRow, Facility, Loan
from balance_the_loan_books.pipeline import RunSummary, run
from balance_the_loan_books.yields import expected_yield, round_cents

__all__ = [
    "Allocator",
    "Bank",
    "BannedState",
    "Covenant",
    "CovenantRow",
    "Facility",
    "InputError",
    "Loan",
    "MaxDefaultLikelihood",
    "RunSummary",
    "__version__",
    "build_covenants",
    "covenants_for_facility",
    "expected_yield",
    "round_cents",
    "run",
]
