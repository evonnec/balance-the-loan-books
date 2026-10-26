"""Covenants: restrictions on which loans a facility may fund.

To add a new kind of covenant, subclass :class:`Covenant`, write a builder function that turns a
:class:`~balance_the_loan_books.models.CovenantRow` into an instance (or ``None`` when the row
does not use that kind), and pass it with the defaults as ``builders=(*DEFAULT_BUILDERS, builder)``
to :class:`~balance_the_loan_books.allocator.Allocator` or
:func:`~balance_the_loan_books.pipeline.run`. There is no global registry to mutate.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import override

from balance_the_loan_books.models import CovenantRow, Facility, Loan


class Covenant(ABC):
    """A single restriction on the loans a facility may fund."""

    @abstractmethod
    def allows(self, loan: Loan) -> bool:
        """Return ``True`` if the covenant permits funding ``loan``."""


@dataclass(frozen=True, slots=True)
class MaxDefaultLikelihood(Covenant):
    """Loans whose default likelihood is above ``maximum`` are not allowed.

    The bound is inclusive: a loan with exactly ``maximum`` is allowed.
    """

    maximum: Decimal

    @override
    def allows(self, loan: Loan) -> bool:
        return loan.default_likelihood <= self.maximum


@dataclass(frozen=True, slots=True)
class BannedState(Covenant):
    """Loans originating in ``state`` are not allowed."""

    state: str

    @override
    def allows(self, loan: Loan) -> bool:
        return loan.state != self.state


type CovenantBuilder = Callable[[CovenantRow], Covenant | None]


def _max_default_likelihood(row: CovenantRow) -> Covenant | None:
    if row.max_default_likelihood is None:
        return None
    return MaxDefaultLikelihood(row.max_default_likelihood)


def _banned_state(row: CovenantRow) -> Covenant | None:
    if row.banned_state is None:
        return None
    return BannedState(row.banned_state)


DEFAULT_BUILDERS: tuple[CovenantBuilder, ...] = (_max_default_likelihood, _banned_state)
"""The built-in builders, consulted for every covenant row unless others are injected."""

COVENANT_BUILDERS = DEFAULT_BUILDERS
"""Backward-compatible alias of :data:`DEFAULT_BUILDERS` (an immutable tuple)."""


def build_covenants(
    row: CovenantRow, builders: Iterable[CovenantBuilder] = DEFAULT_BUILDERS
) -> tuple[Covenant, ...]:
    """Turn one covenant row into its covenants (a row may hold more than one)."""
    built = (builder(row) for builder in builders)
    return tuple(covenant for covenant in built if covenant is not None)


def covenants_for_facility(
    facility: Facility,
    rows: Iterable[CovenantRow],
    builders: Iterable[CovenantBuilder] = DEFAULT_BUILDERS,
) -> tuple[Covenant, ...]:
    """Collect every covenant that applies to ``facility``.

    A row applies when its ``facility_id`` equals the facility's id, or, when the row has no
    ``facility_id``, when its ``bank_id`` equals the facility's bank.
    """
    applicable: list[Covenant] = []
    for row in rows:
        if row.facility_id is None:
            applies = row.bank_id == facility.bank_id
        else:
            applies = row.facility_id == facility.id
        if applies:
            applicable.extend(build_covenants(row, builders))
    return tuple(applicable)
