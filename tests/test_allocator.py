from balance_the_loan_books.allocator import Allocator
from balance_the_loan_books.models import Loan
from helpers import make_facility, make_loan, make_row


def test_picks_cheapest_facility() -> None:
    facilities = [
        make_facility(id=1, interest_rate="0.08"),
        make_facility(id=2, interest_rate="0.05"),
        make_facility(id=3, interest_rate="0.07"),
    ]
    assert Allocator(facilities, []).assign(make_loan()) == 2


def test_equal_rates_break_ties_by_lowest_facility_id() -> None:
    facilities = [
        make_facility(id=7, interest_rate="0.05"),
        make_facility(id=3, interest_rate="0.050"),
        make_facility(id=5, interest_rate="0.05"),
    ]
    assert Allocator(facilities, []).assign(make_loan()) == 3


def test_skips_facility_without_enough_capacity() -> None:
    facilities = [
        make_facility(id=1, interest_rate="0.01", amount=999),
        make_facility(id=2, interest_rate="0.09", amount=5000),
    ]
    assert Allocator(facilities, []).assign(make_loan(amount=1000)) == 2


def test_loan_exactly_filling_capacity_fits() -> None:
    allocator = Allocator([make_facility(amount=1000)], [])
    assert allocator.assign(make_loan(id=1, amount=1000)) == 1
    assert allocator.assign(make_loan(id=2, amount=1)) is None


def test_capacity_decrements_across_loans() -> None:
    facilities = [
        make_facility(id=1, interest_rate="0.01", amount=2500),
        make_facility(id=2, interest_rate="0.02", amount=10_000),
    ]
    allocator = Allocator(facilities, [])
    got = [allocator.assign(make_loan(id=i, amount=1000)) for i in range(1, 5)]
    assert got == [1, 1, 2, 2]


def test_bank_wide_covenant_blocks_all_facilities_of_that_bank() -> None:
    facilities = [
        make_facility(id=1, bank_id=1, interest_rate="0.01"),
        make_facility(id=2, bank_id=1, interest_rate="0.02"),
        make_facility(id=3, bank_id=2, interest_rate="0.09"),
    ]
    rows = [make_row(bank_id=1, banned_state="VT")]
    allocator = Allocator(facilities, rows)
    assert allocator.assign(make_loan(state="VT")) == 3
    assert allocator.assign(make_loan(state="MO")) == 1


def test_facility_level_covenant_blocks_only_that_facility() -> None:
    facilities = [
        make_facility(id=1, bank_id=1, interest_rate="0.01"),
        make_facility(id=2, bank_id=1, interest_rate="0.02"),
    ]
    rows = [make_row(bank_id=1, facility_id=1, max_default_likelihood="0.03")]
    allocator = Allocator(facilities, rows)
    assert allocator.assign(make_loan(default_likelihood="0.04")) == 2
    assert allocator.assign(make_loan(default_likelihood="0.03")) == 1  # inclusive bound


def test_unfunded_when_nothing_fits() -> None:
    allocator = Allocator([make_facility(amount=100)], [make_row(bank_id=1, banned_state="VT")])
    assert allocator.assign(make_loan(amount=101, state="MO")) is None  # capacity
    assert allocator.assign(make_loan(amount=1, state="VT")) is None  # covenant


def test_no_facilities_means_everything_unfunded() -> None:
    allocator = Allocator([], [])
    assert allocator.assign(make_loan()) is None
    assert allocator.yields() == []


def test_unfunded_loan_does_not_consume_capacity_or_yield() -> None:
    allocator = Allocator([make_facility(amount=1000)], [])
    assert allocator.assign(make_loan(amount=2000)) is None
    assert allocator.yields() == [(1, 0)]
    assert allocator.assign(make_loan(amount=1000)) == 1


def test_yields_include_zero_rows_sorted_by_id_and_sum_loans() -> None:
    facilities = [
        make_facility(id=5, interest_rate="0.09"),
        make_facility(id=0, interest_rate="0.06"),
        make_facility(id=2, interest_rate="0.01"),
    ]
    allocator = Allocator(facilities, [])
    # Loans: 10000 @ 0.10, dl 0 -> yield vs facility 2 (0.01): 900 each.
    allocator.assign(make_loan(id=1, amount=10_000, interest_rate="0.10", default_likelihood="0"))
    allocator.assign(make_loan(id=2, amount=10_000, interest_rate="0.10", default_likelihood="0"))
    assert allocator.yields() == [(0, 0), (2, 1800), (5, 0)]


def test_yield_is_rounded_once_per_facility_not_per_loan() -> None:
    # Each loan yields 0.4 cents; per-loan rounding would give 0, per-facility gives 1 (1.2 -> 1).
    allocator = Allocator([make_facility(interest_rate="0")], [])
    for i in range(3):
        allocator.assign(make_loan(id=i, amount=4, interest_rate="0.1", default_likelihood="0"))
    assert allocator.yields() == [(1, 1)]


def _loans() -> list[Loan]:
    states = ["MO", "VT", "CA", "MO", "NY", "VT", "MO", "CA"]
    return [
        make_loan(
            id=i + 1,
            amount=1000 + 700 * i,
            state=states[i],
            default_likelihood=f"0.0{i % 7}",
        )
        for i in range(8)
    ]


def test_streaming_assignment_unaffected_by_later_loans() -> None:
    facilities = [
        make_facility(id=1, interest_rate="0.03", amount=6000),
        make_facility(id=2, interest_rate="0.05", amount=9000, bank_id=2),
        make_facility(id=3, interest_rate="0.05", amount=4000, bank_id=2),
    ]
    rows = [
        make_row(bank_id=1, banned_state="VT"),
        make_row(bank_id=2, facility_id=2, max_default_likelihood="0.04"),
    ]
    loans = _loans()

    def decisions(batch: list[Loan]) -> list[int | None]:
        allocator = Allocator(facilities, rows)
        return [allocator.assign(loan) for loan in batch]

    full = decisions(loans)
    for k in range(len(loans) + 1):
        assert decisions(loans[:k]) == full[:k]
