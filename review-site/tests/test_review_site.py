#!/usr/bin/env python3
"""Tests for review_site.py: the rules by themselves, then a whole site from a small repository.

    python3 review-site/tests/test_review_site.py
"""

import json
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import review_site as rs  # noqa: E402


def png(w=3, h=2):
    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + b"\xff\xff\xff" * w for _ in range(h))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def git(cwd, *args):
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.org", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.org", "PATH": __import__("os").environ["PATH"], "HOME": str(cwd)}
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, env=env)


RESULTS = {
    "schema": "paper2repro/results/v1",
    "paper": {"id": "PMC1", "title": "A paper <script>alert(1)</script>", "citation": "A et al. 2020", "doi": "10.1000/x1"},
    "items": [
        {"id": "fig1.curve", "label": "Fig. 1, the curve", "kind": "figure", "method": "pixels", "verdict": "partly",
         "pixels": {"tolerance_px": 2, "published_near_ours": 0.6, "ours_near_published": 0.7, "threshold": 0.75,
                    "controls": [{"name": "wrong", "kind": "wrong_input", "score": 0.3}]},
         "outputs": ["figure-reproduction/output/fig1_ours.png", "figure-reproduction/output/fig1_overlay.png"],
         "cause": {"category": "unknown", "status": "open", "summary": "Our curve is lower. Fig. 3 shows it too.",
                   "evidence": ["figure-reproduction/output/scores.json (gap)"],
                   "hypotheses": [{"hypothesis": "The database", "test": "Rerun", "result": "rejected"},
                                  {"hypothesis": "The seed", "test": "Rerun", "result": "rejected"}]}},
        {"id": "table1", "label": "Table 1, two methods", "kind": "table", "method": "values", "verdict": "differs",
         "values": {"tolerance": {"printed": True},
                    "fields": [{"name": "A ACC", "expected": "79.96", "observed": 78.88},
                               {"name": "A SN", "expected": "81.91", "observed": 81.912},
                               {"name": "B ACC", "expected": "70.00", "observed": 71.5},
                               {"name": "B SN", "expected": "60.0", "observed": 60.04}],
                    "exceptions": [{"field": "A ACC", "category": "paper_error", "evidence": "run/a.json: 79.91, not 79.96"}]},
         "assumptions": [{"what": "UniRef100 for nr", "source": "our_choice", "sensitivity": "0.5 points"}],
         "cause": {"category": "unknown", "status": "open", "summary": "Within 2 points.",
                   "hypotheses": [{"hypothesis": "The seed", "test": "Rerun", "result": "rejected"},
                                  {"hypothesis": "The database", "test": "Rerun", "result": "rejected"}]}},
        {"id": "text.n", "label": "Number of chains", "kind": "value", "method": "values", "verdict": "exact",
         "values": {"tolerance": {"printed": True}, "fields": [{"name": "chains", "expected": "525", "observed": 525}]}},
        {"id": "fig2", "label": "Fig. 2, a drawing", "kind": "figure", "method": "none", "verdict": "not_attempted",
         "cause": {"category": "not_a_result", "status": "explained", "summary": "A drawing."}},
    ],
}


