#!/usr/bin/env python3
"""Validate a reproduction's results.json, compute every verdict, and summarize it.

Usage:
  check_results.py results.json             check; exit 1 on any error or stale verdict
  check_results.py results.json --write     fill in the computed verdicts and summary
  check_results.py results.json --markdown  also print the summary table (README, PR body)
  check_results.py results.json --root DIR  folder the items' output paths are relative to
                                            (default: the folder holding results.json)
  check_results.py results.json --skip-files  do not check that output files exist
  check_results.py results.json --base OLD.json  reviews already in OLD.json (the file on main) may lack
                                            a reason: they warn instead of failing

Order of a verdict: the numbers (printed tolerance, then the noise band), then the paper's claims
(an item whose claims all hold and whose cause is explained agrees), then a reviewer's "review"
block, which must say why ("reason").

Verdicts are computed here from the numbers in the file, never typed by hand. The rules are
in references/results-json.md. Standard library only.
"""

import argparse
import json
import math
import os
import re
import sys

SCHEMA = "paper2repro/results/v1"
VERDICTS = ["exact", "agrees", "partly", "inconclusive", "differs", "not_attempted"]
KINDS = {"figure", "table", "value", "code_check"}
METHODS = {"pixels", "values", "check", "none"}
SOURCES = {"authors_code", "port", "papers_data", "supplement_values", "reconstructed", "public_data", "none"}
CONTROL_KINDS = {"wrong_input", "near_miss"}
ASSUMPTION_SOURCES = {"paper", "authors_code", "our_choice", "read_from_figure", "found_by_search"}
FITTED = {"read_from_figure", "found_by_search"}
CAUSES = {
    "rendering_only", "paper_error", "undocumented_setting", "code_differs_from_paper", "code_does_not_run",
    "data_differs", "data_unavailable", "proprietary_software", "nondeterminism", "environment",
    "not_a_result", "metric_resolution", "unknown",
}
NEEDS_CAUSE = {"partly", "inconclusive", "differs", "not_attempted"}
PICTURES = (".png", ".jpg", ".jpeg", ".gif", ".webp")
FRAME_PX = 2  # how far the panel of ours may be from the published size and still be on its frame
INK_OUTSIDE = 0.01  # share of our ink that may fall outside the published picture
AXIS_SHARE = 0.005  # how far an axis limit of ours may be from the published one, as a share of the axis
SEMVER = r"\d+\.\d+\.\d+"
REVIEW_VERDICTS = {"agrees", "partly", "differs"}
REASON_KINDS = {"noise", "paper_error", "follows", "data_release", "judgment"}
CLAIM_RESULTS = {"holds", "partly", "fails"}
CLAIM_RAISES = {"partly", "inconclusive", "differs"}  # computed verdicts a claim that holds can raise to agrees
MAX_SAMPLES = 3  # largest gap in samples the noise band allows, and only when the paper gives no seeds, folds or settings
# A reason that says nothing: what the review page wrote when the reviewer only clicked.
EMPTY_REASON = re.compile(r"without comment|per review comment|^.{0,60}?\b(exact|agrees|partly|inconclusive|differs|not.attempted)\W*(→|->|to)\W*(agrees|partly|differs)\W*$", re.I)


