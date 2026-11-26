#!/usr/bin/env python3
"""Review and revise one Paper2Repro pull request until it holds (Claude Agent SDK).

Run from a checkout of the pull request's head branch in fossil:

  review_pr.py --repo . --pr 35 --skill-root ~/.claude/skills/paper2agent --p2r ../Paper2Repro

Each round: a full clean rerun (gate), two blind reviewers (figures, claims), a decision
(findings.py), then a fixer and a push. Stops when clean, when only needs_human findings are
left, after --rounds rounds, or at --budget USD. Then posts one comment, sets a label and
runs the lessons step against Paper2Repro. See ../SKILL.md and ../references/deploy.md.

Needs: claude-agent-sdk, git, gh (GH_TOKEN for fossil; P2R_GH_TOKEN for Paper2Repro),
nextflow and the paper's toolchain, ANTHROPIC_API_KEY.
"""

import argparse
import asyncio
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import findings as F  # noqa: E402

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query  # noqa: E402

REFS = Path(__file__).resolve().parent.parent / "references"
LESSONS_BRANCH = "paper2revise/lessons"
P2R_REPO = "jeonglab-bcm/Paper2Repro"
LABEL_CLEAN, LABEL_HUMAN = "paper2revise-clean", "needs-human"
LESSONS_RESERVE_USD = 3.0
MIN_ROUND_USD = 4.0


def log(msg):
    print(f"[paper2revise {dt.datetime.now():%H:%M:%S}] {msg}", flush=True)


def sh(cmd, cwd=None, check=True, env=None, timeout=None):
    r = subprocess.run(cmd, cwd=cwd, env=env, timeout=timeout, text=True, capture_output=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"{' '.join(map(str, cmd))} exited {r.returncode}: {r.stderr[-2000:]}")
    return r


def brief(name, **values):
    text = (REFS / name).read_text()
    for k, v in values.items():
        text = text.replace("{" + k + "}", str(v))
    return text


class Budget:
    def __init__(self, total):
        self.total, self.spent = total, 0.0

    def remaining(self):
        return self.total - self.spent

    def for_step(self, share=1.0, reserve=LESSONS_RESERVE_USD):
        return max(0.5, (self.remaining() - reserve) * share)


async def run_agent(label, prompt, opts, budget, logdir):
    """Run one agent to completion. Returns (structured_output, ResultMessage or None)."""
    log(f"{label}: start (cap ${opts.max_budget_usd:.2f})")
    result = None
    try:
        async for m in query(prompt=prompt, options=opts):
            if isinstance(m, ResultMessage):
                result = m
    except Exception as e:  # the CLI process died; record and let the caller decide
        log(f"{label}: error {e!r}")
    cost = (result.total_cost_usd or 0.0) if result else 0.0
    budget.spent += cost
    record = {
        "label": label, "cost_usd": cost,
        "subtype": result.subtype if result else "crashed",
        "is_error": result.is_error if result else True,
        "num_turns": result.num_turns if result else 0,
        "session_id": result.session_id if result else None,
        "result": (result.result or "")[-4000:] if result else "",
        "structured_output": result.structured_output if result else None,
    }
    (logdir / f"{label}.json").write_text(json.dumps(record, indent=2))
    log(f"{label}: {record['subtype']}, {record['num_turns']} turns, ${cost:.2f} (total ${budget.spent:.2f})")
    return (result.structured_output if result and not result.is_error else None), result


# ---------------------------------------------------------------- pull request and paper

def pr_info(repo, pr):
    out = sh(["gh", "pr", "view", str(pr), "--json", "body,headRefName,url,files,number"], cwd=repo).stdout
    return json.loads(out)


def detect_paper(repo, info):
    ids = sorted({m.group(1) for f in info.get("files", [])
                  if (m := re.match(r"^(PMC\d+)/", f["path"])) and (Path(repo) / m.group(1) / "results.json").exists()})
    if len(ids) != 1:
        raise SystemExit(f"expected one paper folder with results.json in the pull request, found {ids or 'none'}; pass --paper")
    return ids[0]


