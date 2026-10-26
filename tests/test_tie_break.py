"""The equal-rate tie-break policy: unit behaviour, CLI flag and effect on the large data set."""

import csv
from pathlib import Path

import pytest

from balance_the_loan_books.allocator import Allocator, TieBreak
from balance_the_loan_books.cli import main
from balance_the_loan_books.pipeline import run
from helpers import DATA, make_facility, make_loan, read_text, write_dataset

EQUAL_RATES = [
    make_facility(id=7, interest_rate="0.05"),
    make_facility(id=3, interest_rate="0.050"),
    make_facility(id=5, interest_rate="0.05"),
]


def _first_choice(facilities: list, tie_break: TieBreak | None) -> int | None:  # type: ignore[type-arg]
    if tie_break is None:
        return Allocator(facilities, []).assign(make_loan())
    return Allocator(facilities, [], tie_break=tie_break).assign(make_loan())


def test_default_is_lowest_id() -> None:
    assert _first_choice(EQUAL_RATES, None) == 3


@pytest.mark.parametrize(
    ("tie_break", "expected"),
    [(TieBreak.LOWEST_ID, 3), (TieBreak.FILE_ORDER, 7), (TieBreak.HIGHEST_ID, 7)],
)
def test_each_policy_picks_its_facility(tie_break: TieBreak, expected: int) -> None:
    assert _first_choice(EQUAL_RATES, tie_break) == expected


def test_file_order_follows_the_rows() -> None:
    assert _first_choice([EQUAL_RATES[1], EQUAL_RATES[2], EQUAL_RATES[0]], TieBreak.FILE_ORDER) == 3
    assert _first_choice([EQUAL_RATES[2], EQUAL_RATES[0], EQUAL_RATES[1]], TieBreak.FILE_ORDER) == 5


def test_lowest_and_highest_id_ignore_row_order() -> None:
    reversed_rows = EQUAL_RATES[::-1]
    assert _first_choice(reversed_rows, TieBreak.LOWEST_ID) == 3
    assert _first_choice(reversed_rows, TieBreak.HIGHEST_ID) == 7


def test_rate_still_outranks_every_tie_break() -> None:
    facilities = [
        make_facility(id=1, interest_rate="0.09"),
        make_facility(id=2, interest_rate="0.01"),
    ]
    for tie_break in TieBreak:
        assert _first_choice(facilities, tie_break) == 2


def test_plain_string_value_is_accepted() -> None:
    assert Allocator(EQUAL_RATES, [], tie_break="highest-id").assign(make_loan()) == 7  # type: ignore[arg-type]


def test_run_passes_tie_break_through(tmp_path: Path) -> None:
    write_dataset(
        tmp_path / "ds",
        loans=[("0.15", 100, 1, "0.01", "MO")],
        facilities=[(1000, "0.05", 1, 1), (1000, "0.05", 2, 1)],
    )
    run(tmp_path / "ds" / "input", tmp_path / "a", tie_break=TieBreak.HIGHEST_ID)
    assert read_text(tmp_path / "a" / "assignments.csv") == "loan_id,facility_id\n1,2\n"
    run(tmp_path / "ds" / "input", tmp_path / "b")
    assert read_text(tmp_path / "b" / "assignments.csv") == "loan_id,facility_id\n1,1\n"


def test_cli_rejects_unknown_policy(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main([str(DATA / "small"), "--tie-break", "most-capacity"])
    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def _large(tmp_path: Path, *extra: str) -> list[dict[str, str]]:
    assert main([str(DATA / "large"), "--output-dir", str(tmp_path), *extra]) == 0
    with (tmp_path / "assignments.csv").open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_cli_default_equals_explicit_lowest_id(tmp_path: Path) -> None:
    default = _large(tmp_path / "d")
    explicit = _large(tmp_path / "e", "--tie-break", "lowest-id")
    assert default == explicit
    assert read_text(tmp_path / "e" / "yields.csv") == read_text(DATA / "large/output/yields.csv")


@pytest.mark.parametrize(
    ("policy", "unfunded", "differs"),
    [("lowest-id", ["425"], 0), ("file-order", [], 158), ("highest-id", [], 313)],
)
def test_large_data_outcome_per_policy(
    policy: str, unfunded: list[str], differs: int, tmp_path: Path
) -> None:
    rows = _large(tmp_path / policy, "--tie-break", policy)
    baseline = _large(tmp_path / "base")
    assert [r["loan_id"] for r in rows if r["facility_id"] == ""] == unfunded
    assert sum(a != b for a, b in zip(rows, baseline, strict=True)) == differs
