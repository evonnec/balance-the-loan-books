"""The streaming assignment engine."""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from balance_the_loan_books.covenants import Covenant, covenants_for_facility
from balance_the_loan_books.models import Cents, CovenantRow, Facility, FacilityId, Loan
from balance_the_loan_books.yields import expected_yield, round_cents


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

    Facilities are tried in ascending ``(interest_rate, id)`` order, so equal rates are broken
    deterministically by lowest facility id. A loan only fits when ``loan.amount`` is at most the
    facility's remaining capacity.
    """

    def __init__(self, facilities: Iterable[Facility], covenant_rows: Sequence[CovenantRow]):
        ordered = sorted(facilities, key=lambda f: (f.interest_rate, f.id))
        self._states = [
            _FacilityState(f, covenants_for_facility(f, covenant_rows), f.amount) for f in ordered
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