def fetch_paper(pmcid, dest):
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            dest.write_bytes(r.read())
        return dest
    except Exception as e:
        log(f"paper full text not fetched ({e!r}); reviewers work from the published figures")
        dest.write_text(f"The full text of {pmcid} could not be fetched from {url}.\n")
        return dest


def item_ids(repo, paper):
    try:
        return {i["id"] for i in json.loads((Path(repo) / paper / "results.json").read_text())["items"]}
    except Exception:
        return set()


# ---------------------------------------------------------------- gate

def gate(repo, paper, skill_root, work, timeout):
    """Clean worktree at HEAD; one-command rerun and the checks. Returns (gate, worktree, fresh)."""
    wt, fresh = work / "wt", work / "fresh"
    for p in (wt, fresh, work / "nf-work"):
        shutil.rmtree(p, ignore_errors=True)
    sh(["git", "worktree", "prune"], cwd=repo, check=False)
    sh(["git", "worktree", "add", "--detach", str(wt), "HEAD"], cwd=repo)
    steps = []

    def step(name, cmd, t=1800):
        try:
            r = subprocess.run(cmd, cwd=wt, text=True, capture_output=True, timeout=t)
            out, code = r.stdout + r.stderr, r.returncode
        except subprocess.TimeoutExpired as e:
            out, code = f"timed out after {t} s\n{e.stdout or ''}{e.stderr or ''}", "timeout"
        (work / f"gate-{name}.log").write_text(out if isinstance(out, str) else str(out))
        steps.append({"name": name, "ok": code == 0, "exit": code, "log_tail": str(out)[-6000:]})
        log(f"gate {name}: {'pass' if code == 0 else f'FAIL ({code})'}")

    step("nextflow", ["nextflow", "run", f"{paper}/figure-reproduction/main.nf", "--outdir", str(fresh),
                      "-ansi-log", "false", "-work-dir", str(work / "nf-work")], t=timeout)
    step("check_results", [sys.executable, str(skill_root / "paper2repro/scripts/check_results.py"), f"{paper}/results.json"])
    if (wt / paper / "package" / "pyproject.toml").exists():
        step("check_package", [sys.executable, str(skill_root / "paper2repro/scripts/check_package.py"), f"{paper}/package"], t=3600)
    # Blindness: the reviewers' copy holds no ledger, conversation or earlier review rounds.
    shutil.rmtree(wt / paper / "session", ignore_errors=True)
    return {"ok": all(s["ok"] for s in steps), "steps": steps}, wt, fresh


# ---------------------------------------------------------------- one run

async def review_round(args, n, wt, fresh, paper_file, pr_body_file, budget, logdir):
    common = dict(
        model=args.model, effort=args.effort, cwd=str(wt), permission_mode="bypassPermissions",
        allowed_tools=["Read", "Glob", "Grep", "Bash"],
        disallowed_tools=["Edit", "Write", "NotebookEdit", "WebFetch", "WebSearch", "Agent", "Skill"],
        setting_sources=[], add_dirs=[str(fresh), str(paper_file.parent), str(args.skill_root)],
        output_format={"type": "json_schema", "schema": F.FINDINGS_SCHEMA}, max_turns=args.review_turns,
    )
    values = dict(worktree=wt, fresh=fresh, paper=paper_file, paper_id=args.paper, skill_root=args.skill_root, pr_body=pr_body_file)
    jobs = []
    for who, ref in (("figures", "review-figures.md"), ("claims", "review-claims.md")):
        opts = ClaudeAgentOptions(**common, max_budget_usd=budget.for_step(0.15))
        jobs.append(run_agent(f"round{n}-review-{who}", brief(ref, **values), opts, budget, logdir))
    outs = await asyncio.gather(*jobs)
    lists = []
    for who, (out, _res) in zip(("figures", "claims"), outs):
        if not out or "findings" not in out:
            return None, f"{who} reviewer returned no findings"
        lists.append(out["findings"])
    return lists, None


