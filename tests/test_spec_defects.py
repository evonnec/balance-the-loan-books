"""Strict ``xfail`` tests pinning the agreed behaviour for each confirmed defect.

Every test asserts the *end* behaviour a user sees (for input problems: exit code 1, one stderr
line starting ``error:`` that names the file and ``line N``, no traceback, previous outputs
untouched). They fail on the current code, which ``xfail(strict=True)`` records; once a defect is
fixed the test XPASSes, strict mode fails the suite, and the marker is removed. ``#N`` is the
GitHub issue the behaviour belongs to. Tests that already pass (current behaviour that the fix
must keep) are ordinary tests, not xfails.

Test inputs derive from ``data/small/input``; replaced lines are always line 2 (the first data
row), so expected messages name ``line 2``.
"""

import contextlib
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from balance_the_loan_books.allocator import Allocator
from balance_the_loan_books.cli import main
from helpers import DATA, make_facility, make_loan, read_text, write_dataset

FILES = ("banks.csv", "facilities.csv", "covenants.csv", "loans.csv")


def defect(issue: int, text: str) -> pytest.MarkDecorator:
    """The strict xfail marker, tagged with its issue number."""
    return pytest.mark.xfail(strict=True, reason=f"#{issue}: {text}")


def small_input(tmp_path: Path) -> Path:
    target = tmp_path / "ds" / "input"
    shutil.copytree(DATA / "small" / "input", target)
    return target


def replace_line(path: Path, line: int, new: bytes) -> None:
    """Replace the 1-based ``line`` of ``path`` (keeping all other bytes, ``\\n`` endings)."""
    lines = path.read_bytes().replace(b"\r\n", b"\n").split(b"\n")
    lines[line - 1] = new
    path.write_bytes(b"\n".join(lines))


