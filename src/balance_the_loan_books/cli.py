"""Command line interface: ``balance-the-loan-books <dataset_dir>``."""

import sys
from collections.abc import Sequence
from pathlib import Path
lazy import argparse

from balance_the_loan_books import __version__
from balance_the_loan_books.io import InputError
from balance_the_loan_books.pipeline import run

EXIT_OK = 0
EXIT_BAD_INPUT = 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="balance-the-loan-books",
        description=(
            "Assign each loan to the cheapest facility whose covenants and capacity allow it. "
            "Reads <dataset_dir>/input/*.csv and writes <dataset_dir>/output/*.csv."
        ),
    )
    parser.add_argument(
        "dataset_dir", nargs="?", type=Path, help="directory with input/ and output/"
    )
    parser.add_argument("--input-dir", type=Path, help="override <dataset_dir>/input")
    parser.add_argument("--output-dir", type=Path, help="override <dataset_dir>/output")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return the process exit code (0 ok, 1 bad input, 2 usage error)."""
    parser = build_parser()
    args = parser.parse_args(argv)
    input_dir: Path | None = args.input_dir
    output_dir: Path | None = args.output_dir
    dataset_dir: Path | None = args.dataset_dir
    if dataset_dir is not None:
        input_dir = input_dir or dataset_dir / "input"
        output_dir = output_dir or dataset_dir / "output"
    if input_dir is None or output_dir is None:
        parser.error("give a dataset_dir, or both --input-dir and --output-dir")
    try:
        summary = run(input_dir, output_dir)
    except InputError, OSError:  # PEP 758: no parentheses, but also no ``as`` binding
        print(f"error: {sys.exception()}", file=sys.stderr)
        return EXIT_BAD_INPUT
    print(
        f"funded {summary.funded} of {summary.loans} loans across {summary.facilities} facilities;"
        f" wrote {output_dir}",
        file=sys.stderr,
    )
    return EXIT_OK
