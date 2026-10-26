from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest

from balance_the_loan_books.io import (
    InputError,
    iter_loans,
    read_banks,
    read_covenants,
    read_facilities,
    write_assignments,
    write_yields,
)
from balance_the_loan_books.models import Bank, CovenantRow, Facility, Loan
from helpers import read_text, write_csv

LOANS_HEADER = ("id", "interest_rate", "amount", "default_likelihood", "state")


class TestReadBanks:
    def test_reads_by_header_with_shuffled_columns(self, tmp_path: Path) -> None:
        path = write_csv(tmp_path / "banks.csv", ("name", "id"), [("Granite Savings", 1)])
        assert read_banks(path) == [Bank(id=1, name="Granite Savings")]

    def test_extra_columns_are_ignored(self, tmp_path: Path) -> None:
        path = write_csv(tmp_path / "banks.csv", ("id", "name", "notes"), [(1, "A", "x")])
        assert read_banks(path) == [Bank(id=1, name="A")]


class TestReadFacilities:
    HEADER = ("id", "bank_id", "interest_rate", "amount")

    def test_shuffled_columns(self, tmp_path: Path) -> None:
        path = write_csv(tmp_path / "f.csv", self.HEADER, [(2, 1, "0.07", 61104)])
        assert read_facilities(path) == [
            Facility(id=2, bank_id=1, interest_rate=Decimal("0.07"), amount=61104)
        ]

    def test_float_formatted_amount_is_accepted(self, tmp_path: Path) -> None:
        path = write_csv(tmp_path / "f.csv", self.HEADER, [(2, 1, "0.07", "61104.0")])
        assert read_facilities(path)[0].amount == 61104

    def test_non_integral_amount_is_rejected_with_line_number(self, tmp_path: Path) -> None:
        path = write_csv(
            tmp_path / "f.csv", self.HEADER, [(1, 1, "0.07", 10), (2, 1, "0.07", "5.5")]
        )
        with pytest.raises(InputError, match=rf"{path.name}, line 3: amount is not a whole number"):
            read_facilities(path)

    def test_bad_number_message_has_path_and_line(self, tmp_path: Path) -> None:
        path = write_csv(tmp_path / "f.csv", self.HEADER, [(1, 1, "abc", 10)])
        with pytest.raises(InputError) as info:
            read_facilities(path)
        assert str(info.value).startswith(f"{path}, line 2: ")
        assert "'abc'" in str(info.value)

    def test_bad_integer_id(self, tmp_path: Path) -> None:
        path = write_csv(tmp_path / "f.csv", self.HEADER, [("x1", 1, "0.07", 10)])
        with pytest.raises(InputError, match=r"line 2: not an integer: 'x1'"):
            read_facilities(path)


class TestReadCovenants:
    HEADER = ("facility_id", "max_default_likelihood", "bank_id", "banned_state")

    def test_blank_optional_fields_become_none(self, tmp_path: Path) -> None:
        path = write_csv(
            tmp_path / "c.csv",
            self.HEADER,
            [("", "", 1, ""), (3, "0.09", 1, " MT "), ("", "", 2, "VT")],
        )
        assert read_covenants(path) == [
            CovenantRow(bank_id=1),
            CovenantRow(
                bank_id=1, facility_id=3, max_default_likelihood=Decimal("0.09"), banned_state="MT"
            ),
            CovenantRow(bank_id=2, banned_state="VT"),
        ]

    def test_shuffled_columns(self, tmp_path: Path) -> None:
        path = write_csv(
            tmp_path / "c.csv",
            ("banned_state", "bank_id", "max_default_likelihood", "facility_id"),
            [("CA", 2, "", 1)],
        )
        assert read_covenants(path) == [CovenantRow(bank_id=2, facility_id=1, banned_state="CA")]

    def test_bad_optional_value_is_reported(self, tmp_path: Path) -> None:
        path = write_csv(tmp_path / "c.csv", self.HEADER, [("", "high", 1, "")])
        with pytest.raises(InputError, match=r"line 2: not a number: 'high'"):
            read_covenants(path)

    def test_missing_bank_id_is_reported(self, tmp_path: Path) -> None:
        path = write_csv(tmp_path / "c.csv", self.HEADER, [("", "", "", "VT")])
        with pytest.raises(InputError, match=r"line 2: not an integer: ''"):
            read_covenants(path)


