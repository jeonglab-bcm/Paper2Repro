#!/usr/bin/env python3
"""Write the bundled example input and its expected output.

The input is synthetic: OD = 0.01 * 2 ** (t / d) for three wells with known doubling times d,
capped at a plateau of 0.9, plus a blank well. The expected output follows from the formula,
not from the package, so the package's tests check it against something independent.

Run from the package folder: python3 scripts/make_example_data.py
"""

import csv
import math
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "src" / "example_method" / "data"
WINDOW = (0.05, 0.5)
TIMES = [0.5 * i for i in range(21)]  # 0 to 10 h
WELLS = {"A1": 1.0, "A2": 1.5, "A3": 2.0}  # doubling time in hours
BLANK = ("B1", 0.02)


def od(t, d):
    return min(0.01 * 2 ** (t / d), 0.9)


def main():
    with open(DATA / "growth_curves.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["well", "time_h", "od600"])
        for well, d in WELLS.items():
            for t in TIMES:
                w.writerow([well, t, repr(od(t, d))])
        for t in TIMES:
            w.writerow([BLANK[0], t, BLANK[1]])

    with open(DATA / "growth_curves_expected.csv", "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["well", "n_points", "growth_rate_per_h", "doubling_time_h", "r_squared"])
        for well, d in WELLS.items():
            n = sum(WINDOW[0] <= od(t, d) <= WINDOW[1] for t in TIMES)
            w.writerow([well, n, repr(math.log(2) / d), repr(d), "1.0"])
        w.writerow([BLANK[0], 0, "", "", ""])


if __name__ == "__main__":
    main()
