loan 1 uses facility 1. 126122 decreases by 10552 (amt of loan 1)
now left with 115570 in facility 1
expected yield = (1 - default_likelihood) * loan_interest_rate * amount - default_likelihood * amount - facility_interest_rate * amount
(1 - 0.02) * .15 * 10552 - (0.02 * 10552) - (0.06 * 10552) = .98 * 1582.8 - 211.04 - 633.12 = 1551.144 - 211.04 - 633.12 = 706.984

loan 2 uses facility 2. 61104 decreases by 51157 (amt of loan 2)
now left with 9947 left in facility 2
(1 - .01) * .15 * 51157 - (0.01 * 51157) - (0.07 * 51157) = .99 * 7673.55 - 511.57 - 3580.99 = 7596.8145 - 511.57 - 3580.99 = 3504.2545

loan 3 uses facility 1. 115570 decreases by 74965 (amt of loan 3)
now left with 40,605 in facility 1
(1 - .06) * .35 * 74965 - (0.06 * 74965) - (0.06 * 74965) = .94 * 26237.75 - 4497.9 - 4497.9 = 24663.485 - 4497.9 - 4497.9 = 15667.685

facility id 1 total 16374.669 (round to the nearest int)
facility id 2 total 3504.2545 (round to the nearest int)