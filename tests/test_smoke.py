from pathlib import Path

from balance_the_loan_books.cli import main

DATA = Path(__file__).parent.parent / "data"


def test_small_matches_reference_output(tmp_path: Path) -> None:
    code = main([str(DATA / "small"), "--output-dir", str(tmp_path)])

    assert code == 0
    for name in ("assignments.csv", "yields.csv"):
        assert (tmp_path / name).read_text() == (DATA / "small" / "output" / name).read_text()
    assert (tmp_path / "assignments.csv").read_text() == "loan_id,facility_id\n1,1\n2,2\n3,1\n"
    assert (tmp_path / "yields.csv").read_text() == "facility_id,expected_yield\n1,16375\n2,3504\n"
