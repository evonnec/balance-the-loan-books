# Balance the Loan Books

A small, dependency-free Python 3.15 command-line tool for a lender that funds customer loans
from several bank debt facilities. It streams a list of loans, assigns each one to the cheapest
facility whose covenants and remaining capacity allow it, and reports the expected yield per
facility. Money math uses `Decimal` (no binary-float error), output is deterministic, and the
covenant rules and the equal-rate tie-break are pluggable.

## Problem

- A bank offers one or more facilities. A facility has an interest rate (what the lender pays to
  draw on it) and a capacity in cents.
- A covenant restricts which loans a facility may fund. Two kinds exist: a **maximum default
  likelihood** (loans above it are refused) and a **banned state** (loans originating there are
  refused).
- A covenant row names a `bank_id` and optionally a `facility_id`. With a `facility_id` it binds
  that facility only; without one it binds every facility of the bank. One row may carry both
  restrictions, which count as two covenants.
- Loans arrive in order and are processed as a stream: a loan's assignment never depends on later
  loans.
- Each loan goes to the cheapest facility (lowest interest rate) that satisfies every applicable
  covenant and has enough capacity left. A loan nothing can take stays unfunded.
- Expected yield of a loan on a facility:

  ```
  (1 - default_likelihood) * loan_rate * amount
    - default_likelihood * amount
    - facility_rate * amount
  ```

  A facility's yield is the sum over its loans, rounded to whole cents.

A hand-worked example is in [docs/worked-example.md](docs/worked-example.md).

## Quick start

Requires Python 3.15 and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```
uv sync
uv run balance-the-loan-books data/small --output-dir out/small    # reads data/small/input
uv run balance-the-loan-books data/large --output-dir out/large
```

Always pass `--output-dir` when trying the bundled data: without it the tool writes into
`data/<name>/output`, which holds the committed reference results that the golden tests compare
against.

Install it as a standalone tool, or run the module directly:

```
uv tool install .                               # or: pipx install .
balance-the-loan-books data/small --output-dir out/small

uv run python -m balance_the_loan_books data/small --output-dir out/small
```

## CLI reference

```
balance-the-loan-books [dataset_dir] [--input-dir DIR] [--output-dir DIR]
                        [--tie-break {lowest-id,file-order,highest-id}] [--version]
```

