#!/usr/bin/env python3
"""Tests for session_log.py on synthetic Claude Code stream-json transcripts.

The event shapes follow Claude Code 2.1 stream-json output: per-block assistant events
that repeat the message usage, tool results in user events, task_* events for subagents,
and a final result event with modelUsage.

Usage: python3 tests/skill-regression/test_session_log.py
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
sys.path.insert(0, str(HERE))
import session_log  # noqa: E402

AGENT_ID = "toolu_agent"


def usage(inp, out, read, write):
    return {"input_tokens": inp, "output_tokens": out, "cache_read_input_tokens": read, "cache_creation_input_tokens": write}


def assistant(mid, block, ts, parent=None, u=None):
    return {"type": "assistant", "parent_tool_use_id": parent, "timestamp": ts,
            "message": {"id": mid, "model": "claude-test", "content": [block], "usage": u or usage(2, 3, 100, 50)}}


def tool_result(tid, text, ts, error=False, parent=None):
    return {"type": "user", "parent_tool_use_id": parent, "timestamp": ts,
            "message": {"content": [{"type": "tool_result", "tool_use_id": tid, "content": text, "is_error": error}]}}


EVENTS = [
    {"type": "system", "subtype": "init", "session_id": "s1", "model": "claude-test", "claude_code_version": "2.1.0", "tools": ["Bash", "Agent"]},
    assistant("m1", {"type": "thinking", "thinking": ""}, "2026-11-01T00:00:00.000Z"),
    assistant("m1", {"type": "tool_use", "id": AGENT_ID, "name": "Agent", "input": {"description": "Fit psi", "prompt": "..."}}, "2026-11-01T00:00:01.000Z"),
    {"type": "system", "subtype": "task_started", "tool_use_id": AGENT_ID, "subagent_type": "general-purpose", "description": "Fit psi"},
    {"type": "user", "parent_tool_use_id": AGENT_ID, "timestamp": "2026-11-01T00:00:01.100Z", "message": {"content": [{"type": "text", "text": "Fit psi for saliva."}]}},
    assistant("m1", {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "Rscript fit.R\n--verbose"}}, "2026-11-01T00:00:02.000Z"),
    tool_result("t1", "psi = 0.0039", "2026-11-01T00:00:12.000Z"),
    assistant("m1", {"type": "tool_use", "id": "t2", "name": "Read", "input": {"file_path": "/x/missing.csv"}}, "2026-11-01T00:00:13.000Z"),
    tool_result("t2", "File does not exist.", "2026-11-01T00:00:13.500Z", error=True),
    assistant("m2", {"type": "tool_use", "id": "t3", "name": "Bash", "input": {"command": "ls"}}, "2026-11-01T00:00:14.000Z",
              parent=AGENT_ID, u=usage(1, 5, 0, 900)),
    tool_result("t3", "a\nb", "2026-11-01T00:00:15.000Z", parent=AGENT_ID),
    {"type": "system", "subtype": "task_notification", "tool_use_id": AGENT_ID, "status": "completed",
     "usage": {"total_tokens": 1234, "tool_uses": 1, "duration_ms": 4000}},
    tool_result(AGENT_ID, [{"type": "text", "text": "done"}], "2026-11-01T00:00:16.000Z"),
    assistant("m3", {"type": "text", "text": "All done."}, "2026-11-01T00:00:17.000Z", u=usage(2, 7, 300, 10)),
]
RESULT = {"type": "result", "subtype": "success", "is_error": False, "num_turns": 3, "duration_ms": 17000,
          "total_cost_usd": 1.25, "permission_denials": [], "subagent_stats": {"spawned": 1},
          "modelUsage": {"claude-test": {"inputTokens": 10, "outputTokens": 500, "cacheReadInputTokens": 400,
                                         "cacheCreationInputTokens": 960, "costUSD": 1.0},
                         "claude-small": {"inputTokens": 1, "outputTokens": 20, "cacheReadInputTokens": 0,
                                          "cacheCreationInputTokens": 0, "costUSD": 0.25}}}


class SessionLogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, events, name="t.jsonl"):
        p = self.root / name
        p.write_text("\n".join(json.dumps(e) for e in events) + "\nnot json\n")
        return p

    def test_complete_run_uses_final_totals(self):
        s = session_log.parse(self.write(EVENTS + [RESULT]))
        self.assertEqual(s["usage_source"], "final")
        self.assertEqual(s["meta"]["cost_usd"], 1.25)
        self.assertEqual(s["totals"], {"input": 11, "output": 520, "cache_read": 400, "cache_write": 960})
        self.assertEqual(s["models"]["claude-small"]["cost_usd"], 0.25)

    def test_tool_calls_errors_and_durations(self):
        s = session_log.parse(self.write(EVENTS + [RESULT]))
        self.assertEqual(s["tools"]["Bash"], {"calls": 2, "errors": 0, "seconds": 11.0, "unfinished": 0})
        self.assertEqual(s["tools"]["Read"]["errors"], 1)
        bash = next(x for x in s["entries"] if x.get("id") == "t1")
        self.assertEqual(bash["brief"], "Rscript fit.R")
        self.assertEqual(bash["duration_ms"], 10000)

    def test_subagent_work_is_attributed(self):
        s = session_log.parse(self.write(EVENTS + [RESULT]))
        self.assertEqual(s["subagents"][AGENT_ID]["status"], "completed")
        self.assertEqual(s["subagents"][AGENT_ID]["tokens"], 1234)
        self.assertEqual(s["usage_by_agent"][AGENT_ID]["cache_write"], 900)
        self.assertEqual(s["usage_by_agent"]["main"]["messages"], 2)
        nested = [x for x in s["entries"] if x.get("agent") == AGENT_ID]
        self.assertEqual([x["kind"] for x in nested], ["subagent_prompt", "tool"])

    def test_cut_off_run_falls_back_to_stream_usage(self):
        events = EVENTS[:9]  # stops after the failed Read, the subagent still running
        s = session_log.parse(self.write(events))
        self.assertEqual(s["usage_source"], "partial")
        self.assertIsNone(s["meta"]["cost_usd"])
        self.assertEqual(s["totals"], {"input": 2, "output": 3, "cache_read": 100, "cache_write": 50})  # m1 counted once
        self.assertEqual(s["tools"]["Agent"]["unfinished"], 1)
        self.assertEqual(s["subagents"][AGENT_ID]["status"], "running")
        md = session_log.summary_md(s)
        self.assertIn("Cost is not available", md)
        self.assertIn("n/a", md)

    def test_empty_thinking_is_skipped(self):
        s = session_log.parse(self.write(EVENTS + [RESULT]))
        self.assertNotIn("thinking", [x["kind"] for x in s["entries"]])

    def test_render_writes_all_outputs(self):
        t = self.write(EVENTS + [RESULT])
        prompt = self.root / "prompt.md"
        prompt.write_text("Reproduce Table 1. </script><b>")
        out = self.root / "out"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(session_log.main(["render", str(t), "--out", str(out), "--prompt", str(prompt)]), 0)
        for f in ("summary.md", "session.md", "session.json", "session.html"):
            self.assertTrue((out / f).is_file(), f)
        page = (out / "session.html").read_text()
        self.assertNotIn("</script><b>", page)  # transcript text cannot close the data block
        self.assertIn("**Prompt:** Reproduce Table 1.", (out / "session.md").read_text())

    def test_summary_compares_several_sessions(self):
        a = self.write(EVENTS + [RESULT], "a.jsonl")
        b = self.write(EVENTS[:9], "b.jsonl")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            session_log.main(["summary", str(a), str(b)])
        text = buf.getvalue()
        self.assertIn("| success |", text)
        self.assertIn("cut off", text)
        self.assertIn("$1.25", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
