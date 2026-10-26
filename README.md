# Balance the Loan Books

A lender borrows from banking partners through debt facilities and uses those facilities to fund
customer loans. This program reads a stream of loans and assigns each one to a facility, respecting
every covenant (lending restriction) the banks place on their facilities.

## Problem

- A bank can offer several facilities. Each facility has an interest rate (what the lender pays to
  use it) and a capacity in cents.
- A covenant restricts which loans a facility may fund. Two kinds exist:
  - a maximum default likelihood: loans above it are not allowed;
  - a banned state: loans originating in that state are not allowed.
- A covenant applies to a single facility when `facility_id` is set, otherwise to every facility of
  the bank. A row with both a maximum default likelihood and a banned state is two covenants.
- Loans arrive in order and must be processed as a stream: a loan's assignment may not depend on
  later loans.
- Each loan goes to the cheapest facility (lowest interest rate) that satisfies all applicable
  covenants and still has enough capacity. A loan no facility can take stays unfunded.

## Input

Four CSV files per data set (`data/small/input/` and `data/large/input/`). Columns are read by
header name, so their order in the files does not matter:

| File | Columns |
| --- | --- |
| `facilities.csv` | `amount` (capacity, cents), `interest_rate`, `id`, `bank_id` |
| `banks.csv` | `id`, `name` |
| `covenants.csv` | `facility_id` (optional), `max_default_likelihood` (optional), `bank_id`, `banned_state` (optional) |
| `loans.csv` | `interest_rate`, `amount` (cents), `id`, `default_likelihood`, `state` |

## Expected yield

```
expected_yield = (1 - default_likelihood) * loan_interest_rate * amount
               - default_likelihood * amount
               - facility_interest_rate * amount
```

## Output

- `assignments.csv`: `loan_id,facility_id` (empty `facility_id` when unfunded).
- `yields.csv`: `facility_id,expected_yield`, the sum of the expected yields of the facility's loans,
  rounded to the nearest cent.

The `small` data set includes reference outputs for checking the implementation.

## Running it

Requires Python 3.15 and [uv](https://docs.astral.sh/uv/).

```
uv sync
uv run balance-the-loan-books data/small     # reads data/small/input, writes data/small/output
uv run balance-the-loan-books data/large
uv run balance-the-loan-books --input-dir IN --output-dir OUT
```

Data sets live under `data/<name>/{input,output}/`. A hand-worked example is in
`docs/worked-example.md`.

Behaviour decisions: ties on interest rate go to the lowest facility id; a maximum default
likelihood is inclusive; yields are computed with `Decimal` and rounded half up to whole cents;
`yields.csv` lists every facility, including those that funded nothing (yield 0).

## Development

```
uv run pytest && uv run ruff check . && uv run ruff format --check . && uv run mypy src tests
```