def run_cli(input_dir: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    """Run the CLI against ``input_dir`` (outputs next to it); return (exit code, stderr)."""
    code = main(["--input-dir", str(input_dir), "--output-dir", str(input_dir.parent / "output")])
    return code, capsys.readouterr().err


def assert_rejected(
    input_dir: Path, capsys: pytest.CaptureFixture[str], name: str, line: int | None = 2
) -> None:
    """Exit 1, a single ``error:`` line naming the file (and line), and no traceback."""
    code, err = run_cli(input_dir, capsys)
    assert code == 1, f"exit code {code}, stderr: {err!r}"
    assert err.startswith("error: "), err
    assert err.count("\n") == 1, err
    assert "Traceback" not in err
    assert name in err, err
    if line is None:
        assert re.search(r"line \d+", err), err
    else:
        assert f"line {line}" in err, err


def rows_of(input_dir: Path, name: str) -> list[bytes]:
    """Lines of an input file (the bundled inputs use CRLF; it is normalised to LF)."""
    return input_dir.joinpath(name).read_bytes().replace(b"\r\n", b"\n").split(b"\n")


# --- #1: malformed rows ---------------------------------------------------------------------


@defect(1, "a row with fewer fields than the header is an InputError, not an AttributeError")
@pytest.mark.parametrize("name", FILES)
def test_short_row_is_rejected_with_path_and_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    input_dir = small_input(tmp_path)
    replace_line(input_dir / name, 2, b"1")
    assert_rejected(input_dir, capsys, name)


@defect(1, "short row surfaces as InputError from the reader (library level)")
def test_short_loan_row_raises_input_error_with_line(tmp_path: Path) -> None:
    from balance_the_loan_books.io import InputError, iter_loans

    path = tmp_path / "l.csv"
    path.write_bytes(b"id,interest_rate,amount,default_likelihood,state\n1,0.1,10\n")
    with pytest.raises(InputError, match="line 2"):
        list(iter_loans(path))


@defect(1, "a row with more fields than the header is rejected, not silently misparsed")
@pytest.mark.parametrize("name", FILES)
def test_extra_field_is_rejected_with_path_and_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    input_dir = small_input(tmp_path)
    good = rows_of(input_dir, name)[1]
    replace_line(input_dir / name, 2, good + b",9")
    assert_rejected(input_dir, capsys, name)


@defect(1, "an unquoted thousands separator (10,552) must not invent a phantom loan")
def test_unquoted_thousands_separator_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_dir = small_input(tmp_path)
    replace_line(input_dir / "loans.csv", 2, b"0.15,10,552,1,0.02,MO")
    assert_rejected(input_dir, capsys, "loans.csv")
    assert not (input_dir.parent / "output" / "assignments.csv").exists()


NON_FINITE = ["NaN", "-NaN", "sNaN", "Infinity", "-Infinity", "inf"]
# (file, zero-based column in that file's header, human name)
NUMERIC_COLUMNS = [
    ("loans.csv", 0, "loan interest_rate"),
    ("loans.csv", 1, "loan amount"),
    ("loans.csv", 3, "loan default_likelihood"),
    ("facilities.csv", 1, "facility interest_rate"),
    ("facilities.csv", 0, "facility amount"),
    ("covenants.csv", 1, "covenant max_default_likelihood"),
]


# NaN and -NaN in an *amount* column already fail cleanly today (the "whole cents" check), so
# those combinations are ordinary regression tests; every other combination is a defect.
ALREADY_REJECTED = {("loans.csv", 1, "NaN"), ("loans.csv", 1, "-NaN")}
ALREADY_REJECTED |= {("facilities.csv", 0, "NaN"), ("facilities.csv", 0, "-NaN")}

NON_FINITE_CASES = [
    pytest.param(
        name,
        column,
        label,
        value,
        marks=[]
        if (name, column, value) in ALREADY_REJECTED
        else [defect(1, "NaN / sNaN / Infinity in a numeric column is an InputError with a line")],
        id=f"{name}-{label.replace(' ', '_')}-{value}",
    )
    for name, column, label in NUMERIC_COLUMNS
    for value in NON_FINITE
]


@pytest.mark.parametrize(("name", "column", "label", "value"), NON_FINITE_CASES)
def test_non_finite_number_is_rejected_with_path_and_line(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    name: str,
    column: int,
    label: str,
    value: str,
) -> None:
    input_dir = small_input(tmp_path)
    fields = rows_of(input_dir, name)[1].split(b",")
    fields[column] = value.encode()
    replace_line(input_dir / name, 2, b",".join(fields))
    assert_rejected(input_dir, capsys, name)


@defect(1, "bytes that are not UTF-8 (e.g. cp1252) are an InputError, not UnicodeDecodeError")
@pytest.mark.parametrize("name", FILES)
def test_non_utf8_byte_is_rejected_with_path_and_a_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    input_dir = small_input(tmp_path)
    fields = rows_of(input_dir, name)[1].split(b",")
    fields[-1] = b"Caf\xe9"
    replace_line(input_dir / name, 2, b",".join(fields))
    assert_rejected(input_dir, capsys, name, line=None)


@defect(1, "a field over the csv module's size limit is an InputError, not _csv.Error")
@pytest.mark.parametrize("name", FILES)
def test_huge_field_is_rejected_with_path_and_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    input_dir = small_input(tmp_path)
    fields = rows_of(input_dir, name)[1].split(b",")
    fields[-1] = b"9" * 131_073
    replace_line(input_dir / name, 2, b",".join(fields))
    assert_rejected(input_dir, capsys, name)


@defect(1, "a failed run (NaN loan rate) must leave both previous outputs byte-identical")
def test_nan_loan_rate_leaves_previous_outputs_untouched(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_dir = small_input(tmp_path)
    output_dir = input_dir.parent / "output"
    assert main(["--input-dir", str(input_dir), "--output-dir", str(output_dir)]) == 0
    before = {p.name: p.read_bytes() for p in output_dir.iterdir()}
    capsys.readouterr()
    replace_line(input_dir / "loans.csv", 2, b"NaN,10552,1,0.02,MO")
    code, err = run_cli(input_dir, capsys)
    assert code == 1
    assert err.startswith("error: ")
    assert {p.name: p.read_bytes() for p in output_dir.iterdir()} == before


# --- #2: value ranges, states, references ---------------------------------------------------

LOAN = ("0.1", 100, 1, "0.01", "MO")


def _dataset(
    tmp_path: Path,
    *,
    facilities: Any = ((1000, "0.05", 1, 1),),
    covenants: Any = (),
    loans: Any = (LOAN,),
    banks: Any = ((1, "A"), (2, "B")),
) -> Path:
    return write_dataset(
        tmp_path / "ds", banks=banks, facilities=facilities, covenants=covenants, loans=loans
    )


@defect(2, "a non-positive loan amount is rejected with its line number")
@pytest.mark.parametrize("amount", [-50, 0])
def test_non_positive_loan_amount_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], amount: int
) -> None:
    input_dir = _dataset(tmp_path, loans=[("0.1", amount, 1, "0.01", "MO")])
    assert_rejected(input_dir, capsys, "loans.csv")


