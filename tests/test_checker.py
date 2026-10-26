"""The independent checker agrees with the program and the committed references, and has teeth.

``checker.py`` imports nothing from the package, so agreement here is evidence that does not
depend on the package's own yield or ordering code. The committed ``data/large/output`` files
were first produced by this program (a self-snapshot); this module checks them against an
implementation written separately.
"""

import shutil
from fractions import Fraction
from pathlib import Path

import pytest

import checker
from balance_the_loan_books.cli import main
from helpers import DATA, read_text, write_dataset

NAMES = ["small", "large"]


@pytest.mark.parametrize("name", NAMES)
def test_checker_reproduces_committed_outputs(name: str) -> None:
    assignments, yields = checker.expected_text(DATA / name / "input")
    assert assignments == read_text(DATA / name / "output" / "assignments.csv")
    assert yields == read_text(DATA / name / "output" / "yields.csv")


@pytest.mark.parametrize("name", NAMES)
def test_checker_validates_committed_outputs(name: str) -> None:
    out = DATA / name / "output"
    problems = checker.validate(
        DATA / name / "input",
        out / "assignments.csv",
        out / "yields.csv",
        lowest_id_tie_break=True,
    )
    assert problems == []


@pytest.mark.parametrize("name", NAMES)
def test_checker_agrees_with_fresh_program_output(name: str, tmp_path: Path) -> None:
    assert main([str(DATA / name), "--output-dir", str(tmp_path)]) == 0
    assignments, yields = checker.expected_text(DATA / name / "input")
    assert read_text(tmp_path / "assignments.csv") == assignments
    assert read_text(tmp_path / "yields.csv") == yields
    assert (
        checker.validate(
            DATA / name / "input",
            tmp_path / "assignments.csv",
            tmp_path / "yields.csv",
            lowest_id_tie_break=True,
        )
        == []
    )


def test_checker_finds_loan_425_unfunded() -> None:
    assignments, _ = checker.expected(DATA / "large" / "input")
    assert [loan for loan, facility in assignments if facility is None] == [425]


def test_checker_small_matches_hand_worked_values() -> None:
    assignments, yields = checker.expected(DATA / "small" / "input")
    assert assignments == [(1, 1), (2, 2), (3, 1)]
    assert yields == [(1, 16375), (2, 3504)]


# --- the checker must reject wrong outputs ------------------------------------------------


@pytest.fixture
def good_large(tmp_path: Path) -> tuple[Path, Path, Path]:
    """(input dir, assignments copy, yields copy) of the committed large reference."""
    out = DATA / "large" / "output"
    assignments = shutil.copy(out / "assignments.csv", tmp_path / "assignments.csv")
    yields = shutil.copy(out / "yields.csv", tmp_path / "yields.csv")
    return DATA / "large" / "input", Path(assignments), Path(yields)


def _problems(good: tuple[Path, Path, Path]) -> list[str]:
    return checker.validate(*good, lowest_id_tie_break=True)


def test_checker_flags_swapped_assignment(good_large: tuple[Path, Path, Path]) -> None:
    _, assignments, _ = good_large
    lines = read_text(assignments).splitlines()
    loan, facility = lines[1].split(",")
    other = "2" if facility != "2" else "3"
    lines[1] = f"{loan},{other}"
    assignments.write_text("\n".join(lines) + "\n")
    assert _problems(good_large)


def test_checker_flags_yield_off_by_one_cent(good_large: tuple[Path, Path, Path]) -> None:
    _, _, yields = good_large
    lines = read_text(yields).splitlines()
    fid, value = lines[1].split(",")
    lines[1] = f"{fid},{int(value) + 1}"
    yields.write_text("\n".join(lines) + "\n")
    problems = _problems(good_large)
    assert any("yields" in p for p in problems)


def test_checker_flags_loan_funded_that_should_be_unfunded(
    good_large: tuple[Path, Path, Path],
) -> None:
    _, assignments, _ = good_large
    text = read_text(assignments)
    assert text.endswith("425,\n")
    assignments.write_text(text[:-1] + "1\n")
    assert any("425" in p for p in _problems(good_large))


