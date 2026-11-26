"""End-to-end test of review_pr.py's loop with a fake agent, fake gh and fake nextflow.

Run: uv run --no-project --with-requirements ../assets/requirements.txt python test_review_pr.py
No API calls are made.
"""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import review_pr as R  # noqa: E402
from claude_agent_sdk import ResultMessage  # noqa: E402


def git(*a, cwd):
    subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True)


def make_world(tmp):
    """A bare 'origin', a clone on branch pr-branch, a skill root, fake gh and nextflow on PATH."""
    origin, repo, skill, bin_ = tmp / "origin.git", tmp / "fossil", tmp / "skill", tmp / "bin"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    subprocess.run(["git", "clone", "-q", str(origin), str(repo)], check=True, capture_output=True)
    for k, v in (("user.name", "t"), ("user.email", "t@t")):
        git("config", k, v, cwd=repo)
    git("checkout", "-q", "-b", "pr-branch", cwd=repo)
    paper = repo / "PMC1" / "figure-reproduction"
    paper.mkdir(parents=True)
    (paper / "main.nf").write_text("// fake\n")
    (repo / "PMC1" / "results.json").write_text(json.dumps({"items": [{"id": "fig2"}, {"id": "fig3"}]}))
    (repo / "PMC1" / "session").mkdir()
    (repo / "PMC1" / "session" / "ledger.json").write_text("{}")
    git("add", "-A", cwd=repo)
    git("commit", "-q", "-m", "init", cwd=repo)
    git("push", "-q", "origin", "pr-branch", cwd=repo)

    scripts = skill / "paper2repro" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "check_results.py").write_text("import sys; sys.exit(0)\n")

    bin_.mkdir()
    calls = tmp / "gh-calls.txt"
    (bin_ / "gh").write_text(
        "#!/bin/sh\n"
        f'echo "$@" >> {calls}\n'
        'if [ "$1 $2" = "pr view" ]; then\n'
        '  echo \'{"body":"PR body","headRefName":"pr-branch","url":"https://x/pull/7","number":7,'
        '"files":[{"path":"PMC1/results.json"}]}\'\n'
        "fi\n"
    )
    (bin_ / "nextflow").write_text("#!/bin/sh\nexit 0\n")
    for f in bin_.iterdir():
        f.chmod(0o755)
    os.environ["PATH"] = f"{bin_}:{os.environ['PATH']}"
    return origin, repo, skill, calls


def result(out, cost=1.0, sid="s1"):
    return ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=3,
                         session_id=sid, total_cost_usd=cost, result="done", structured_output=out)


def fake_query_factory(script, seen):
    """script: label-prefix -> list of outputs, consumed in order."""
    async def fake_query(prompt, options):
        role = ("review" if options.output_format["schema"] is R.F.FINDINGS_SCHEMA else
                "fix" if options.output_format and options.output_format["schema"] is R.F.FIX_SCHEMA else "lessons")
        who = "figures" if "Figures reviewer" in prompt else "claims" if "Claims reviewer" in prompt else role
        seen.append({"who": who, "cwd": options.cwd, "resume": options.resume, "budget": options.max_budget_usd,
                     "disallowed": list(options.disallowed_tools)})
        if who == "fix" and script.get("fix_edit"):
            script.pop("fix_edit")(Path(options.cwd))
        yield result(script[who].pop(0))
    return fake_query


def finding(item, sev="blocking"):
    return {"item": item, "area": "figure", "severity": sev, "problem": "axes doubled", "evidence": "overlay", "fix": "redraw"}


def run(tmp, script, budget=50.0, rounds=5):
    origin, repo, skill, calls = make_world(tmp)
    seen = []
    R.query = fake_query_factory(script, seen)
    R.fetch_paper = lambda pmcid, dest: (dest.write_text("paper"), dest)[1]
    args = R.argparse.Namespace(
        repo=str(repo), pr=7, paper=None, skill_root=str(skill), p2r=None, work=str(tmp / "work"),
        model="claude-opus-5-5", effort="high", budget=budget, rounds=rounds, nudges=2, gate_timeout=60,
        review_turns=10, fix_turns=10, no_subagents=False, no_push=False, no_lessons=True)
    code = asyncio.run(R.main_async(args))
    return code, repo, origin, calls, seen


