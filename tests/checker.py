"""An independent reference implementation and validator for the loan assignment problem.

This module imports nothing from ``balance_the_loan_books``. It uses only the standard library
(``csv`` for parsing, ``fractions.Fraction`` for exact arithmetic) and restates the problem from
the README: parsing, covenant logic, expected yield and rounding are all written out again here,
so a bug shared with the package cannot hide behind a shared helper.

Two entry points:

* :func:`expected` computes the assignments and yields the problem statement implies for an input
  directory, under a lowest-facility-id tie-break among equal rates.
* :func:`validate` audits an arbitrary ``assignments.csv`` / ``yields.csv`` pair against an input
  directory and returns a list of human-readable violations (empty means the output is correct).
  It accepts any tie-break among equal-rate facilities by default.

Both take the CSV *text* as found on disk: ``float`` is never used.
"""

import csv
from collections.abc import Iterator
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

ZERO = Fraction(0)
ONE = Fraction(1)
HALF = Fraction(1, 2)


@dataclass(frozen=True)
class Fac:
    id: int
    bank: int
    rate: Fraction
    capacity: int


@dataclass(frozen=True)
class Cov:
    bank: int
    facility: int | None
    max_dl: Fraction | None
    banned: str | None


@dataclass(frozen=True)
class Ln:
    id: int
    rate: Fraction
    amount: int
    dl: Fraction
    state: str


@dataclass(frozen=True)
class Data:
    facilities: list[Fac]
    covenants: list[Cov]
    loans: list[Ln]


type Assignments = list[tuple[int, int | None]]
type Yields = list[tuple[int, int]]