def number(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def printed_tolerance(expected):
    """Half a unit in the last printed digit of the expected value: '277.37' gives 0.005."""
    s = str(expected).replace(",", "").strip()
    if "e" in s.lower():
        mant, exp = s.lower().split("e")
        dec = len(mant.split(".")[1]) if "." in mant else 0
        return 0.5 * 10 ** (int(exp) - dec)
    dec = len(s.split(".")[1]) if "." in s else 0
    return 0.5 * 10 ** (-dec)


def noise_band(f, iid, errors):
    """How far a field may stray from the printed value through the method's own noise, or None.

    noise: {"runs": [our values over seeds or reruns]} (their range), {"spread": x}, {"mc_se": se} (2 SE),
    {"samples": k, "n": N, "scale": 100, "why": "..."} (k of N samples, at most 3, only when the paper
    gives no seeds, folds or settings). The band is the largest of those given; it adds to the field's
    tolerance (the printed rounding), since the paper's own value carries both.
    """
    nz = f.get("noise")
    if nz is None:
        return None
    name = f.get("name")
    if not isinstance(nz, dict) or not ({"runs", "spread", "mc_se", "samples"} & set(nz)):
        errors.append(f"{iid}: field {name} noise needs runs, spread, mc_se or samples")
        return None
    band = []
    if "runs" in nz:
        runs = [number(v) for v in nz["runs"] or []]
        if len(runs) < 2 or any(r is None for r in runs):
            errors.append(f"{iid}: field {name} noise.runs needs at least two numbers (our runs with other seeds)")
        else:
            band.append(max(runs) - min(runs))
    for key, factor in (("spread", 1), ("mc_se", 2)):
        if key in nz:
            v = number(nz[key])
            if v is None or v < 0:
                errors.append(f"{iid}: field {name} noise.{key} must be a number >= 0")
            else:
                band.append(factor * v)
    if "samples" in nz:
        k, n, scale = number(nz.get("samples")), number(nz.get("n")), number(nz.get("scale", 1))
        if k is None or n is None or scale is None or n <= 0 or k < 0:
            errors.append(f"{iid}: field {name} noise.samples needs samples, n (and scale, 100 for percent)")
        elif k > MAX_SAMPLES:
            errors.append(f"{iid}: field {name} noise.samples is {k:g}; the band allows at most {MAX_SAMPLES} samples")
        elif not str(nz.get("why", "")).strip():
            errors.append(f"{iid}: field {name} noise.samples needs why: what the paper does not give (seeds, folds, settings)")
        else:
            band.append(k / n * scale)
    return max(band) if band else None


def field_status(f, tol, iid, errors):
    """'printed' when the field is within its tolerance, 'noise' when only within its noise band, else 'miss'."""
    exp, obs = f.get("expected"), f.get("observed")
    tol = f.get("tolerance", tol) or {}
    a, b = number(exp), number(obs)
    band = noise_band(f, iid, errors)
    if a is None or b is None:
        return "printed" if exp == obs else "miss"
    if math.isnan(a) or math.isnan(b):
        return "miss"
    allowed = 1e-12
    if tol.get("printed"):
        allowed += printed_tolerance(exp)
    allowed += tol.get("abs", 0) + tol.get("rel", 0) * abs(a)
    if abs(a - b) <= allowed:
        return "printed"
    if band is not None and abs(a - b) <= allowed + band:  # the method's noise on top of the printed rounding
        return "noise"
    return "miss"


def field_matches(f, tol):
    return field_status(f, tol, "?", []) == "printed"


def verdict_of(item, errors):
    """The verdict the item's numbers support, and a short description of the measure."""
    iid = item.get("id", "?")
    method = item.get("method")
    if method == "none":
        return "not_attempted", "not attempted"

    if method == "check":
        c = item.get("check") or {}
        if "passed" not in c:
            errors.append(f"{iid}: check items need check.passed")
            return None, ""
        return ("agrees" if c["passed"] else "differs"), c.get("detail", "")

    if method == "values":
        v = item.get("values") or {}
        fields = v.get("fields") or []
        if not fields:
            errors.append(f"{iid}: values items need values.fields")
            return None, ""
        excepted = {e.get("field") for e in v.get("exceptions", []) if e.get("category") == "paper_error"}
        for e in v.get("exceptions", []):
            if e.get("category") not in CAUSES or not e.get("evidence"):
                errors.append(f"{iid}: exception {e.get('field')} needs a category and evidence")
        counted = [f for f in fields if f.get("name") not in excepted]
        status = [field_status(f, v.get("tolerance"), iid, errors) for f in counted]
        hits, noisy = status.count("printed"), status.count("noise")
        bad_exc = [f.get("name") for f in fields if f.get("name") in excepted and field_matches(f, v.get("tolerance"))]
        if bad_exc:
            errors.append(f"{iid}: fields listed as paper errors already match: {bad_exc}")
        measure = (f"{hits} of {len(counted)} fields as printed" + (f", {noisy} more within noise" if noisy else "")
                   + (f", {len(excepted)} paper errors" if excepted else ""))
        if counted and hits == len(counted):
            fitted = any(a.get("source") in FITTED for a in item.get("assumptions", []))
            return ("agrees" if fitted else "exact"), measure
        if counted and hits + noisy == len(counted):
            item["_basis"] = f"within noise: {noisy} of {len(counted)} fields off the printed digits, inside our runs' spread"
            return "agrees", measure
        return ("partly" if hits + noisy else "differs"), measure

    if method == "pixels":
        p = item.get("pixels") or {}
        try:
            s = min(float(p["published_near_ours"]), float(p["ours_near_published"]))
            thr = float(p["threshold"])
        except (KeyError, TypeError, ValueError):
            errors.append(f"{iid}: pixel items need published_near_ours, ours_near_published and threshold")
            return None, ""
        controls = p.get("controls") or []
        for c in controls:
            if c.get("kind") not in CONTROL_KINDS or number(c.get("score")) is None or not c.get("name"):
                errors.append(f"{iid}: control {c.get('name')!r} needs a name, a kind ({'/'.join(sorted(CONTROL_KINDS))}) and a score")
        wrong = [float(c["score"]) for c in controls if c.get("kind") == "wrong_input" and number(c.get("score")) is not None]
        near = [float(c["score"]) for c in controls if c.get("kind") == "near_miss" and number(c.get("score")) is not None]
        if not wrong:
            errors.append(f"{iid}: pixel items need at least one wrong_input control")
        best = max(wrong + near, default=0.0)
        if thr <= best:
            errors.append(f"{iid}: threshold {thr} does not reject the control that scored {best}")
        tol = p.get("tolerance_px")
        measure = f"{100 * s:.2f}% within {tol} px (pass {100 * thr:.1f}%, best control {100 * best:.1f}%)"
        if wrong and s <= max(wrong):
            return "differs", measure
        if near and s <= max(near):
            return "inconclusive", measure
        return ("agrees" if s >= thr else "partly"), measure

    errors.append(f"{iid}: method must be one of {sorted(METHODS)}")
    return None, ""


def axis_gap(ax):
    """How far the limits of ours are from the published ones, as a share of the published axis; None if not numbers."""
    pub, ours = ax.get("published"), ax.get("ours")
    nums = [number(v) for v in (pub if isinstance(pub, list) else []) + (ours if isinstance(ours, list) else [])]
    if len(nums) != 4 or any(n is None or math.isnan(n) for n in nums):
        return None
    if ax.get("scale") == "log":
        if min(nums) <= 0:
            return math.inf
        nums = [math.log10(n) for n in nums]
    span = abs(nums[1] - nums[0])
    return math.inf if not span else max(abs(nums[2] - nums[0]), abs(nums[3] - nums[1])) / span


def check_layout(item, errors):
    """A figure of ours that is shown next to the published one is on its frame: same panel, same axes.

    Three records pass: drawn_on_published (our series on a copy of the published picture), a new
    drawing measured by compare_figure.py with its axis limits equal to the published ones, or
    not_comparable with the reason, for a drawing that has no axes to share.
    """
    iid, lay = item.get("id", "?"), item.get("layout")
    if item.get("kind") != "figure" or item.get("method") == "none":
        return
    if not any(str(o).lower().endswith(PICTURES) for o in item.get("outputs") or []):
        return
    how = "see references/figure-matching.md, The published frame"
    if not isinstance(lay, dict):
        errors.append(f"{iid}: a figure with a picture of ours needs layout, which says that it is on the published frame ({how})")
        return
    if "not_comparable" in lay:
        if not str(lay["not_comparable"] or "").strip():
            errors.append(f"{iid}: layout.not_comparable needs the reason")
        return
    if lay.get("drawn_on_published") is True:
        return
    size = lay.get("panel_size_difference_px")
    if not (isinstance(size, list) and len(size) == 2 and all(number(v) is not None for v in size)):
        errors.append(f"{iid}: layout needs panel_size_difference_px [dx, dy] from compare_figure.py's report ({how})")
    else:
        allowed = max(FRAME_PX, number((item.get("pixels") or {}).get("tolerance_px")) or 0)
        if max(abs(number(v)) for v in size) > allowed:
            errors.append(f"{iid}: ours is not on the published frame: its panel is {size[0]} x {size[1]} px off the published size "
                          f"(allowed {allowed:g}). Draw it at the published size with its axes at the published box ({how})")
    lost = number(lay.get("ink_outside_frame"))
    if lost is None:
        errors.append(f"{iid}: layout needs ink_outside_frame from compare_figure.py's report")
    elif lost > INK_OUTSIDE:
        errors.append(f"{iid}: {100 * lost:.1f}% of our ink falls outside the published picture: ours is larger than the published figure, or shifted")
    axes = lay.get("axes")
    if not isinstance(axes, list) or not axes:
        errors.append(f"{iid}: layout needs axes, the limits of each axis as published and as ours draws it")
        return
    for ax in axes:
        name = ax.get("axis") if isinstance(ax, dict) else None
        if not name or "published" not in ax or "ours" not in ax:
            errors.append(f"{iid}: each of layout.axes needs axis, published and ours")
            continue
        gap = axis_gap(ax)
        if gap is None:
            # an axis of names (bars, groups, rows of a heat map): the same names in the same order
            if [str(v) for v in ax["published"] or []] != [str(v) for v in ax["ours"] or []] or not ax["published"]:
                errors.append(f"{iid}: the {name} axis of ours is {ax['ours']}, the published one {ax['published']}: draw ours with the published axis")
        elif gap > AXIS_SHARE:
            errors.append(f"{iid}: the {name} axis of ours runs {ax['ours'][0]} to {ax['ours'][1]}, the published one {ax['published'][0]} to {ax['published'][1]}: "
                          "draw ours with the published limits, and count the points that fall outside")


def check_cause(item, verdict, errors):
    iid, cause = item.get("id", "?"), item.get("cause")
    if verdict not in NEEDS_CAUSE and not cause:
        return
    if not cause:
        errors.append(f"{iid}: verdict {verdict} needs a cause")
        return
    if cause.get("category") not in CAUSES:
        errors.append(f"{iid}: cause.category must be one of {sorted(CAUSES)}")
    if not str(cause.get("summary", "")).strip():
        errors.append(f"{iid}: cause.summary is empty")
    status = cause.get("status")
    hyps = cause.get("hypotheses") or []
    for h in hyps:
        if not h.get("hypothesis") or not h.get("test") or h.get("result") not in ("supported", "rejected", "inconclusive"):
            errors.append(f"{iid}: each hypothesis needs hypothesis, test and result (supported/rejected/inconclusive)")
    if status == "explained":
        if not cause.get("evidence") and not any(h.get("result") == "supported" for h in hyps):
            errors.append(f"{iid}: an explained cause needs evidence or a supported hypothesis")
        if cause.get("category") == "unknown":
            errors.append(f"{iid}: an explained cause cannot have category unknown")
    elif status == "open":
        if len([h for h in hyps if h.get("result") in ("rejected", "inconclusive")]) < 2:
            errors.append(f"{iid}: an open cause needs at least two tested hypotheses (what was ruled out)")
    else:
        errors.append(f"{iid}: cause.status must be explained or open")


def check_claims(data, ids, errors):
    """The paper's claims, each resting on items. Returns {item id: [claims]}."""
    claims = data.get("claims")
    if claims is None:
        return {}
    if not isinstance(claims, list):
        errors.append("claims must be a list")
        return {}
    by_item, seen = {}, set()
    for c in claims:
        cid = c.get("id")
        if not cid or cid in seen:
            errors.append(f"claim {cid!r}: needs a unique id")
        seen.add(cid)
        for key in ("text", "where", "test"):
            if not str(c.get(key, "")).strip():
                errors.append(f"claim {cid}: {key} is empty")
        if c.get("result") not in CLAIM_RESULTS:
            errors.append(f"claim {cid}: result must be one of {sorted(CLAIM_RESULTS)}")
        rests = c.get("items")
        if not isinstance(rests, list) or not rests:
            errors.append(f"claim {cid}: items must list the ids it rests on")
            continue
        for iid in rests:
            if iid not in ids:
                errors.append(f"claim {cid}: rests on {iid!r}, which is not an item")
            by_item.setdefault(iid, []).append(c)
    return by_item


def apply_claims(item, computed, measure, claims, for_review):
    """An item whose numbers miss but whose claims all hold agrees, when its cause is explained.

    With an open cause the gap is not understood yet (a wrong setting of ours looks the same), so a
    person decides: the item keeps its computed verdict and is listed for review.
    """
    if computed not in CLAIM_RAISES or not claims or any(c.get("result") != "holds" for c in claims):
        return computed, measure
    names = ", ".join(c["id"] for c in claims)
    if (item.get("cause") or {}).get("status") == "explained":
        item["_basis"] = f"claim holds ({names}); the numbers alone give {computed.replace('_', ' ')}"
        return "agrees", f"{measure}; claims hold: {names}"
    for_review.append(f"{item.get('id')}: claims hold ({names}) but the cause of the gap is open; a person decides")
    return computed, measure


def apply_review(item, computed, measure, errors, warnings, old_reviews, ids):
    """The reviewer's verdict when the item has a review, else the computed one."""
    r = item.get("review")
    if r is None:
        return computed, measure
    iid = item.get("id", "?")
    if r.get("verdict") not in REVIEW_VERDICTS:
        errors.append(f"{iid}: review.verdict must be one of {sorted(REVIEW_VERDICTS)}")
        return computed, measure
    if not r.get("by") or not r.get("url"):
        errors.append(f"{iid}: a review needs by and url")
    reason, problem = r.get("reason"), None
    if not isinstance(reason, dict):
        problem = "a review needs reason {kind, text}: why the reviewer set this verdict"
    elif reason.get("kind") not in REASON_KINDS:
        problem = f"review.reason.kind must be one of {sorted(REASON_KINDS)}"
    elif not str(reason.get("text", "")).strip() or EMPTY_REASON.search(str(reason.get("text"))):
        problem = f"review.reason.text {reason.get('text')!r} gives no reason"
    elif reason["kind"] == "follows" and reason.get("item") not in ids:
        problem = "a reason of kind follows names the item it follows (reason.item)"
    if problem:
        old = old_reviews.get(iid)
        unchanged = old is not None and {k: old.get(k) for k in ("verdict", "computed", "by", "url")} == {k: r.get(k) for k in ("verdict", "computed", "by", "url")}
        (warnings if unchanged else errors).append(f"{iid}: {problem}")
    if r.get("computed") != computed:
        errors.append(f"{iid}: reviewed when the numbers gave {r.get('computed')!r}, now they give {computed!r}: review it again")
        return computed, measure
    return r["verdict"], f"{measure}; computed {computed.replace('_', ' ')}, reviewer {r['verdict']}"


def check_item(item, root, errors):
    iid = item.get("id")
    if not iid:
        errors.append("an item has no id")
    for key, allowed in (("kind", KINDS), ("method", METHODS), ("source", SOURCES)):
        if item.get(key) not in allowed:
            errors.append(f"{iid}: {key} must be one of {sorted(allowed)}")
    if not item.get("label"):
        errors.append(f"{iid}: label is empty")
    for a in item.get("assumptions", []):
        if a.get("source") not in ASSUMPTION_SOURCES or not a.get("what"):
            errors.append(f"{iid}: each assumption needs what and a source ({'/'.join(sorted(ASSUMPTION_SOURCES))})")
        if a.get("source") in FITTED and not a.get("sensitivity"):
            errors.append(f"{iid}: assumption {a.get('what')!r} was {a.get('source')}; say how sensitive the result is to it")
    if item.get("kind") == "figure" and item.get("method") == "pixels":
        outs = item.get("outputs") or []
        if len(outs) < 2:
            errors.append(f"{iid}: a scored figure needs its render and overlay listed in outputs")
        if root:
            for o in outs:
                if not os.path.exists(os.path.join(root, o)):
                    errors.append(f"{iid}: output {o} does not exist under {root}")
    check_layout(item, errors)
    verdict, measure = verdict_of(item, errors)
    if verdict:
        check_cause(item, verdict, errors)
    return verdict, measure


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--markdown", action="store_true")
    ap.add_argument("--root")
    ap.add_argument("--skip-files", action="store_true")
    ap.add_argument("--base", help="the same results.json as it stands on main: its unchanged reviews may lack a reason")
    args = ap.parse_args()

    with open(args.results, encoding="utf-8") as f:
        data = json.load(f)
    root = None if args.skip_files else args.root or os.path.dirname(os.path.abspath(args.results))
    errors, stale, rows, warnings, for_review = [], [], [], [], []
    old_reviews = {}
    if args.base and os.path.exists(args.base):
        with open(args.base, encoding="utf-8") as f:
            old_reviews = {i.get("id"): i["review"] for i in json.load(f).get("items") or [] if isinstance(i.get("review"), dict)}

    if data.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")
    for key in ("id", "title", "citation", "doi", "license"):
        if not (data.get("paper") or {}).get(key):
            errors.append(f"paper.{key} is missing")
    run = data.get("run") or {}
    for key in ("date", "pipeline", "command", "inputs"):
        if not run.get(key):
            errors.append(f"run.{key} is missing")
    for i in run.get("inputs", []):
        if not i.get("sha256") or not i.get("name"):
            errors.append(f"run.inputs: {i.get('name')!r} needs a name and a sha256")

    skill = data.get("skill") or {}
    if skill.get("name") != "paper2repro" or not re.fullmatch(SEMVER, str(skill.get("version", ""))):
        errors.append("skill is missing or has no version: run the installed skill's scripts/skill_version.py on this file")
    elif skill.get("tag") != f"paper2repro-v{skill['version']}":
        errors.append(f"skill.tag must be paper2repro-v{skill['version']}")

    items = data.get("items") or []
    if not items:
        errors.append("items is empty")
    ids = [i.get("id") for i in items]
    for d in sorted({x for x in ids if ids.count(x) > 1}):
        errors.append(f"duplicate item id {d}")

    claims_of = check_claims(data, set(ids), errors)
    counts = dict.fromkeys(VERDICTS, 0)
    open_causes = reviewed = 0
    for item in items:
        verdict, measure = check_item(item, root, errors)
        if not verdict:
            continue
        verdict, measure = apply_claims(item, verdict, measure, claims_of.get(item.get("id"), []), for_review)
        verdict, measure = apply_review(item, verdict, measure, errors, warnings, old_reviews, set(ids))
        counts[verdict] += 1
        if (item.get("cause") or {}).get("status") == "open":
            open_causes += 1
        if item.get("review") and item["review"].get("verdict") == verdict:
            reviewed += 1
        if item.get("verdict") != verdict:
            stale.append(f"{item.get('id')}: stored {item.get('verdict')!r}, computed {verdict!r}")
            item["verdict"] = verdict
        # basis: why the verdict is what it is, when the printed digits alone do not say (noise band, claims)
        basis = item.pop("_basis", None)
        if item.get("review") and item["review"].get("verdict") == verdict:
            basis = None  # the reviewer's reason is the basis
        if item.get("basis") != basis:
            stale.append(f"{item.get('id')}: basis is out of date")
            if basis:
                item["basis"] = basis
            else:
                item.pop("basis", None)
        why = (item.get("cause") or {}).get("summary", "")
        fitted = [a["what"] for a in item.get("assumptions", []) if a.get("source") in FITTED]
        if fitted and not why:
            why = "Assumed: " + "; ".join(fitted)
        rows.append((item.get("label", item.get("id")), verdict, measure, why))
    for item in items:
        item.pop("_basis", None)

    summary = {"items": len(items), **counts, "open_causes": open_causes}
    if reviewed:
        summary["reviewed"] = reviewed
    if for_review:
        summary["for_review"] = len(for_review)
    if data.get("claims"):
        summary["claims"] = {r: sum(c.get("result") == r for c in data["claims"]) for r in sorted(CLAIM_RESULTS)}
    if data.get("summary") != summary:
        stale.append("summary is out of date")
        data["summary"] = summary

    if args.write and not errors:
        with open(args.results, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")
        stale = []

    if args.markdown:
        print("| Item | Verdict | Measure | Why |")
        print("| --- | --- | --- | --- |")
        for label, v, m, why in rows:
            print(f"| {label} | {v.replace('_', ' ')} | {m} | {why} |")
        print()
        print(", ".join(f"{summary[v]} {v.replace('_', ' ')}" for v in VERDICTS if summary[v]) + f"; {open_causes} open causes"
              + (f"; {reviewed} verdicts set by a reviewer" if reviewed else "") + ".")
        if for_review:
            print()
            print("For a person:")
            for line in for_review:
                print(f"- {line}")

    for e in errors:
        print(f"ERROR {e}", file=sys.stderr)
    for w in warnings:
        print(f"WARN {w} (already on main; give it a reason)", file=sys.stderr)
    for r in for_review:
        print(f"REVIEW {r}", file=sys.stderr)
    for s in stale:
        print(f"STALE {s} (run with --write)", file=sys.stderr)
    if errors or stale:
        sys.exit(1)
    print(f"OK {args.results}: " + json.dumps(summary), file=sys.stderr)


if __name__ == "__main__":
    main()
