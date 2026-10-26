from pathlib import Path

import pytest

from balance_the_loan_books.io import InputError
from balance_the_loan_books.pipeline import RunSummary, run, validate_references
from helpers import make_facility, make_row, read_text, write_dataset


class TestValidateReferences:
    def test_valid_references_pass(self) -> None:
        validate_references(
            [make_facility(id=1, bank_id=1), make_facility(id=2, bank_id=2)],
            [make_row(bank_id=1, facility_id=1), make_row(bank_id=2)],
            {1, 2},
        )

    def test_duplicate_facility_id(self) -> None:
        facilities = [make_facility(id=1), make_facility(id=1)]
        with pytest.raises(InputError, match="duplicate facility id: 1"):
            validate_references(facilities, [], {1})

    def test_facility_with_unknown_bank(self) -> None:
        with pytest.raises(InputError, match="facility 4 references unknown bank 9"):
            validate_references([make_facility(id=4, bank_id=9)], [], {1})

    def test_covenant_with_unknown_facility(self) -> None:
        with pytest.raises(InputError, match="covenant references unknown facility 8"):
            validate_references([make_facility()], [make_row(facility_id=8)], {1})

    def test_covenant_with_unknown_bank(self) -> None:
        with pytest.raises(InputError, match="covenant references unknown bank 7"):
            validate_references([make_facility()], [make_row(bank_id=7)], {1})


class TestRun:
    def test_summary_counts(self, tmp_path: Path) -> None:
        input_dir = write_dataset(
            tmp_path,
            facilities=[(1000, "0.05", 1, 1)],
            loans=[
                ("0.1", 600, 1, "0", "MO"),
                ("0.1", 600, 2, "0", "MO"),  # no capacity left
                ("0.1", 400, 3, "0", "MO"),
            ],
        )
        summary = run(input_dir, tmp_path / "out")
        assert summary == RunSummary(loans=3, funded=2, facilities=1)
        assert read_text(tmp_path / "out" / "assignments.csv") == (
            "loan_id,facility_id\n1,1\n2,\n3,1\n"
        )

    def test_empty_loans_file_gives_header_only_assignments_and_zero_yields(
        self, tmp_path: Path
    ) -> None:
        input_dir = write_dataset(tmp_path, facilities=[(10, "0.05", 3, 1), (10, "0.06", 0, 1)])
        summary = run(input_dir, tmp_path / "out")
        assert summary == RunSummary(loans=0, funded=0, facilities=2)
        assert read_text(tmp_path / "out" / "assignments.csv") == "loan_id,facility_id\n"
        assert read_text(tmp_path / "out" / "yields.csv") == (
            "facility_id,expected_yield\n0,0\n3,0\n"
        )

    def test_bad_loan_leaves_previous_outputs_untouched(self, tmp_path: Path) -> None:
        out = tmp_path / "out"
        run(write_dataset(tmp_path / "good", loans=[("0.1", 5, 1, "0", "MO")]), out)
        before = (out / "assignments.csv").read_bytes()

        bad = write_dataset(
            tmp_path / "bad", loans=[("0.1", 5, 1, "0", "MO"), ("x", 5, 2, "0", "MO")]
        )
        with pytest.raises(InputError, match="line 3"):
            run(bad, out)

        assert (out / "assignments.csv").read_bytes() == before
        assert sorted(p.name for p in out.iterdir()) == ["assignments.csv", "yields.csv"]

    def test_reference_errors_surface_from_run(self, tmp_path: Path) -> None:
        input_dir = write_dataset(tmp_path, facilities=[(10, "0.05", 1, 99)])
        with pytest.raises(InputError, match="unknown bank 99"):
            run(input_dir, tmp_path / "out")
