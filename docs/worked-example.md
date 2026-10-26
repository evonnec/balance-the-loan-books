# Worked example: the `small` data set

Facilities (from `data/small/input/`):

| Facility | Bank | Rate | Capacity |
| --- | --- | --- | --- |
| 1 | 2 | 0.06 | 126122 |
| 2 | 1 | 0.07 | 61104 |

Covenants: facility 2 allows a default likelihood of at most 0.09 and bans `MT`; facility 1
allows a default likelihood of at most 0.06 and bans `VT`.

Expected yield per loan:

```
(1 - default_likelihood) * loan_rate * amount
  - default_likelihood * amount
  - facility_rate * amount
```

## Loan 1 (amount 10552, rate 0.15, default likelihood 0.02, MO)

Both facilities allow it and both have room. Facility 1 is the cheaper (0.06 < 0.07), so it is
chosen. Remaining capacity of facility 1: 126122 - 10552 = 115570.

```
(1 - 0.02) * 0.15 * 10552 - 0.02 * 10552 - 0.06 * 10552
  = 1551.144 - 211.04 - 633.12 = 706.984
```

## Loan 2 (amount 51157, rate 0.15, default likelihood 0.01, VT)

Facility 1 bans `VT`, so only facility 2 is allowed. Remaining capacity of facility 2:
61104 - 51157 = 9947.

```
(1 - 0.01) * 0.15 * 51157 - 0.01 * 51157 - 0.07 * 51157
  = 7596.8145 - 511.57 - 3580.99 = 3504.2545
```

## Loan 3 (amount 74965, rate 0.35, default likelihood 0.06, AL)

Facility 2 no longer has room (9947 < 74965). Facility 1 allows it (0.06 is not above its
maximum of 0.06) and has 115570 left, so it is chosen. Remaining capacity of facility 1:
115570 - 74965 = 40605.

```
(1 - 0.06) * 0.35 * 74965 - 0.06 * 74965 - 0.06 * 74965
  = 24663.485 - 4497.9 - 4497.9 = 15667.685
```

## Totals

| Facility | Loans | Sum of expected yields | Rounded to the cent |
| --- | --- | --- | --- |
| 1 | 1, 3 | 706.984 + 15667.685 = 16374.669 | 16375 |
| 2 | 2 | 3504.2545 | 3504 |

These match `data/small/output/yields.csv`.
