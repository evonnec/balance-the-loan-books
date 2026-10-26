"""CLI end to end with mocked paths: argument resolution, stdout/stderr contract, exit codes."""

import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from balance_the_loan_books import cli
from balance_the_loan_books.cli import main
from balance_the_loan_books.io import InputError
from balance_the_loan_books.pipeline import RunSummary
from helpers import DATA, write_dataset

SUMMARY = RunSummary(loans=3, funded=2, facilities=4)


def _paths(runner: mock.Mock) -> tuple[Path, Path]:
    (input_dir, output_dir), _ = runner.call_args
    return input_dir, output_dir


@pytest.mark.parametrize(
    ("argv", "expected_in", "expected_out"),
    [
        (["ds"], "ds/input", "ds/output"),
        (["ds", "--input-dir", "i"], "i", "ds/output"),
        (["ds", "--output-dir", "o"], "ds/input", "o"),
        (["--input-dir", "i", "--output-dir", "o"], "i", "o"),
        (["ds", "--input-dir", "i", "--output-dir", "o"], "i", "o"),
        (["/abs/ds"], "/abs/ds/input", "/abs/ds/output"),
    ],
)
def test_path_resolution_passed_to_run(
    monkeypatch: pytest.MonkeyPatch, argv: list[str], expected_in: str, expected_out: str
) -> None:
    runner = mock.Mock(return_value=SUMMARY)
    monkeypatch.setattr(cli, "run", runner)
    assert main(argv) == 0
    assert _paths(runner) == (Path(expected_in), Path(expected_out))


def test_success_writes_one_summary_line_to_stderr_and_nothing_to_stdout(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "run", mock.Mock(return_value=SUMMARY))
    assert main(["ds"]) == 0
    captured = capsys.readouterr()
    assert captured.out == ""
    out_dir = Path("ds", "output")
    assert captured.err == f"funded 2 of 3 loans across 4 facilities; wrote {out_dir}\n"


@pytest.mark.parametrize(
    "error", [InputError("loans.csv, line 7: bad"), FileNotFoundError(2, "gone"), OSError(5, "io")]
)
def test_input_and_os_errors_exit_1_with_one_error_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], error: Exception
) -> None:
    monkeypatch.setattr(cli, "run", mock.Mock(side_effect=error))
    assert main(["ds"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == f"error: {error}\n"


def test_run_is_not_called_on_usage_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = mock.Mock(return_value=SUMMARY)
    monkeypatch.setattr(cli, "run", runner)
    for argv in ([], ["--input-dir", "i"], ["--output-dir", "o"], ["--bogus"], ["a", "b"]):
        with pytest.raises(SystemExit) as info:
            main(argv)
        assert info.value.code == 2
    runner.assert_not_called()
    err = capsys.readouterr().err
    assert err.count("usage:") == 5
    assert "give a dataset_dir, or both --input-dir and --output-dir" in err


def test_unexpected_exceptions_are_not_swallowed_as_bad_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "run", mock.Mock(side_effect=RuntimeError("bug")))
    with pytest.raises(RuntimeError, match="bug"):
        main(["ds"])


def test_help_goes_to_stdout_and_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as info:
        main(["--help"])
    assert info.value.code == 0
    captured = capsys.readouterr()
    assert "--input-dir" in captured.out
    assert captured.err == ""


# --- real subprocess: exit status and streams as a shell sees them ---------------------------


def _cli(*args: str | Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "balance_the_loan_books", *map(str, args)],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def test_subprocess_success_contract(tmp_path: Path) -> None:
    result = _cli(DATA / "small", "--output-dir", tmp_path)
    assert (result.returncode, result.stdout) == (0, "")
    assert result.stderr == f"funded 3 of 3 loans across 2 facilities; wrote {tmp_path}\n"


def test_subprocess_bad_input_contract(tmp_path: Path) -> None:
    input_dir = write_dataset(tmp_path / "ds", loans=[("0.1", "x", 1, "0.01", "MO")])
    result = _cli("--input-dir", input_dir, "--output-dir", tmp_path / "out")
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith("error: ")
    assert "line 2" in result.stderr
    assert "Traceback" not in result.stderr
    assert result.stderr.count("\n") == 1


def test_subprocess_missing_dataset_and_usage_errors(tmp_path: Path) -> None:
    missing = _cli(tmp_path / "nowhere")
    assert missing.returncode == 1
    assert missing.stderr.startswith("error: missing input file")
    usage = _cli()
    assert usage.returncode == 2
    assert usage.stdout == ""
    assert "usage:" in usage.stderr


def test_subprocess_version() -> None:
    result = _cli("--version")
    assert result.returncode == 0
    assert result.stdout.startswith("balance-the-loan-books ")