@defect(2, "a negative facility capacity is rejected with its line number")
def test_negative_facility_capacity_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_dir = _dataset(tmp_path, facilities=[(-1, "0.05", 1, 1)])
    assert_rejected(input_dir, capsys, "facilities.csv")


@defect(2, "default_likelihood outside [0, 1] is rejected")
@pytest.mark.parametrize("value", ["1.2", "-0.3"])
def test_loan_default_likelihood_out_of_range_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], value: str
) -> None:
    input_dir = _dataset(tmp_path, loans=[("0.1", 100, 1, value, "MO")])
    assert_rejected(input_dir, capsys, "loans.csv")


@defect(2, "max_default_likelihood outside [0, 1] is rejected")
@pytest.mark.parametrize("value", ["1.5", "-0.1"])
def test_covenant_max_default_likelihood_out_of_range_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], value: str
) -> None:
    input_dir = _dataset(tmp_path, covenants=[(1, value, 1, None)])
    assert_rejected(input_dir, capsys, "covenants.csv")


@defect(2, "negative interest rates are rejected (loan and facility)")
@pytest.mark.parametrize("which", ["loan", "facility"])
def test_negative_interest_rate_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], which: str
) -> None:
    if which == "loan":
        input_dir = _dataset(tmp_path, loans=[("-0.1", 100, 1, "0.01", "MO")])
        assert_rejected(input_dir, capsys, "loans.csv")
    else:
        input_dir = _dataset(tmp_path, facilities=[(1000, "-0.05", 1, 1)])
        assert_rejected(input_dir, capsys, "facilities.csv")


@defect(2, "a covenant row with neither restriction is a silent no-op and is rejected")
def test_covenant_row_without_any_restriction_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_dir = _dataset(tmp_path, covenants=[(None, None, 1, None)])
    assert_rejected(input_dir, capsys, "covenants.csv")


@defect(2, "a facility-level covenant row whose bank_id is not the facility's bank is rejected")
def test_covenant_bank_must_match_the_facility_bank(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_dir = _dataset(
        tmp_path,
        facilities=[(1000, "0.05", 1, 1), (1000, "0.06", 2, 2)],
        covenants=[(1, None, 2, "MO")],  # facility 1 belongs to bank 1, the row says bank 2
    )
    assert_rejected(input_dir, capsys, "covenants.csv")


@defect(2, "duplicate bank ids are rejected")
def test_duplicate_bank_ids_are_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_dir = _dataset(tmp_path, banks=[(1, "A"), (1, "B")])
    assert_rejected(input_dir, capsys, "banks.csv", line=None)


@defect(2, "a malformed state code (not two letters) is rejected")
@pytest.mark.parametrize("state", ["", "V", "VTX", "V1"])
def test_malformed_loan_state_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], state: str
) -> None:
    input_dir = _dataset(tmp_path, loans=[("0.1", 100, 1, "0.01", state)])
    assert_rejected(input_dir, capsys, "loans.csv")