class Rules(unittest.TestCase):
    def test_printed_tolerance_is_half_a_unit_of_the_last_digit(self):
        tol = {"printed": True}
        self.assertTrue(rs.field_matches({"expected": "81.91", "observed": 81.912}, tol))
        self.assertFalse(rs.field_matches({"expected": "79.96", "observed": 78.88}, tol))
        self.assertTrue(rs.field_matches({"expected": 0.5, "observed": 0.503}, {"abs": 0.005}))
        self.assertEqual(rs.fmt_obs(78.8765, "79.96"), "78.88")

    def test_fields_are_laid_out_as_the_papers_table(self):
        fs = rs.fields_of(RESULTS["items"][1])
        kind, (rows, cols, cells) = rs.shape_fields(fs)
        self.assertEqual((kind, rows, cols), ("matrix", ["A", "B"], ["ACC", "SN"]))
        self.assertTrue(cells[("A", "ACC")]["error"])
        self.assertTrue(cells[("A", "SN")]["match"])
        self.assertEqual(rs.measure_of(RESULTS["items"][1]), "2 of 3 as printed, 1 paper error")

    def test_numbered_fields_become_series(self):
        fs = [{"name": f"ACC at LG {i}", "a": 0.7 + i / 100, "b": 0.71, "match": False, "error": None} for i in range(1, 7)]
        kind, data = rs.shape_fields(fs)
        self.assertEqual(kind, "series")
        self.assertEqual(len(data["ACC at LG"]), 6)
        self.assertEqual(rs.shape_fields([{"name": "one", "a": 1, "b": 1}])[0], "list")

    def test_files_are_sorted_by_what_a_reviewer_reads(self):
        folders = ["PMC1"]
        cases = {
            "PMC1/package/src/m/core.py": "method",
            "PMC1/figure-reproduction/pipeline/experiments.py": "analysis",
            "PMC1/figure-reproduction/main.nf": "analysis",
            "PMC1/figure-reproduction/pipeline/check_results.py": "plumbing",
            "PMC1/package/tests/test_m.py": "tests",
            "PMC1/package/src/m/data/x.pssm": "generated",
            "PMC1/figure-reproduction/output/run/a.json": "generated",
            "PMC1/results.json": "generated",
            "PMC1/session/conversation.md": "generated",
            "site/PMC1/index.html": "generated",
            "PMC1/README.md": "docs",
            "README.md": "shared",
            "site/index.html": "shared",
            "tools/x.py": "shared",
        }
        for path, want in cases.items():
            self.assertEqual(rs.classify(path, folders)[0], want, path)

    def test_first_sentence_keeps_abbreviations_whole(self):
        self.assertEqual(rs.first_sentence("As Lou et al. 2014 define them. The rest.")[0], "As Lou et al. 2014 define them.")
        self.assertEqual(rs.first_sentence("See Fig. 3 for it. More.")[0], "See Fig. 3 for it.")

    def test_items_that_share_their_hypotheses_share_a_card(self):
        open_cards, explained = rs.cause_cards("PMC1", RESULTS["items"])
        self.assertEqual(len(open_cards), 1)
        self.assertEqual(open_cards[0]["title"], "Fig. 1 · Table 1")
        self.assertEqual(open_cards[0]["verdict"], "differs")
        self.assertEqual(explained, [])
        kinds = [c["kind"] for c in rs.decision_cards("PMC1", RESULTS["items"], [], [])]
        self.assertEqual(kinds, ["cause", "choices", "errors", "skipped"])

    def test_image_size(self):
        self.assertEqual(rs.image_size(png(7, 5)), (7, 5))
        self.assertIsNone(rs.image_size(b"<svg/>"))


