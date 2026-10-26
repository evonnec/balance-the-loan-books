"""Fault injection: failures while reading or writing must never leave partial or mixed output.

Faults are injected with ``monkeypatch``/``unittest.mock`` at the seams the pipeline uses: the
loan iterator, ``csv.writer``, ``Path.replace``, ``Path.mkdir``, file permissions and deletion of
an input file between reads. After every fault the previous outputs are byte-identical and no
temp file (``.<name>.*.tmp``) remains.
"""

import csv
import errno
import os
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from balance_the_loan_books import pipeline
from balance_the_loan_books.cli import main
from balance_the_loan_books.io import InputError, iter_loans, read_covenants
from balance_the_loan_books.models import Loan
from helpers import write_dataset

LOANS_A = [("0.15", 100, i, "0.01", "MO") for i in range(1, 6)]
LOANS_B = [("0.15", 250, i, "0.02", "MO") for i in range(1, 9)]

posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX permissions and unlink")


def _snapshot(directory: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(directory.iterdir())}


def _good_run(tmp_path: Path) -> tuple[Path, Path, dict[str, bytes]]:
    """A dataset with a completed first run; returns (input dir, output dir, output bytes)."""
    input_dir = write_dataset(tmp_path / "ds", loans=LOANS_A)
    output_dir = tmp_path / "ds" / "output"
    pipeline.run(input_dir, output_dir)  # not via main(): keeps the summary line off stderr
    return input_dir, output_dir, _snapshot(output_dir)


def _second_input(input_dir: Path, tmp_path: Path) -> Path:
    """A different input, so that a (wrongly) completed second run would visibly change output."""
    other = write_dataset(tmp_path / "other", loans=LOANS_B)
    assert other != input_dir
    return other


def _failing_loans(after: int, error: BaseException) -> Callable[[Path], Iterator[Loan]]:
    """An ``iter_loans`` replacement that yields ``after`` real loans, then raises ``error``."""

    def fake(path: Path) -> Iterator[Loan]:
        for index, loan in enumerate(iter_loans(path)):
            if index == after:
                raise error
            yield loan
        raise error

    return fake


# --- failure while the loan stream is being written ----------------------------------------


@pytest.mark.parametrize("after", [0, 1, 4])
def test_stream_failure_mid_write_keeps_previous_outputs_and_leaves_no_temp_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], after: int
) -> None:
    _, output_dir, before = _good_run(tmp_path)
    other = _second_input(tmp_path / "ds" / "input", tmp_path)
    monkeypatch.setattr(
        pipeline, "iter_loans", _failing_loans(after, OSError(errno.EIO, "injected read failure"))
    )
    assert main(["--input-dir", str(other), "--output-dir", str(output_dir)]) == 1
    assert capsys.readouterr().err.startswith("error: ")
    assert _snapshot(output_dir) == before


