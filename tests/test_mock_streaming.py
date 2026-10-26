"""Streaming proof: no lookahead, no buffering, and memory that does not grow with the loans."""

import csv
import gc
import tracemalloc
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from balance_the_loan_books import pipeline
from balance_the_loan_books.io import InputError, iter_loans
from balance_the_loan_books.models import Loan
from helpers import LOANS_HEADER, write_csv, write_dataset

LOANS = [("0.15", 100, i, "0.01", "MO") for i in range(1, 21)]


def test_each_assignment_is_written_before_the_next_loan_is_pulled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Interleave the events 'loan i handed to the allocator' and 'row for loan i written'."""
    input_dir = write_dataset(tmp_path / "ds", loans=LOANS)
    events: list[tuple[str, int]] = []
    real_iter = iter_loans
    real_writer = csv.writer

    def recording_iter(path: Path) -> Iterator[Loan]:
        for loan in real_iter(path):
            events.append(("pull", loan.id))
            yield loan

    class RecordingWriter:
        def __init__(self, inner: Any) -> None:
            self._inner = inner

        def writerow(self, row: Any) -> object:
            if isinstance(row[0], int):  # data rows carry int ids; headers are strings
                events.append(("emit", row[0]))
            return self._inner.writerow(row)

        def writerows(self, rows: Any) -> object:
            return self._inner.writerows(rows)

    monkeypatch.setattr(pipeline, "iter_loans", recording_iter)
    monkeypatch.setattr(csv, "writer", lambda *a, **k: RecordingWriter(real_writer(*a, **k)))
    pipeline.run(input_dir, tmp_path / "out")

    expected = [event for i in range(1, 21) for event in (("pull", i), ("emit", i))]
    assert events == expected


def test_loan_source_is_consumed_one_at_a_time_and_never_materialised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A source that tracks its own position: the writer never gets ahead of it by more than one."""
    input_dir = write_dataset(tmp_path / "ds", loans=LOANS)
    state = {"pulled": 0, "max_gap": 0}
    real_iter = iter_loans
    real_writer = csv.writer
    written = {"rows": 0}

    def tracked(path: Path) -> Iterator[Loan]:
        for loan in real_iter(path):
            state["pulled"] += 1
            state["max_gap"] = max(state["max_gap"], state["pulled"] - written["rows"])
            yield loan

    class Counting:
        def __init__(self, inner: Any) -> None:
            self._inner = inner

        def writerow(self, row: Any) -> object:
            written["rows"] += 1
            return self._inner.writerow(row)

        def writerows(self, rows: Any) -> object:
            return self._inner.writerows(rows)

    monkeypatch.setattr(pipeline, "iter_loans", tracked)
    monkeypatch.setattr(csv, "writer", lambda *a, **k: Counting(real_writer(*a, **k)))
    pipeline.run(input_dir, tmp_path / "out")
    # rows written includes the header, so after k loans were pulled k + 1 rows exist at most
    # once the assignment for loan k is written: gap (pulled - written) is never positive.
    assert state["pulled"] == len(LOANS)
    assert state["max_gap"] <= 0


def test_a_late_bad_row_proves_earlier_rows_were_processed_before_it_was_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Error line numbers come from the reader's position, i.e. a streaming read."""
    input_dir = write_dataset(tmp_path / "ds", loans=LOANS)
    with (input_dir / "loans.csv").open("a", encoding="utf-8") as handle:
        handle.write("0.15,oops,99,0.01,MO\n")
    with pytest.raises(InputError, match=r"line 22"):
        pipeline.run(input_dir, tmp_path / "out")
    assert not (tmp_path / "out" / "assignments.csv").exists()
    capsys.readouterr()


# --- memory ---------------------------------------------------------------------------------


def _write_loans(path: Path, count: int) -> None:
    states = ["MO", "VT", "AZ", "CA"]
    rows = ((f"0.{10 + i % 20}", 100 + i % 900, i + 1, "0.02", states[i % 4]) for i in range(count))
    write_csv(path, LOANS_HEADER, rows)


def _peak_bytes(input_dir: Path, out: Path) -> int:
    gc.collect()
    tracemalloc.start()
    try:
        pipeline.run(input_dir, out)
        return tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()


def _scaled_dataset(root: Path, count: int) -> Path:
    input_dir = write_dataset(
        root,
        facilities=((10**12, "0.05", 1, 1), (10**12, "0.06", 2, 1)),
        covenants=((None, "0.05", 1, "VT"),),
    )
    _write_loans(input_dir / "loans.csv", count)
    return input_dir


def test_peak_memory_does_not_scale_with_the_number_of_loans(tmp_path: Path) -> None:
    small = _scaled_dataset(tmp_path / "small", 1_000)
    large = _scaled_dataset(tmp_path / "large", 10_000)
    peak_small = _peak_bytes(small, tmp_path / "small_out")
    peak_large = _peak_bytes(large, tmp_path / "large_out")
    # 10x the loans: a program that held them would use roughly 10x the memory.
    assert peak_large < 2 * peak_small + 64 * 1024, (peak_small, peak_large)


def test_memory_probe_detects_a_non_streaming_reader(tmp_path: Path) -> None:
    """Control: the probe above would catch a reader that materialises every loan."""
    small = _scaled_dataset(tmp_path / "small", 1_000)
    large = _scaled_dataset(tmp_path / "large", 10_000)

    def eager_peak(input_dir: Path) -> int:
        gc.collect()
        tracemalloc.start()
        try:
            held = list(iter_loans(input_dir / "loans.csv"))
            assert held
            return tracemalloc.get_traced_memory()[1]
        finally:
            tracemalloc.stop()

    assert eager_peak(large) > 5 * eager_peak(small)
