import runpy
import subprocess
import sys
from pathlib import Path

import pytest

import balance_the_loan_books
from balance_the_loan_books.cli import main
from helpers import DATA, read_text, write_dataset

LOAN = [("0.15", 100, 1, "0.01", "MO")]


def _dataset(tmp_path: Path) -> Path:
    root = tmp_path / "ds"
    write_dataset(root, loans=LOAN)
    return root


def test_dataset_dir_form_reads_input_and_writes_output(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _dataset(tmp_path)
    assert main([str(root)]) == 0
    assert read_text(root / "output" / "assignments.csv") == "loan_id,facility_id\n1,1\n"
    assert (root / "output" / "yields.csv").is_file()
    assert "funded 1 of 1 loans across 1 facilities" in capsys.readouterr().err


def test_explicit_input_and_output_dirs(tmp_path: Path) -> None:
    root = _dataset(tmp_path)
    out = tmp_path / "elsewhere"
    assert main(["--input-dir", str(root / "input"), "--output-dir", str(out)]) == 0
    assert (out / "assignments.csv").is_file()
    assert not (root / "output").exists()


def test_output_dir_overrides_dataset_dir(tmp_path: Path) -> None:
    root = _dataset(tmp_path)
    out = tmp_path / "custom"
    assert main([str(root), "--output-dir", str(out)]) == 0
    assert (out / "yields.csv").is_file()
    assert not (root / "output").exists()


def test_input_dir_overrides_dataset_dir(tmp_path: Path) -> None:
    other = tmp_path / "other"
    write_dataset(other, loans=LOAN)
    out = tmp_path / "ds" / "output"
    assert main([str(tmp_path / "ds"), "--input-dir", str(other / "input")]) == 0
    assert (out / "assignments.csv").is_file()


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        main(["--version"])
    assert info.value.code == 0
    assert capsys.readouterr().out.strip() == (
        f"balance-the-loan-books {balance_the_loan_books.__version__}"
    )


@pytest.mark.parametrize(
    "argv",
    [[], ["--input-dir", "x"], ["--output-dir", "y"], ["--bogus"]],
)
def test_usage_errors_exit_2(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        main(argv)
    assert info.value.code == 2
    assert "usage:" in capsys.readouterr().err


def test_bad_input_exits_1_with_error_on_stderr(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_dataset(tmp_path / "ds", loans=[("x", 1, 1, "0", "MO")])
    assert main([str(tmp_path / "ds")]) == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("error: ")
    assert "line 2" in captured.err
    assert captured.out == ""


def test_missing_input_dir_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(tmp_path / "nowhere")]) == 1
    assert "error: missing input file" in capsys.readouterr().err


def test_os_error_exits_1(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _dataset(tmp_path)
    blocker = tmp_path / "blocker"
    blocker.write_text("a file, not a directory")
    assert main([str(root), "--output-dir", str(blocker / "sub")]) == 1
    assert capsys.readouterr().err.startswith("error: ")


def test_python_dash_m_runs_the_cli(tmp_path: Path) -> None:
    root = _dataset(tmp_path)
    result = subprocess.run(
        [sys.executable, "-m", "balance_the_loan_books", str(root)],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert read_text(root / "output" / "assignments.csv") == "loan_id,facility_id\n1,1\n"


def test_python_dash_m_reports_bad_input_with_exit_1(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "balance_the_loan_books", str(tmp_path / "missing")],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 1
    assert result.stderr.startswith("error: ")


def test_bundled_data_dir_exists() -> None:
    assert (DATA / "small" / "input").is_dir()


def test_main_module_exits_with_cli_status_in_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Same code path as the subprocess tests, but visible to coverage.
    monkeypatch.setattr(sys, "argv", ["balance_the_loan_books", str(_dataset(tmp_path))])
    with pytest.raises(SystemExit) as info:
        runpy.run_module("balance_the_loan_books", run_name="__main__")
    assert info.value.code == 0
