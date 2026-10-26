"""Regression tests: the bundled data sets must reproduce the committed outputs exactly."""

import csv
from pathlib import Path

import pytest

from balance_the_loan_books.cli import main
from helpers import DATA, read_text


@pytest.mark.parametrize("name", ["small", "large"])
@pytest.mark.parametrize("output", ["assignments.csv", "yields.csv"])
def test_output_equals_committed_reference(name: str, output: str, tmp_path: Path) -> None:
    assert main([str(DATA / name), "--output-dir", str(tmp_path)]) == 0
    assert read_text(tmp_path / output) == read_text(DATA / name / "output" / output)


def test_small_hand_worked_values(tmp_path: Path) -> None:
    assert main([str(DATA / "small"), "--output-dir", str(tmp_path)]) == 0
    assert read_text(tmp_path / "assignments.csv") == "loan_id,facility_id\n1,1\n2,2\n3,1\n"
    assert read_text(tmp_path / "yields.csv") == "facility_id,expected_yield\n1,16375\n2,3504\n"


def test_large_funds_424_of_425_and_leaves_loan_425_unfunded(tmp_path: Path) -> None:
    assert main([str(DATA / "large"), "--output-dir", str(tmp_path)]) == 0
    with (tmp_path / "assignments.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 425
    unfunded = [row["loan_id"] for row in rows if row["facility_id"] == ""]
    assert unfunded == ["425"]
    assert sum(1 for row in rows if row["facility_id"]) == 424


def test_large_yields_list_every_facility_sorted(tmp_path: Path) -> None:
    assert main([str(DATA / "large"), "--output-dir", str(tmp_path)]) == 0
    with (tmp_path / "yields.csv").open(newline="", encoding="utf-8") as handle:
        ids = [int(row["facility_id"]) for row in csv.DictReader(handle)]
    assert ids == sorted(ids)
    assert len(ids) == len(set(ids)) == 15