def _table(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _frac(text: str) -> Fraction:
    return Fraction(text.strip())


def _whole(text: str) -> int:
    value = _frac(text)
    if value.denominator != 1:
        raise ValueError(f"not a whole number: {text!r}")
    return int(value)


def load(input_dir: Path) -> Data:
    """Parse the input CSVs by header name."""
    facilities = [
        Fac(
            id=int(r["id"]),
            bank=int(r["bank_id"]),
            rate=_frac(r["interest_rate"]),
            capacity=_whole(r["amount"]),
        )
        for r in _table(input_dir / "facilities.csv")
    ]
    covenants = [
        Cov(
            bank=int(r["bank_id"]),
            facility=int(r["facility_id"]) if r["facility_id"].strip() else None,
            max_dl=_frac(r["max_default_likelihood"])
            if r["max_default_likelihood"].strip()
            else None,
            banned=r["banned_state"].strip() or None,
        )
        for r in _table(input_dir / "covenants.csv")
    ]
    loans = [
        Ln(
            id=int(r["id"]),
            rate=_frac(r["interest_rate"]),
            amount=_whole(r["amount"]),
            dl=_frac(r["default_likelihood"]),
            state=r["state"].strip(),
        )
        for r in _table(input_dir / "loans.csv")
    ]
    return Data(facilities, covenants, loans)


def covenant_ok(fac: Fac, loan: Ln, covenants: list[Cov]) -> bool:
    """True when every covenant applying to ``fac`` permits ``loan``.

    A row with a facility id binds that facility; a row without one binds every facility of the
    row's bank. A maximum default likelihood is inclusive; a banned state is an exact match.
    """
    for cov in covenants:
        applies = cov.bank == fac.bank if cov.facility is None else cov.facility == fac.id
        if not applies:
            continue
        if cov.max_dl is not None and loan.dl > cov.max_dl:
            return False
        if cov.banned is not None and loan.state == cov.banned:
            return False
    return True


def loan_yield(loan: Ln, facility_rate: Fraction) -> Fraction:
    """``(1 - dl) * loan_rate * amount - dl * amount - facility_rate * amount``, exactly."""
    return (
        (ONE - loan.dl) * loan.rate * loan.amount
        - loan.dl * loan.amount
        - (facility_rate * loan.amount)
    )


def round_half_up(value: Fraction) -> int:
    """Round to a whole number, halves away from zero."""
    magnitude = abs(value)
    rounded = int(magnitude // 1 + (1 if magnitude % 1 >= HALF else 0))
    return -rounded if value < 0 else rounded


def _feasible(data: Data, loan: Ln, remaining: dict[int, int]) -> list[Fac]:
    return [
        f
        for f in data.facilities
        if loan.amount <= remaining[f.id] and covenant_ok(f, loan, data.covenants)
    ]


def solve(data: Data) -> tuple[Assignments, dict[int, Fraction]]:
    """Greedy cheapest-first with lowest-id tie-break; returns assignments and exact sums."""
    remaining = {f.id: f.capacity for f in data.facilities}
    totals = {f.id: ZERO for f in data.facilities}
    assignments: Assignments = []
    for loan in data.loans:
        feasible = _feasible(data, loan, remaining)
        if not feasible:
            assignments.append((loan.id, None))
            continue
        best = min(feasible, key=lambda f: (f.rate, f.id))
        remaining[best.id] -= loan.amount
        totals[best.id] += loan_yield(loan, best.rate)
        assignments.append((loan.id, best.id))
    return assignments, totals


def expected(input_dir: Path) -> tuple[Assignments, Yields]:
    """The assignments and per-facility rounded yields (sorted by id) for ``input_dir``."""
    assignments, totals = solve(load(input_dir))
    return assignments, sorted((fid, round_half_up(total)) for fid, total in totals.items())


def render(assignments: Assignments, yields: Yields) -> tuple[str, str]:
    """The exact text of ``assignments.csv`` and ``yields.csv`` (``\\n`` line endings)."""
    a = "loan_id,facility_id\n" + "".join(f"{i},{'' if f is None else f}\n" for i, f in assignments)
    y = "facility_id,expected_yield\n" + "".join(f"{i},{v}\n" for i, v in yields)
    return a, y


def expected_text(input_dir: Path) -> tuple[str, str]:
    """:func:`render` applied to :func:`expected`."""
    return render(*expected(input_dir))


def _read_pairs(path: Path, header: list[str]) -> Iterator[tuple[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = csv.reader(handle)
        first = next(rows, None)
        if first != header:
            raise ValueError(f"{path.name}: header is {first!r}, expected {header!r}")
        for row in rows:
            if len(row) != 2:
                raise ValueError(f"{path.name}: row {row!r} does not have two fields")
            yield row[0], row[1]


def validate(
    input_dir: Path,
    assignments_path: Path,
    yields_path: Path,
    *,
    lowest_id_tie_break: bool = False,
) -> list[str]:
    """Audit an output pair; return every violation found (empty list means valid).

    Checks: one row per loan in input order; capacity never exceeded; every funded loan satisfies
    all covenants; each funded loan went to a cheapest feasible facility at its time (the lowest
    id among those when ``lowest_id_tie_break`` is set); unfunded loans had no feasible facility;
    yields list every facility once, sorted by id, and equal the exact per-facility sum rounded
    half away from zero.
    """
    data = load(input_dir)
    problems: list[str] = []
    try:
        rows = list(_read_pairs(assignments_path, ["loan_id", "facility_id"]))
        yield_rows = list(_read_pairs(yields_path, ["facility_id", "expected_yield"]))
    except ValueError as error:
        return [str(error)]

    if [r[0] for r in rows] != [str(loan.id) for loan in data.loans]:
        return ["assignments do not list every loan once, in input order"]

    by_id = {f.id: f for f in data.facilities}
    remaining = {f.id: f.capacity for f in data.facilities}
    totals = {f.id: ZERO for f in data.facilities}
    for loan, (_, chosen_text) in zip(data.loans, rows, strict=True):
        feasible = _feasible(data, loan, remaining)
        if chosen_text == "":
            if feasible:
                problems.append(
                    f"loan {loan.id} unfunded but facilities {[f.id for f in feasible]} could"
                    " take it"
                )
            continue
        chosen = by_id.get(int(chosen_text))
        if chosen is None:
            problems.append(f"loan {loan.id} assigned to unknown facility {chosen_text}")
            continue
        if loan.amount > remaining[chosen.id]:
            problems.append(f"loan {loan.id} exceeds remaining capacity of facility {chosen.id}")
        if not covenant_ok(chosen, loan, data.covenants):
            problems.append(f"loan {loan.id} violates a covenant of facility {chosen.id}")
        if chosen in feasible:
            key = (lambda f: (f.rate, f.id)) if lowest_id_tie_break else (lambda f: f.rate)
            if key(chosen) != min(key(f) for f in feasible):
                problems.append(f"loan {loan.id} did not go to the cheapest feasible facility")
        remaining[chosen.id] -= loan.amount
        totals[chosen.id] += loan_yield(loan, chosen.rate)

    for fid, rem in remaining.items():
        if rem < 0:
            problems.append(f"facility {fid} capacity exceeded by {-rem}")

    expected_yields = [
        (str(fid), str(round_half_up(total))) for fid, total in sorted(totals.items())
    ]
    if yield_rows != expected_yields:
        problems.append(f"yields {yield_rows} != expected {expected_yields}")
    return problems
