"""Property tests: the allocator is checked against a brute-force oracle on random datasets."""

from dataclasses import dataclass
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from balance_the_loan_books.allocator import Allocator
from balance_the_loan_books.models import CovenantRow, Facility, Loan
from balance_the_loan_books.yields import expected_yield, round_cents

STATES = ["AA", "BB", "CC"]
LIKELIHOODS = st.sampled_from([Decimal(s) for s in ("0", "0.01", "0.05", "0.09", "0.1", "0.5")])
RATES = st.sampled_from([Decimal(s) for s in ("0.01", "0.02", "0.02", "0.05", "0.1", "0.35")])


@dataclass(frozen=True)
class Scenario:
    facilities: list[Facility]
    rows: list[CovenantRow]
    loans: list[Loan]


@st.composite
def scenarios(draw: st.DrawFn) -> Scenario:
    n_banks = draw(st.integers(1, 3))
    ids = draw(st.lists(st.integers(0, 12), min_size=1, max_size=5, unique=True))
    facilities = [
        Facility(
            id=fid,
            bank_id=draw(st.integers(1, n_banks)),
            interest_rate=draw(RATES),
            amount=draw(st.integers(0, 3000)),
        )
        for fid in ids
    ]
    rows = draw(
        st.lists(
            st.builds(
                CovenantRow,
                bank_id=st.integers(1, n_banks),
                facility_id=st.one_of(st.none(), st.sampled_from(ids)),
                max_default_likelihood=st.one_of(st.none(), LIKELIHOODS),
                banned_state=st.one_of(st.none(), st.sampled_from(STATES)),
            ),
            max_size=6,
        )
    )
    loans = [
        Loan(
            id=i,
            interest_rate=draw(RATES),
            amount=draw(st.integers(1, 1500)),
            default_likelihood=draw(LIKELIHOODS),
            state=draw(st.sampled_from(STATES)),
        )
        for i in range(1, draw(st.integers(0, 12)) + 1)
    ]
    return Scenario(facilities, rows, loans)


def _permits(facility: Facility, rows: list[CovenantRow], loan: Loan) -> bool:
    """Independent re-statement of the covenant rules, straight from the problem text."""
    for row in rows:
        applies = (
            row.bank_id == facility.bank_id
            if row.facility_id is None
            else row.facility_id == facility.id
        )
        if not applies:
            continue
        if (
            row.max_default_likelihood is not None
            and loan.default_likelihood > row.max_default_likelihood
        ):
            return False
        if row.banned_state is not None and loan.state == row.banned_state:
            return False
    return True


@given(scenarios())
def test_allocator_matches_brute_force_oracle(scenario: Scenario) -> None:
    allocator = Allocator(scenario.facilities, scenario.rows)
    remaining = {f.id: f.amount for f in scenario.facilities}
    by_id = {f.id: f for f in scenario.facilities}
    loan_yields: dict[int, Decimal] = {f.id: Decimal(0) for f in scenario.facilities}

    for loan in scenario.loans:
        feasible = [
            f
            for f in scenario.facilities
            if loan.amount <= remaining[f.id] and _permits(f, scenario.rows, loan)
        ]
        chosen = allocator.assign(loan)

        if not feasible:
            assert chosen is None, "unfunded loans must truly have no feasible facility"
            continue

        assert chosen is not None
        cheapest = min(feasible, key=lambda f: (f.interest_rate, f.id))
        assert chosen == cheapest.id, "loan must go to the cheapest feasible facility"
        facility = by_id[chosen]
        assert _permits(facility, scenario.rows, loan), "funded loan violates a covenant"
        remaining[chosen] -= loan.amount
        assert remaining[chosen] >= 0, "facility exceeded capacity"
        loan_yields[chosen] += expected_yield(loan, facility.interest_rate)

    assert allocator.yields() == sorted(
        (fid, round_cents(total)) for fid, total in loan_yields.items()
    )


@given(scenarios())
def test_facility_yields_sum_to_loan_yields(scenario: Scenario) -> None:
    allocator = Allocator(scenario.facilities, scenario.rows)
    by_id = {f.id: f for f in scenario.facilities}
    per_loan = Decimal(0)
    for loan in scenario.loans:
        chosen = allocator.assign(loan)
        if chosen is not None:
            per_loan += expected_yield(loan, by_id[chosen].interest_rate)

    total = sum(cents for _, cents in allocator.yields())
    # Rounding happens once per facility, so the integer total can differ from the exact
    # per-loan sum by at most half a cent per facility.
    assert abs(Decimal(total) - per_loan) <= Decimal("0.5") * len(scenario.facilities)
    assert len(allocator.yields()) == len(scenario.facilities)


@given(scenarios(), st.data())
def test_prefix_decisions_are_stable(scenario: Scenario, data: st.DataObject) -> None:
    k = data.draw(st.integers(0, len(scenario.loans)))

    def run(loans: list[Loan]) -> list[int | None]:
        allocator = Allocator(scenario.facilities, scenario.rows)
        return [allocator.assign(loan) for loan in loans]

    assert run(scenario.loans[:k]) == run(scenario.loans)[:k]
