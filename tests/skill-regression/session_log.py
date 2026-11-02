#!/usr/bin/env python3
"""Turn Claude Code stream-json transcripts into a readable session log with cost and token usage.

Commands:
  summary <transcript> [<transcript> ...]
      One transcript: print the cost, token and tool summary.
      Several: print one comparison row per session (for example, weekly runs).
  render <transcript> --out <dir> [--prompt <file>]
      Write summary.md, session.md (full timeline), session.json and session.html (viewer).

Token and cost totals come from the final `result` event, which covers the main agent and
all subagents. If the run was cut off before that event, totals fall back to the per-message
usage in the stream. That fallback has no cost, and it undercounts output tokens, because the
stream reports usage when each message starts. The summary says which source it used.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

MAX_TEXT = 4000
TOKEN_FIELDS = ("input", "output", "cache_read", "cache_write")


def _ts(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def _clip(s: str, n: int = MAX_TEXT) -> str:
    return s if len(s) <= n else s[:n] + f"\n... [{len(s) - n} more characters]"


def _result_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text", f"[{c.get('type')}]") for c in content if isinstance(c, dict))
    return ""


def _brief(name: str, inp: dict) -> str:
    for key in {"Bash": "command", "Read": "file_path", "Write": "file_path", "Edit": "file_path",
                "NotebookEdit": "notebook_path", "WebFetch": "url", "WebSearch": "query", "Agent": "description",
                "Task": "description", "Skill": "skill", "Glob": "pattern", "Grep": "pattern"}.get(name, ""), *inp:
        v = inp.get(key) if key else None
        if isinstance(v, str) and v:
            return v.splitlines()[0][:160]
    return ""


def parse(path: Path, prompt: str | None = None) -> dict:
    events = []
    for line in path.read_text(errors="replace").splitlines():
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    meta: dict = {"transcript": str(path)}
    entries: list[dict] = []
    open_calls: dict[str, dict] = {}
    msg_usage: dict[str, dict] = {}
    subagents: dict[str, dict] = {}
    result = None
    stamps = []

    if prompt:
        entries.append({"kind": "prompt", "agent": None, "text": _clip(prompt)})

    for e in events:
        t, sub = e.get("type"), e.get("subtype")
        ts = _ts(e.get("timestamp"))
        if ts:
            stamps.append(ts)
        agent = e.get("parent_tool_use_id")
        if t == "system" and sub == "init":
            meta.update({k: e.get(k) for k in ("session_id", "model", "claude_code_version", "cwd", "permissionMode")})
            meta["tool_count"] = len(e.get("tools") or [])
        elif t == "system" and sub == "task_started":
            subagents.setdefault(e.get("tool_use_id"), {}).update(
                type=e.get("subagent_type"), description=e.get("description"), status="running")
        elif t == "system" and sub == "task_notification":
            u = e.get("usage") or {}
            subagents.setdefault(e.get("tool_use_id"), {}).update(
                status=e.get("status"), tokens=u.get("total_tokens"), tool_uses=u.get("tool_uses"),
                duration_ms=u.get("duration_ms"))
        elif t == "assistant":
            m = e.get("message") or {}
            mid, u = m.get("id"), m.get("usage") or {}
            if mid:
                prev = msg_usage.get(mid, {"model": m.get("model"), "agent": agent})
                for k, src in (("input", "input_tokens"), ("output", "output_tokens"),
                               ("cache_read", "cache_read_input_tokens"), ("cache_write", "cache_creation_input_tokens")):
                    prev[k] = max(prev.get(k, 0), u.get(src) or 0)
                msg_usage[mid] = prev
            for c in m.get("content") or []:
                kind = c.get("type")
                if kind == "text" and c.get("text", "").strip():
                    entries.append({"kind": "text", "agent": agent, "ts": ts, "text": _clip(c["text"])})
                elif kind == "thinking" and c.get("thinking", "").strip():
                    entries.append({"kind": "thinking", "agent": agent, "ts": ts, "text": _clip(c.get("thinking", ""))})
                elif kind == "tool_use":
                    inp = c.get("input") or {}
                    entry = {"kind": "tool", "agent": agent, "ts": ts, "id": c.get("id"), "tool": c.get("name"),
                             "brief": _brief(c.get("name", ""), inp), "input": _clip(json.dumps(inp, indent=1)),
                             "output": None, "is_error": None, "duration_ms": None}
                    entries.append(entry)
                    open_calls[c.get("id")] = entry
        elif t == "user":
            content = (e.get("message") or {}).get("content")
            for c in content if isinstance(content, list) else []:
                if c.get("type") == "tool_result" and c.get("tool_use_id") in open_calls:
                    entry = open_calls.pop(c["tool_use_id"])
                    entry["output"] = _clip(_result_text(c.get("content")))
                    entry["is_error"] = bool(c.get("is_error"))
                    if ts and entry.get("ts"):
                        entry["duration_ms"] = int((ts - entry["ts"]) * 1000)
                elif c.get("type") == "text" and agent and c.get("text"):
                    entries.append({"kind": "subagent_prompt", "agent": agent, "ts": ts, "text": _clip(c["text"])})
        elif t == "result":
            result = e

    for entry in open_calls.values():
        entry["is_error"] = None  # no result: the run stopped while the call was open

    tools: dict[str, dict] = defaultdict(lambda: {"calls": 0, "errors": 0, "seconds": 0.0, "unfinished": 0})
    for x in entries:
        if x["kind"] == "tool":
            s = tools[x["tool"]]
            s["calls"] += 1
            s["errors"] += x["is_error"] is True
            s["unfinished"] += x["output"] is None
            s["seconds"] += (x["duration_ms"] or 0) / 1000

    if result:
        usage_source = "final"
        models = {name: {"input": u.get("inputTokens", 0), "output": u.get("outputTokens", 0),
                         "cache_read": u.get("cacheReadInputTokens", 0), "cache_write": u.get("cacheCreationInputTokens", 0),
                         "cost_usd": u.get("costUSD")} for name, u in (result.get("modelUsage") or {}).items()}
        meta.update({"status": result.get("subtype"), "is_error": result.get("is_error"),
                     "num_turns": result.get("num_turns"), "duration_ms": result.get("duration_ms"),
                     "cost_usd": result.get("total_cost_usd"), "stop_reason": result.get("terminal_reason") or result.get("stop_reason"),
                     "permission_denials": len(result.get("permission_denials") or []),
                     "subagents_spawned": (result.get("subagent_stats") or {}).get("spawned")})
    else:
        usage_source = "partial"
        models = defaultdict(lambda: {k: 0 for k in TOKEN_FIELDS} | {"cost_usd": None})
        for u in msg_usage.values():
            for k in TOKEN_FIELDS:
                models[u["model"] or "unknown"][k] += u.get(k, 0)
        models = dict(models)
        meta.update({"status": "cut off (no result event)", "cost_usd": None,
                     "duration_ms": int((max(stamps) - min(stamps)) * 1000) if stamps else None,
                     "num_turns": len(msg_usage), "subagents_spawned": len(subagents)})

    by_agent: dict[str, dict] = defaultdict(lambda: {k: 0 for k in TOKEN_FIELDS} | {"messages": 0})
    for u in msg_usage.values():
        a = by_agent[u["agent"] or "main"]
        a["messages"] += 1
        for k in TOKEN_FIELDS:
            a[k] += u.get(k, 0)

    totals = {k: sum(m.get(k) or 0 for m in models.values()) for k in TOKEN_FIELDS}
    return {"meta": meta, "usage_source": usage_source, "models": models, "totals": totals,
            "tools": dict(sorted(tools.items(), key=lambda kv: -kv[1]["calls"])), "subagents": subagents,
            "usage_by_agent": dict(by_agent), "entries": entries}


def _n(x) -> str:
    return f"{x:,}" if isinstance(x, int) else "-"


def _usd(x) -> str:
    return f"${x:,.2f}" if isinstance(x, (int, float)) else "n/a"


def _dur(ms) -> str:
    if not isinstance(ms, (int, float)):
        return "-"
    s = int(ms / 1000)
    return f"{s // 3600}h {s % 3600 // 60:02d}m" if s >= 3600 else f"{s // 60}m {s % 60:02d}s"


def summary_md(s: dict) -> str:
    m, t = s["meta"], s["totals"]
    calls = sum(x["calls"] for x in s["tools"].values())
    errors = sum(x["errors"] for x in s["tools"].values())
    out = ["## Session summary", "",
           "| Status | Model | Duration | Turns | Tool calls | Tool errors | Subagents | Cost |",
           "| --- | --- | --- | --- | --- | --- | --- | --- |",
           f"| {m.get('status')} | {m.get('model') or '-'} | {_dur(m.get('duration_ms'))} | {_n(m.get('num_turns'))} "
           f"| {calls:,} | {errors:,} | {_n(m.get('subagents_spawned'))} | {_usd(m.get('cost_usd'))} |", ""]
    if s["usage_source"] == "partial":
        out += ["> The run stopped before Claude Code wrote its final totals. Token counts below come from the "
                "stream and undercount output tokens. Cost is not available.", ""]
    out += ["### Tokens and cost by model", "", "| Model | Input | Output | Cache read | Cache write | Cost |",
            "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for name, u in s["models"].items():
        out.append(f"| {name} | {_n(u['input'])} | {_n(u['output'])} | {_n(u['cache_read'])} | {_n(u['cache_write'])} | {_usd(u['cost_usd'])} |")
    out.append(f"| **Total** | {_n(t['input'])} | {_n(t['output'])} | {_n(t['cache_read'])} | {_n(t['cache_write'])} | {_usd(m.get('cost_usd'))} |")
    out += ["", "### Tools", "", "| Tool | Calls | Errors | Unfinished | Time |", "| --- | ---: | ---: | ---: | ---: |"]
    for name, x in s["tools"].items():
        out.append(f"| {name} | {x['calls']} | {x['errors']} | {x['unfinished']} | {_dur(x['seconds'] * 1000)} |")
    if s["subagents"]:
        out += ["", "### Subagents", "", "| Description | Type | Status | Tool uses | Tokens | Duration |",
                "| --- | --- | --- | ---: | ---: | ---: |"]
        for a in s["subagents"].values():
            out.append(f"| {a.get('description') or '-'} | {a.get('type') or '-'} | {a.get('status') or '-'} "
                       f"| {_n(a.get('tool_uses'))} | {_n(a.get('tokens'))} | {_dur(a.get('duration_ms'))} |")
    return "\n".join(out) + "\n"


def compare_md(sessions: list[dict]) -> str:
    out = ["## Sessions", "", "| Transcript | Status | Model | Duration | Turns | Tool calls | Errors | Subagents | Tokens in / out | Cost |",
           "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for s in sessions:
        m, t = s["meta"], s["totals"]
        calls = sum(x["calls"] for x in s["tools"].values())
        errors = sum(x["errors"] for x in s["tools"].values())
        tin = t["input"] + t["cache_read"] + t["cache_write"]
        out.append(f"| {m['transcript']} | {m.get('status')} | {m.get('model') or '-'} | {_dur(m.get('duration_ms'))} "
                   f"| {_n(m.get('num_turns'))} | {calls:,} | {errors:,} | {_n(m.get('subagents_spawned'))} "
                   f"| {tin:,} / {t['output']:,}{'*' if s['usage_source'] == 'partial' else ''} | {_usd(m.get('cost_usd'))} |")
    if any(s["usage_source"] == "partial" for s in sessions):
        out += ["", "\\* Run cut off; tokens from the stream, output undercounted."]
    return "\n".join(out) + "\n"


def timeline_md(s: dict) -> str:
    names = {k: (v.get("description") or k) for k, v in s["subagents"].items()}
    out = [summary_md(s), "## Timeline", ""]
    for x in s["entries"]:
        who = f"[{names.get(x['agent'], x['agent'])}] " if x.get("agent") else ""
        if x["kind"] == "tool":
            status = "running" if x["output"] is None else ("error" if x["is_error"] else "ok")
            out += [f"- {who}**{x['tool']}** `{x['brief']}` ({status}, {_dur(x['duration_ms'])})"]
        elif x["kind"] == "text":
            out += [f"- {who}**Assistant:** " + x["text"].replace("\n", "\n  ")]
        elif x["kind"] in ("prompt", "subagent_prompt"):
            out += [f"- {who}**Prompt:** " + x["text"][:600].replace("\n", "\n  ")]
    return "\n".join(out) + "\n"


HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Session log</title>
<style>
:root{--bg:#fbfaf8;--fg:#1d1d1b;--mut:#6b6a66;--line:#e3e1dc;--card:#fff;--err:#b42318;--ok:#2f7d4f;--acc:#3d5a98;--sub:#f3f1ec}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--fg:#ecebe7;--mut:#9b9a95;--line:#2e2d2a;--card:#1f1f1d;--err:#f0786c;--ok:#6cc08b;--acc:#8fa8e0;--sub:#262523}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px}h1{font-size:20px;margin:0 0 4px}h2{font-size:16px;margin:28px 0 8px}
.mut{color:var(--mut)}.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:8px;margin:16px 0}
.tile{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px}.tile b{display:block;font-size:18px;font-variant-numeric:tabular-nums}
.tile span{color:var(--mut);font-size:12px}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
.tw{overflow-x:auto}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);white-space:nowrap}td.r,th.r{text-align:right}
.note{background:var(--sub);border-left:3px solid var(--err);padding:8px 12px;border-radius:4px}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0}.bar input,.bar select{font:inherit;padding:4px 8px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg)}
.e{border:1px solid var(--line);border-radius:6px;background:var(--card);margin:6px 0}.e.agent{margin-left:24px;background:var(--sub)}
.e summary{cursor:pointer;padding:6px 10px;display:flex;gap:8px;align-items:baseline;overflow:hidden}.e summary code{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;flex:1}
.k{font-weight:600;flex:none}.k.tool{color:var(--acc)}.st{flex:none;font-size:12px}.st.error{color:var(--err)}.st.ok{color:var(--ok)}.who{flex:none;font-size:12px;color:var(--mut)}
pre{margin:0;padding:8px 10px;border-top:1px solid var(--line);white-space:pre-wrap;word-break:break-word;font:12px/1.45 ui-monospace,Menlo,monospace;max-height:420px;overflow:auto}
</style></head><body><main>
<h1>Session log</h1><div class="mut" id="sub"></div><div class="tiles" id="tiles"></div><div id="note"></div>
<h2>Tokens and cost by model</h2><div class="tw"><table id="models"></table></div>
<h2>Tools</h2><div class="tw"><table id="tools"></table></div>
<div id="subs"></div>
<h2>Timeline</h2>
<div class="bar"><input id="q" placeholder="Search" size="24"><select id="kind"><option value="">All entries</option><option value="tool">Tool calls</option><option value="error">Errors only</option><option value="text">Assistant text</option><option value="thinking">Thinking</option></select><select id="who"><option value="">All agents</option><option value="main">Main agent</option></select><span class="mut" id="count"></span></div>
<div id="tl"></div>
</main>
<script type="application/json" id="data">__DATA__</script>
<script>
const S=JSON.parse(document.getElementById('data').textContent),M=S.meta,T=S.totals;
const n=x=>typeof x==='number'?x.toLocaleString():'-',usd=x=>typeof x==='number'?'$'+x.toFixed(2):'n/a';
const dur=ms=>{if(typeof ms!=='number')return'-';const s=Math.round(ms/1000);return s>=3600?`${Math.floor(s/3600)}h ${String(Math.floor(s%3600/60)).padStart(2,'0')}m`:`${Math.floor(s/60)}m ${String(s%60).padStart(2,'0')}s`};
const el=(t,a={},...c)=>{const e=document.createElement(t);Object.assign(e,a);e.append(...c);return e};
const tools=Object.values(S.tools),calls=tools.reduce((a,b)=>a+b.calls,0),errs=tools.reduce((a,b)=>a+b.errors,0);
document.getElementById('sub').textContent=[M.model,M.claude_code_version&&'Claude Code '+M.claude_code_version,M.session_id].filter(Boolean).join(' · ');
for(const [l,v] of [['Status',M.status],['Cost',usd(M.cost_usd)],['Duration',dur(M.duration_ms)],['Turns',n(M.num_turns)],['Tool calls',n(calls)],['Tool errors',n(errs)],['Subagents',n(M.subagents_spawned)],['Output tokens',n(T.output)]])
 document.getElementById('tiles').append(el('div',{className:'tile'},el('b',{textContent:v??'-'}),el('span',{textContent:l})));
if(S.usage_source==='partial')document.getElementById('note').append(el('p',{className:'note',textContent:'The run stopped before Claude Code wrote its final totals. Token counts come from the stream and undercount output tokens. Cost is not available.'}));
const table=(id,head,rows)=>{const t=document.getElementById(id);t.append(el('tr',{},...head.map(([h,r])=>el('th',{textContent:h,className:r?'r':''}))));for(const row of rows)t.append(el('tr',{},...row.map((v,i)=>el('td',{textContent:v,className:head[i][1]?'r':''}))))};
const mrows=Object.entries(S.models).map(([k,u])=>[k,n(u.input),n(u.output),n(u.cache_read),n(u.cache_write),usd(u.cost_usd)]);mrows.push(['Total',n(T.input),n(T.output),n(T.cache_read),n(T.cache_write),usd(M.cost_usd)]);
table('models',[['Model'],['Input',1],['Output',1],['Cache read',1],['Cache write',1],['Cost',1]],mrows);
table('tools',[['Tool'],['Calls',1],['Errors',1],['Unfinished',1],['Time',1]],Object.entries(S.tools).map(([k,x])=>[k,n(x.calls),n(x.errors),n(x.unfinished),dur(x.seconds*1000)]));
const names={};for(const [k,a] of Object.entries(S.subagents)){names[k]=a.description||k;document.getElementById('who').append(el('option',{value:k,textContent:a.description||k}))}
if(Object.keys(S.subagents).length){const d=document.getElementById('subs');d.append(el('h2',{textContent:'Subagents'}),el('div',{className:'tw'},el('table',{id:'subt'})));
 table('subt',[['Description'],['Type'],['Status'],['Tool uses',1],['Tokens',1],['Duration',1]],Object.values(S.subagents).map(a=>[a.description||'-',a.type||'-',a.status||'-',n(a.tool_uses),n(a.tokens),dur(a.duration_ms)]))}
const label={prompt:'Prompt',subagent_prompt:'Prompt',text:'Assistant',thinking:'Thinking'};
function render(){const q=document.getElementById('q').value.toLowerCase(),k=document.getElementById('kind').value,w=document.getElementById('who').value,tl=document.getElementById('tl');tl.replaceChildren();let shown=0;
 for(const x of S.entries){if(w&&(w==='main'?x.agent:x.agent!==w))continue;
  if(k==='error'?!(x.kind==='tool'&&x.is_error):k&&x.kind!==k)continue;
  const body=[x.brief,x.text,x.input,x.output].filter(Boolean).join('\\n');if(q&&!(body.toLowerCase().includes(q)||(x.tool||'').toLowerCase().includes(q)))continue;
  if(++shown>3000)break;
  const s=el('summary');
  if(x.kind==='tool'){const st=x.output==null?'running':x.is_error?'error':'ok';s.append(el('span',{className:'k tool',textContent:x.tool}),el('code',{textContent:x.brief}),el('span',{className:'st '+st,textContent:st+' · '+dur(x.duration_ms)}))}
  else s.append(el('span',{className:'k',textContent:label[x.kind]}),el('code',{textContent:(x.text||'').split('\\n')[0]}));
  if(x.agent)s.append(el('span',{className:'who',textContent:names[x.agent]||'subagent'}));
  const d=el('details',{className:'e'+(x.agent?' agent':'')},s);
  if(x.kind==='tool'){d.append(el('pre',{textContent:'Input\\n'+x.input}));if(x.output!=null)d.append(el('pre',{textContent:'Output\\n'+x.output}))}else d.append(el('pre',{textContent:x.text}));
  tl.append(d)}
 document.getElementById('count').textContent=shown>3000?'Showing the first 3000 matches':shown+' entries'}
for(const id of['q','kind','who'])document.getElementById(id).addEventListener('input',render);render();
</script></body></html>
"""


def write_html(s: dict, path: Path) -> None:
    data = json.dumps(s).replace("</", "<\\/")
    path.write_text(HTML.replace("__DATA__", data))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    a = sp.add_parser("summary")
    a.add_argument("transcripts", type=Path, nargs="+")
    b = sp.add_parser("render")
    b.add_argument("transcript", type=Path)
    b.add_argument("--out", type=Path, required=True)
    b.add_argument("--prompt", type=Path)
    args = ap.parse_args(argv)

    if args.cmd == "summary":
        sessions = [parse(p) for p in args.transcripts]
        print(summary_md(sessions[0]) if len(sessions) == 1 else compare_md(sessions))
        return 0
    prompt = args.prompt.read_text() if args.prompt and args.prompt.is_file() else None
    s = parse(args.transcript, prompt)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "summary.md").write_text(summary_md(s))
    (args.out / "session.md").write_text(timeline_md(s))
    (args.out / "session.json").write_text(json.dumps(s, indent=1))
    write_html(s, args.out / "session.html")
    print(f"Wrote summary.md, session.md, session.json and session.html to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