def test_needs_human_after_nudge():
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)

        def edit(cwd):
            (cwd / "PMC1" / "fix.txt").write_text("fix")

        script = {
            "figures": [{"findings": [finding("Fig 2")]}, {"findings": [finding("fig2")]}],
            "claims": [{"findings": []}, {"findings": []}],
            "fix": [
                {"results": [{"key": "figure:fig2", "status": "needs_human", "what_changed": "", "hypotheses_tested": ["one"]}]},
                {"results": [{"key": "figure:fig2", "status": "needs_human", "what_changed": "", "hypotheses_tested": ["h1", "h2"]}]},
            ],
            "fix_edit": edit,
        }
        code, repo, origin, calls, seen = run(tmp, script)
        assert code == 1
        rec = json.loads((repo / "PMC1/session/review/paper2revise.json").read_text())
        assert rec["outcome"] == "human", rec["outcome"]
        assert [r["decision"] for r in rec["rounds"]] == ["fix", "human"]
        # the fixer was sent back once, by resuming its session
        fixes = [s for s in seen if s["who"] == "fix"]
        assert len(fixes) == 2 and fixes[1]["resume"] == "s1"
        # reviewers never saw the session folder and could not edit
        reviews = [s for s in seen if s["who"] in ("figures", "claims")]
        assert all("Edit" in s["disallowed"] and "Write" in s["disallowed"] for s in reviews)
        assert all(s["cwd"] != str(repo) for s in reviews)
        # the fix and the run record reached the remote branch
        log = subprocess.run(["git", "log", "--format=%s", "pr-branch"], cwd=origin, capture_output=True, text=True).stdout
        assert "Paper2Revise round 1" in log and "Paper2Revise: human" in log
        assert "fix.txt" in subprocess.run(["git", "ls-tree", "-r", "--name-only", "pr-branch"], cwd=origin,
                                           capture_output=True, text=True).stdout
        gh = calls.read_text()
        assert "--add-label needs-human" in gh and "pr comment 7" in gh
        comment = (tmp / "work" / "comment.md").read_text()
        assert "needs a human" in comment and "tested: h2" in comment


def test_clean_first_round():
    with tempfile.TemporaryDirectory() as t:
        script = {"figures": [{"findings": [finding("fig2", "minor")]}], "claims": [{"findings": []}], "fix": []}
        code, repo, origin, calls, seen = run(Path(t), script)
        assert code == 0
        assert "--add-label paper2revise-clean" in calls.read_text()
        assert not any(s["who"] == "fix" for s in seen)


def test_removed_item_is_caught_next_round():
    with tempfile.TemporaryDirectory() as t:
        def drop(cwd):
            p = cwd / "PMC1" / "results.json"
            p.write_text(json.dumps({"items": [{"id": "fig2"}]}))

        script = {
            "figures": [{"findings": [finding("fig3")]}, {"findings": []}],
            "claims": [{"findings": []}, {"findings": []}],
            "fix": [{"results": [{"key": "figure:fig3", "status": "fixed", "what_changed": "x", "hypotheses_tested": []}]}],
            "fix_edit": drop,
        }
        code, repo, origin, calls, seen = run(Path(t), script, rounds=2)
        rec = json.loads((repo / "PMC1/session/review/paper2revise.json").read_text())
        keys = [f["key"] for f in rec["rounds"][1]["findings"]]
        assert "pipeline:fig3" in keys, keys
        assert rec["outcome"] == "rounds"


def test_budget_stops_before_a_round():
    with tempfile.TemporaryDirectory() as t:
        code, repo, origin, calls, seen = run(Path(t), {"figures": [], "claims": [], "fix": []}, budget=5.0)
        rec = json.loads((repo / "PMC1/session/review/paper2revise.json").read_text())
        assert rec["outcome"] == "budget" and not seen


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("pass", name)
