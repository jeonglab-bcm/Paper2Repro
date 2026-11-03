#!/usr/bin/env python3
"""Record a Claude Code session: prompts, turns, tool calls and tokens.

Reads the session transcript that Claude Code writes under ~/.claude/projects/<slug>/
(<session-id>.jsonl, plus subagent transcripts in <session-id>/) and writes:

  <out>/ledger.json      counts and token totals (schema paper2repro/session-ledger/v1)
  <out>/conversation.md  every human prompt and every reply, with tool calls as one-liners

Usage:
  session_ledger.py --out PMC1234567/session                  # newest session of this project
  session_ledger.py --session-id <id> --out PMC1234567/session
  session_ledger.py --transcript <path.jsonl> --out DIR
  session_ledger.py --from-hook --out DIR                      # Stop hook: reads the hook JSON on stdin

Standard library only. Thinking blocks and tool outputs are left out; strings that look
like credentials are masked.
"""

import argparse
import datetime as dt
import glob
import json
import os
import re
import sys

SECRET = re.compile(
    r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}|AKIA[0-9A-Z]{16}"
    r"|xox[abposr]-[A-Za-z0-9-]{10,}|(?i:bearer)\s+[A-Za-z0-9._-]{20,})"
)
TOKEN_KEYS = ("input", "cache_creation", "cache_read", "output", "thinking")


def mask(text):
    return SECRET.sub("[redacted]", text)


def project_dir(cwd):
    """Claude Code's transcript folder for cwd, or for the nearest parent that has one."""
    root = os.path.expanduser("~/.claude/projects")
    path = os.path.abspath(cwd)
    while True:
        cand = os.path.join(root, re.sub(r"[^A-Za-z0-9]", "-", path))
        if os.path.isdir(cand) or os.path.dirname(path) == path:
            return cand
        path = os.path.dirname(path)


def find_transcript(args):
    if args.transcript:
        return args.transcript
    if args.from_hook:
        hook = json.load(sys.stdin)
        if hook.get("transcript_path"):
            return hook["transcript_path"]
        args.session_id = hook.get("session_id")
    base = project_dir(args.project_dir)
    if args.session_id:
        return os.path.join(base, f"{args.session_id}.jsonl")
    files = sorted(glob.glob(os.path.join(base, "*.jsonl")), key=os.path.getmtime)
    if not files:
        sys.exit(f"no transcripts in {base}")
    return files[-1]


def read_jsonl(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    pass  # a line being written while we read
    return rows


def text_of(content):
    if isinstance(content, str):
        return content
    return "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")


def is_human(row):
    """A prompt typed by the person: not a tool result, not injected context."""
    if row.get("type") != "user" or row.get("isMeta") or row.get("isCompactSummary") or row.get("isSidechain"):
        return False
    content = row.get("message", {}).get("content")
    if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
        return False
    text = text_of(content).strip()
    return bool(text) and not text.startswith(("<local-command-", "<command-stdout>"))


def parse(rows):
    """Prompts, replies, tool calls and per-response token usage, in transcript order."""
    events, usage, models, tools = [], {}, set(), {}
    seen_tools = set()
    cost = None
    for row in rows:
        t, at = row.get("type"), row.get("timestamp")
        if t == "cost-state":
            cost = row
        elif t == "attachment":
            a = row.get("attachment", {})
            if a.get("type") == "queued_command" and a.get("origin", {}).get("kind") == "human":
                events.append({"role": "user", "at": a.get("timestamp") or at, "text": str(a.get("prompt", "")), "mid_turn": True})
        elif is_human(row):
            events.append({"role": "user", "at": at, "text": text_of(row["message"]["content"])})
        elif t == "assistant":
            msg = row.get("message", {})
            mid = msg.get("id") or row.get("requestId") or row.get("uuid")
            if msg.get("model") and not msg["model"].startswith("<"):
                models.add(msg["model"])
            u = msg.get("usage") or {}
            # Streaming writes one row per content block with the same message id; keep the last.
            if u and (mid not in usage or u.get("output_tokens", 0) >= usage[mid].get("output_tokens", 0)):
                usage[mid] = u
            for b in msg.get("content", []):
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text" and b.get("text", "").strip():
                    events.append({"role": "assistant", "at": at, "text": b["text"]})
                elif b.get("type") == "tool_use" and b.get("id") not in seen_tools:
                    seen_tools.add(b.get("id"))
                    name = b.get("name", "?")
                    tools[name] = tools.get(name, 0) + 1
                    inp = b.get("input") or {}
                    desc = inp.get("description") or inp.get("command") or inp.get("file_path") or inp.get("query") or inp.get("skill") or ""
                    events.append({"role": "tool", "at": at, "name": name, "text": " ".join(str(desc).split())[:160]})
    # Prompts can be recorded twice (queued, then delivered); drop a repeat within two minutes.
    out, last = [], {}
    for e in events:
        if e["role"] == "user":
            key = e["text"].strip()
            t0 = last.get(key)
            if t0 and e["at"] and abs((parse_time(e["at"]) - t0).total_seconds()) < 120:
                continue
            last[key] = parse_time(e["at"]) if e["at"] else None
        out.append(e)
    return out, usage, models, tools, cost