| Argument | Meaning |
| --- | --- |
| `dataset_dir` | Directory holding `input/` and `output/`. |
| `--input-dir` | Read the CSVs from here instead of `<dataset_dir>/input`. |
| `--output-dir` | Write results here instead of `<dataset_dir>/output` (created if missing). |
| `--tie-break` | Order of facilities with equal interest rates: `lowest-id` (default), `file-order` (row order of `facilities.csv`) or `highest-id`. See [Tie-break](#tie-break-among-equal-rates). |
| `--version` | Print the version and exit. |

Give either `dataset_dir` or both `--input-dir` and `--output-dir`. A one-line summary
(`funded N of M loans across F facilities`) goes to stderr.

| Exit code | Meaning |
| --- | --- |
| 0 | Success. |
| 1 | Bad input (missing file or column, unparseable value, dangling reference) or an I/O error. The message on stderr starts with `error:` and, for row problems, names `path, line N`. |
| 2 | Usage error (argparse). |

## Input and output formats

Columns are looked up by header name, so column order in the files does not matter; extra
columns are ignored. The orders below are those of the bundled files.

| File | Columns | Notes |
| --- | --- | --- |
| `input/banks.csv` | `id,name` | |
| `input/facilities.csv` | `amount,interest_rate,id,bank_id` | `amount` is capacity in cents; `61104.0` is accepted, `61104.5` is rejected. |
| `input/covenants.csv` | `facility_id,max_default_likelihood,bank_id,banned_state` | `facility_id`, `max_default_likelihood` and `banned_state` may be blank. |
| `input/loans.csv` | `interest_rate,amount,id,default_likelihood,state` | `amount` in whole cents. |
| `output/assignments.csv` | `loan_id,facility_id` | One row per loan, in input order; `facility_id` is empty when unfunded. |
| `output/yields.csv` | `facility_id,expected_yield` | One row per facility, sorted by id, including those that funded nothing (`0`). Whole cents. |

Output uses `\n` line endings on every platform.

## Behaviour decisions

The problem statement leaves these open; each is covered by a test.

| Decision | Reason |
| --- | --- |
| Facilities are tried cheapest first; equal rates go to the lowest facility id (`--tie-break lowest-id`, the default). | Output does not change when the rows of `facilities.csv` are re-sorted. This choice decides whether loan 425 of `data/large` is funded; see [Tie-break](#tie-break-among-equal-rates). |
| A loan fits when `amount <= remaining capacity`. | A facility may be filled exactly. |
| The maximum default likelihood is inclusive (`<=`). | "At most" reads as inclusive, and the worked example needs it (loan 3 sits exactly on facility 1's 0.06). |
| A covenant row with a blank `facility_id` binds the whole bank. | That is what the blank means. |
| A row with both a likelihood and a state is two covenants. | Both restrictions must hold. |
| All money math is `Decimal` (exact within the default 28-significant-digit context, ample for cent amounts); rounding is `ROUND_HALF_UP` to whole cents, once per facility on the exact sum. | No binary-float error; rounding per loan would accumulate error. Halves round away from zero, so `-0.5` becomes `-1`. |
| `yields.csv` lists every facility, sorted by id, including id `0` and unused facilities. | A complete, stable report. |
| Unfunded loans appear in `assignments.csv` with an empty `facility_id`. | Every input loan has exactly one output row. |
| Each output file is written atomically (hidden temp file, then rename). | A failure never leaves a truncated file. The two files are replaced one after the other, so a failure while writing `yields.csv` can leave a new `assignments.csv` next to an old `yields.csv`. |
| Bad input raises `InputError` with a `path, line N:` message; the CLI prints one `error:` line and exits 1. Detected: missing file or column, a row whose field count differs from the header's, bytes that are not UTF-8, a field over the csv size limit, unparseable numbers, and non-finite numbers (`NaN`, `sNaN`, `Infinity`). | Actionable errors, and no silent misparse: an unquoted `10,552` is a six-field row and is rejected rather than read as a different loan. Blank lines are skipped. Range and consistency checks are tracked separately. |
| State matching is case-sensitive and exact (after trimming whitespace). | Postal codes are expected in upper case on both sides; covered by a test that documents it. |

## Design

```
src/balance_the_loan_books/
  models.py     frozen dataclasses: Loan, Facility, Bank, CovenantRow; type aliases
  yields.py     expected_yield, round_cents (Decimal arithmetic)
  covenants.py  Covenant ABC, MaxDefaultLikelihood, BannedState, DEFAULT_BUILDERS
  allocator.py  Allocator, TieBreak: ordered facility states, assign(loan) -> facility id | None
  io.py         CSV readers (by header), lazy iter_loans, atomic writers, InputError
  pipeline.py   validate_references, run(input_dir, output_dir) -> RunSummary
  cli.py        argparse front end, exit codes
```

Data flow: `run` reads banks, facilities and covenant rows eagerly, validates references,
builds one `Allocator`, then pulls loans from the lazy `iter_loans` reader. Each decision is
passed to the writer as it is made and streamed into a hidden temp file; `assignments.csv` appears
when the stream ends, and `yields.csv` is written after it.

### Adding a covenant type

Subclass `Covenant`, write a builder that returns an instance or `None` for rows that do not use
it, and pass the builders to the allocator. There is no global registry: `DEFAULT_BUILDERS` is an
immutable tuple, and each `Allocator` (or `run`) takes its own `builders`, so allocators with
different covenant sets can coexist in one process.

```python
from dataclasses import dataclass
from typing import override

from balance_the_loan_books import Allocator, DEFAULT_BUILDERS
from balance_the_loan_books.covenants import Covenant
from balance_the_loan_books.models import CovenantRow, Loan


@dataclass(frozen=True, slots=True)
class MinAmount(Covenant):
    minimum: int

    @override
    def allows(self, loan: Loan) -> bool:
        return loan.amount >= self.minimum


def build_min_amount(row: CovenantRow) -> Covenant | None:
    # Read a new CovenantRow field; return None when the row does not set it.
    return None


allocator = Allocator(facilities, covenant_rows, builders=(*DEFAULT_BUILDERS, build_min_amount))
# or: run(input_dir, output_dir, builders=(*DEFAULT_BUILDERS, build_min_amount))
```

A new CSV column also needs a field on `CovenantRow` and a parse step in `io.read_covenants`.
`tests/test_covenants.py` shows a custom covenant being honoured by one allocator while another
in the same process uses the defaults.

### Streaming and atomic writes

Loans are read one row at a time and decisions are written as they are made, so the program never
holds the loan list. Each output file is written to a temp file next to its destination and moved
into place only on success; an error mid-stream (for example a malformed row late in
`loans.csv`) leaves any previous output untouched and removes the temp file.

### Complexity

With F facilities, C covenant rows, k covenants per facility and N loans:

- setup: O(F log F + C·F) (sort facilities, match every row against every facility);
- per loan: O(F·k) worst case, with early exit at the first facility that accepts;
- memory: O(F·k + C), independent of N. A bank-wide covenant row is instantiated once per
  facility of that bank, so in the worst case k grows with C and memory is O(F·C).

## Results on the bundled data sets

| Data set | Loans | Funded | Outcome |
| --- | --- | --- | --- |
| `data/small` | 3 | 3 | Output equals the committed reference exactly (`1,1 / 2,2 / 3,1`; yields 16375 and 3504). |
| `data/large` | 425 | 424 | Default (`lowest-id`) output equals the committed files in `data/large/output`. Loan 425 is unfunded. |

### Tie-break among equal rates

Several facilities share an interest rate, so the order among them matters. On `data/large` it
decides the headline result. Measured by running each policy:

| `--tie-break` | Funded | Unfunded | Assignments that differ from `lowest-id` |
| --- | --- | --- | --- |
| `lowest-id` (default) | 424 of 425 | loan 425 | - |
| `file-order` | 425 of 425 | none | 158 of 425 |
| `highest-id` | 425 of 425 | none | 313 of 425 |

Loan 425 (amount 86614, state `AZ`) is the last loan in the file. Under `lowest-id` the roomiest
facility when it arrives is facility 13 with 77357 left, which is too little. Under `file-order`
or `highest-id` earlier loans land on other equal-rate facilities, facility 13 still has 87402,
and it takes loan 425. So the loan is not unfundable in itself: whether it is funded depends on
the tie-break.

`lowest-id` is the default because its results do not depend on the row order of
`facilities.csv` (reversing the rows gives byte-identical output), and it keeps the committed
reference outputs valid. The trade-off is that funding loan 425 is a property of this data set's
tie order, not of any general rule: ordering ties by capacity (not offered as a policy) leaves 425
unfunded again. The problem statement accepts that tie ordering may leave the last large loan
unassigned.

Covenant readings are also constrained by the guarantee that loans can be placed: reading the
maximum default likelihood as exclusive leaves 36 loans unfunded on `data/large` under every
tie-break, while the inclusive reading chosen here leaves at most loan 425.

In code: `Allocator(facilities, rows, tie_break=TieBreak.FILE_ORDER)` or
`run(input_dir, output_dir, tie_break=TieBreak.FILE_ORDER)`.

## Development

```
uv sync --locked
uv run pytest                    # includes coverage, fails under 100%
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv build
```

The suite has per-module unit tests, golden tests against the committed outputs, and
[hypothesis](https://hypothesis.readthedocs.io/) property tests that compare the allocator with a
brute-force oracle (the profile is derandomized, 200 examples). Add `--no-cov` when running a
subset, since the coverage threshold applies to the whole suite.

## Python 3.15 notes

- **Lazy imports (PEP 810):** `lazy import csv` in `io.py` and `lazy import argparse` in `cli.py`
  defer loading those modules until first use. The CLI builds its parser and reads CSV on every
  run, so both modules are loaded anyway; the only saving is for code that imports the library
  without running the CLI or reading files.
- **Unparenthesised `except` (PEP 758):** `except InputError, OSError:` in `cli.py`. Without
  parentheses the clause cannot bind `as`, so the error is read from `sys.exception()`.
- **`type` aliases (PEP 695):** `Cents`, `FacilityId`, `LoanId`, `BankId` in `models.py` and
  `CovenantBuilder` in `covenants.py`; generic functions use the `def f[T]` syntax in `io.py`.
- `typing.override` marks the covenant `allows` methods.

## Releasing

See [docs/RELEASING.md](docs/RELEASING.md).

## Future work

Design notes, not commitments.

- **More covenant types.** Likely candidates are a minimum or maximum loan amount, a per-state
  exposure cap, and a concentration limit (share of a facility's capacity per state). Exposure
  caps need per-facility running state; that fits behind the same `Covenant` interface if
  `allows` gains access to the facility's current usage.
- **Service form.** Wrap `Allocator` in a long-lived service: load facilities and covenants at
  start-up, expose `POST /loans` returning the chosen facility and `GET /yields`, and persist
  remaining capacity transactionally so a restart or a second replica cannot over-allocate.
  Assignment must stay serialised per facility pool (single writer or row-level locking).
- **Batch optimisation.** Greedy cheapest-first is the policy the problem specifies for the stream.
  It maximises each loan's own yield, but not total yield or the number of funded loans, even
  online: a low-yield loan can use up a cheap facility that a later loan needed. With all loans in
  hand, assignment is a capacitated matching problem
  (min-cost flow or an ILP) that can fund more loans or earn more yield. It would be an
  alternative `run` mode, with the streaming path kept as the default.

## License

GPL-3.0-or-later. See [LICENSE](LICENSE).
