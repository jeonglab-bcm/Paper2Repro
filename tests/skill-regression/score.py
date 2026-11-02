#!/usr/bin/env python3
"""Score an unattended Paper2Repro run against the known answers for a case.

Hard checks (any failure exits 1):
  - result.json exists and parses.
  - Table 1: each fitted psi rounds to the published value, lies within a relative
    tolerance of the reference fit, and is not just the printed value copied back.
  - Fig. 2: the data CSV uses the published grid, and the render file exists.
  - The transcript shows no access to the existing reproduction.

Reported only: Fig. 2 points identical to the reference series, the agent's
compare_figure.py metrics, cost, turns and duration.

Usage: python3 score.py --case <case dir> --project <project dir>
                        [--transcript run.jsonl] [--fig2-reference ref.csv]
                        [--report report.md] [--json score.json]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path


class Score:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []
        self.failed = False

    def hard(self, item: str, ok: bool, detail: str) -> None:
        self.failed |= not ok
        self.rows.append((item, detail, "pass" if ok else "FAIL"))

    def info(self, item: str, detail: str) -> None:
        self.rows.append((item, detail, "info"))

    def markdown(self, case: str) -> str:
        head = [f"## Skill regression: {case}", "", f"**Result: {'FAIL' if self.failed else 'pass'}**", "",
                "| Check | Detail | Status |", "| --- | --- | --- |"]
        return "\n".join(head + [f"| {a} | {b} | {c} |" for a, b, c in self.rows]) + "\n"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as f:
        return list(csv.DictReader(f))


def check_table1(s: Score, cfg: dict, result: dict) -> None:
    t1 = cfg["table1"]
    got = result.get("table1") or {}
    for site, exp in t1["sites"].items():
        item = f"Table 1 ψ, {site}"
        try:
            psi = float(got[site]["psi"])
        except (KeyError, TypeError, ValueError):
            s.hard(item, False, "missing or not a number")
            continue
        rounds = round(psi, t1["precision"]) == exp["paper"]
        rel = abs(psi - exp["reference"]) / exp["reference"]
        copied = psi == exp["paper"]
        ok = rounds and rel <= t1["rel_tol_vs_reference"] and not copied
        why = [] if ok else [m for m, bad in (("does not round to paper", not rounds),
                                             ("far from reference fit", rel > t1["rel_tol_vs_reference"]),
                                             ("equals the printed value", copied)) if bad]
        s.hard(item, ok, f"{psi:.6g} (paper {exp['paper']}, rel. diff from reference {rel:.1e})"
               + (f": {', '.join(why)}" if why else ""))


def check_fig2(s: Score, cfg: dict, result: dict, project: Path, ref_csv: Path | None) -> None:
    f2 = result.get("fig2") or {}
    g = cfg["fig2"]["grid"]
    path = project / str(f2.get("data_csv") or "")
    if not f2.get("data_csv") or not path.is_file():
        s.hard("Fig. 2 grid", False, "data_csv missing")
    else:
        try:
            rows = read_csv(path)
            psi = [float(r["psi"]) for r in rows]
            err = [float(r["error"]) for r in rows]
        except (KeyError, ValueError) as e:
            s.hard("Fig. 2 grid", False, f"cannot read columns psi,error: {e}")
            rows = []
        if rows:
            by = (g["to"] - g["from"]) / (g["n"] - 1)
            want = [g["from"] + i * by for i in range(g["n"])]
            same_n = len(psi) == g["n"]
            worst = max((abs(a - b) / b for a, b in zip(psi, want)), default=float("inf")) if same_n else float("inf")
            ok = same_n and worst <= cfg["fig2"]["grid_rel_tol"]
            s.hard("Fig. 2 grid", ok, f"{len(psi)} points, {min(psi):.3g} to {max(psi):.3g}"
                   + ("" if ok else f" (expected {g['n']} points, {g['from']:g} to {g['to']:g})"))
            if ref_csv and ref_csv.is_file() and ok:
                ref = [float(r["error"]) for r in read_csv(ref_csv)]
                same = sum(1 for a, b in zip(err, ref) if a == b)
                tol = cfg["fig2"].get("value_abs_tol", 1e-12)
                close = sum(1 for a, b in zip(err, ref) if abs(a - b) <= tol)
                s.info("Fig. 2 values vs reference", f"{same} of {len(ref)} bitwise identical, {close} within {tol:g}")
    render = f2.get("render")
    s.hard("Fig. 2 render", bool(render) and (project / str(render)).is_file(), str(render))
    rep = f2.get("compare_report")
    if rep and (project / rep).is_file():
        try:
            r = json.loads((project / rep).read_text())
            keys = [k for k in ("mean_abs_grey_difference", "chamfer_inside_panel_px", "shift_px",
                                "panel_size_difference_px", "warnings") if k in r]
            s.info("Fig. 2 compare_figure report", ", ".join(f"{k} {r[k]}" for k in keys) or "present")
        except json.JSONDecodeError:
            s.info("Fig. 2 compare_figure report", "unreadable")
    else:
        s.info("Fig. 2 compare_figure report", "not provided")


def check_transcript(s: Score, cfg: dict, transcript: Path | None) -> None:
    if not transcript:
        return
    if not transcript.is_file():
        s.hard("No access to existing reproduction", False, "transcript missing")
        return
    text = transcript.read_text(errors="replace")
    hits = sorted({m for m in cfg["transcript_leak_markers"] if m in text})
    s.hard("No access to existing reproduction", not hits, ", ".join(hits) or "no markers in transcript")
    results = []
    for line in text.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "result":
            results.append(ev)
    if results:  # cost is cumulative across result events; turns and durations are per segment
        s.info("Agent run", f"{results[-1].get('subtype')}, {sum(r.get('num_turns') or 0 for r in results)} turns, "
               f"{sum(r.get('duration_ms') or 0 for r in results) / 60000:.0f} min, "
               f"${results[-1].get('total_cost_usd') or 0:.2f}")
    else:
        s.info("Agent run", "no result event (cut off)")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", type=Path, required=True)
    ap.add_argument("--project", type=Path, required=True)
    ap.add_argument("--transcript", type=Path)
    ap.add_argument("--fig2-reference", type=Path)
    ap.add_argument("--report", type=Path)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)

    cfg = json.loads((a.case / "expected.json").read_text())
    s = Score()
    try:
        result = json.loads((a.project / "result.json").read_text())
        s.hard("result.json", True, "present")
    except (OSError, json.JSONDecodeError) as e:
        s.hard("result.json", False, f"missing or invalid: {e.__class__.__name__}")
        result = {}
    if result:
        check_table1(s, cfg, result)
        check_fig2(s, cfg, result, a.project, a.fig2_reference)
        cmd = (result.get("pipeline") or {}).get("command")
        s.info("Pipeline command", f"`{cmd}`" if cmd else "not provided")
    check_transcript(s, cfg, a.transcript)

    md = s.markdown(cfg["case"])
    print(md)
    if a.report:
        a.report.write_text(md)
    if a.json:
        a.json.write_text(json.dumps({"case": cfg["case"], "passed": not s.failed,
                                      "checks": [dict(zip(("check", "detail", "status"), r)) for r in s.rows]}, indent=1))
    return 1 if s.failed else 0


if __name__ == "__main__":
    sys.exit(main())
