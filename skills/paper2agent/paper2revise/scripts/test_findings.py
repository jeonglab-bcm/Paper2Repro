import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import findings as F  # noqa: E402


def f(item, area="figure", sev="blocking", problem="p"):
    return {"item": item, "area": area, "severity": sev, "problem": problem, "evidence": "e", "fix": "x"}


def test_norm_item():
    assert F.norm_item("Fig. 3B") == "fig3b"
    assert F.norm_item("Figure 3b") == "fig3b"
    assert F.norm_item("fig3b_overlay.png") == "fig3b"
    assert F.norm_item("Table 1") == "table1"
    assert F.norm_item("") == "general"


def test_merge_keeps_blocking_and_all_problems():
    m = F.merge([f("Fig 3B", sev="minor", problem="a")], [f("fig3b", problem="b"), f("t1", area="claim", sev="minor")])
    assert [x["key"] for x in m] == ["figure:fig3b", "claim:t1"]
    assert m[0]["severity"] == "blocking"
    assert [p["problem"] for p in m[0]["problems"]] == ["a", "b"]


def test_merge_rejects_bad_area():
    try:
        F.merge([f("x", area="style")])
    except ValueError:
        return
    raise AssertionError("bad area accepted")


def test_gate_findings():
    gate = {"ok": False, "steps": [{"name": "nextflow", "ok": False, "exit": 1, "log_tail": "boom"}, {"name": "check_results", "ok": True}]}
    out = F.gate_findings(gate)
    assert len(out) == 1 and out[0]["area"] == "pipeline" and out[0]["severity"] == "blocking"


def test_decide():
    blk = F.merge([f("fig2")])
    minor = F.merge([f("fig2", sev="minor")])
    assert F.decide(minor, []) == "clean"
    assert F.decide(blk, []) == "fix"
    earlier = [{"fix": {"results": [{"key": "figure:fig2", "status": "needs_human", "what_changed": "", "hypotheses_tested": ["a", "b"]}]}}]
    assert F.decide(blk, earlier) == "human"
    both = F.merge([f("fig2"), f("fig3")])
    assert F.decide(both, earlier) == "fix"
    assert [x["key"] for x in F.to_fix(both, earlier)] == ["figure:fig3"]


def test_unanswered():
    given = F.merge([f("fig2"), f("fig3"), f("fig4", sev="minor")])
    out = {"results": [
        {"key": "figure:fig2", "status": "fixed", "what_changed": "c", "hypotheses_tested": []},
        {"key": "figure:fig3", "status": "needs_human", "what_changed": "", "hypotheses_tested": ["only one"]},
    ]}
    assert F.unanswered(given, out) == ["figure:fig3"]
    assert F.unanswered(given, None) == ["figure:fig2", "figure:fig3"]


def test_summary_lists_open_items():
    r1 = {"gate": {"ok": True}, "findings": F.merge([f("fig2", problem="axes doubled")]),
          "fix": {"results": [{"key": "figure:fig2", "status": "needs_human", "what_changed": "", "hypotheses_tested": ["h1", "h2"]}]}}
    r2 = {"gate": {"ok": True}, "findings": F.merge([f("fig2", problem="axes doubled")])}
    text = F.summary({"outcome": "human", "rounds": [r1, r2], "cost_usd": 12.5, "budget_usd": 50, "rounds_path": "x"})
    assert "needs a human" in text and "figure:fig2" in text and "tested: h2" in text and "$12.50" in text


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
    print("ok")