def parse_time(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def total(usages):
    s = dict.fromkeys(TOKEN_KEYS, 0)
    for u in usages:
        s["input"] += u.get("input_tokens", 0) or 0
        s["cache_creation"] += u.get("cache_creation_input_tokens", 0) or 0
        s["cache_read"] += u.get("cache_read_input_tokens", 0) or 0
        s["output"] += u.get("output_tokens", 0) or 0
        s["thinking"] += (u.get("output_tokens_details") or {}).get("thinking_tokens", 0) or 0
    # thinking is part of output, so it is not added again
    s["total"] = s["input"] + s["cache_creation"] + s["cache_read"] + s["output"]
    return s


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, help="folder for ledger.json and conversation.md")
    ap.add_argument("--transcript")
    ap.add_argument("--session-id")
    ap.add_argument("--project-dir", default=os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
    ap.add_argument("--from-hook", action="store_true")
    args = ap.parse_args()

    path = find_transcript(args)
    rows = read_jsonl(path)
    events, usage, models, tools, cost = parse(rows)
    stamps = [parse_time(r["timestamp"]) for r in rows if r.get("timestamp")]

    # Subagent transcripts live beside the main one, in a folder named after the session.
    side_files = [p for p in glob.glob(os.path.join(path[: -len(".jsonl")], "**", "*.jsonl"), recursive=True)]
    side_usage, side_tools = {}, {}
    for p in side_files:
        _, u, m, tl, _ = parse(read_jsonl(p))
        side_usage.update({f"{p}:{k}": v for k, v in u.items()})
        models |= m
        for k, v in tl.items():
            side_tools[k] = side_tools.get(k, 0) + v

    main_tokens, side_tokens = total(usage.values()), total(side_usage.values())
    prompts = [e for e in events if e["role"] == "user"]
    ledger = {
        "schema": "paper2repro/session-ledger/v1",
        "session_id": rows[0].get("sessionId") if rows else os.path.basename(path)[:-6],
        "transcript": os.path.basename(path),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "started_at": min(stamps).isoformat(timespec="seconds") if stamps else None,
        "ended_at": max(stamps).isoformat(timespec="seconds") if stamps else None,
        "wall_clock_minutes": round((max(stamps) - min(stamps)).total_seconds() / 60, 1) if stamps else None,
        "models": sorted(models),
        "human_prompts": len(prompts),
        "mid_turn_prompts": sum(1 for e in prompts if e.get("mid_turn")),
        "assistant_responses": len(usage),
        "tool_calls": sum(tools.values()),
        "tool_calls_by_name": dict(sorted(tools.items(), key=lambda kv: -kv[1])),
        "tokens": main_tokens,
        "subagents": {"transcripts": len(side_files), "assistant_responses": len(side_usage),
                      "tool_calls": sum(side_tools.values()), "tokens": side_tokens},
        "tokens_all": {k: main_tokens[k] + side_tokens[k] for k in main_tokens},
        "prompts": [{"at": e["at"], "text": mask(e["text"]), "mid_turn": bool(e.get("mid_turn"))} for e in prompts],
    }
    if cost:
        # Claude Code's own running total, written at the end of each turn.
        ledger["cost_state"] = {k: cost.get(k) for k in ("totalCostUSD", "totalDuration", "totalAPIDuration", "modelUsage")}
        ledger["cost_state"]["note"] = ("Claude Code's own total at the end of the last finished turn. It also counts side "
                                        "requests that are not conversation responses, so it can exceed tokens.")

    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "ledger.json"), "w", encoding="utf-8") as f:
        json.dump(ledger, f, indent=2, ensure_ascii=False)
        f.write("\n")

    t = ledger["tokens_all"]
    lines = [
        f"# Session {ledger['session_id']}",
        "",
        "| Measure | Value |",
        "| --- | --- |",
        f"| Started / ended (UTC) | {ledger['started_at']} / {ledger['ended_at']} |",
        f"| Wall clock | {ledger['wall_clock_minutes']} min |",
        f"| Models | {', '.join(ledger['models'])} |",
        f"| Human prompts | {ledger['human_prompts']} ({ledger['mid_turn_prompts']} sent mid-turn) |",
        f"| Assistant responses (API calls) | {ledger['assistant_responses']} + {ledger['subagents']['assistant_responses']} in subagents |",
        f"| Tool calls | {ledger['tool_calls']} + {ledger['subagents']['tool_calls']} in subagents |",
        f"| Tokens: input / cache write / cache read / output | {t['input']:,} / {t['cache_creation']:,} / {t['cache_read']:,} / {t['output']:,} |",
        f"| Tokens: total (incl. subagents) | {t['total']:,} |",
        "",
        "## Conversation",
        "",
    ]
    for e in events:
        when = (e["at"] or "")[:19].replace("T", " ")
        if e["role"] == "user":
            tag = "User (sent mid-turn)" if e.get("mid_turn") else "User"
            lines += [f"### {tag} · {when}", "", mask(e["text"]).strip(), ""]
        elif e["role"] == "assistant":
            lines += [f"### Claude · {when}", "", mask(e["text"]).strip(), ""]
        else:
            lines += [f"- `{e['name']}` {mask(e['text'])}", ""]
    with open(os.path.join(args.out, "conversation.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(json.dumps({k: ledger[k] for k in ("session_id", "human_prompts", "assistant_responses", "tool_calls", "tokens_all")}, indent=1))


if __name__ == "__main__":
    main()
