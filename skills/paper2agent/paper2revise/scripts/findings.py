#!/usr/bin/env python3
"""Finding keys, merging, the round decision and the summary comment for Paper2Revise.

Usage:
  findings.py summary <rounds.json>   print the pull-request comment for a finished run
  findings.py decide <rounds.json>    print the decision for the last round

Standard library only. review_pr.py imports this module; the rules live here so they are tested.
"""

import json
import re
import sys

AREAS = ("figure", "claim", "pipeline")
SEVERITIES = ("blocking", "minor")
FIX_STATUSES = ("fixed", "needs_human", "not_a_problem")

FINDINGS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["findings"],
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["item", "area", "severity", "problem", "evidence", "fix"],
                "properties": {
                    "item": {"type": "string"},
                    "area": {"type": "string", "enum": list(AREAS)},
                    "severity": {"type": "string", "enum": list(SEVERITIES)},
                    "problem": {"type": "string"},
                    "evidence": {"type": "string"},
                    "fix": {"type": "string"},
                },
            },
        }
    },
}

FIX_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["results"],
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["key", "status", "what_changed", "hypotheses_tested"],
                "properties": {
                    "key": {"type": "string"},
                    "status": {"type": "string", "enum": list(FIX_STATUSES)},
                    "what_changed": {"type": "string"},
                    "hypotheses_tested": {"type": "array", "items": {"type": "string"}},
                },
            },
        }
    },
}


def norm_item(item):
    """'Fig. 3B' -> 'fig3b', 'Table 1' -> 'table1', 'fig3b_ours.png' -> 'fig3b'."""
    s = str(item).strip().lower()
    s = re.sub(r"_(ours|overlay|published)\b.*$", "", s)
    s = re.sub(r"\.(png|jpe?g|svg|pdf)$", "", s)
    s = re.sub(r"^figure", "fig", s)
    s = re.sub(r"^supplementary\s*", "s", s)
    return re.sub(r"[^a-z0-9]+", "", s) or "general"


def key_of(f):
    return f"{f['area']}:{norm_item(f['item'])}"


def merge(*lists):
    """Merge findings from several reviewers. Findings with one key are kept together:
    the key is blocking if any of them is, and every problem is kept."""
    merged = {}
    for lst in lists:
        for f in lst:
            if f.get("area") not in AREAS or f.get("severity") not in SEVERITIES:
                raise ValueError(f"bad finding: {f!r}")
            k = key_of(f)
            if k not in merged:
                merged[k] = {"key": k, "item": f["item"], "area": f["area"], "severity": f["severity"], "problems": []}
            m = merged[k]
            if f["severity"] == "blocking":
                m["severity"] = "blocking"
            m["problems"].append({k2: f[k2] for k2 in ("problem", "evidence", "fix")})
    return sorted(merged.values(), key=lambda m: (m["severity"] != "blocking", m["key"]))


def gate_findings(gate):
    """A failed gate step is a blocking pipeline finding."""
    out = []
    for step in gate.get("steps", []):
        if not step["ok"]:
            out.append({
                "item": step["name"], "area": "pipeline", "severity": "blocking",
                "problem": f"{step['name']} failed in the clean rerun (exit {step.get('exit')}).",
                "evidence": step.get("log_tail", "")[-4000:],
                "fix": "Make the step pass from a clean checkout without changing data or pass marks.",
            })
    return out


def human_keys(rounds):
    """Keys the fixer flagged needs_human in any earlier round."""
    keys = set()
    for r in rounds:
        for res in (r.get("fix") or {}).get("results", []):
            if res["status"] == "needs_human":
                keys.add(res["key"])
    return keys


def decide(findings, earlier_rounds):
    """'clean': no blocking finding. 'human': every blocking finding is already flagged
    needs_human. 'fix': work to do."""
    blocking = [f for f in findings if f["severity"] == "blocking"]
    if not blocking:
        return "clean"
    flagged = human_keys(earlier_rounds)
    if all(f["key"] in flagged for f in blocking):
        return "human"
    return "fix"


def to_fix(findings, earlier_rounds):
    """The findings the fixer gets: blocking ones not flagged needs_human yet, then minor ones."""
    flagged = human_keys(earlier_rounds)
    return [f for f in findings if not (f["severity"] == "blocking" and f["key"] in flagged)]


def unanswered(given, fix_output):
    """Blocking keys the fixer was given and returned no valid result for."""
    answered = set()
    for res in (fix_output or {}).get("results", []):
        if res.get("status") not in FIX_STATUSES:
            continue
        if res["status"] == "needs_human" and len(res.get("hypotheses_tested") or []) < 2:
            continue
        answered.add(res.get("key"))
    return [f["key"] for f in given if f["severity"] == "blocking" and f["key"] not in answered]


def summary(run):
    """The pull-request comment for a finished run."""
    rounds = run.get("rounds", [])
    outcome = run.get("outcome", "unknown")
    head = {
        "clean": "**Paper2Revise: clean.** A blind review and a full clean rerun found no blocking problem.",
        "human": "**Paper2Revise: needs a human.** The findings below were investigated and could not be fixed without a decision.",
        "rounds": "**Paper2Revise: stopped at the round limit** with blocking findings left.",
        "budget": "**Paper2Revise: stopped at the cost cap** with blocking findings left.",
        "error": "**Paper2Revise: stopped on an error.**",
    }.get(outcome, f"**Paper2Revise: {outcome}.**")
    lines = [head, ""]
    lines.append(f"Rounds: {len(rounds)}. Cost: ${run.get('cost_usd', 0):.2f} of ${run.get('budget_usd', 0):.2f}.")
    if run.get("error"):
        lines += ["", f"Error: `{run['error']}`"]
    lines += ["", "| Round | Gate | Blocking | Minor | Fixed | Needs human |", "| --- | --- | --- | --- | --- | --- |"]
    for i, r in enumerate(rounds, 1):
        fs = r.get("findings", [])
        res = (r.get("fix") or {}).get("results", [])
        lines.append(
            f"| {i} | {'pass' if r.get('gate', {}).get('ok') else 'fail'} "
            f"| {sum(f['severity'] == 'blocking' for f in fs)} | {sum(f['severity'] == 'minor' for f in fs)} "
            f"| {sum(x['status'] == 'fixed' for x in res)} | {sum(x['status'] == 'needs_human' for x in res)} |"
        )
    if rounds:
        last = rounds[-1].get("findings", [])
        left = [f for f in last if f["severity"] == "blocking"]
        if left:
            notes = {}
            for r in rounds:
                for x in (r.get("fix") or {}).get("results", []):
                    notes[x["key"]] = x
            lines += ["", "### Left open", ""]
            for f in left:
                lines.append(f"- **{f['key']}**: {f['problems'][0]['problem']}")
                n = notes.get(f["key"])
                if n and n["status"] == "needs_human":
                    for h in n["hypotheses_tested"]:
                        lines.append(f"  - tested: {h}")
    if run.get("lessons_pr"):
        lines += ["", f"Rule changes for Paper2Repro: {run['lessons_pr']}"]
    lines += ["", "Rounds, findings and fixes: `" + run.get("rounds_path", "") + "`."]
    return "\n".join(lines)


def main(argv):
    if len(argv) != 3 or argv[1] not in ("summary", "decide"):
        print(__doc__)
        return 2
    run = json.load(open(argv[2]))
    if argv[1] == "summary":
        print(summary(run))
    else:
        rounds = run.get("rounds", [])
        print(decide(rounds[-1]["findings"], rounds[:-1]) if rounds else "fix")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
