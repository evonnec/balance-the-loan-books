from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal
from typing import override

import pytest

from balance_the_loan_books import covenants
from balance_the_loan_books.allocator import Allocator
from balance_the_loan_books.covenants import (
    BannedState,
    Covenant,
    MaxDefaultLikelihood,
    build_covenants,
    covenants_for_facility,
)
from balance_the_loan_books.models import CovenantRow, Loan
from helpers import make_facility, make_loan, make_row


class TestMaxDefaultLikelihood:
    covenant = MaxDefaultLikelihood(Decimal("0.09"))

    def test_below_maximum_is_allowed(self) -> None:
        assert self.covenant.allows(make_loan(default_likelihood="0.08"))

    def test_exactly_maximum_is_allowed(self) -> None:
        assert self.covenant.allows(make_loan(default_likelihood="0.09"))

    def test_equal_value_with_different_exponent_is_allowed(self) -> None:
        assert self.covenant.allows(make_loan(default_likelihood="0.090"))

    def test_just_above_maximum_is_rejected(self) -> None:
        assert not self.covenant.allows(make_loan(default_likelihood="0.0900001"))

    def test_zero_maximum_only_allows_zero(self) -> None:
        zero = MaxDefaultLikelihood(Decimal(0))
        assert zero.allows(make_loan(default_likelihood="0"))
        assert not zero.allows(make_loan(default_likelihood="0.01"))


class TestBannedState:
    covenant = BannedState("MT")

    def test_banned_state_is_rejected(self) -> None:
        assert not self.covenant.allows(make_loan(state="MT"))

    def test_other_state_is_allowed(self) -> None:
        assert self.covenant.allows(make_loan(state="MO"))

    def test_state_match_is_case_sensitive(self) -> None:
        # Documents current behaviour: "mt" is not "MT". Inputs are expected to use the
        # upper-case two-letter postal code on both sides.
        assert self.covenant.allows(make_loan(state="mt"))
        assert not BannedState("mt").allows(make_loan(state="mt"))

    def test_covenant_is_abstract(self) -> None:
        with pytest.raises(TypeError):
            Covenant()  # type: ignore[abstract]


class TestBuildCovenants:
    def test_row_with_no_restrictions_builds_nothing(self) -> None:
        assert build_covenants(make_row()) == ()

    def test_max_default_only(self) -> None:
        row = make_row(max_default_likelihood="0.05")
        assert build_covenants(row) == (MaxDefaultLikelihood(Decimal("0.05")),)

    def test_banned_state_only(self) -> None:
        assert build_covenants(make_row(banned_state="VT")) == (BannedState("VT"),)

    def test_row_with_both_fields_is_two_covenants(self) -> None:
        row = make_row(max_default_likelihood="0.05", banned_state="VT")
        assert build_covenants(row) == (MaxDefaultLikelihood(Decimal("0.05")), BannedState("VT"))


class TestCovenantsForFacility:
    def test_facility_level_row_applies_only_to_that_facility(self) -> None:
        rows = [make_row(bank_id=1, facility_id=2, banned_state="VT")]
        assert covenants_for_facility(make_facility(id=2, bank_id=1), rows) == (BannedState("VT"),)
        assert covenants_for_facility(make_facility(id=3, bank_id=1), rows) == ()

    def test_bank_level_row_applies_to_every_facility_of_the_bank(self) -> None:
        rows = [make_row(bank_id=1, banned_state="VT")]
        for facility_id in (2, 3):
            facility = make_facility(id=facility_id, bank_id=1)
            assert covenants_for_facility(facility, rows) == (BannedState("VT"),)

    def test_other_banks_rows_are_ignored(self) -> None:
        rows = [make_row(bank_id=2, banned_state="VT")]
        assert covenants_for_facility(make_facility(id=1, bank_id=1), rows) == ()

    def test_facility_level_row_ignores_bank_id_match_alone(self) -> None:
        # The facility id decides for facility-level rows, whatever the row's bank_id says.
        rows = [make_row(bank_id=1, facility_id=9, banned_state="VT")]
        assert covenants_for_facility(make_facility(id=2, bank_id=1), rows) == ()

    def test_bank_and_facility_rows_accumulate_in_row_order(self) -> None:
        rows = [
            make_row(bank_id=1, max_default_likelihood="0.10"),
            make_row(bank_id=1, facility_id=1, banned_state="CA"),
            make_row(bank_id=2, banned_state="NY"),
        ]
        assert covenants_for_facility(make_facility(id=1, bank_id=1), rows) == (
            MaxDefaultLikelihood(Decimal("0.10")),
            BannedState("CA"),
        )


@dataclass(frozen=True, slots=True)
class MinAmount(Covenant):
    """Test-only covenant, used to show the registry is the single extension point."""

    minimum: int

    @override
    def allows(self, loan: Loan) -> bool:
        return loan.amount >= self.minimum


class TestExtensibility:
    @pytest.fixture
    def with_min_amount(self, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
        def build(row: CovenantRow) -> Covenant | None:
            # Piggy-back on banned_state text like "MIN:500" to avoid changing CovenantRow.
            if row.banned_state is not None and row.banned_state.startswith("MIN:"):
                return MinAmount(int(row.banned_state.removeprefix("MIN:")))
            return None

        monkeypatch.setattr(covenants, "COVENANT_BUILDERS", [*covenants.COVENANT_BUILDERS, build])
        yield

    def test_custom_builder_is_used_by_build_covenants(self, with_min_amount: None) -> None:
        row = make_row(banned_state="MIN:500")
        assert MinAmount(500) in build_covenants(row)

    def test_allocator_honours_custom_covenant(self, with_min_amount: None) -> None:
        facilities = [
            make_facility(id=1, interest_rate="0.01"),
            make_facility(id=2, interest_rate="0.02"),
        ]
        rows = [make_row(bank_id=1, facility_id=1, banned_state="MIN:500")]
        allocator = Allocator(facilities, rows)

        assert allocator.assign(make_loan(id=1, amount=499)) == 2  # too small for facility 1
        assert allocator.assign(make_loan(id=2, amount=500)) == 1