class TestIterLoans:
    def test_parses_loans_with_shuffled_columns(self, tmp_path: Path) -> None:
        path = write_csv(
            tmp_path / "l.csv",
            ("state", "id", "default_likelihood", "amount", "interest_rate"),
            [(" MO ", 1, "0.02", 10552, "0.15")],
        )
        assert list(iter_loans(path)) == [
            Loan(
                id=1,
                interest_rate=Decimal("0.15"),
                amount=10552,
                default_likelihood=Decimal("0.02"),
                state="MO",
            )
        ]

    def test_float_formatted_amount_is_accepted(self, tmp_path: Path) -> None:
        path = write_csv(tmp_path / "l.csv", LOANS_HEADER, [(1, "0.1", "61104.0", "0", "MO")])
        assert next(iter_loans(path)).amount == 61104

    def test_non_integral_amount_is_rejected(self, tmp_path: Path) -> None:
        path = write_csv(tmp_path / "l.csv", LOANS_HEADER, [(1, "0.1", "61104.5", "0", "MO")])
        with pytest.raises(InputError, match="whole number of cents"):
            list(iter_loans(path))

    def test_header_only_file_yields_nothing(self, tmp_path: Path) -> None:
        path = write_csv(tmp_path / "l.csv", LOANS_HEADER, [])
        assert list(iter_loans(path)) == []

    def test_missing_file(self, tmp_path: Path) -> None:
        path = tmp_path / "nope.csv"
        with pytest.raises(InputError, match=r"missing input file: .*nope\.csv"):
            list(iter_loans(path))

    def test_missing_columns_are_named(self, tmp_path: Path) -> None:
        path = write_csv(tmp_path / "l.csv", ("id", "amount"), [(1, 2)])
        with pytest.raises(
            InputError, match=r"missing column\(s\): interest_rate, default_likelihood, state"
        ):
            list(iter_loans(path))

    def test_empty_file_reports_missing_columns(self, tmp_path: Path) -> None:
        path = tmp_path / "l.csv"
        path.write_bytes(b"")
        with pytest.raises(InputError, match="missing column"):
            list(iter_loans(path))

    def test_is_lazy_a_late_bad_row_does_not_fail_earlier_rows(self, tmp_path: Path) -> None:
        path = write_csv(
            tmp_path / "l.csv",
            LOANS_HEADER,
            [(1, "0.1", 10, "0", "MO"), (2, "0.1", 20, "0", "MO"), (3, "oops", 30, "0", "MO")],
        )
        stream: Iterator[Loan] = iter_loans(path)
        assert next(stream).id == 1
        assert next(stream).id == 2
        with pytest.raises(InputError, match=r"line 4: not a number: 'oops'"):
            next(stream)

    def test_error_line_number_counts_physical_lines(self, tmp_path: Path) -> None:
        path = tmp_path / "l.csv"
        path.write_bytes(
            b'id,interest_rate,amount,default_likelihood,state\n1,0.1,10,0,"M\nO"\n2,0.1,x,0,MO\n'
        )
        with pytest.raises(InputError, match=r"line 4: "):
            list(iter_loans(path))

    def test_crlf_input_is_accepted(self, tmp_path: Path) -> None:
        path = tmp_path / "l.csv"
        path.write_bytes(b"id,interest_rate,amount,default_likelihood,state\r\n1,0.1,10,0,MO\r\n")
        assert [loan.state for loan in iter_loans(path)] == ["MO"]


class TestWriters:
    def test_write_assignments_exact_bytes(self, tmp_path: Path) -> None:
        path = tmp_path / "assignments.csv"
        count = write_assignments(path, [(1, 2), (2, None), (3, 0)])
        assert count == 3
        assert path.read_bytes() == b"loan_id,facility_id\n1,2\n2,\n3,0\n"

    def test_write_yields_exact_bytes(self, tmp_path: Path) -> None:
        path = tmp_path / "yields.csv"
        write_yields(path, [(0, 0), (2, -150), (3, 16375)])
        assert path.read_bytes() == b"facility_id,expected_yield\n0,0\n2,-150\n3,16375\n"

    def test_empty_assignments_writes_header_only(self, tmp_path: Path) -> None:
        path = tmp_path / "assignments.csv"
        assert write_assignments(path, []) == 0
        assert read_text(path) == "loan_id,facility_id\n"

    def test_creates_missing_parent_directories(self, tmp_path: Path) -> None:
        path = tmp_path / "a" / "b" / "yields.csv"
        write_yields(path, [])
        assert path.is_file()

    def test_success_leaves_no_temp_files(self, tmp_path: Path) -> None:
        write_assignments(tmp_path / "assignments.csv", [(1, 1)])
        assert [p.name for p in tmp_path.iterdir()] == ["assignments.csv"]

    def test_overwrites_previous_file_on_success(self, tmp_path: Path) -> None:
        path = tmp_path / "assignments.csv"
        write_assignments(path, [(1, 1)])
        write_assignments(path, [(9, None)])
        assert path.read_bytes() == b"loan_id,facility_id\n9,\n"

    def test_failure_midway_keeps_previous_file_and_cleans_up(self, tmp_path: Path) -> None:
        path = tmp_path / "assignments.csv"
        write_assignments(path, [(1, 1)])
        before = path.read_bytes()

        def boom() -> Iterator[tuple[int, int | None]]:
            yield 5, 5
            raise RuntimeError("stream died")

        with pytest.raises(RuntimeError, match="stream died"):
            write_assignments(path, boom())

        assert path.read_bytes() == before
        assert [p.name for p in tmp_path.iterdir()] == ["assignments.csv"]

    def test_failure_on_first_write_creates_no_file(self, tmp_path: Path) -> None:
        path = tmp_path / "out" / "yields.csv"

        def boom() -> Iterator[tuple[int, int]]:
            raise RuntimeError("nope")
            yield 1, 1  # pragma: no cover - makes this a generator

        with pytest.raises(RuntimeError):
            write_yields(path, boom())
        assert list(path.parent.iterdir()) == []
