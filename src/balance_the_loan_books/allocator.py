"""The streaming assignment engine."""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from balance_the_loan_books.covenants import (
    DEFAULT_BUILDERS,
    Covenant,
    CovenantBuilder,
    covenants_for_facility,
)
from balance_the_loan_books.models import Cents, CovenantRow, Facility, FacilityId, Loan
from balance_the_loan_books.yields import expected_yield, round_cents


class TieBreak(StrEnum):
    """How facilities with equal interest rates are ordered; the CLI spells these as the values."""

    LOWEST_ID = "lowest-id"
    """Lowest facility id first. Independent of the row order of ``facilities.csv`` (default)."""
    FILE_ORDER = "file-order"
    """Order of the rows in ``facilities.csv``."""
    HIGHEST_ID = "highest-id"
    """Highest facility id first."""


_SORT_KEYS: dict[TieBreak, Callable[[Facility], tuple[Decimal, int]]] = {
    TieBreak.LOWEST_ID: lambda f: (f.interest_rate, f.id),
    TieBreak.HIGHEST_ID: lambda f: (f.interest_rate, -f.id),
    TieBreak.FILE_ORDER: lambda f: (f.interest_rate, 0),
}


@dataclass(slots=True)
class _FacilityState:
    facility: Facility
    covenants: tuple[Covenant, ...]
    remaining: Cents
    total_yield: Decimal = field(default_factory=Decimal)

    def accepts(self, loan: Loan) -> bool:
        return loan.amount <= self.remaining and all(c.allows(loan) for c in self.covenants)


class Allocator:
    """Assigns loans one at a time to the cheapest facility that can take them.

    Facilities are tried in ascending interest rate order; equal rates are ordered by
    ``tie_break`` (default :attr:`TieBreak.LOWEST_ID`, which does not depend on the order of
    ``facilities``). Covenant rows are turned into covenants by ``builders``. A loan only fits when
    ``loan.amount`` is at most the facility's remaining capacity.
    """

    def __init__(
        self,
        facilities: Iterable[Facility],
        covenant_rows: Sequence[CovenantRow],
        *,
        tie_break: TieBreak = TieBreak.LOWEST_ID,
        builders: Sequence[CovenantBuilder] = DEFAULT_BUILDERS,
    ):
        # sorted() is stable, so FILE_ORDER only needs the interest rate as its key.
        ordered = sorted(facilities, key=_SORT_KEYS[TieBreak(tie_break)])
        self._states = [
            _FacilityState(f, covenants_for_facility(f, covenant_rows, builders), f.amount)
            for f in ordered
        ]

    def assign(self, loan: Loan) -> FacilityId | None:
        """Assign ``loan`` and return its facility id, or ``None`` if no facility can take it."""
        for state in self._states:
            if state.accepts(loan):
                state.remaining -= loan.amount
                state.total_yield += expected_yield(loan, state.facility.interest_rate)
                return state.facility.id
        return None

    def yields(self) -> list[tuple[FacilityId, Cents]]:
        """Rounded total expected yield per facility, sorted by facility id.

        Every facility is listed, including those that funded nothing (yield 0).
        """
        return sorted((s.facility.id, round_cents(s.total_yield)) for s in self._states)
