#!/usr/bin/env python3
"""Self-test for the paper2repro scripts. Run after changing any of them:

    python3 scripts/test_paper2repro.py
"""

import copy
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLE = os.path.join(HERE, "..", "assets", "example-results.json")


def run(script, *args, stdin=None):
    p = subprocess.run([sys.executable, os.path.join(HERE, script), *args], input=stdin,
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def results_case(tmp, name, mutate):
    data = json.load(open(EXAMPLE))
    mutate(data)
    path = os.path.join(tmp, f"{name}.json")
    json.dump(data, open(path, "w"))
    # Inside the fossil repository the example's renders exist; elsewhere skip that check.
    root = os.path.join(HERE, "..", "..", "..", "..", "PMC1847688")
    return run("check_results.py", path, "--write", *(["--root", root] if os.path.isdir(root) else ["--skip-files"]))


def item(data, iid):
    return next(i for i in data["items"] if i["id"] == iid)


def main():
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        # check_results.py: the example passes; each broken rule is caught.
        rc, out = results_case(tmp, "ok", lambda d: None)
        if rc != 0:
            failures.append(f"example should pass: {out}")
        verdicts = {i["id"]: i["verdict"] for i in json.load(open(os.path.join(tmp, "ok.json")))["items"]}
        expect = {"fig2": "agrees", "fig3.b": "inconclusive", "fig9.b": "partly", "text.plasma_totals": "differs", "fig1": "not_attempted"}
        for k, v in expect.items():
            if verdicts.get(k) != v:
                failures.append(f"{k}: verdict {verdicts.get(k)}, expected {v}")
        broken = {
            "no wrong-input control": lambda d: item(d, "fig2")["pixels"].update(controls=[c for c in item(d, "fig2")["pixels"]["controls"] if c["kind"] != "wrong_input"]),
            "threshold below a control": lambda d: item(d, "fig2")["pixels"].update(threshold=0.98),
            "open cause with one test": lambda d: item(d, "fig9.b")["cause"].update(hypotheses=item(d, "fig9.b")["cause"]["hypotheses"][:1]),
            "partly without a cause": lambda d: item(d, "fig9.b").pop("cause"),
            "fitted setting without sensitivity": lambda d: item(d, "fig2")["assumptions"][0].pop("sensitivity"),
            "figure without its renders": lambda d: item(d, "fig7").update(outputs=[]),
            "input without a checksum": lambda d: d["run"]["inputs"][0].pop("sha256"),
        }
        for name, mutate in broken.items():
            rc, out = results_case(tmp, name.replace(" ", "_"), mutate)
            if rc == 0:
                failures.append(f"check_results.py accepted: {name}")
        # A paper-error exception turns a 2-of-3 table into an exact one.
        def paper_error(d):
            v = item(d, "text.plasma_totals")["values"]
            v["fields"] = [{"name": "a", "expected": "1.25", "observed": 1.2504}, {"name": "b", "expected": "3", "observed": 4}]
            v["exceptions"] = [{"field": "b", "category": "paper_error", "evidence": "printed total contradicts its own rows"}]
            item(d, "text.plasma_totals").pop("cause")
        rc, out = results_case(tmp, "paper_error", paper_error)
        got = item(json.load(open(os.path.join(tmp, "paper_error.json"))), "text.plasma_totals").get("verdict") if rc == 0 else out
        if got != "exact":
            failures.append(f"paper-error exception: {got}")

        # compare_runs.py: numbers within tolerance agree, real changes do not.
        a, b = os.path.join(tmp, "fresh"), os.path.join(tmp, "committed")
        os.makedirs(a), os.makedirs(b)
        json.dump({"x": 1.0, "y": [1, 2]}, open(os.path.join(a, "r.json"), "w"))
        json.dump({"x": 1.0 + 1e-13, "y": [1, 2]}, open(os.path.join(b, "r.json"), "w"))
        open(os.path.join(a, "t.csv"), "w").write("a,b\n1,2.0\n")
        open(os.path.join(b, "t.csv"), "w").write("a,b\n1,2\n")
        rc, out = run("compare_runs.py", a, b)
        if rc != 0:
            failures.append(f"compare_runs.py should agree: {out}")
        open(os.path.join(a, "t.csv"), "w").write("a,b\n1,2.1\n")
        rc, out = run("compare_runs.py", a, b)
        if rc == 0:
            failures.append("compare_runs.py missed a changed CSV cell")
        try:
            from PIL import Image
            Image.new("RGB", (4, 4), "white").save(os.path.join(a, "p.png"), optimize=True)
            Image.new("RGB", (4, 4), "white").save(os.path.join(b, "p.png"), compress_level=0)
            open(os.path.join(a, "t.csv"), "w").write("a,b\n1,2\n")
            rc, out = run("compare_runs.py", a, b)
            if rc != 0:
                failures.append(f"compare_runs.py should compare PNGs by pixels: {out}")
        except ImportError:
            print("Pillow missing: image comparison not tested")

        # session_ledger.py: prompts (typed and mid-turn), deduplicated usage, tool calls.
        rows = [
            {"type": "user", "timestamp": "2026-01-01T00:00:00Z", "sessionId": "s1", "message": {"role": "user", "content": "reproduce PMC1"}},
            {"type": "assistant", "timestamp": "2026-01-01T00:00:05Z", "message": {"id": "m1", "model": "m", "usage": {"input_tokens": 3, "cache_read_input_tokens": 100, "output_tokens": 5}, "content": [{"type": "text", "text": "ok"}]}},
            {"type": "assistant", "timestamp": "2026-01-01T00:00:06Z", "message": {"id": "m1", "model": "m", "usage": {"input_tokens": 3, "cache_read_input_tokens": 100, "output_tokens": 9}, "content": [{"type": "tool_use", "id": "t1", "name": "Bash", "input": {"description": "list files", "command": "ls"}}]}},
            {"type": "user", "timestamp": "2026-01-01T00:00:07Z", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "x"}]}},
            {"type": "attachment", "timestamp": "2026-01-01T00:00:08Z", "attachment": {"type": "queued_command", "prompt": "also add a json", "origin": {"kind": "human"}}},
            {"type": "user", "timestamp": "2026-01-01T00:00:09Z", "isMeta": True, "message": {"role": "user", "content": [{"type": "text", "text": "skill text"}]}},
        ]
        tr = os.path.join(tmp, "s1.jsonl")
        open(tr, "w").write("\n".join(json.dumps(r) for r in rows))
        rc, out = run("session_ledger.py", "--transcript", tr, "--out", os.path.join(tmp, "ledger"))
        led = json.load(open(os.path.join(tmp, "ledger", "ledger.json"))) if rc == 0 else {}
        want = {"human_prompts": 2, "mid_turn_prompts": 1, "assistant_responses": 1, "tool_calls": 1}
        for k, v in want.items():
            if led.get(k) != v:
                failures.append(f"session_ledger.py {k}: {led.get(k)}, expected {v} ({out[:200]})")
        if led.get("tokens", {}).get("output") != 9:
            failures.append(f"session_ledger.py should keep the last usage of a message: {led.get('tokens')}")

    for f in failures:
        print("FAIL", f)
    print("all tests passed" if not failures else f"{len(failures)} failures")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
