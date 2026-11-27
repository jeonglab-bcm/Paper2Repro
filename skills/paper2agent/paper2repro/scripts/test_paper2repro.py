#!/usr/bin/env python3
"""Self-test for the paper2repro scripts. Run after changing any of them:

    python3 scripts/test_paper2repro.py
"""

import copy
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLE = os.path.join(HERE, "..", "assets", "example-results.json")


def run(script, *args, stdin=None):
    p = subprocess.run([sys.executable, os.path.join(HERE, script), *args], input=stdin,
                       capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def results_case(tmp, name, mutate, *extra):
    data = json.load(open(EXAMPLE))
    mutate(data)
    path = os.path.join(tmp, f"{name}.json")
    json.dump(data, open(path, "w"))
    # Inside the fossil repository the example's renders exist; elsewhere skip that check.
    root = os.path.join(HERE, "..", "..", "..", "..", "PMC1847688")
    return run("check_results.py", path, "--write", *extra, *(["--root", root] if os.path.isdir(root) else ["--skip-files"]))


def verdict_after(tmp, name, mutate, iid, *extra):
    """(verdict, basis, summary, output) of one item after check_results.py --write, or (None, None, None, output)."""
    rc, out = results_case(tmp, name, mutate, *extra)
    if rc != 0:
        return None, None, None, out
    d = json.load(open(os.path.join(tmp, f"{name}.json")))
    i = item(d, iid)
    return i.get("verdict"), i.get("basis"), d["summary"], out


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
        # a new drawing of ours that is on the published frame: same panel, same axis limits
        redrawn = {"panel_size_difference_px": [0, -1], "ink_outside_frame": 0.0, "axes": [
            {"axis": "x", "published": ["2000", "10000"], "ours": [2000, 10010]},
            {"axis": "y", "scale": "log", "published": [0.001, 1], "ours": [0.001, 1]},
            {"axis": "bars", "published": ["mean", "median", "ES"], "ours": ["mean", "median", "ES"]}]}
        lay = lambda d, **change: item(d, "fig2").update(layout={**redrawn, **change})  # noqa: E731
        for name, mutate in {
            "a new drawing on the published frame": lambda d: lay(d),
            "a drawing with no axes to share, with the reason": lambda d: item(d, "fig2").update(layout={"not_comparable": "A network laid out at random in the paper and in ours."}),
            "a panel off by the item's own pixel tolerance": lambda d: (item(d, "fig2")["pixels"].update(tolerance_px=3), lay(d, panel_size_difference_px=[3, 0])),
            "a figure that is not attempted needs no layout": lambda d: item(d, "fig1").pop("layout", None),
        }.items():
            rc, out = results_case(tmp, name.replace(" ", "_"), mutate)
            if rc != 0:
                failures.append(f"check_results.py refused {name}: {out}")
        broken = {
            "figure with a picture and no layout": lambda d: item(d, "fig2").pop("layout"),
            "panel off the published frame": lambda d: lay(d, panel_size_difference_px=[0, -15]),
            "ours larger than the published picture": lambda d: lay(d, ink_outside_frame=0.2),
            "new drawing without its axis limits": lambda d: lay(d, axes=[]),
            "axis limits that are not the published ones": lambda d: lay(d, axes=[{"axis": "y", "published": [0, 250], "ours": [0, 300]}]),
            "log axis that starts a decade off": lambda d: lay(d, axes=[{"axis": "y", "scale": "log", "published": [0.001, 1], "ours": [0.01, 1]}]),
            "bars in another order": lambda d: lay(d, axes=[{"axis": "bars", "published": ["mean", "median"], "ours": ["median", "mean"]}]),
            "not comparable without a reason": lambda d: item(d, "fig2").update(layout={"not_comparable": " "}),
            "layout without the measured panel": lambda d: item(d, "fig2").update(layout={"axes": redrawn["axes"], "ink_outside_frame": 0}),
            "no wrong-input control": lambda d: item(d, "fig2")["pixels"].update(controls=[c for c in item(d, "fig2")["pixels"]["controls"] if c["kind"] != "wrong_input"]),
            "threshold below a control": lambda d: item(d, "fig2")["pixels"].update(threshold=0.98),
            "open cause with one test": lambda d: item(d, "fig9.b")["cause"].update(hypotheses=item(d, "fig9.b")["cause"]["hypotheses"][:1]),
            "partly without a cause": lambda d: item(d, "fig9.b").pop("cause"),
            "fitted setting without sensitivity": lambda d: item(d, "fig2")["assumptions"][0].pop("sensitivity"),
            "figure without its renders": lambda d: item(d, "fig7").update(outputs=[]),
            "input without a checksum": lambda d: d["run"]["inputs"][0].pop("sha256"),
            "no skill version": lambda d: d.pop("skill"),
            "skill version not semver": lambda d: d["skill"].update(version="0.5", tag="paper2repro-v0.5"),
            "skill tag not its version": lambda d: d["skill"].update(tag="paper2repro-v0.4.0"),
        }
        for name, mutate in broken.items():
            rc, out = results_case(tmp, name.replace(" ", "_"), mutate)
            if rc == 0:
                failures.append(f"check_results.py accepted: {name}")
        # From 0.8.0 an open cause, or a not-attempted item that had something to lose, carries the checklist.
        done = {"wayback": "web.archive.org searched for the lab page: no capture", "references": "ref. 12's settings tried (H3)",
                "leakage": "n/a: no training step", "convergence": "rerun at the paper's 500 iterations: same counts"}

        def at_080(d, checklist=True):
            d["skill"].update(version="0.8.0", tag="paper2repro-v0.8.0")
            for i in d["items"]:
                c = i.get("cause") or {}
                if checklist and (c.get("status") == "open" or i.get("verdict") == "not_attempted") and c.get("category") != "not_a_result":
                    c["checklist"] = dict(done)
        for name, mutate in {
            "0.8.0 with every checklist": at_080,
            "0.7.0 needs no checklist": lambda d: d["skill"].update(version="0.7.0", tag="paper2repro-v0.7.0"),
            "0.8.0: a diagram not attempted needs no checklist": lambda d: (at_080(d), item(d, "fig1")["cause"].pop("checklist", None)),
        }.items():
            rc, out = results_case(tmp, re.sub(r"\W+", "_", name), mutate)
            if rc != 0:
                failures.append(f"check_results.py refused {name}: {out}")
        for name, mutate in {
            "0.8.0 open cause without a checklist": lambda d: (at_080(d), item(d, "fig9.b")["cause"].pop("checklist")),
            "0.8.0 not attempted without a checklist": lambda d: (at_080(d), item(d, "fig9.c")["cause"].pop("checklist")),
            "checklist with a bare n/a": lambda d: (at_080(d), item(d, "fig9.b")["cause"]["checklist"].update(leakage="n/a")),
            "checklist missing convergence": lambda d: (at_080(d), item(d, "fig9.b")["cause"]["checklist"].pop("convergence")),
            "checklist with an unknown entry": lambda d: (at_080(d), item(d, "fig9.b")["cause"]["checklist"].update(vibes="fine")),
            "a checklist given before 0.8.0 is still checked": lambda d: item(d, "fig9.b")["cause"].update(checklist={"wayback": ""}),
        }.items():
            rc, out = results_case(tmp, re.sub(r"\W+", "_", name), mutate)
            if rc == 0:
                failures.append(f"check_results.py accepted: {name}")
            elif "checklist" not in out:
                failures.append(f"check_results.py refused {name} for another reason: {out[:300]}")

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

        # 0.7.0: the noise band. Cases from fossil's reviewer overrides, where the printed digits were too strict.
        def one_field(d, expected, observed, noise):
            t = item(d, "text.plasma_totals")
            t["values"]["fields"] = [{"name": "f", "expected": expected, "observed": observed, **({"noise": noise} if noise is not None else {})}]
        noise_cases = {
            # PMC3392844 text.indication: 0.9111 against 0.9110, inside our seed range
            "seed range": (("0.9110", 0.9111, {"runs": [0.9109, 0.9111, 0.9112]}), "agrees"),
            # PMC522806 Fig. 4 colon: 3 of 62 samples, the paper gives no folds or seeds
            "three of 62 samples": (("91.94", 87.10, {"samples": 3, "n": 62, "scale": 100, "why": "no folds or seeds given"}), "agrees"),
            # PMC2661051 Table 5: one rate outside the band at 2 Monte Carlo SE is back inside
            "two Monte Carlo SE": (("0.050", 0.056, {"mc_se": 0.0035}), "agrees"),
            "outside every band": (("0.9110", 0.9200, {"runs": [0.9109, 0.9112]}), "differs"),
            "no band, printed digits only": (("0.9110", 0.9111, None), "differs"),
        }
        for name, (args, want) in noise_cases.items():
            got, basis, _, out = verdict_after(tmp, "noise_" + name.replace(" ", "_"), lambda d, a=args: one_field(d, *a), "text.plasma_totals")
            if got != want:
                failures.append(f"noise band, {name}: {got}, expected {want} {out if got is None else ''}")
            elif want == "agrees" and not (basis or "").startswith("within noise"):
                failures.append(f"noise band, {name}: basis {basis!r} should say within noise")
        for name, noise in {
            "more than three samples": {"samples": 4, "n": 62, "scale": 100, "why": "no folds"},
            "samples without saying what the paper leaves out": {"samples": 2, "n": 62, "scale": 100},
            "one run is not a spread": {"runs": [0.9111]},
            "noise with nothing in it": {},
        }.items():
            rc, out = results_case(tmp, "badnoise", lambda d, n=noise: one_field(d, "0.9110", 0.9111, n))
            if rc == 0:
                failures.append(f"check_results.py accepted: {name}")

        # 0.7.0: claims. An item whose claims hold agrees when its cause is explained; with an open cause a person decides.
        claim = {"id": "c1", "text": "Most classes are rare", "where": "Results, p. 5", "items": ["fig9.b"],
                 "test": "share of classes in the first bar", "result": "holds"}
        explain = lambda d: item(d, "fig9.b")["cause"].update(status="explained", category="data_differs", evidence=["notes.md"])  # noqa: E731
        got, basis, summary, out = verdict_after(tmp, "claim_explained", lambda d: (d.update(claims=[claim]), explain(d)), "fig9.b")
        if got != "agrees" or not (basis or "").startswith("claim holds") or summary.get("claims") != {"fails": 0, "holds": 1, "partly": 0}:
            failures.append(f"a claim that holds on an explained gap: {got} {basis!r} {summary} {out if got is None else ''}")
        got, basis, summary, out = verdict_after(tmp, "claim_open", lambda d: d.update(claims=[claim]), "fig9.b")
        if got != "partly" or summary.get("for_review") != 1 or "REVIEW fig9.b" not in out:
            failures.append(f"a claim that holds on an open gap should go to a person: {got} {summary} {out}")
        got, _, _, out = verdict_after(tmp, "claim_partly", lambda d: (d.update(claims=[{**claim, "result": "partly"}]), explain(d)), "fig9.b")
        if got != "partly":
            failures.append(f"a claim that only partly holds should raise nothing: {got} {out if got is None else ''}")
        for name, c in {
            "claim resting on no item": {**claim, "items": []},
            "claim resting on a missing item": {**claim, "items": ["fig99"]},
            "claim without a test": {**claim, "test": ""},
            "claim with an unknown result": {**claim, "result": "mostly"},
        }.items():
            rc, out = results_case(tmp, "badclaim", lambda d, c=c: d.update(claims=[c]))
            if rc == 0:
                failures.append(f"check_results.py accepted: {name}")

        # 0.7.0: a review sets the verdict and must say why.
        review = {"verdict": "agrees", "computed": "partly", "by": "someone", "url": "https://example.org/r/1",
                  "reason": {"kind": "noise", "text": "within 1 to 3 samples; the paper gives no folds"}}
        got, _, summary, out = verdict_after(tmp, "review_ok", lambda d: item(d, "fig9.b").update(review=review), "fig9.b")
        if got != "agrees" or summary.get("reviewed") != 1:
            failures.append(f"a review with a reason: {got} {summary} {out if got is None else ''}")
        follows = {**review, "reason": {"kind": "follows", "item": "fig2", "text": "the same numbers as Fig. 2, accepted"}}
        got, _, _, out = verdict_after(tmp, "review_follows", lambda d: item(d, "fig9.b").update(review=follows), "fig9.b")
        if got != "agrees":
            failures.append(f"a review that follows another item: {got} {out}")
        for name, r in {
            "review without a reason": {k: v for k, v in review.items() if k != "reason"},
            "review 'without comment'": {**review, "reason": {"kind": "judgment", "text": "Review card: Agrees, without comment."}},
            "review that only restates the change": {**review, "reason": {"kind": "judgment", "text": "Partly → Agrees."}},
            "review that restates the change after a label": {**review, "reason": {"kind": "judgment", "text": "Review: Fig. 1 Partly to Agrees."}},
            "review pointing to a comment": {**review, "reason": {"kind": "judgment", "text": "Set per review comment #6000027304."}},
            "review with an unknown kind": {**review, "reason": {"kind": "vibes", "text": "looks fine to me"}},
            "follows naming no item": {**review, "reason": {"kind": "follows", "text": "as Table 3"}},
            "review of a verdict the numbers no longer give": {**review, "computed": "differs"},
        }.items():
            rc, out = results_case(tmp, "badreview", lambda d, r=r: item(d, "fig9.b").update(review=r))
            if rc == 0:
                failures.append(f"check_results.py accepted: {name}")
        # A review already on main without a reason warns; a changed one fails.
        old = {k: v for k, v in review.items() if k != "reason"}
        base = os.path.join(tmp, "base.json")
        data = json.load(open(EXAMPLE))
        item(data, "fig9.b")["review"] = old
        json.dump(data, open(base, "w"))
        rc, out = results_case(tmp, "review_on_main", lambda d: item(d, "fig9.b").update(review=old), "--base", base)
        if rc != 0 or "WARN fig9.b" not in out:
            failures.append(f"an unchanged review on main without a reason should warn, not fail: {out}")
        rc, out = results_case(tmp, "review_changed", lambda d: item(d, "fig9.b").update(review={**old, "by": "someone-else"}), "--base", base)
        if rc == 0:
            failures.append("a changed review without a reason should fail even with --base")
        # A --base that is not there says so, and every review is checked as new (a new paper has no file on main).
        missing = os.path.join(tmp, "not-on-main.json")
        rc, out = results_case(tmp, "base_missing", lambda d: item(d, "fig9.b").update(review=review), "--base", missing)
        if rc != 0 or f"WARN --base {missing} not found" not in out:
            failures.append(f"a missing --base should warn and check every review as new: {out}")
        rc, out = results_case(tmp, "base_missing_old", lambda d: item(d, "fig9.b").update(review=old), "--base", missing)
        if rc == 0 or "not found" not in out:
            failures.append(f"with a missing --base, a review without a reason should fail: {out}")

        # skill_version.py: the block comes from VERSION; it replaces an old one and keeps the rest.
        version = open(os.path.join(HERE, "..", "VERSION")).read().strip()
        stamped = os.path.join(tmp, "stamped.json")
        old = json.load(open(EXAMPLE))
        old["skill"] = {"name": "paper2repro", "version": "0.0.1"}
        json.dump(old, open(stamped, "w"))
        rc, out = run("skill_version.py", stamped)
        new = json.load(open(stamped)) if rc == 0 else {}
        skill = new.get("skill", {})
        if (skill.get("version"), skill.get("tag")) != (version, f"paper2repro-v{version}") or set(skill) != {"name", "version", "tag", "commit", "modified"}:
            failures.append(f"skill_version.py wrote {skill} ({out[:200]})")
        keys = list(new)
        if [k for k in keys if k != "skill"] != [k for k in old if k != "skill"] or keys[keys.index("session") + 1:][:1] != ["skill"] or new.get("items") != old["items"]:
            failures.append(f"skill_version.py should keep the other fields in order: {list(new)}")
        import shutil
        bare = os.path.join(tmp, "bare-skill")
        shutil.copytree(os.path.join(HERE, ".."), bare, ignore=shutil.ignore_patterns("package-template", "__pycache__"))
        p = subprocess.run([sys.executable, os.path.join(bare, "scripts", "skill_version.py")], capture_output=True, text=True)
        if p.returncode != 0 or json.loads(p.stdout or "{}").get("commit") is not None:
            failures.append(f"skill_version.py outside a git checkout should report commit null: {p.stdout}{p.stderr}")

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
            # Rows Claude Code writes as the user that nobody typed (fossil#140): not prompts.
            {"type": "user", "timestamp": "2026-01-01T00:01:00Z", "message": {"role": "user", "content":
                "<task-notification> <task-type>queued-remote-notifications</task-type> <status>pending</status> <summary>1 unread notification (GitHub activity)</summary></task-notification>"}},
            {"type": "user", "timestamp": "2026-01-01T00:02:00Z", "message": {"role": "user", "content":
                "<task-notification> <task-id>b1</task-id> <summary>Monitor event: \"CI checks on PR #1\"</summary></task-notification>"}},
            {"type": "user", "timestamp": "2026-01-01T00:03:00Z", "message": {"role": "user", "content": "<bash-input>git pull</bash-input>"}},
            {"type": "user", "timestamp": "2026-01-01T00:03:01Z", "message": {"role": "user", "content": "<bash-stdout>Already up to date.</bash-stdout><bash-stderr></bash-stderr>"}},
            {"type": "user", "timestamp": "2026-01-01T00:04:00Z", "message": {"role": "user", "content":
                "<command-name>/model</command-name> <command-message>model</command-message> <command-args>(model)</command-args>"}},
            {"type": "user", "timestamp": "2026-01-01T00:05:00Z", "message": {"role": "user", "content":
                "<command-name>/compact</command-name> <command-message>compact</command-message> <command-args></command-args>"}},
            {"type": "user", "timestamp": "2026-01-01T00:05:30Z", "message": {"role": "user", "content": "/compact"}},
            {"type": "user", "timestamp": "2026-01-01T00:06:00Z", "message": {"role": "user", "content": "[Request interrupted by user for tool use]"}},
            # A skill invoked as a slash command is a typed prompt and still counts.
            {"type": "user", "timestamp": "2026-01-01T00:07:00Z", "message": {"role": "user", "content":
                "<command-message>paper2repro</command-message> <command-name>/paper2repro</command-name> <command-args>Reproduce PMC2</command-args>"}},
        ]
        tr = os.path.join(tmp, "s1.jsonl")
        open(tr, "w").write("\n".join(json.dumps(r) for r in rows))
        rc, out = run("session_ledger.py", "--transcript", tr, "--out", os.path.join(tmp, "ledger"))
        led = json.load(open(os.path.join(tmp, "ledger", "ledger.json"))) if rc == 0 else {}
        want = {"human_prompts": 3, "mid_turn_prompts": 1, "system_notifications": 2, "assistant_responses": 1, "tool_calls": 1}
        for k, v in want.items():
            if led.get(k) != v:
                failures.append(f"session_ledger.py {k}: {led.get(k)}, expected {v} ({out[:200]})")
        if led.get("tokens", {}).get("output") != 9:
            failures.append(f"session_ledger.py should keep the last usage of a message: {led.get('tokens')}")

        # session_ledger.py masks personal details as it writes, and --check finds any left.
        rows = [
            {"type": "user", "timestamp": "2026-01-01T00:00:00Z", "sessionId": "s2", "message": {"role": "user", "content":
                "I am Jane Q. Doe (jane.doe@example.edu); my files are in /Users/jdoe/papers and C:\\Users\\jdoe\\x"}},
            {"type": "assistant", "timestamp": "2026-01-01T00:00:05Z", "message": {"id": "m1", "model": "m", "usage": {"output_tokens": 1},
                "content": [{"type": "text", "text": "Thanks, JANE Q. DOE. Reading /home/jdoe/papers (git@github.com:org/repo); token ghp_" + "a" * 30}]}},
        ]
        tr = os.path.join(tmp, "s2.jsonl")
        open(tr, "w").write("\n".join(json.dumps(r) for r in rows))
        out_dir = os.path.join(tmp, "ledger2")
        rc, out = run("session_ledger.py", "--transcript", tr, "--out", out_dir, "--redact", "Jane Q. Doe", "--project-dir", tmp)
        written = "".join(open(os.path.join(out_dir, n)).read() for n in ("ledger.json", "conversation.md")) if rc == 0 else out
        for leak in ("Jane", "JANE", "jane.doe@", "/Users/jdoe", "/home/jdoe", "jdoe\\", "ghp_"):
            if leak in written:
                failures.append(f"session_ledger.py left {leak!r} in the ledger: {written[:400]}")
        if rc == 0 and "git@github.com:org/repo" not in written:
            failures.append("session_ledger.py should keep a git SSH remote, which is not an email")
        rc, out = run("session_ledger.py", "--check", out_dir, "--redact", "Jane Q. Doe", "--project-dir", tmp)
        if rc != 0:
            failures.append(f"session_ledger.py --check should pass on a masked ledger: {out}")
        with open(os.path.join(out_dir, "conversation.md"), "a") as f:
            f.write("\nadded by hand: jane.doe@example.edu, Jane Q. Doe\n")
        rc, out = run("session_ledger.py", "--check", out_dir, "--redact", "Jane Q. Doe", "--project-dir", tmp)
        if rc == 0 or "email" not in out or "name" not in out:
            failures.append(f"session_ledger.py --check should find the email and the name added by hand: {out}")

        # check_package.py: notebook comparison, TUTORIAL.md rendering, and the template's layout.
        sys.path.insert(0, HERE)
        import check_package as cp
        if not cp.same_text("rate 0.6931471805599453\n", "rate 0.6931471805599452"):
            failures.append("check_package.same_text should allow rounding-level differences")
        for a, b in (("rate 0.6931", "rate 0.6932"), ("4 of 4 wells", "3 of 4 wells"), ("A1 ok", "A2 ok")):
            if cp.same_text(a, b):
                failures.append(f"check_package.same_text accepted {a!r} vs {b!r}")

        def nb(*cells):
            return {"nbformat": 4, "cells": [
                {"cell_type": "code", "source": src, "metadata": {"tags": tags}, "execution_count": 1,
                 "outputs": [{"output_type": "stream", "name": "stdout", "text": out}] if out else []}
                for src, out, tags in cells]}
        committed = nb(("print(x)", "x = 1.0\n", []), ("print(t)", "took 3.1 s\n", ["nondeterministic"]))
        compared, skipped, problems = cp.compare_notebooks(committed, nb(("print(x)", "x = 1.0\n", []), ("print(t)", "took 2.7 s\n", [])))
        if (compared, skipped, problems) != (1, 1, []):
            failures.append(f"compare_notebooks on an equal run: {compared}, {skipped}, {problems}")
        _, _, problems = cp.compare_notebooks(committed, nb(("print(x)", "x = 1.5\n", []), ("print(t)", "", [])))
        if len(problems) != 1:
            failures.append(f"compare_notebooks should report one changed output: {problems}")
        broken = nb(("print(x)", "", []), ("print(t)", "", []))
        broken["cells"][0]["outputs"] = [{"output_type": "error", "ename": "NameError", "evalue": "x", "traceback": []}]
        _, _, problems = cp.compare_notebooks(committed, broken)
        if not any("NameError" in p for p in problems):
            failures.append(f"compare_notebooks should report an error output: {problems}")

        png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        rendered = {"cells": [
            {"cell_type": "markdown", "source": ["# Title\n", "Text."]},
            {"cell_type": "code", "source": "plot()", "outputs": [
                {"output_type": "stream", "name": "stdout", "text": "ok\n"},
                {"output_type": "display_data", "data": {"image/png": png, "text/plain": "<Figure>"}}]}]}
        text, files = cp.render_markdown(rendered)
        for want in ("# Title\nText.", "```python\nplot()\n```", "```text\nok\n```", "](TUTORIAL_files/cell-02-1.png)"):
            if want not in text:
                failures.append(f"render_markdown output lacks {want!r}")
        if "<Figure>" in text or list(files) != ["cell-02-1.png"] or not files["cell-02-1.png"].startswith(b"\x89PNG"):
            failures.append(f"render_markdown images: {list(files)}")

        template = os.path.join(HERE, "..", "assets", "package-template")
        rc, out = run("check_package.py", template, "--layout-only")
        if rc != 0:
            failures.append(f"the package template should pass --layout-only (stale tutorial? run --write): {out}")
        copy = os.path.join(tmp, "pkg")
        shutil.copytree(template, copy)
        os.remove(os.path.join(copy, "src", "example_method", "data", "README.md"))
        md = os.path.join(copy, "tutorial", "TUTORIAL.md")
        with open(md, "a") as f:
            f.write("\nedited by hand\n")
        rc, out = run("check_package.py", copy, "--layout-only")
        if rc == 0 or "data/README.md" not in out or "TUTORIAL.md matches" not in out:
            failures.append(f"check_package.py should catch missing data provenance and a hand-edited TUTORIAL.md: {out}")
        rpkg = os.path.join(tmp, "rpkg")
        os.makedirs(rpkg)
        with open(os.path.join(rpkg, "DESCRIPTION"), "w") as f:
            f.write("Package: peakfit\nVersion: 0.1.0\n")
        rc, out = run("check_package.py", rpkg, "--layout-only")
        if rc != 2 or "R package" not in out:
            failures.append(f"check_package.py should stop on an R package with exit code 2: {rc} {out}")

    for f in failures:
        print("FAIL", f)
    print("all tests passed" if not failures else f"{len(failures)} failures")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
