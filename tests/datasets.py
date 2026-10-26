"""Hypothesis strategies that draw whole datasets as CSV-ready rows.

Generated data always satisfies the *agreed* input rules (positive loan amounts, likelihoods in
[0, 1], upper-case two-letter states, facility-level covenants naming the facility's own bank,
every covenant row carrying a restriction), so the property tests stay valid when input
validation is tightened. Zero-capacity facilities, equal rates and exhausted capacity are drawn
deliberately.
"""

from dataclasses import dataclass, field

from hypothesis import strategies as st

from helpers import Cell

STATES = ("AA", "BB", "CC")
LIKELIHOODS = ("0", "0.01", "0.05", "0.09", "0.1", "0.5", "1")
RATES = ("0", "0.01", "0.02", "0.02", "0.05", "0.1", "0.35")
LOAN_RATES = ("0.01", "0.1", "0.15", "0.333", "0.5")

type Row = tuple[Cell, ...]


@dataclass(frozen=True)
class Dataset:
    """Rows in the real column orders of the bundled files (see ``helpers``)."""

    banks: list[Row]
    facilities: list[Row]
    covenants: list[Row]
    loans: list[Row] = field(default_factory=list)


@st.composite
def datasets(draw: st.DrawFn, *, max_loans: int = 15) -> Dataset:
    n_banks = draw(st.integers(1, 3))
    banks: list[Row] = [(b, f"Bank {b}") for b in range(1, n_banks + 1)]
    ids = draw(st.lists(st.integers(0, 12), min_size=1, max_size=5, unique=True))
    fac_bank = {fid: draw(st.integers(1, n_banks)) for fid in ids}
    capacity = st.one_of(st.just(0), st.integers(0, 3000))
    facilities: list[Row] = [
        (
            f"{draw(capacity)}{draw(st.sampled_from(['', '.0']))}",
            draw(st.sampled_from(RATES)),
            fid,
            fac_bank[fid],
        )
        for fid in ids
    ]

    covenants: list[Row] = []
    for _ in range(draw(st.integers(0, 6))):
        max_dl = draw(st.one_of(st.none(), st.sampled_from(LIKELIHOODS)))
        banned = draw(st.one_of(st.none(), st.sampled_from(STATES)))
        if max_dl is None and banned is None:
            banned = draw(st.sampled_from(STATES))
        facility_level = draw(st.booleans())
        if facility_level:
            fid = draw(st.sampled_from(ids))
            covenants.append((fid, max_dl, fac_bank[fid], banned))
        else:
            covenants.append((None, max_dl, draw(st.integers(1, n_banks)), banned))

    loans: list[Row] = [
        (
            draw(st.sampled_from(LOAN_RATES)),
            draw(st.integers(1, 1500)),
            i,
            draw(st.sampled_from(LIKELIHOODS)),
            draw(st.sampled_from(STATES)),
        )
        for i in range(1, draw(st.integers(0, max_loans)) + 1)
    ]
    return Dataset(banks, facilities, covenants, loans)
