"""CSV reading and writing. Columns are always looked up by header name, never by position."""

import os
import tempfile
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Protocol
lazy import csv

from balance_the_loan_books.models import (
    Bank,
    Cents,
    CovenantRow,
    Facility,
    FacilityId,
    Loan,
    LoanId,
)


class InputError(ValueError):
    """An input file is missing, lacks a column, or contains an unparseable value."""


def _parse_decimal(text: str) -> Decimal:
    try:
        value = Decimal(text.strip())
    except InvalidOperation:
        raise ValueError(f"not a number: {text!r}") from None
    if not value.is_finite():
        raise ValueError(f"not a finite number: {text!r}")
    return value


def _parse_cents(text: str) -> Cents:
    value = _parse_decimal(text)
    if value != value.to_integral_value():
        raise ValueError(f"amount is not a whole number of cents: {text!r}")
    return int(value)


def _parse_int(text: str) -> int:
    try:
        return int(text.strip())
    except ValueError:
        raise ValueError(f"not an integer: {text!r}") from None


def _optional[T](text: str | None, parse: Callable[[str], T]) -> T | None:
    if text is None or not text.strip():
        return None
    return parse(text)


def _undecodable_line(path: Path) -> int:
    """The 1-based physical line of the first byte sequence that is not valid UTF-8."""
    with path.open("rb") as handle:
        for number, raw in enumerate(handle, start=1):
            try:
                raw.decode("utf-8")
            except UnicodeDecodeError:
                return number
    return 1  # pragma: no cover - the caller only asks after a decode failure


def _rows(path: Path, required: tuple[str, ...]) -> Iterator[tuple[int, dict[str, str]]]:
    """Yield ``(line_number, row)`` for each data row, checking the header first.

    Rows whose field count differs from the header's, undecodable bytes and oversized fields
    are reported as `InputError` with the offending line.
    """
    try:
        handle = path.open(newline="", encoding="utf-8")
    except FileNotFoundError:
        raise InputError(f"missing input file: {path}") from None
    with handle:
        reader = csv.reader(handle)
        try:
            header = next(reader, [])
            missing = [name for name in required if name not in header]
            if missing:
                raise InputError(f"{path}: missing column(s): {', '.join(missing)}")
            width = len(header)
            for fields in reader:
                if not fields:
                    continue  # blank line
                if len(fields) != width:
                    raise InputError(
                        f"{path}, line {reader.line_num}: expected {width} fields, "
                        f"found {len(fields)}"
                    )
                yield reader.line_num, dict(zip(header, fields, strict=True))
        except UnicodeDecodeError:
            raise InputError(f"{path}, line {_undecodable_line(path)}: not valid UTF-8") from None
        except csv.Error as error:
            raise InputError(f"{path}, line {reader.line_num}: {error}") from None


def _records[R](
    path: Path, required: tuple[str, ...], build: Callable[[dict[str, str]], R]
) -> Iterator[R]:
    for line, row in _rows(path, required):
        try:
            yield build(row)
        except (ValueError, TypeError, KeyError, ArithmeticError) as error:
            raise InputError(f"{path}, line {line}: {error}") from error


def read_banks(path: Path) -> list[Bank]:
    return list(
        _records(
            path,
            ("id", "name"),
            lambda r: Bank(id=_parse_int(r["id"]), name=r["name"]),
        )
    )


def read_facilities(path: Path) -> list[Facility]:
    return list(
        _records(
            path,
            ("id", "bank_id", "interest_rate", "amount"),
            lambda r: Facility(
                id=_parse_int(r["id"]),
                bank_id=_parse_int(r["bank_id"]),
                interest_rate=_parse_decimal(r["interest_rate"]),
                amount=_parse_cents(r["amount"]),
            ),
        )
    )


def read_covenants(path: Path) -> list[CovenantRow]:
    return list(
        _records(
            path,
            ("bank_id", "facility_id", "max_default_likelihood", "banned_state"),
            lambda r: CovenantRow(
                bank_id=_parse_int(r["bank_id"]),
                facility_id=_optional(r["facility_id"], _parse_int),
                max_default_likelihood=_optional(r["max_default_likelihood"], _parse_decimal),
                banned_state=_optional(r["banned_state"], str.strip),
            ),
        )
    )


def iter_loans(path: Path) -> Iterator[Loan]:
    """Lazily yield loans in file order; the file is read one row at a time."""
    return _records(
        path,
        ("id", "interest_rate", "amount", "default_likelihood", "state"),
        lambda r: Loan(
            id=_parse_int(r["id"]),
            interest_rate=_parse_decimal(r["interest_rate"]),
            amount=_parse_cents(r["amount"]),
            default_likelihood=_parse_decimal(r["default_likelihood"]),
            state=r["state"].strip(),
        ),
    )


class RowSink(Protocol):
    """The part of a ``csv.writer`` this module uses."""

    def writerow(self, row: Iterable[object], /) -> object: ...
    def writerows(self, rows: Iterable[Iterable[object]], /) -> object: ...


@contextmanager
def _atomic_csv(path: Path, header: tuple[str, ...]) -> Iterator[RowSink]:
    """Write a CSV to a temp file beside ``path`` and move it into place on success."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(header)
            yield writer
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def write_assignments(path: Path, assignments: Iterable[tuple[LoanId, FacilityId | None]]) -> int:
    """Write ``loan_id,facility_id`` rows as they are produced; return the row count.

    Unfunded loans get an empty ``facility_id``.
    """
    count = 0
    with _atomic_csv(path, ("loan_id", "facility_id")) as writer:
        for loan_id, facility_id in assignments:
            writer.writerow((loan_id, "" if facility_id is None else facility_id))
            count += 1
    return count


def write_yields(path: Path, yields: Iterable[tuple[FacilityId, Cents]]) -> None:
    with _atomic_csv(path, ("facility_id", "expected_yield")) as writer:
        writer.writerows(yields)
