#!/usr/bin/env python3
"""Tests for the skill-regression harness: score.py and blind_skill.py.

Builds synthetic agent outputs (good, copied, wrong, leaking) and checks the verdicts.
Also blinds the real skill and fails if any answer marker survives.

Usage: python3 tests/skill-regression/test_score.py
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASE = HERE / "pmc4081639"
SKILL = HERE.parents[1] / "skills" / "paper2agent"
sys.path.insert(0, str(HERE))
import blind_skill  # noqa: E402
import score  # noqa: E402

CFG = json.loads((CASE / "expected.json").read_text())


def grid(frm=1e-11, to=1e-10, n=300):
    by = (to - frm) / (n - 1)
    return [frm + i * by for i in range(n)]


def make_project(root: Path, *, psi=None, xs=None, render=True, result=True) -> Path:
    p = root / "project"
    p.mkdir()
    xs = grid() if xs is None else xs
    (p / "fig2.csv").write_text("psi,error\n" + "".join(f"{x!r},{1e-5 * (i % 7)!r}\n" for i, x in enumerate(xs)))
    if render:
        (p / "fig2.png").write_bytes(b"\x89PNG")
    psi = psi or {k: v["reference"] for k, v in CFG["table1"]["sites"].items()}
    if result:
        (p / "result.json").write_text(json.dumps({
            "table1": {k: {"psi": v} for k, v in psi.items()},
            "fig2": {"data_csv": "fig2.csv", "render": "fig2.png", "compare_report": None},
            "pipeline": {"command": "nextflow run main.nf"},
        }))
    return p


def run(project: Path, transcript: Path | None = None, ref: Path | None = None) -> tuple[int, dict]:
    out = project.parent / "score.json"
    args = ["--case", str(CASE), "--project", str(project), "--json", str(out)]
    if transcript:
        args += ["--transcript", str(transcript)]
    if ref:
        args += ["--fig2-reference", str(ref)]
    with contextlib.redirect_stdout(io.StringIO()):
        code = score.main(args)
    data = json.loads(out.read_text())
    return code, {c["check"]: c for c in data["checks"]}


class ScoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_correct_run_passes(self):
        t = self.root / "t.jsonl"
        t.write_text(json.dumps({"type": "result", "subtype": "success", "num_turns": 3,
                                 "duration_ms": 60000, "total_cost_usd": 1.5}) + "\n")
        code, checks = run(make_project(self.root), t)
        self.assertEqual(code, 0, checks)
        self.assertIn("3 turns", checks["Agent run"]["detail"])

    def test_printed_values_copied_back_fail(self):
        psi = {k: v["paper"] for k, v in CFG["table1"]["sites"].items()}
        code, checks = run(make_project(self.root, psi=psi))
        self.assertEqual(code, 1)
        self.assertIn("equals the printed value", checks["Table 1 ψ, saliva"]["detail"])

    def test_psi_that_rounds_wrong_fails(self):
        psi = {k: v["reference"] for k, v in CFG["table1"]["sites"].items()}
        psi["tongue"] = 0.00790
        code, checks = run(make_project(self.root, psi=psi))
        self.assertEqual(code, 1)
        self.assertEqual(checks["Table 1 ψ, tongue"]["status"], "FAIL")
        self.assertEqual(checks["Table 1 ψ, saliva"]["status"], "pass")

    def test_missing_site_fails(self):
        psi = {k: v["reference"] for k, v in CFG["table1"]["sites"].items() if k != "tonsils"}
        code, checks = run(make_project(self.root, psi=psi))
        self.assertEqual(code, 1)
        self.assertEqual(checks["Table 1 ψ, tonsils"]["status"], "FAIL")

    def test_wrong_grid_fails(self):
        code, checks = run(make_project(self.root, xs=grid(frm=0.0)))
        self.assertEqual(code, 1)
        self.assertEqual(checks["Fig. 2 grid"]["status"], "FAIL")

    def test_wrong_grid_length_fails(self):
        code, checks = run(make_project(self.root, xs=grid(n=200)))
        self.assertEqual(code, 1)
        self.assertEqual(checks["Fig. 2 grid"]["status"], "FAIL")

    def test_missing_render_fails(self):
        code, checks = run(make_project(self.root, render=False))
        self.assertEqual(code, 1)
        self.assertEqual(checks["Fig. 2 render"]["status"], "FAIL")

    def test_missing_result_json_fails(self):
        code, checks = run(make_project(self.root, result=False))
        self.assertEqual(code, 1)
        self.assertEqual(checks["result.json"]["status"], "FAIL")

    def test_leak_in_transcript_fails(self):
        t = self.root / "t.jsonl"
        t.write_text(json.dumps({"type": "user", "content": "git clone https://github.com/jeonglab-bcm/fossil"}) + "\n")
        code, checks = run(make_project(self.root), t)
        self.assertEqual(code, 1)
        self.assertEqual(checks["No access to existing reproduction"]["status"], "FAIL")

    def test_identical_count_against_reference(self):
        p = make_project(self.root)
        ref = self.root / "ref.csv"
        lines = (p / "fig2.csv").read_text().splitlines()
        lines[5] = lines[5].split(",")[0] + ",9.0"
        ref.write_text("\n".join(lines) + "\n")
        code, checks = run(p, ref=ref)
        self.assertEqual(code, 0)
        self.assertEqual(checks["Fig. 2 values identical to reference"]["detail"], "299 of 300")


class BlindTests(unittest.TestCase):
    def test_real_skill_blinds_cleanly(self):
        with tempfile.TemporaryDirectory() as d:
            dest = Path(d) / "skill"
            leaks = blind_skill.blind(SKILL, dest, CFG["skill_redact_markers"], f"example-{CFG['case']}*.md")
            self.assertEqual(leaks, [])
            self.assertTrue((dest / "SKILL.md").is_file())
            self.assertTrue((dest / "paper2repro" / "scripts" / "compare_figure.py").is_file())
            example = dest / "paper2repro" / "references" / f"example-{CFG['case']}.md"
            self.assertIn("withheld", example.read_text())

    def test_redaction_keeps_other_sentences(self):
        line = "5. Accept a grid only when it fits. Example: `seq(1e-11, 1e-10)` worked."
        out = blind_skill.redact_line(line, ["1e-11"])
        self.assertIn("Accept a grid only when it fits.", out)
        self.assertNotIn("1e-11", out)
        self.assertIn("withheld", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