@defect(2, "a malformed banned_state in covenants.csv is rejected")
@pytest.mark.parametrize("state", ["V", "VTX", "V1"])
def test_malformed_banned_state_is_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], state: str
) -> None:
    input_dir = _dataset(tmp_path, covenants=[(1, None, 1, state)])
    assert_rejected(input_dir, capsys, "covenants.csv")


def _assignment_of_vt_loan(tmp_path: Path, loan_state: str, banned: str) -> str | None:
    """Facility 1 (cheaper) bans ``banned``; facility 2 does not. Return the loan's facility.

    ``None`` means the run was rejected (exit 1), which the agreed spec also allows.
    """
    input_dir = _dataset(
        tmp_path,
        facilities=[(1000, "0.05", 1, 1), (1000, "0.06", 2, 2)],
        covenants=[(1, None, 1, banned)],
        loans=[("0.1", 100, 1, "0.01", loan_state)],
    )
    out = tmp_path / "out"
    if main(["--input-dir", str(input_dir), "--output-dir", str(out)]) != 0:
        return None
    return read_text(out / "assignments.csv").splitlines()[1].split(",")[1]


@defect(2, "a lowercase loan state is normalised (or rejected), never funded past a ban")
def test_lowercase_loan_state_cannot_bypass_a_banned_state(tmp_path: Path) -> None:
    assert _assignment_of_vt_loan(tmp_path, "vt", "VT") in (None, "2")


@defect(2, "a lowercase banned_state still bans the upper-case loan state")
def test_lowercase_banned_state_still_bans(tmp_path: Path) -> None:
    assert _assignment_of_vt_loan(tmp_path, "VT", "vt") in (None, "2")


@defect(2, "Allocator keeps capacity non-negative even if handed a negative-amount loan")
def test_allocator_never_exceeds_capacity_after_a_negative_loan() -> None:
    allocator = Allocator([make_facility(id=1, amount=100)], [])
    # Rejecting the negative loan is acceptable; accepting it and growing capacity is not.
    with contextlib.suppress(ValueError, AssertionError):
        allocator.assign(make_loan(id=1, amount=-50))
    assert allocator.assign(make_loan(id=2, amount=150)) is None


# --- #3: BOM and padded headers -------------------------------------------------------------


