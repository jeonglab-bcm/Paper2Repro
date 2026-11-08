"""Command line: example-method INPUT.csv [-o OUTPUT.csv] [--window LOW HIGH]."""

from __future__ import annotations

import argparse
import sys

from . import (
    DEFAULT_WINDOW,
    __version__,
    doubling_times,
    example_path,
    read_curves,
    write_results,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="example-method",
        description="Doubling time of each well from OD600 growth curves.",
    )
    ap.add_argument("input", nargs="?", help="CSV with columns well, time_h, od600")
    ap.add_argument("-o", "--output", help="output CSV (default: standard output)")
    ap.add_argument(
        "--window",
        nargs=2,
        type=float,
        metavar=("LOW", "HIGH"),
        default=DEFAULT_WINDOW,
        help=f"OD range used for the fit (default: {DEFAULT_WINDOW[0]} {DEFAULT_WINDOW[1]})",
    )
    ap.add_argument(
        "--example-path", action="store_true", help="print the path of the bundled example input and exit"
    )
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = ap.parse_args(argv)

    if args.example_path:
        print(example_path())
        return 0
    if not args.input:
        ap.error("INPUT is required")
    results = doubling_times(read_curves(args.input), window=args.window)
    if args.output:
        with open(args.output, "w", newline="", encoding="utf-8") as f:
            write_results(results, f)
    else:
        write_results(results, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
