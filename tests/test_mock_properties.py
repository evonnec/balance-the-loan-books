"""Property tests over whole datasets written to CSV and run through the real pipeline.

The program's output must equal the independent checker's output exactly, and must keep
holding under transformations that should not change it. Datasets come from ``datasets.py``;
the example count follows the Hypothesis profile (``HYPOTHESIS_PROFILE=dev`` for more).
"""

import tempfile
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

import checker
from balance_the_loan_books.pipeline import run
from datasets import STATES, Dataset, Row, datasets
from helpers import read_text, write_dataset

type Outputs = tuple[str, str]

# Each example here writes CSV files and runs the pipeline, so these properties draw a quarter of
# the profile's examples (decided when the module is imported, after conftest loads the profile).
file_backed = settings(max_examples=max(20, settings().max_examples // 4))


def outputs(dataset: Dataset) -> Outputs:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        input_dir = write_dataset(
            root,
            banks=dataset.banks,
            facilities=dataset.facilities,
            covenants=dataset.covenants,
            loans=dataset.loans,
        )
        run(input_dir, root / "out")
        return (
            read_text(root / "out" / "assignments.csv"),
            read_text(root / "out" / "yields.csv"),
        )


def reference(dataset: Dataset) -> Outputs:
    with tempfile.TemporaryDirectory() as raw:
        input_dir = write_dataset(
            Path(raw),
            banks=dataset.banks,
            facilities=dataset.facilities,
            covenants=dataset.covenants,
            loans=dataset.loans,
        )
        return checker.expected_text(input_dir)


@file_backed
@given(datasets())
def test_program_output_equals_independent_checker(dataset: Dataset) -> None:
    assert outputs(dataset) == reference(dataset)


@file_backed
@given(datasets())
def test_program_output_passes_checker_audit(dataset: Dataset) -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        input_dir = write_dataset(
            root,
            banks=dataset.banks,
            facilities=dataset.facilities,
            covenants=dataset.covenants,
            loans=dataset.loans,
        )
        run(input_dir, root / "out")
        problems = checker.validate(
            input_dir,
            root / "out" / "assignments.csv",
            root / "out" / "yields.csv",
            lowest_id_tie_break=True,
        )
    assert problems == []


def _shuffled(draw: st.DataObject, rows: Sequence[Row]) -> list[Row]:
    return draw.draw(st.permutations(list(rows)))


@file_backed
@given(datasets(), st.data())
def test_row_order_of_banks_facilities_and_covenants_is_irrelevant(
    dataset: Dataset, data: st.DataObject
) -> None:
    shuffled = replace(
        dataset,
        banks=_shuffled(data, dataset.banks),
        facilities=_shuffled(data, dataset.facilities),
        covenants=_shuffled(data, dataset.covenants),
    )
    assert outputs(shuffled) == outputs(dataset)


@file_backed
@given(datasets(), st.data())
def test_duplicating_a_covenant_row_changes_nothing(dataset: Dataset, data: st.DataObject) -> None:
    if not dataset.covenants:
        return
    index = data.draw(st.integers(0, len(dataset.covenants) - 1))
    doubled = replace(dataset, covenants=[*dataset.covenants, dataset.covenants[index]])
    assert outputs(doubled) == outputs(dataset)


@file_backed
@given(datasets())
def test_a_facility_banning_every_state_changes_nothing(dataset: Dataset) -> None:
    new_id = 1 + max(int(str(row[2])) for row in dataset.facilities)
    bank = 1
    cheapest = replace(
        dataset,
        facilities=[*dataset.facilities, (10_000_000, "0", new_id, bank)],
        covenants=[*dataset.covenants, *((new_id, None, bank, state) for state in STATES)],
    )
    before_assignments, before_yields = outputs(dataset)
    after_assignments, after_yields = outputs(cheapest)
    assert after_assignments == before_assignments
    expected = sorted(
        [*before_yields.splitlines()[1:], f"{new_id},0"], key=lambda line: int(line.split(",")[0])
    )
    assert after_yields.splitlines()[1:] == expected


def _scaled(dataset: Dataset, factor: int) -> Dataset:
    def facility(row: Row) -> Row:
        return (int(float(str(row[0]))) * factor, *row[1:])

    def loan(row: Row) -> Row:
        return (row[0], int(str(row[1])) * factor, *row[2:])

    return replace(
        dataset,
        facilities=[facility(r) for r in dataset.facilities],
        loans=[loan(r) for r in dataset.loans],
    )


@file_backed
@given(datasets())
def test_scaling_all_amounts_by_100_scales_yields_and_keeps_assignments(
    dataset: Dataset,
) -> None:
    base_assignments, base_yields = outputs(dataset)
    scaled_assignments, scaled_yields = outputs(_scaled(dataset, 100))
    assert scaled_assignments == base_assignments

    def values(text: str) -> list[tuple[str, int]]:
        return [(a, int(b)) for a, b in (line.split(",") for line in text.splitlines()[1:])]

    base, scaled = values(base_yields), values(scaled_yields)
    assert [f for f, _ in base] == [f for f, _ in scaled]
    for (_, small), (_, big) in zip(base, scaled, strict=True):
        # Each rounds an exact value to the nearest cent: they differ by at most
        # 100 * 0.5 (rounding the small one) + 0.5 (rounding the big one), i.e. 50 cents.
        assert abs(big - 100 * small) <= 50


@file_backed
@given(datasets())
def test_loan_stream_prefix_gets_identical_decisions(dataset: Dataset) -> None:
    half = replace(dataset, loans=dataset.loans[: len(dataset.loans) // 2])
    full_rows = outputs(dataset)[0].splitlines()[1:]
    half_rows = outputs(half)[0].splitlines()[1:]
    assert full_rows[: len(half_rows)] == half_rows