async def fix_round(args, n, findings, budget, logdir, work):
    fpath = work / f"round{n}-findings.json"
    fpath.write_text(json.dumps(findings, indent=2))
    prompt = brief("fix-rules.md", repo=args.repo, paper_id=args.paper, skill_root=args.skill_root, findings_path=fpath)
    base = dict(
        model=args.model, effort=args.effort, cwd=str(args.repo), permission_mode="bypassPermissions",
        disallowed_tools=["Agent"] if args.no_subagents else [], setting_sources=["user", "project"],
        add_dirs=[str(work), str(args.skill_root)],
        output_format={"type": "json_schema", "schema": F.FIX_SCHEMA}, max_turns=args.fix_turns,
    )
    out, res = await run_agent(f"round{n}-fix", prompt, ClaudeAgentOptions(**base, max_budget_usd=budget.for_step()), budget, logdir)
    # The fixer does not get to stop early: ask again for every blocking finding left without a result.
    for nudge in range(1, args.nudges + 1):
        missing = F.unanswered(findings, out)
        if not missing or not res or not res.session_id or budget.remaining() - LESSONS_RESERVE_USD < 1:
            break
        log(f"round{n}: fixer left {len(missing)} blocking findings without a result; asking again")
        again = (f"These blocking findings have no valid result yet: {', '.join(missing)}. "
                 "Work on each until it is fixed, or until at least two hypotheses are tested and it is needs_human. "
                 "Then return results for every finding you were given, in the same JSON format.")
        prev = out
        out, res = await run_agent(f"round{n}-fix-nudge{nudge}", again,
                                   ClaudeAgentOptions(**base, resume=res.session_id, max_budget_usd=budget.for_step()), budget, logdir)
        if prev and out:  # keep results from the first pass that the second did not repeat
            keys = {r["key"] for r in out.get("results", [])}
            out["results"] = out.get("results", []) + [r for r in prev.get("results", []) if r["key"] not in keys]
        out = out or prev
    return out


def commit_and_push(args, head_ref, message):
    sh(["git", "add", "-A"], cwd=args.repo)
    if sh(["git", "diff", "--cached", "--quiet"], cwd=args.repo, check=False).returncode != 0:
        sh(["git", "commit", "-q", "-m", message], cwd=args.repo)
    if args.no_push:
        return
    for attempt in range(4):
        if sh(["git", "push", "origin", f"HEAD:refs/heads/{head_ref}"], cwd=args.repo, check=False).returncode == 0:
            return
        time.sleep(2 ** (attempt + 1))
    raise RuntimeError("push failed four times")


def save_run(args, run, head_ref, message):
    path = Path(args.repo) / args.paper / "session" / "review" / "paper2revise.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(run, indent=2))
    commit_and_push(args, head_ref, message)


async def lessons(args, run, budget, logdir, work):
    p2r = Path(args.p2r)
    env = dict(os.environ, GH_TOKEN=os.environ.get("P2R_GH_TOKEN", os.environ.get("GH_TOKEN", "")))
    sh(["git", "fetch", "-q", "origin", "main"], cwd=p2r)
    has = sh(["git", "ls-remote", "--exit-code", "--heads", "origin", LESSONS_BRANCH], cwd=p2r, check=False).returncode == 0
    if has:
        sh(["git", "fetch", "-q", "origin", LESSONS_BRANCH], cwd=p2r)
        sh(["git", "checkout", "-q", "-B", LESSONS_BRANCH, "FETCH_HEAD"], cwd=p2r)
    else:
        sh(["git", "checkout", "-q", "-B", LESSONS_BRANCH, "origin/main"], cwd=p2r)
    start = sh(["git", "rev-parse", "HEAD"], cwd=p2r).stdout.strip()
    rpath = work / "rounds.json"
    rpath.write_text(json.dumps(run, indent=2))
    prompt = brief("lessons.md", p2r=p2r, branch=LESSONS_BRANCH, rounds_path=rpath, paper_id=args.paper, pr_url=run["pr_url"])
    opts = ClaudeAgentOptions(model=args.model, effort=args.effort, cwd=str(p2r), permission_mode="bypassPermissions",
                              disallowed_tools=["Agent", "WebFetch", "WebSearch"], setting_sources=[], add_dirs=[str(work)],
                              max_turns=150, max_budget_usd=max(0.5, budget.remaining()))
    await run_agent("lessons", prompt, opts, budget, logdir)
    sh(["git", "add", "-A"], cwd=p2r)
    if sh(["git", "diff", "--cached", "--quiet"], cwd=p2r, check=False).returncode != 0:
        sh(["git", "commit", "-q", "-m", f"Paper2Revise lessons from {args.paper}"], cwd=p2r)
    if sh(["git", "rev-parse", "HEAD"], cwd=p2r).stdout.strip() == start or args.no_push:
        return None
    sh(["git", "push", "-q", "origin", f"HEAD:refs/heads/{LESSONS_BRANCH}"], cwd=p2r, env=env)
    existing = json.loads(sh(["gh", "pr", "list", "--repo", P2R_REPO, "--head", LESSONS_BRANCH, "--state", "open",
                              "--json", "url"], cwd=p2r, env=env).stdout)
    if existing:
        return existing[0]["url"]
    body = ("Rule changes that Paper2Revise drew from its reviews of Paper2Repro pull requests. "
            "Each run adds commits here; see `skills/paper2agent/paper2revise/references/lessons-log.md`.\n\n"
            f"First run: {args.paper}, {run['pr_url']}.\n\n---\n_Generated by Paper2Revise (Claude Agent SDK)_")
    return sh(["gh", "pr", "create", "--repo", P2R_REPO, "--head", LESSONS_BRANCH, "--base", "main",
               "--title", "Paper2Revise: lessons for Paper2Repro", "--body", body], cwd=p2r, env=env).stdout.strip()