def _assert_small_reference(input_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, err = run_cli(input_dir, capsys)
    assert (code, err.startswith("funded 3 of 3 loans")) == (0, True), err
    output = input_dir.parent / "output"
    for name in ("assignments.csv", "yields.csv"):
        assert read_text(output / name) == read_text(DATA / "small" / "output" / name)


@defect(3, "a UTF-8 BOM at the start of an input file is accepted")
@pytest.mark.parametrize("name", FILES)
def test_bom_prefixed_file_is_read_correctly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    input_dir = small_input(tmp_path)
    path = input_dir / name
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    _assert_small_reference(input_dir, capsys)


@defect(3, "spaces around header names are ignored")
@pytest.mark.parametrize("name", FILES)
def test_padded_header_names_are_read_correctly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    input_dir = small_input(tmp_path)
    header = rows_of(input_dir, name)[0].decode().split(",")
    replace_line(input_dir / name, 1, (" , ".join(header)).encode())
    _assert_small_reference(input_dir, capsys)


@defect(3, "the missing-column error lists the header that was actually found")
def test_missing_column_error_shows_the_header_found(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_dir = small_input(tmp_path)
    (input_dir / "banks.csv").write_bytes(b"id;name\n1;A\n2;B\n")
    code, err = run_cli(input_dir, capsys)
    assert code == 1
    assert err.startswith("error: ")
    assert "id;name" in err


@defect(3, "duplicate header names are an InputError")
@pytest.mark.parametrize("name", ["banks.csv", "loans.csv"])
def test_duplicate_header_names_are_rejected(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    input_dir = small_input(tmp_path)
    lines = rows_of(input_dir, name)
    first = lines[0].split(b",")[-1]  # a column the run does not otherwise depend on
    # Same width in every row, so only the duplicate name (not a ragged row) can be the problem.
    lines = [lines[0] + b"," + first, *(line + b",1" for line in lines[1:] if line)]
    (input_dir / name).write_bytes(b"\n".join(lines) + b"\n")
    assert_rejected(input_dir, capsys, name, line=None)


# --- #5: paired replacement and umask ---------------------------------------------------------


def _tmp_files(directory: Path) -> list[str]:
    return [p.name for p in directory.iterdir() if p.name.endswith(".tmp")]


@defect(5, "a failure computing yields must not replace assignments.csv on its own")
def test_yields_failure_leaves_both_previous_files_untouched(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    input_dir = small_input(tmp_path)
    output_dir = input_dir.parent / "output"
    assert main(["--input-dir", str(input_dir), "--output-dir", str(output_dir)]) == 0
    before = {p.name: p.read_bytes() for p in output_dir.iterdir()}
    replace_line(input_dir / "loans.csv", 2, b"0.15,100,7,0.01,MO")
    capsys.readouterr()
    with mock.patch.object(Allocator, "yields", side_effect=OSError("injected")):
        assert main(["--input-dir", str(input_dir), "--output-dir", str(output_dir)]) == 1
    assert {p.name: p.read_bytes() for p in output_dir.iterdir()} == before
    assert _tmp_files(output_dir) == []


@defect(5, "a failure while writing yields.csv must not replace assignments.csv on its own")
def test_yields_write_failure_leaves_both_previous_files_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import csv

    input_dir = small_input(tmp_path)
    output_dir = input_dir.parent / "output"
    assert main(["--input-dir", str(input_dir), "--output-dir", str(output_dir)]) == 0
    before = {p.name: p.read_bytes() for p in output_dir.iterdir()}
    replace_line(input_dir / "loans.csv", 2, b"0.15,100,7,0.01,MO")
    real_writer = csv.writer

    class FailsOnYields:
        def __init__(self, inner: Any) -> None:
            self._inner = inner
            self._yields = False

        def writerow(self, row: Any) -> object:
            self._yields = self._yields or row[0] == "facility_id"
            return self._inner.writerow(row)

        def writerows(self, rows: Any) -> object:
            if self._yields:
                raise OSError("injected: disk full")
            return self._inner.writerows(rows)

    monkeypatch.setattr(csv, "writer", lambda *a, **k: FailsOnYields(real_writer(*a, **k)))
    assert main(["--input-dir", str(input_dir), "--output-dir", str(output_dir)]) == 1
    assert {p.name: p.read_bytes() for p in output_dir.iterdir()} == before
    assert _tmp_files(output_dir) == []


posix_only = pytest.mark.skipif(sys.platform == "win32", reason="POSIX file modes")


@posix_only
@pytest.mark.parametrize(
    "umask",
    [
        0o077,  # owner-only is what the code produces today: a regression guard
        pytest.param(0o022, marks=defect(5, "outputs honour the umask (0644 under 022)")),
        pytest.param(0o002, marks=defect(5, "outputs honour the umask (0664 under 002)")),
        pytest.param(0o000, marks=defect(5, "outputs honour the umask (0666 under 000)")),
    ],
)
def test_output_files_have_mode_0o666_minus_umask(tmp_path: Path, umask: int) -> None:
    input_dir = small_input(tmp_path)
    output_dir = input_dir.parent / "output"
    previous = os.umask(umask)
    try:
        assert main(["--input-dir", str(input_dir), "--output-dir", str(output_dir)]) == 0
    finally:
        os.umask(previous)
    for name in ("assignments.csv", "yields.csv"):
        assert (output_dir / name).stat().st_mode & 0o777 == 0o666 & ~umask
