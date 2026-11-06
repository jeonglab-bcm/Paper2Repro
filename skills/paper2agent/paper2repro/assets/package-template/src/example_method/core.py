"""Doubling time of each well from optical-density (OD600) growth curves.

This is the template's stand-in method. Replace this module with the paper's method.

The method keeps the points whose OD lies inside a window (the exponential phase by default),
fits log(OD) against time by least squares, and reports the growth rate, the doubling time
ln(2) / rate and the R^2 of the fit.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import IO

DEFAULT_WINDOW = (0.05, 0.5)
FIELDS = ["well", "n_points", "growth_rate_per_h", "doubling_time_h", "r_squared"]
INPUT_COLUMNS = {"well", "time_h", "od600"}


def read_curves(path: str | Path) -> dict[str, list[tuple[float, float]]]:
    """Read a CSV with columns well, time_h, od600 into {well: [(time_h, od600), ...]}."""
    curves: dict[str, list[tuple[float, float]]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = INPUT_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: missing columns {sorted(missing)}")
        for row in reader:
            curves.setdefault(row["well"], []).append((float(row["time_h"]), float(row["od600"])))
    return curves


def doubling_time(
    points: Iterable[tuple[float, float]], window: Sequence[float] = DEFAULT_WINDOW
) -> dict:
    """Fit one growth curve. Returns n_points, growth_rate_per_h, doubling_time_h, r_squared.

    Values are None when fewer than three points fall inside the window or the curve does not grow.
    """
    low, high = window
    if not 0 < low < high:
        raise ValueError(f"window must satisfy 0 < low < high, got {tuple(window)}")
    used = [(t, math.log(od)) for t, od in points if low <= od <= high]
    n = len(used)
    empty = {"n_points": n, "growth_rate_per_h": None, "doubling_time_h": None, "r_squared": None}
    if n < 3:
        return empty
    mean_t = sum(t for t, _ in used) / n
    mean_y = sum(y for _, y in used) / n
    sxx = sum((t - mean_t) ** 2 for t, _ in used)
    sxy = sum((t - mean_t) * (y - mean_y) for t, y in used)
    syy = sum((y - mean_y) ** 2 for _, y in used)
    if sxx == 0:
        return empty
    rate = sxy / sxx
    r_squared = 1.0 if syy == 0 else sxy * sxy / (sxx * syy)
    return {
        "n_points": n,
        "growth_rate_per_h": rate,
        "doubling_time_h": math.log(2) / rate if rate > 0 else None,
        "r_squared": r_squared,
    }


def doubling_times(
    curves: Mapping[str, Iterable[tuple[float, float]]], window: Sequence[float] = DEFAULT_WINDOW
) -> list[dict]:
    """Fit every well, in input order."""
    return [{"well": well, **doubling_time(points, window)} for well, points in curves.items()]


def write_results(results: Iterable[Mapping], out: IO[str]) -> None:
    """Write results as CSV with full float precision; missing values are empty cells."""
    writer = csv.DictWriter(out, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    for r in results:
        writer.writerow({k: "" if r[k] is None else repr(r[k]) if isinstance(r[k], float) else r[k] for k in FIELDS})


def read_results(path: str | Path) -> list[dict]:
    """Read a results CSV written by write_results (or the bundled expected output)."""
    rows = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(
                {
                    "well": row["well"],
                    "n_points": int(row["n_points"]),
                    **{k: float(row[k]) if row[k] else None for k in FIELDS[2:]},
                }
            )
    return rows