def test_writer_failure_mid_stream_keeps_previous_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``csv.writer.writerow`` raising ENOSPC on the third row (a full disk)."""
    _, output_dir, before = _good_run(tmp_path)
    other = _second_input(tmp_path / "ds" / "input", tmp_path)
    real_writer = csv.writer
    calls = 0

    class FullDisk:
        def __init__(self, inner: Any) -> None:
            self._inner = inner

        def writerow(self, row: Any) -> object:
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError(errno.ENOSPC, "No space left on device")
            return self._inner.writerow(row)

        def writerows(self, rows: Any) -> object:
            return self._inner.writerows(rows)

    monkeypatch.setattr(csv, "writer", lambda *a, **k: FullDisk(real_writer(*a, **k)))
    assert main(["--input-dir", str(other), "--output-dir", str(output_dir)]) == 1
    assert "No space left on device" in capsys.readouterr().err
    assert calls == 3
    assert _snapshot(output_dir) == before


def test_first_replace_failing_keeps_previous_outputs_and_removes_temp_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, output_dir, before = _good_run(tmp_path)
    other = _second_input(tmp_path / "ds" / "input", tmp_path)
    with mock.patch.object(Path, "replace", side_effect=PermissionError(errno.EACCES, "denied")):
        assert main(["--input-dir", str(other), "--output-dir", str(output_dir)]) == 1
    assert "denied" in capsys.readouterr().err
    assert _snapshot(output_dir) == before


def test_failure_on_a_fresh_output_dir_leaves_no_files_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    input_dir = write_dataset(tmp_path / "ds", loans=LOANS_A)
    out = tmp_path / "fresh" / "nested"
    monkeypatch.setattr(pipeline, "iter_loans", _failing_loans(2, OSError(errno.EIO, "boom")))
    assert main(["--input-dir", str(input_dir), "--output-dir", str(out)]) == 1
    assert list(out.iterdir()) == []


def test_temp_files_live_beside_the_destination_and_are_hidden_while_streaming(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """While the stream is open only a hidden temp file exists, never a half-written target."""
    input_dir = write_dataset(tmp_path / "ds", loans=LOANS_A)
    out = tmp_path / "out"
    seen: list[list[str]] = []
    real = iter_loans

    def spy(path: Path) -> Iterator[Loan]:
        for loan in real(path):
            seen.append(sorted(p.name for p in out.iterdir()))
            yield loan

    monkeypatch.setattr(pipeline, "iter_loans", spy)
    assert main(["--input-dir", str(input_dir), "--output-dir", str(out)]) == 0
    assert seen
    for names in seen:
        assert len(names) == 1
        assert names[0].startswith(".assignments.csv.")
        assert names[0].endswith(".tmp")
    assert sorted(p.name for p in out.iterdir()) == ["assignments.csv", "yields.csv"]


# --- interrupts -----------------------------------------------------------------------------


@pytest.mark.parametrize("fresh", [True, False])
def test_keyboard_interrupt_while_streaming_leaves_no_partial_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fresh: bool
) -> None:
    if fresh:
        input_dir = write_dataset(tmp_path / "ds", loans=LOANS_A)
        output_dir = tmp_path / "out"
        before: dict[str, bytes] = {}
    else:
        input_dir, output_dir, before = _good_run(tmp_path)
        input_dir = _second_input(input_dir, tmp_path)
    monkeypatch.setattr(pipeline, "iter_loans", _failing_loans(2, KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        main(["--input-dir", str(input_dir), "--output-dir", str(output_dir)])
    after = _snapshot(output_dir) if output_dir.exists() else {}
    assert after == before


def test_keyboard_interrupt_is_not_reported_as_bad_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    input_dir = write_dataset(tmp_path / "ds", loans=LOANS_A)
    monkeypatch.setattr(pipeline, "iter_loans", _failing_loans(1, KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        main(["--input-dir", str(input_dir), "--output-dir", str(tmp_path / "out")])
    assert "error:" not in capsys.readouterr().err


# --- output directory problems ----------------------------------------------------------------


@posix_only
@pytest.mark.skipif(sys.platform != "win32" and os.geteuid() == 0, reason="root ignores modes")
def test_unwritable_output_dir_exits_1_and_keeps_previous_outputs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, output_dir, before = _good_run(tmp_path)
    other = _second_input(tmp_path / "ds" / "input", tmp_path)
    output_dir.chmod(0o500)
    try:
        assert main(["--input-dir", str(other), "--output-dir", str(output_dir)]) == 1
        err = capsys.readouterr().err
        assert err.startswith("error: ")
        assert "Traceback" not in err
    finally:
        output_dir.chmod(0o700)
    assert _snapshot(output_dir) == before


def test_output_path_that_is_a_file_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_dir = write_dataset(tmp_path / "ds", loans=LOANS_A)
    blocker = tmp_path / "out"
    blocker.write_text("not a directory")
    assert main(["--input-dir", str(input_dir), "--output-dir", str(blocker)]) == 1
    assert capsys.readouterr().err.startswith("error: ")
    assert blocker.read_text() == "not a directory"


def test_mkdir_permission_error_is_reported_not_raised(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_dir = write_dataset(tmp_path / "ds", loans=LOANS_A)
    with mock.patch.object(
        Path, "mkdir", side_effect=PermissionError(errno.EACCES, "mkdir denied")
    ):
        assert main(["--input-dir", str(input_dir), "--output-dir", str(tmp_path / "x")]) == 1
    assert "mkdir denied" in capsys.readouterr().err


def test_mkstemp_failure_is_reported_and_creates_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_dir = write_dataset(tmp_path / "ds", loans=LOANS_A)
    out = tmp_path / "out"
    with mock.patch("tempfile.mkstemp", side_effect=OSError(errno.EMFILE, "too many open files")):
        assert main(["--input-dir", str(input_dir), "--output-dir", str(out)]) == 1
    assert "too many open files" in capsys.readouterr().err
    assert list(out.iterdir()) == []


# --- input files disappearing ---------------------------------------------------------------


def test_loans_file_deleted_after_setup_is_a_clean_input_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``loans.csv`` vanishes after the other inputs were read, before streaming starts."""
    _, output_dir, before = _good_run(tmp_path)
    other = _second_input(tmp_path / "ds" / "input", tmp_path)
    real = read_covenants

    def read_then_delete(path: Path) -> Any:
        rows = real(path)
        (other / "loans.csv").unlink()
        return rows

    monkeypatch.setattr(pipeline, "read_covenants", read_then_delete)
    assert main(["--input-dir", str(other), "--output-dir", str(output_dir)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: missing input file")
    assert "loans.csv" in err
    assert _snapshot(output_dir) == before


@pytest.mark.parametrize("name", ["banks.csv", "facilities.csv", "covenants.csv", "loans.csv"])
def test_each_missing_input_file_is_named_and_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    input_dir = write_dataset(tmp_path / "ds", loans=LOANS_A)
    (input_dir / name).unlink()
    assert main(["--input-dir", str(input_dir), "--output-dir", str(tmp_path / "out")]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: missing input file")
    assert name in err
    assert "Traceback" not in err


@posix_only
def test_loans_file_unlinked_while_streaming_does_not_corrupt_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On POSIX an open file survives unlink: the run completes with the loans it opened."""
    input_dir = write_dataset(tmp_path / "ds", loans=LOANS_A)
    out = tmp_path / "out"
    real = iter_loans

    def unlink_after_first(path: Path) -> Iterator[Loan]:
        for index, loan in enumerate(real(path)):
            if index == 1:
                path.unlink()
            yield loan

    monkeypatch.setattr(pipeline, "iter_loans", unlink_after_first)
    assert main(["--input-dir", str(input_dir), "--output-dir", str(out)]) == 0
    assert (out / "assignments.csv").read_text().count("\n") == 1 + len(LOANS_A)


def test_input_error_mid_stream_keeps_previous_outputs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A malformed row late in ``loans.csv`` (an existing, supported failure) rolls back cleanly."""
    _, output_dir, before = _good_run(tmp_path)
    other = _second_input(tmp_path / "ds" / "input", tmp_path)
    with (other / "loans.csv").open("a", encoding="utf-8") as handle:
        handle.write("0.15,abc,99,0.01,MO\n")
    assert main(["--input-dir", str(other), "--output-dir", str(output_dir)]) == 1
    assert "line 10" in capsys.readouterr().err
    assert _snapshot(output_dir) == before


def test_input_error_type_is_what_the_cli_maps_to_exit_1() -> None:
    assert issubclass(InputError, ValueError)
