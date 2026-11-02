#!/usr/bin/env python3
"""Tests for skill_checksum.py: stable across copies, sensitive to content, blind to caches.

Usage: python3 skills/paper2agent/scripts/test_skill_checksum.py
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import skill_checksum  # noqa: E402


def make_skill(root: Path) -> Path:
    (root / "sub").mkdir(parents=True)
    (root / "SKILL.md").write_text("---\nname: demo-skill\n---\n# Demo\n")
    (root / "sub" / "a.md").write_text("alpha\n")
    (root / "sub" / "B.md").write_text("beta\n")
    return root


class ChecksumTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = make_skill(Path(self.tmp.name) / "skill")

    def tearDown(self):
        self.tmp.cleanup()

    def test_copy_at_another_path_has_same_checksum(self):
        copy = Path(self.tmp.name) / "elsewhere" / "installed"
        shutil.copytree(self.root, copy)
        a, b = skill_checksum.checksum(self.root), skill_checksum.checksum(copy)
        self.assertEqual(a, b)
        self.assertEqual(a["skill"], "demo-skill")
        self.assertEqual(a["files"], 3)
        self.assertRegex(a["checksum"], r"^sha256:[0-9a-f]{64}$")

    def test_content_and_rename_change_checksum(self):
        base = skill_checksum.checksum(self.root)["checksum"]
        (self.root / "sub" / "a.md").write_text("alpha!\n")
        edited = skill_checksum.checksum(self.root)["checksum"]
        self.assertNotEqual(base, edited)
        (self.root / "sub" / "a.md").rename(self.root / "sub" / "c.md")
        self.assertNotEqual(edited, skill_checksum.checksum(self.root)["checksum"])

    def test_caches_are_ignored(self):
        base = skill_checksum.checksum(self.root)
        (self.root / "sub" / "__pycache__").mkdir()
        (self.root / "sub" / "__pycache__" / "x.cpython-313.pyc").write_bytes(b"\0")
        (self.root / "sub" / "y.pyc").write_bytes(b"\0")
        (self.root / ".DS_Store").write_bytes(b"\0")
        self.assertEqual(base, skill_checksum.checksum(self.root))

    def test_manifest_matches_sha256sum_format(self):
        lines = skill_checksum.manifest(self.root)
        self.assertEqual([line[66:].strip() for line in lines], ["SKILL.md", "sub/B.md", "sub/a.md"])
        want = hashlib.sha256(b"alpha\n").hexdigest() + "  sub/a.md\n"
        self.assertIn(want, lines)
        digest = hashlib.sha256("".join(lines).encode()).hexdigest()
        self.assertEqual(skill_checksum.checksum(self.root)["checksum"], "sha256:" + digest)

    def test_cli_defaults_to_the_containing_skill(self):
        out = subprocess.run([sys.executable, str(HERE / "skill_checksum.py")], check=True,
                             capture_output=True, text=True).stdout
        data = json.loads(out)
        self.assertEqual(data["skill"], "paper2agent")
        self.assertEqual(data, skill_checksum.checksum(HERE.parent))


if __name__ == "__main__":
    unittest.main(verbosity=2)
