"""Factories and file helpers shared by the tests (importable as ``helpers``)."""

from collections.abc import Iterable, Sequence
from decimal import Decimal
from pathlib import Path

from balance_the_loan_books.models import CovenantRow, Facility, Loan

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA = REPO_ROOT / "data"

# Column orders exactly as they appear in the bundled data files.
BANKS_HEADER = ("id", "name")
FACILITIES_HEADER = ("amount", "interest_rate", "id", "bank_id")
COVENANTS_HEADER = ("facility_id", "max_default_likelihood", "bank_id", "banned_state")
LOANS_HEADER = ("interest_rate", "amount", "id", "default_likelihood", "state")

type Cell = str | int | float | Decimal | None
type Table = Iterable[Sequence[Cell]]


def make_loan(
    *,
    id: int = 1,
    interest_rate: str = "0.15",
    amount: int = 1000,
    default_likelihood: str = "0.02",
    state: str = "MO",
) -> Loan:
    """Build a loan; rates are given as strings so they stay exact."""
    return Loan(
        id=id,
        interest_rate=Decimal(interest_rate),
        amount=amount,
        default_likelihood=Decimal(default_likelihood),
        state=state,
    )


def make_facility(
    *,
    id: int = 1,
    bank_id: int = 1,
    interest_rate: str = "0.05",
    amount: int = 1_000_000,
) -> Facility:
    return Facility(id=id, bank_id=bank_id, interest_rate=Decimal(interest_rate), amount=amount)


def make_row(
    *,
    bank_id: int = 1,
    facility_id: int | None = None,
    max_default_likelihood: str | None = None,
    banned_state: str | None = None,
) -> CovenantRow:
    return CovenantRow(
        bank_id=bank_id,
        facility_id=facility_id,
        max_default_likelihood=(
            None if max_default_likelihood is None else Decimal(max_default_likelihood)
        ),
        banned_state=banned_state,
    )


def _csv_text(header: Sequence[str], rows: Table) -> str:
    lines = [",".join(header)]
    lines.extend(",".join("" if cell is None else str(cell) for cell in row) for row in rows)
    return "\n".join(lines) + "\n"


def write_csv(path: Path, header: Sequence[str], rows: Table) -> Path:
    """Write a CSV with ``\\n`` line endings regardless of platform."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_csv_text(header, rows).encode("utf-8"))
    return path


def write_dataset(
    root: Path,
    *,
    banks: Table = ((1, "Test Bank"),),
    facilities: Table = ((1_000_000, "0.05", 1, 1),),
    covenants: Table = (),
    loans: Table = (),
) -> Path:
    """Write the four input CSVs under ``root/input`` (real column orders); return that dir.

    Rows are positional tuples in the real column order: see the ``*_HEADER`` constants.
    """
    input_dir = root / "input"
    write_csv(input_dir / "banks.csv", BANKS_HEADER, banks)
    write_csv(input_dir / "facilities.csv", FACILITIES_HEADER, facilities)
    write_csv(input_dir / "covenants.csv", COVENANTS_HEADER, covenants)
    write_csv(input_dir / "loans.csv", LOANS_HEADER, loans)
    return input_dir


def read_text(path: Path) -> str:
    """Read a file as text without newline translation, then normalise CRLF to LF."""
    return path.read_bytes().decode("utf-8").replace("\r\n", "\n")