def report(args, run):
    body = F.summary(run) + "\n\n---\n_Generated by Paper2Revise (Claude Agent SDK)_"
    (Path(args.work) / "comment.md").write_text(body)
    print(body)
    if args.no_push:
        return
    on = LABEL_CLEAN if run["outcome"] == "clean" else LABEL_HUMAN
    off = LABEL_HUMAN if on == LABEL_CLEAN else LABEL_CLEAN
    sh(["gh", "label", "create", on, "--force", "--color", "0e8a16" if on == LABEL_CLEAN else "d93f0b"], cwd=args.repo, check=False)
    sh(["gh", "pr", "edit", str(args.pr), "--add-label", on, "--remove-label", off], cwd=args.repo, check=False)
    sh(["gh", "pr", "comment", str(args.pr), "--body-file", str(Path(args.work) / "comment.md")], cwd=args.repo)


async def main_async(args):
    args.repo = Path(args.repo).resolve()
    args.skill_root = Path(args.skill_root).expanduser().resolve()
    work = Path(args.work or tempfile.mkdtemp(prefix="paper2revise-")).resolve()
    args.work = work
    logdir = work / "agents"
    logdir.mkdir(parents=True, exist_ok=True)
    info = pr_info(args.repo, args.pr)
    args.paper = args.paper or detect_paper(args.repo, info)
    head_ref = info["headRefName"]
    log(f"PR {info['url']}, paper {args.paper}, branch {head_ref}, work {work}")
    (work / "paper").mkdir(exist_ok=True)
    paper_file = fetch_paper(args.paper, work / "paper" / f"{args.paper}.xml")
    pr_body_file = work / "pr-body.md"
    pr_body_file.write_text(info.get("body") or "")

    budget = Budget(args.budget)
    run = {"schema": "paper2revise/run/v1", "pr_url": info["url"], "paper": args.paper, "budget_usd": args.budget,
           "model": args.model, "started": dt.datetime.now(dt.timezone.utc).isoformat(), "rounds": [],
           "rounds_path": f"{args.paper}/session/review/paper2revise.json"}
    outcome = "rounds"
    try:
        for n in range(1, args.rounds + 1):
            if budget.remaining() - LESSONS_RESERVE_USD < MIN_ROUND_USD:
                outcome = "budget"
                break
            log(f"round {n}")
            before = item_ids(args.repo, args.paper)
            g, wt, fresh = gate(args.repo, args.paper, args.skill_root, work, args.gate_timeout)
            lists, err = await review_round(args, n, wt, fresh, paper_file, pr_body_file, budget, logdir)
            sh(["git", "worktree", "remove", "--force", str(wt)], cwd=args.repo, check=False)
            if err:
                if budget.remaining() - LESSONS_RESERVE_USD < MIN_ROUND_USD:
                    outcome = "budget"
                    break
                raise RuntimeError(err)
            merged = F.merge(*lists, F.gate_findings(g), run["rounds"][-1].get("guard", []) if run["rounds"] else [])
            rnd = {"n": n, "gate": {"ok": g["ok"], "steps": [{k: s[k] for k in ("name", "ok", "exit")} for s in g["steps"]]},
                   "findings": merged, "cost_usd_so_far": round(budget.spent, 2)}
            run["rounds"].append(rnd)
            decision = F.decide(merged, run["rounds"][:-1])
            rnd["decision"] = decision
            log(f"round {n}: {sum(f['severity'] == 'blocking' for f in merged)} blocking, decision {decision}")
            if decision in ("clean", "human"):
                outcome = decision
                break
            if n == args.rounds:
                break  # no fix whose result nobody would review
            if budget.remaining() - LESSONS_RESERVE_USD < MIN_ROUND_USD:
                outcome = "budget"
                break
            rnd["fix"] = await fix_round(args, n, F.to_fix(merged, run["rounds"][:-1]), budget, logdir, work)
            removed = sorted(before - item_ids(args.repo, args.paper))
            if removed:  # an item may never be dropped to close a finding
                rnd["guard"] = [{"item": i, "area": "pipeline", "severity": "blocking",
                                 "problem": f"Item {i} was removed from results.json by the fixer.",
                                 "evidence": "results.json item ids before and after the fix round.",
                                 "fix": "Restore the item; report it as attempted or not_attempted with a cause."} for i in removed]
            rnd["cost_usd_so_far"] = round(budget.spent, 2)
            run["cost_usd"] = round(budget.spent, 2)
            save_run(args, run, head_ref, f"Paper2Revise round {n}: fixes for {args.paper}")
    except Exception as e:
        outcome = "error"
        run["error"] = repr(e)[:2000]
        log(f"error: {e!r}")
    run["outcome"] = outcome
    run["cost_usd"] = round(budget.spent, 2)
    if not args.no_lessons and run["rounds"] and any(r["findings"] for r in run["rounds"]):
        try:
            run["lessons_pr"] = await lessons(args, run, budget, logdir, work)
        except Exception as e:
            log(f"lessons step failed: {e!r}")
    run["cost_usd"] = round(budget.spent, 2)
    run["finished"] = dt.datetime.now(dt.timezone.utc).isoformat()
    try:
        save_run(args, run, head_ref, f"Paper2Revise: {outcome} for {args.paper}")
    except Exception as e:
        log(f"could not save the run record: {e!r}")
    report(args, run)
    return 0 if outcome == "clean" else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".", help="fossil checkout on the pull request's head branch")
    ap.add_argument("--pr", type=int, required=True)
    ap.add_argument("--paper", help="paper folder (PMC id); detected from the pull request's files")
    ap.add_argument("--skill-root", default="~/.claude/skills/paper2agent")
    ap.add_argument("--p2r", help="Paper2Repro clone for the lessons step")
    ap.add_argument("--work", help="scratch folder (default: a new temporary folder)")
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--budget", type=float, default=50.0, help="USD cap for the whole run")
    ap.add_argument("--rounds", type=int, default=5)
    ap.add_argument("--nudges", type=int, default=2, help="times to send the fixer back for unanswered findings")
    ap.add_argument("--gate-timeout", type=int, default=4 * 3600, help="seconds for the Nextflow rerun")
    ap.add_argument("--review-turns", type=int, default=250)
    ap.add_argument("--fix-turns", type=int, default=600)
    ap.add_argument("--no-subagents", action="store_true", help="do not let the fixer start subagents")
    ap.add_argument("--no-push", action="store_true", help="commit locally only; no push, comment, label or lessons PR")
    ap.add_argument("--no-lessons", action="store_true")
    args = ap.parse_args()
    if not args.no_lessons and not args.p2r:
        ap.error("--p2r is required unless --no-lessons")
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