class Site(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        up = root / "upstream"
        up.mkdir()
        git(up, "init", "-q", "-b", "main")
        (up / "README.md").write_text("# repo\n\nline\n")
        git(up, "add", "-A")
        git(up, "commit", "-q", "-m", "start")

        git(up, "checkout", "-q", "-b", "paper")
        fr = up / "PMC1" / "figure-reproduction"
        (fr / "published").mkdir(parents=True)
        (fr / "output").mkdir()
        (fr / "pipeline").mkdir()
        (up / "PMC1" / "package" / "src" / "m").mkdir(parents=True)
        (up / "PMC1" / "results.json").write_text(json.dumps(RESULTS))
        (fr / "published" / "figure-1.png").write_bytes(png(4, 3))
        (fr / "published" / "evil.svg").write_text("<svg onload='alert(1)'/>")
        (fr / "output" / "fig1_ours.png").write_bytes(png(4, 3))
        (fr / "output" / "fig1_overlay.png").write_bytes(png(4, 3))
        (up / "PMC1" / "package" / "src" / "m" / "core.py").write_text("def dt(x):\n    return x  # <b>not html</b>\n")
        (fr / "pipeline" / "check_results.py").write_text("print('zqxplumb')\n")
        (up / "README.md").write_text("# repo\n\nline about PMC1\n")
        git(up, "add", "-A")
        git(up, "commit", "-q", "-m", "paper")

        git(up, "checkout", "-q", "main")
        git(up, "checkout", "-q", "-b", "side")
        (up / "README.md").write_text("# repo\n\nanother line\n")
        (up / "tools.py").write_text("x = 1\n")
        git(up, "add", "-A")
        git(up, "commit", "-q", "-m", "side")
        git(up, "checkout", "-q", "main")

        clone = root / "clone"
        subprocess.run(["git", "clone", "-q", str(up), str(clone)], check=True, capture_output=True)
        git(clone, "update-ref", "refs/review/pr-7", "refs/remotes/origin/paper")
        prs = root / "prs.json"
        prs.write_text(json.dumps([{"number": 7, "title": "Reproduce PMC1", "user": {"login": "someone"},
                                    "head": {"ref": "paper"}, "updated_at": "2026-11-09T00:00:00Z"}]))
        cls.out = root / "site"
        rs.main(["--repo", "o/r", "--clone", str(clone), "--out", str(cls.out), "--prs-json", str(prs), "--no-fetch",
                 "--max-age-days", "100000"])
        cls.page = (cls.out / "pr-7" / "index.html").read_text()
        cls.index = (cls.out / "index.html").read_text()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_a_pull_request_and_a_branch_without_one_each_get_a_page(self):
        self.assertIn('href="pr-7/"', self.index)
        self.assertIn('href="branch-side/"', self.index)
        self.assertNotIn("branch-paper", self.index)  # the branch of the pull request is not listed twice
        self.assertTrue((self.out / "branch-side" / "index.html").exists())
        self.assertTrue((self.out / "assets" / "review.js").exists())

    def test_text_from_the_repository_is_escaped(self):
        for text in (self.page, self.index):
            self.assertNotIn("<script>alert(1)</script>", text)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", text)
        self.assertIn("&lt;b&gt;", self.page)

    def test_only_raster_pictures_are_copied(self):
        names = sorted(p.suffix for p in (self.out / "pr-7" / "img").iterdir())
        self.assertEqual(names, [".png", ".png", ".png"])
        self.assertIn('<figure class="pub">', self.page)
        self.assertIn('<figure class="ovl">', self.page)

    def test_the_page_is_laid_out_by_the_paper(self):
        self.assertIn('id="fig-1"', self.page)
        self.assertIn("Fig. 1 · Table 1", self.page)
        self.assertIn("2 of 2 tested causes ruled out", self.page)
        self.assertIn('<th scope="row">A</th>', self.page)
        self.assertIn("paper error", self.page)
        self.assertEqual(self.page.count('<article class="card'), 5)  # cause, choices, errors, outside, not attempted

    def test_only_the_method_and_what_is_shared_is_shown_as_code(self):
        self.assertIn("package/src/m/core.py", self.page)
        self.assertIn("not html", self.page)  # core.py is shown
        self.assertIn('class="l add"', self.page)  # README.md, as a diff
        self.assertNotIn("zqxplumb", self.page)  # check_results.py is listed, not shown
        self.assertIn("pipeline/check_results.py", self.page)

    def test_conflicts_between_open_changes_are_said(self):
        self.assertIn("Conflicts with side on README.md", self.page)
        self.assertIn("conflict with each other", self.index)

    def test_a_change_without_a_paper_still_gets_a_page(self):
        side = (self.out / "branch-side" / "index.html").read_text()
        self.assertIn("No Paper2Repro results.json", side)
        self.assertIn("tools.py", side)


if __name__ == "__main__":
    unittest.main(verbosity=1)
