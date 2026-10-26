"""Wire the readers, the allocator and the writers together."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from balance_the_loan_books.allocator import Allocator
from balance_the_loan_books.io import (
    InputError,
    iter_loans,
    read_banks,
    read_covenants,
    read_facilities,
    write_assignments,
    write_yields,
)
from balance_the_loan_books.models import CovenantRow, Facility, FacilityId, LoanId


@dataclass(frozen=True, slots=True, kw_only=True)
class RunSummary:
    loans: int
    funded: int
    facilities: int


def validate_references(
    facilities: list[Facility], rows: list[CovenantRow], bank_ids: set[int]
) -> None:
    """Raise :class:`InputError` for duplicate facility ids or dangling references."""
    ids: set[int] = set()
    for facility in facilities:
        if facility.id in ids:
            raise InputError(f"duplicate facility id: {facility.id}")
        ids.add(facility.id)
        if facility.bank_id not in bank_ids:
            raise InputError(f"facility {facility.id} references unknown bank {facility.bank_id}")
    for row in rows:
        if row.facility_id is not None and row.facility_id not in ids:
            raise InputError(f"covenant references unknown facility {row.facility_id}")
        if row.bank_id not in bank_ids:
            raise InputError(f"covenant references unknown bank {row.bank_id}")


def run(input_dir: Path, output_dir: Path) -> RunSummary:
    """Read ``input_dir/*.csv`` and write ``output_dir/assignments.csv`` and ``yields.csv``.

    Loans are read lazily and each assignment is written as soon as it is decided; yields are
    written once the stream ends. Both files are replaced atomically.
    """
    banks = read_banks(input_dir / "banks.csv")
    facilities = read_facilities(input_dir / "facilities.csv")
    covenant_rows = read_covenants(input_dir / "covenants.csv")
    validate_references(facilities, covenant_rows, {b.id for b in banks})
    allocator = Allocator(facilities, covenant_rows)

    loans = 0
    funded = 0

    def decisions() -> Iterator[tuple[LoanId, FacilityId | None]]:
        nonlocal loans, funded
        for loan in iter_loans(input_dir / "loans.csv"):
            facility_id = allocator.assign(loan)
            loans += 1
            funded += facility_id is not None
            yield loan.id, facility_id

    write_assignments(output_dir / "assignments.csv", decisions())
    write_yields(output_dir / "yields.csv", allocator.yields())
    return RunSummary(loans=loans, funded=funded, facilities=len(facilities))