def test_checker_flags_loan_left_unfunded_that_was_feasible(
    good_large: tuple[Path, Path, Path],
) -> None:
    _, assignments, _ = good_large
    lines = read_text(assignments).splitlines()
    loan, _ = lines[1].split(",")
    lines[1] = f"{loan},"
    assignments.write_text("\n".join(lines) + "\n")
    assert any("unfunded" in p for p in _problems(good_large))


def test_checker_flags_missing_row_and_bad_header(good_large: tuple[Path, Path, Path]) -> None:
    _, assignments, yields = good_large
    lines = read_text(assignments).splitlines()
    assignments.write_text("\n".join(lines[:-1]) + "\n")
    assert _problems(good_large) == ["assignments do not list every loan once, in input order"]
    yields.write_text("facility,yield\n")
    assert "header" in _problems(good_large)[0]


def test_checker_flags_capacity_and_covenant_violations(tmp_path: Path) -> None:
    root = write_dataset(
        tmp_path,
        facilities=((100, "0.01", 1, 1), (1000, "0.02", 2, 1)),
        covenants=((2, None, 1, "XX"),),
        loans=(
            ("0.1", 60, 1, "0.01", "MO"),
            ("0.1", 60, 2, "0.01", "MO"),
            ("0.1", 10, 3, "0.01", "XX"),
        ),
    )
    out = tmp_path / "out"
    out.mkdir()
    (out / "assignments.csv").write_text("loan_id,facility_id\n1,1\n2,1\n3,2\n")
    (out / "yields.csv").write_text("facility_id,expected_yield\n1,0\n2,0\n")
    problems = checker.validate(root, out / "assignments.csv", out / "yields.csv")
    assert any("exceeds remaining capacity" in p for p in problems)
    assert any("violates a covenant" in p for p in problems)
    assert any("capacity exceeded" in p for p in problems)


def test_checker_flags_non_cheapest_choice_and_tie_break(tmp_path: Path) -> None:
    root = write_dataset(
        tmp_path,
        facilities=((1000, "0.02", 1, 1), (1000, "0.02", 2, 1), (1000, "0.05", 3, 1)),
        loans=(("0.1", 10, 1, "0.01", "MO"),),
    )
    out = tmp_path / "out"
    out.mkdir()
    yields = "facility_id,expected_yield\n1,0\n2,0\n3,0\n"
    (out / "yields.csv").write_text(yields)

    def check(facility: int, *, strict: bool) -> list[str]:
        (out / "assignments.csv").write_text(f"loan_id,facility_id\n1,{facility}\n")
        return [
            p
            for p in checker.validate(
                root,
                out / "assignments.csv",
                out / "yields.csv",
                lowest_id_tie_break=strict,
            )
            if "cheapest" in p
        ]

    assert check(3, strict=False)
    assert check(2, strict=False) == []  # equal rate: any tie-break accepted
    assert check(2, strict=True)  # but not under the lowest-id rule
    assert check(1, strict=True) == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Fraction(1, 2), 1),
        (Fraction(-1, 2), -1),
        (Fraction(3, 2), 2),
        (Fraction(-3, 2), -2),
        (Fraction(249, 500), 0),
        (Fraction(-249, 500), 0),
        (Fraction(251, 500), 1),
        (Fraction(0), 0),
        (Fraction(7), 7),
    ],
)
def test_round_half_up_is_away_from_zero(value: Fraction, expected: int) -> None:
    assert checker.round_half_up(value) == expected


def test_checker_covenant_logic_is_inclusive_and_bank_scoped() -> None:
    fac1 = checker.Fac(id=1, bank=1, rate=Fraction(1, 20), capacity=10)
    fac2 = checker.Fac(id=2, bank=2, rate=Fraction(1, 20), capacity=10)
    loan = checker.Ln(id=1, rate=Fraction(1, 10), amount=1, dl=Fraction(6, 100), state="MO")
    bank_wide = [checker.Cov(bank=1, facility=None, max_dl=Fraction(6, 100), banned="VT")]
    assert checker.covenant_ok(fac1, loan, bank_wide)  # equal to the maximum is allowed
    assert checker.covenant_ok(fac2, loan, [checker.Cov(1, None, Fraction(0), "MO")])  # other bank
    assert not checker.covenant_ok(fac1, loan, [checker.Cov(1, None, Fraction(5, 100), None)])
    assert not checker.covenant_ok(fac1, loan, [checker.Cov(2, 1, None, "MO")])  # facility wins
