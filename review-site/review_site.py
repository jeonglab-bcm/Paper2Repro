#!/usr/bin/env python3
"""Build a static review site for reproduction pull requests and branches.

For every open pull request of a repository (and every recent branch without one) that
holds a Paper2Repro ``results.json``, write one page that is organised by the paper, not
by files: the decisions a reviewer has to make, each figure next to the published one,
each table and number next to the printed one, and the code of the method only. An index
page lists the reviews.

    review_site.py --repo jeonglab-bcm/fossil --clone work/fossil --out _site

Nothing from the reviewed repository is run. Its text is escaped and only raster pictures
are copied, because a pull request can come from anyone.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import html
import json
import math
import os
import re
import shutil
import struct
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

try:  # optional: colours for code
    from pygments import highlight
    from pygments.formatters import HtmlFormatter
    from pygments.lexers import get_lexer_for_filename
    from pygments.util import ClassNotFound
except ImportError:  # pragma: no cover
    highlight = None

HERE = Path(__file__).resolve().parent
VERDICTS = ["exact", "agrees", "partly", "inconclusive", "differs", "not_attempted"]
VERDICT_LABEL = {
    "exact": "Exact", "agrees": "Agrees", "partly": "Partly", "inconclusive": "Inconclusive",
    "differs": "Differs", "not_attempted": "Not attempted",
}
SEVERITY = {"differs": 4, "inconclusive": 3, "partly": 2, "not_attempted": 1, "agrees": 0, "exact": 0}
CATEGORY_LABEL = {
    "rendering_only": "Rendering only", "paper_error": "Paper error",
    "undocumented_setting": "Setting not stated", "code_differs_from_paper": "Code differs from paper",
    "code_does_not_run": "Code needed a fix", "data_differs": "Data differ",
    "data_unavailable": "Data not available", "proprietary_software": "Software not available",
    "nondeterminism": "Randomness", "environment": "Environment", "not_a_result": "Not a result",
    "metric_resolution": "Metric cannot tell", "unknown": "Cause unknown",
}
SOURCE_LABEL = {"our_choice": "Our choice", "found_by_search": "Found by search", "read_from_figure": "Read from figure"}
RASTER = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
CODE_EXTS = {
    ".py", ".r", ".nf", ".sh", ".jl", ".m", ".c", ".cc", ".cpp", ".h", ".hpp", ".rs", ".pl", ".js",
    ".ts", ".java", ".f90", ".go", ".smk", ".rmd", ".qmd",
}
GENERATED_PARTS = ("/output/", "/session/", "/published/", "/tutorial/", "/data/")
PLUMBING_RE = re.compile(
    r"^(check_|build_|compare_runs|readme_|pack_|fetch_|run_|make_|page_template|figures?\.|conftest|setup\.)", re.I
)
GROUPS = [  # category, title, whether its code is shown on the page
    ("method", "Method", True),
    ("analysis", "Analysis", True),
    ("shared", "Outside the paper folder", True),
    ("tests", "Tests", False),
    ("plumbing", "Checks and plumbing", False),
    ("docs", "Documents", False),
    ("generated", "Outputs and records", False),
]
MAX_EMBED_LINES = 1500
e = html.escape


# ---------------------------------------------------------------------------- git


class GitError(RuntimeError):
    pass


class Repo:
    def __init__(self, path):
        self.path = str(path)

    def git(self, *args, text=True, check=True):
        r = subprocess.run(["git", "-C", self.path, *args], capture_output=True)
        if check and r.returncode:
            raise GitError(f"git {' '.join(args)}: {r.stderr.decode('utf-8', 'replace').strip()}")
        return r.stdout.decode("utf-8", "replace") if text else r.stdout

    def ok(self, *args):
        return subprocess.run(["git", "-C", self.path, *args], capture_output=True).returncode == 0

    def sha(self, ref):
        return self.git("rev-parse", "--verify", f"{ref}^{{commit}}").strip()

    def exists(self, ref, path):
        return self.ok("cat-file", "-e", f"{ref}:{path}")

    def show(self, ref, path, text=True):
        r = subprocess.run(["git", "-C", self.path, "show", f"{ref}:{path}"], capture_output=True)
        if r.returncode:
            return None
        return r.stdout.decode("utf-8", "replace") if text else r.stdout

    def ls(self, ref, prefix):
        out = self.git("ls-tree", "-r", "--name-only", "-z", ref, "--", prefix, check=False)
        return [p for p in out.split("\0") if p]


def changed_files(repo, base, head):
    ns = repo.git("diff", "--numstat", "--no-renames", "-z", base, head)
    st = repo.git("diff", "--name-status", "--no-renames", "-z", base, head).split("\0")
    status = {st[i + 1]: st[i] for i in range(0, len(st) - 1, 2)}
    files = []
    for rec in ns.split("\0"):
        if not rec:
            continue
        a, d, p = rec.split("\t", 2)
        binary = a == "-"
        files.append({
            "path": p, "added": 0 if binary else int(a), "deleted": 0 if binary else int(d),
            "binary": binary, "status": status.get(p, "M"),
        })
    return files


def conflicts(repo, a, b):
    """Files that conflict when a and b are merged; None when git cannot tell."""
    r = subprocess.run(
        ["git", "-C", repo.path, "merge-tree", "--write-tree", "--name-only", "--no-messages", a, b],
        capture_output=True,
    )
    if r.returncode == 0:
        return []
    if r.returncode != 1:
        return None
    return [ln for ln in r.stdout.decode("utf-8", "replace").splitlines()[1:] if ln.strip()]


# ---------------------------------------------------------------------- the paper


def number(v):
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


def printed_decimals(expected):
    s = str(expected).replace(",", "").strip()
    if "e" in s.lower():
        return None
    return len(s.split(".")[1]) if "." in s else 0


def printed_tolerance(expected):
    """Half a unit in the last printed digit, as Paper2Repro's check_results.py."""
    s = str(expected).replace(",", "").strip()
    if "e" in s.lower():
        mant, exp = s.lower().split("e")
        dec = len(mant.split(".")[1]) if "." in mant else 0
        return 0.5 * 10 ** (int(exp) - dec)
    dec = len(s.split(".")[1]) if "." in s else 0
    return 0.5 * 10 ** (-dec)


def field_matches(f, tol):
    exp, obs = f.get("expected"), f.get("observed")
    tol = f.get("tolerance", tol) or {}
    a, b = number(exp), number(obs)
    if a is None or b is None:
        return exp == obs
    if math.isnan(a) or math.isnan(b):
        return False
    allowed = 1e-12
    if tol.get("printed"):
        allowed += printed_tolerance(exp)
    allowed += tol.get("abs", 0) + tol.get("rel", 0) * abs(a)
    return abs(a - b) <= allowed


def fmt_exp(v):
    if isinstance(v, str):
        return v
    if isinstance(v, bool) or v is None:
        return str(v)
    if isinstance(v, int):
        return str(v)
    return f"{v:.6g}"


def fmt_obs(obs, exp):
    b = number(obs)
    if b is None:
        return str(obs)
    if isinstance(exp, str) and number(exp) is not None:
        dec = printed_decimals(exp)
        if dec is not None:
            return f"{b:.{dec}f}"
    if isinstance(obs, int) and not isinstance(obs, bool):
        return str(obs)
    return f"{b:.4g}"


def fields_of(item):
    """The item's fields, each with whether it matches and whether the paper is in error."""
    v = item.get("values") or {}
    tol = v.get("tolerance") or {}
    errors = {x.get("field"): x for x in v.get("exceptions") or [] if x.get("category") == "paper_error"}
    out = []
    for f in v.get("fields") or []:
        name = str(f.get("name", ""))
        a, b = number(f.get("expected")), number(f.get("observed"))
        gap = None
        if a is not None and b is not None and not (math.isnan(a) or math.isnan(b)):
            gap = abs(a - b) / (abs(a) if a else 1.0)
        out.append({
            "name": name, "exp": fmt_exp(f.get("expected")), "obs": fmt_obs(f.get("observed"), f.get("expected")),
            "a": a, "b": b, "match": field_matches(f, tol), "error": errors.get(name), "gap": gap,
        })
    return out


def measure_of(item):
    m = item.get("method")
    if m == "values":
        fs = fields_of(item)
        counted = [f for f in fs if not f["error"]]
        errs = len(fs) - len(counted)
        hits = sum(f["match"] for f in counted)
        return f"{hits} of {len(counted)} as printed" + (f", {errs} paper error{'s' if errs != 1 else ''}" if errs else "")
    if m == "pixels":
        p = pixel_score(item)
        return f"{p['s'] * 100:.0f}% within {p['tol']:g} px, pass {p['t'] * 100:.0f}%" if p else ""
    if m == "check":
        return "check passed" if (item.get("check") or {}).get("passed") else "check failed"
    return ""


def pixel_score(item):
    p = item.get("pixels")
    if not p:
        return None
    shares = [x for x in (number(p.get("published_near_ours")), number(p.get("ours_near_published"))) if x is not None]
    if not shares:
        return None
    controls = [(number(c.get("score")) or 0.0, c.get("name", ""), c.get("kind", "")) for c in p.get("controls") or []]
    best = max(controls) if controls else None
    return {"s": min(shares), "t": number(p.get("threshold")) or 0.0, "tol": number(p.get("tolerance_px")) or 0.0, "control": best}


FIG_RE = re.compile(r"^fig(?:ure)?[-_. ]?(s?\d+)", re.I)
TAB_RE = re.compile(r"^tab(?:le)?[-_. ]?(s?\d+)", re.I)


def fig_key(item_id):
    m = FIG_RE.match(item_id)
    return m.group(1).lower() if m else None


def token(item):
    """A short name for where an item is in the paper: 'Fig. 3', 'Table 1', 'Text'."""
    i = str(item.get("id", ""))
    m = FIG_RE.match(i)
    if m:
        return f"Fig. {m.group(1).upper()}"
    m = TAB_RE.match(i)
    if m:
        return f"Table {m.group(1).upper()}"
    head = i.split(".")[0].lower()
    known = {"text": "Text", "data": "Data", "code": "Code", "package": "Package", "port": "Port"}
    return known.get(head) or str(item.get("label", i)).split(",")[0]


def tokens(items, limit=5):
    seen = []
    for it in items:
        t = token(it)
        if t not in seen:
            seen.append(t)
    return seen if len(seen) <= limit else seen[: limit - 1] + [f"+{len(seen) - limit + 1}"]


def first_sentence(text):
    text = " ".join(str(text or "").split())
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z(])", text, maxsplit=1)
    return parts[0], (parts[1] if len(parts) > 1 else "")


def card_key(*parts):
    h = hashlib.sha1("\x1f".join(str(p) for p in parts).encode()).hexdigest()
    return h[:12]


def cause_cards(paper_id, items):
    """One card per open cause; items that share their tested hypotheses share a card."""
    groups = {}
    for it in items:
        c = it.get("cause")
        if not c or it.get("verdict") == "not_attempted":
            continue
        if SEVERITY.get(it.get("verdict"), 0) < 2 and c.get("status") != "open":
            continue
        hyps = c.get("hypotheses") or []
        key = ("h", *sorted(str(h.get("hypothesis", "")) for h in hyps)) if hyps else ("s", str(c.get("summary", "")))
        groups.setdefault(key, []).append(it)
    open_cards, explained = [], []
    for members in groups.values():
        lead = next((m for m in members if m.get("kind") in ("table", "value") and fields_of(m)), members[0])
        cause = lead["cause"]
        is_open = any((m.get("cause") or {}).get("status") == "open" for m in members)
        worst = max((m.get("verdict") for m in members), key=lambda v: SEVERITY.get(v, 0))
        nums, seen = [], set()
        for m in members:
            for f in fields_of(m):
                if f["match"] or f["error"] or f["name"] in seen or f["gap"] is None:
                    continue
                seen.add(f["name"])
                nums.append(f)
        nums.sort(key=lambda f: -f["gap"])
        summaries = []
        for m in members:
            s = " ".join(str((m.get("cause") or {}).get("summary", "")).split())
            if s and s not in [x[1] for x in summaries]:
                summaries.append((m.get("label", m["id"]), s))
        card = {
            "kind": "cause", "title": " · ".join(tokens(members)), "status": "open" if is_open else "explained",
            "verdict": worst, "category": cause.get("category", ""), "summary": summaries[0][1] if summaries else "",
            "more": summaries[1:], "nums": nums[:6], "hyps": cause.get("hypotheses") or [],
            "members": members, "evidence": cause.get("evidence") or [],
        }
        card["key"] = card_key(paper_id, "cause", card["title"], card["summary"], card["status"])
        (open_cards if is_open else explained).append(card)
    open_cards.sort(key=lambda c: (-SEVERITY.get(c["verdict"], 0), -len(c["members"])))
    return open_cards, explained


def decision_cards(paper_id, items, shared_files, conflict_notes):
    open_cards, explained = cause_cards(paper_id, items)
    cards = list(open_cards)

    choices, seen = [], {}
    for it in items:
        for a in it.get("assumptions") or []:
            if a.get("source") not in SOURCE_LABEL:
                continue
            what = " ".join(str(a.get("what", "")).split())
            if what in seen:
                if token(it) not in seen[what]["where"]:
                    seen[what]["where"].append(token(it))
                continue
            seen[what] = {"what": what, "source": a.get("source"), "sensitivity": a.get("sensitivity", ""), "where": [token(it)]}
            choices.append(seen[what])
    if choices:
        cards.append({
            "kind": "choices", "title": "Choices the paper does not give", "rows": choices,
            "key": card_key(paper_id, "choices", *[c["what"] for c in choices]),
        })

    errors = []
    for it in items:
        for x in (it.get("values") or {}).get("exceptions") or []:
            if x.get("category") == "paper_error":
                errors.append({"where": token(it), "field": x.get("field", ""), "evidence": x.get("evidence", "")})
    if errors:
        cards.append({
            "kind": "errors", "title": "Values the paper prints that do not follow from its own numbers",
            "rows": errors, "key": card_key(paper_id, "errors", *[f"{x['where']}{x['field']}" for x in errors]),
        })

    if explained:
        cards.append({
            "kind": "explained", "title": "Differences with a tested cause", "rows": explained,
            "key": card_key(paper_id, "explained", *[c["key"] for c in explained]),
        })

    if shared_files:
        cards.append({
            "kind": "outside", "title": "Changes outside the paper folder", "rows": shared_files,
            "notes": conflict_notes,
            "key": card_key(paper_id, "outside", *[f"{f['path']}{f['added']}{f['deleted']}" for f in shared_files]),
        })

    skipped = [it for it in items if it.get("verdict") == "not_attempted"]
    if skipped:
        cards.append({
            "kind": "skipped", "title": "Not attempted", "rows": skipped,
            "key": card_key(paper_id, "skipped", *[it["id"] for it in skipped]),
        })
    return cards


# ------------------------------------------------------------------------- files


def classify(path, folders):
    """(category, paper folder) of a changed file."""
    parts = path.split("/")
    if parts[0] == "site":
        if len(parts) > 2 and parts[1] in folders:
            return "generated", parts[1]
        return "shared", None
    if parts[0] not in folders or len(parts) == 1:
        return "shared", None
    rel = "/" + "/".join(parts[1:])
    name = parts[-1]
    ext = os.path.splitext(name)[1].lower()
    if any(p in rel for p in GENERATED_PARTS) or name in ("results.json", "results_notes.json") or ext == ".ipynb":
        return "generated", parts[0]
    if ext == ".md" or name == "LICENSE":
        return "docs", parts[0]
    if "/tests/" in rel or name.startswith("test_"):
        return "tests", parts[0]
    if ext in CODE_EXTS:
        if PLUMBING_RE.match(name) or "/scripts/" in rel:
            return "plumbing", parts[0]
        return ("method" if "/package/" in rel else "analysis"), parts[0]
    return "plumbing", parts[0]


def image_size(data):
    """(width, height) of a PNG, GIF, JPEG or WebP; None when it cannot be read."""
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", data[16:24])
        if data[:6] in (b"GIF87a", b"GIF89a"):
            return struct.unpack("<HH", data[6:10])
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            if data[12:16] == b"VP8X":
                w = int.from_bytes(data[24:27], "little") + 1
                h = int.from_bytes(data[27:30], "little") + 1
                return w, h
            return None
        if data[:2] == b"\xff\xd8":
            i = 2
            while i + 9 < len(data):
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    h, w = struct.unpack(">HH", data[i + 5:i + 9])
                    return w, h
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                    i += 2
                    continue
                i += 2 + struct.unpack(">H", data[i + 2:i + 4])[0]
    except (struct.error, IndexError):
        return None
    return None


class Images:
    """Copies pictures of the reviewed commit next to the page."""

    def __init__(self, repo, head, outdir):
        self.repo, self.head, self.outdir, self.done = repo, head, Path(outdir), {}

    def add(self, path):
        if path in self.done:
            return self.done[path]
        img = None
        if os.path.splitext(path)[1].lower() in RASTER:
            data = self.repo.show(self.head, path, text=False)
            if data:
                name = hashlib.sha1(path.encode()).hexdigest()[:10] + os.path.splitext(path)[1].lower()
                (self.outdir / "img").mkdir(parents=True, exist_ok=True)
                (self.outdir / "img" / name).write_bytes(data)
                size = image_size(data) or (0, 0)
                img = {"src": f"img/{name}", "w": size[0], "h": size[1], "path": path}
        self.done[path] = img
        return img


def figure_stations(folder, items, tree, images):
    """Group the figure items by figure number, each with its published picture and our renders."""
    published = [p for p in tree if "/published/" in p and os.path.splitext(p)[1].lower() in RASTER]

    def find_published(stem_key):
        for key in (stem_key, re.sub(r"[a-z]+$", "", stem_key)):
            for p in published:
                stem = os.path.splitext(os.path.basename(p))[0].lower()
                m = re.match(r"^fig(?:ure)?[-_. ]?(s?\d+[a-z]*)$", stem)
                if m and m.group(1) == key:
                    return p
        return None

    stations, order = {}, []
    for it in items:
        if it.get("kind") != "figure":
            continue
        key = fig_key(str(it.get("id", ""))) or str(it.get("id"))
        if key not in stations:
            stations[key] = {"key": key, "title": f"Fig. {key.upper()}" if fig_key(str(it.get("id", ""))) else it.get("label", key), "items": [], "renders": []}
            order.append(key)
        st = stations[key]
        st["items"].append(it)
        outs = [str(o) for o in it.get("outputs") or []]
        ours = [o for o in outs if re.search(r"_ours\.[A-Za-z]+$", o)] or [o for o in outs if "overlay" not in o]
        for o in ours:
            if any(r["ours_path"] == o for r in st["renders"]):
                continue
            stem = re.sub(r"_ours$", "", os.path.splitext(os.path.basename(o))[0])
            overlay = next((x for x in outs if os.path.basename(x).startswith(stem + "_overlay")), None)
            m = re.match(r"^fig(?:ure)?[-_. ]?(s?\d+[a-z]*)", stem.lower())
            pub = find_published(m.group(1)) if m else None
            st["renders"].append({
                "ours_path": o, "label": stem, "ours": images.add(f"{folder}/{o}"),
                "overlay": images.add(f"{folder}/{overlay}") if overlay else None,
                "published": images.add(pub) if pub else None,
            })
    for key in order:
        st = stations[key]
        st["renders"] = [r for r in st["renders"] if r["ours"]]
        if not st["renders"]:
            pub = find_published(key)
            st["published_only"] = images.add(pub) if pub else None
    return [stations[k] for k in order]


def load_json(repo, ref, path):
    text = repo.show(ref, path)
    if text is None:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def find_papers(repo, head, files):
    """Paper folders this change touches: (folder, path of its results.json, parsed)."""
    tops = []
    for f in files:
        parts = f["path"].split("/")
        top = parts[1] if parts[0] == "site" and len(parts) > 2 else parts[0]
        if len(parts) > 1 and top not in tops:
            tops.append(top)
    papers = []
    for top in tops:
        for cand in (f"{top}/results.json", f"{top}/figure-reproduction/results.json"):
            data = load_json(repo, head, cand)
            if isinstance(data, dict) and isinstance(data.get("items"), list):
                papers.append((top, cand, data))
                break
    return papers


# --------------------------------------------------------------------- rendering


def stamp(verdict):
    return f'<span class="stamp v-{e(str(verdict))}">{e(VERDICT_LABEL.get(verdict, str(verdict)))}</span>'


def verdict_bar(counts):
    total = sum(counts.get(v, 0) for v in VERDICTS) or 1
    segs = "".join(
        f'<span class="seg v-{v}" style="flex:{counts[v]}" title="{e(VERDICT_LABEL[v])}: {counts[v]}"></span>'
        for v in VERDICTS if counts.get(v)
    )
    legend = "".join(
        f'<span class="lg"><i class="dot v-{v}"></i>{counts[v]} {e(VERDICT_LABEL[v].lower())}</span>'
        for v in VERDICTS if counts.get(v)
    )
    return f'<div class="vbar" role="img" aria-label="{total} items by verdict">{segs}</div><div class="legend">{legend}</div>'


def score_bar(p):
    if not p:
        return ""
    marks = f'<i class="tick pass" style="left:{p["t"] * 100:.1f}%" title="Pass mark {p["t"] * 100:.0f}%"></i>'
    if p["control"]:
        marks += f'<i class="tick ctl" style="left:{p["control"][0] * 100:.1f}%" title="Best control ({e(p["control"][1])}): {p["control"][0] * 100:.0f}%"></i>'
    return (
        f'<span class="score" title="Share of the curve within {p["tol"]:g} px">'
        f'<span class="track"><i class="fill" style="width:{p["s"] * 100:.1f}%"></i>{marks}</span>'
        f'<b>{p["s"] * 100:.0f}%</b></span>'
    )


def series_svg(points):
    xs = [p[0] for p in points]
    ys = [v for p in points for v in (p[1], p[2])]
    lo, hi = min(ys), max(ys)
    pad = (hi - lo) * 0.08 or (abs(hi) * 0.05 or 1.0)
    lo, hi = lo - pad, hi + pad
    x0, x1 = min(xs), max(xs)
    W, H, L, R, T, B = 300, 112, 40, 8, 8, 18

    def px(x):
        return L + (x - x0) / ((x1 - x0) or 1) * (W - L - R)

    def py(y):
        return T + (hi - y) / ((hi - lo) or 1) * (H - T - B)

    def line(idx, cls):
        pts = " ".join(f"{px(p[0]):.1f},{py(p[idx]):.1f}" for p in points)
        dots = "".join(f'<circle cx="{px(p[0]):.1f}" cy="{py(p[idx]):.1f}" r="1.8"/>' for p in points)
        return f'<g class="{cls}"><polyline points="{pts}"/>{dots}</g>'

    return (
        f'<svg viewBox="0 0 {W} {H}" class="series" role="img">'
        f'<line class="ax" x1="{L}" y1="{H - B}" x2="{W - R}" y2="{H - B}"/>'
        f'<text class="tk" x="{L - 4}" y="{py(hi - pad) + 3:.1f}" text-anchor="end">{hi - pad:.3g}</text>'
        f'<text class="tk" x="{L - 4}" y="{py(lo + pad) + 3:.1f}" text-anchor="end">{lo + pad:.3g}</text>'
        f'<text class="tk" x="{L}" y="{H - 5}">{x0:g}</text>'
        f'<text class="tk" x="{W - R}" y="{H - 5}" text-anchor="end">{x1:g}</text>'
        f'{line(1, "s-paper")}{line(2, "s-ours")}</svg>'
    )


def shape_fields(fs):
    """How to draw a list of fields: as series, as the paper's table, or as a list."""
    nums = [f for f in fs if f["a"] is not None and f["b"] is not None]
    series = {}
    for f in nums:
        m = re.match(r"^(.*?\D)\s*(-?\d+(?:\.\d+)?)$", f["name"])
        if m:
            series.setdefault(m.group(1).strip(), []).append((float(m.group(2)), f["a"], f["b"]))
    good = {k: sorted(v) for k, v in series.items() if len(v) >= 4 and len({p[0] for p in v}) == len(v)}
    if good and sum(len(v) for v in good.values()) >= 0.8 * len(fs):
        return "series", good
    rows, cols, cells = [], [], {}
    for f in fs:
        if " " not in f["name"]:
            rows = []
            break
        r, c = f["name"].rsplit(" ", 1)
        r = r.rstrip(",:")
        if r not in rows:
            rows.append(r)
        if c not in cols:
            cols.append(c)
        cells[(r, c)] = f
    if rows and 2 <= len(cols) <= 8 and len(rows) >= 2 and len(cells) >= 0.6 * len(rows) * len(cols):
        if all(sum((r, c) in cells for r in rows) >= 2 for c in cols):
            return "matrix", (rows, cols, cells)
    return "list", fs


def cell_html(f):
    if f is None:
        return '<td class="na"></td>'
    cls = "err" if f["error"] else ("ok" if f["match"] else "off")
    title = f' title="{e(str(f["error"].get("evidence", "")))}"' if f["error"] else ""
    flag = '<i class="flag">paper error</i>' if f["error"] else ""
    return f'<td class="{cls}"{title}><span class="p">{e(f["exp"])}</span><span class="o">{e(f["obs"])}</span>{flag}</td>'


def fields_html(item):
    fs = fields_of(item)
    if not fs:
        return ""
    kind, data = shape_fields(fs)
    if kind == "series":
        charts = "".join(
            f'<figure class="chart"><figcaption>{e(name)}</figcaption>{series_svg(pts)}</figure>' for name, pts in data.items()
        )
        return f'<div class="charts">{charts}</div><div class="key"><span class="k-paper">paper</span><span class="k-ours">ours</span></div>'
    if kind == "matrix":
        rows, cols, cells = data
        head = "".join(f"<th>{e(c)}</th>" for c in cols)
        body = "".join(
            f'<tr><th scope="row">{e(r)}</th>{"".join(cell_html(cells.get((r, c))) for c in cols)}</tr>' for r in rows
        )
        return (
            f'<div class="scroll"><table class="matrix"><thead><tr><th></th>{head}</tr></thead><tbody>{body}</tbody></table></div>'
            '<div class="key cells"><span>upper: paper</span><span class="o">lower: ours</span></div>'
        )
    body = "".join(f'<tr><th scope="row">{e(f["name"])}</th>{cell_html(f)}</tr>' for f in fs)
    return f'<div class="scroll"><table class="matrix list"><tbody>{body}</tbody></table></div>'


def short_label(item):
    label = str(item.get("label", item.get("id", "")))
    t = token(item)
    if label.startswith(t):
        label = label[len(t):].lstrip(" ,:") or label
    return label[:1].upper() + label[1:]


def item_row(item, card_of):
    why = f'<a class="why" href="#d-{card_of[item["id"]]}">why</a>' if item.get("id") in card_of else ""
    changed = '<span class="chip new">changed here</span>' if item.get("_changed") else ""
    p = pixel_score(item)
    detail = ""
    if item.get("method") == "check":
        detail = f'<p class="detail">{e(str((item.get("check") or {}).get("detail", "")))}</p>'
    body = fields_html(item)
    meas = measure_of(item)
    head = (
        f'<div class="ihead">{stamp(item.get("verdict"))}<span class="ilabel">{e(short_label(item))}</span>{changed}'
        f'{score_bar(p)}<span class="meas">{e(meas) if not p else ""}</span>{why}</div>'
    )
    if body:
        open_attr = "" if item.get("verdict") in ("exact", "agrees") else " open"
        body = f'<details class="ibody"{open_attr}><summary>Numbers</summary>{body}</details>'
    return f'<div class="irow" id="i-{e(str(item.get("id", "")))}">{head}{detail}{body}</div>'


def img_tag(img, alt):
    size = f' width="{img["w"]}" height="{img["h"]}"' if img["w"] else ""
    return f'<img src="{e(img["src"])}" alt="{e(alt)}" loading="lazy"{size}>'


def viewer_html(render, title):
    pub, ours, ovl = render.get("published"), render["ours"], render.get("overlay")
    modes = []
    if pub:
        modes += [("side", "Side by side"), ("swipe", "Swipe"), ("blink", "Blink")]
    else:
        modes += [("ours", "Ours")]
    if ovl:
        modes.append(("overlay", "Overlay"))
    buttons = "".join(
        f'<button type="button" data-m="{m}"{" aria-pressed=\"true\"" if i == 0 else ""}>{label}</button>'
        for i, (m, label) in enumerate(modes)
    )
    base = pub or ours
    ratio = f'{base["w"]} / {base["h"]}' if base["w"] and base["h"] else "4 / 3"
    layers = ""
    if pub:
        layers += f'<figure class="pub">{img_tag(pub, title + ", published")}<figcaption>Published</figcaption></figure>'
    layers += f'<figure class="ours">{img_tag(ours, title + ", ours")}<figcaption>Ours</figcaption></figure>'
    if ovl:
        layers += f'<figure class="ovl">{img_tag(ovl, title + ", overlay")}<figcaption>Overlay</figcaption></figure>'
    slider = '<input type="range" class="swipe" min="0" max="100" value="50" aria-label="Swipe between published and ours">' if pub else ""
    return (
        f'<div class="viewer" data-mode="{modes[0][0]}"><div class="modes" role="group" aria-label="View">{buttons}</div>'
        f'<div class="stage" style="--ar:{ratio}">{layers}{slider}</div></div>'
    )


def station_html(st, card_of):
    rows = "".join(item_row(it, card_of) for it in st["items"])
    counts = {}
    for it in st["items"]:
        counts[it.get("verdict")] = counts.get(it.get("verdict"), 0) + 1
    dots = "".join(f'<i class="dot v-{v}" title="{counts[v]} {VERDICT_LABEL[v].lower()}"></i>' * counts[v] for v in VERDICTS if counts.get(v))
    views = "".join(
        (f'<p class="rlabel">{e(r["label"])}</p>' if len(st["renders"]) > 1 else "") + viewer_html(r, st["title"])
        for r in st["renders"]
    )
    if not views and st.get("published_only"):
        views = f'<div class="viewer solo"><div class="stage solo"><figure class="pub">{img_tag(st["published_only"], st["title"] + ", published")}<figcaption>Published; no render of ours</figcaption></figure></div></div>'
    cls = "station" + ("" if views else " noview")
    return (
        f'<section class="{cls}" id="fig-{e(st["key"])}"><header class="shead"><h3>{e(st["title"])}</h3><span class="dots">{dots}</span></header>'
        f'<div class="sgrid">{f"<div class=views>{views}</div>" if views else ""}<div class="rows">{rows}</div></div></section>'
    )


def gh_blob(ctx, path):
    return f'https://github.com/{ctx["repo"]}/blob/{ctx["head"]}/{path}'


def evidence_html(ctx, folder, evidence):
    out = []
    for ev in evidence:
        ev = str(ev)
        if re.match(r"^https?://\S+$", ev):
            out.append(f'<a href="{e(ev)}" rel="noopener">{e(ev)}</a>')
            continue
        path = ev.split(" ")[0].rstrip(":,")
        if "/" in path and ".." not in path:
            out.append(f'<a href="{e(gh_blob(ctx, folder + "/" + path))}" rel="noopener">{e(ev)}</a>')
        else:
            out.append(e(ev))
    return "".join(f"<li>{x}</li>" for x in out)


def decide_html():
    return (
        '<footer class="decide"><button type="button" data-d="ok">Accept</button>'
        '<button type="button" data-d="work">Needs work</button>'
        '<textarea rows="1" placeholder="Note for the author" aria-label="Note for the author"></textarea></footer>'
    )


def num_rows(nums):
    if not nums:
        return ""
    rows = "".join(
        f'<div class="num"><span class="n">{e(f["name"])}</span><span class="p">{e(f["exp"])}</span><span class="o">{e(f["obs"])}</span></div>'
        for f in nums
    )
    return f'<div class="nums"><div class="num head"><span class="n"></span><span class="p">paper</span><span class="o">ours</span></div>{rows}</div>'


def member_chips(members):
    return "".join(
        f'<a class="chip m v-{e(str(m.get("verdict")))}" href="#i-{e(str(m["id"]))}">{e(str(m.get("label", m["id"])))}</a>' for m in members
    )


def card_html(ctx, folder, card):
    k = card["kind"]
    head_bits, body = "", ""
    if k == "cause":
        lead, rest = first_sentence(card["summary"])
        more = ""
        extra = "".join(f"<p><b>{e(str(lbl))}:</b> {e(s)}</p>" for lbl, s in card["more"])
        if rest or extra:
            more = f'<details class="more"><summary>More</summary>{f"<p>{e(rest)}</p>" if rest else ""}{extra}</details>'
        hyps = ""
        if card["hyps"]:
            ruled = sum(1 for h in card["hyps"] if h.get("result") == "rejected")
            lis = "".join(
                f'<li class="h-{e(str(h.get("result", "")))}"><span class="hres">{e(str(h.get("result", "")))}</span>'
                f'<span class="hyp">{e(str(h.get("hypothesis", "")))}</span><span class="test">{e(str(h.get("test", "")))}</span></li>'
                for h in card["hyps"]
            )
            label = f"{ruled} of {len(card['hyps'])} tested causes ruled out" if ruled else f"{len(card['hyps'])} tested causes"
            hyps = f'<details class="hyps"><summary>{label}</summary><ul>{lis}</ul></details>'
        ev = f'<details class="hyps"><summary>Evidence</summary><ul class="ev">{evidence_html(ctx, folder, card["evidence"])}</ul></details>' if card["evidence"] else ""
        head_bits = stamp(card["verdict"]) + f'<span class="chip cat">{e(CATEGORY_LABEL.get(card["category"], card["category"]))}</span>'
        body = f'<p class="lead">{e(lead)}</p>{more}{num_rows(card["nums"])}{hyps}{ev}<div class="members">{member_chips(card["members"])}</div>'
    elif k == "choices":
        rows = "".join(
            f'<li><span class="what">{e(r["what"])}</span><span class="sens">{e(str(r["sensitivity"]))}</span>'
            f'<span class="tags"><i class="chip cat">{e(SOURCE_LABEL[r["source"]])}</i>{"".join(f"<i class=chip>{e(w)}</i>" for w in r["where"][:6])}</span></li>'
            for r in card["rows"]
        )
        head_bits = f'<span class="count">{len(card["rows"])}</span>'
        body = f'<ul class="rows-list">{rows}</ul>'
    elif k == "errors":
        by_where = {}
        for r in card["rows"]:
            by_where.setdefault(r["where"], []).append(r)
        rows = "".join(
            f'<li><span class="what"><b>{e(where)}</b> {"".join(f"<i class=chip>{e(str(r["field"]))}</i> " for r in rs)}</span>'
            f'<details class="hyps"><summary>How we know</summary><ul class="ev">'
            f'{"".join(f"<li>{e(strip_path(r["evidence"]))}</li>" for r in rs)}</ul></details></li>'
            for where, rs in by_where.items()
        )
        head_bits = f'<span class="count">{len(card["rows"])}</span>'
        body = f'<ul class="rows-list">{rows}</ul>'
    elif k == "explained":
        rows = "".join(
            f'<li>{stamp(c["verdict"])}<span class="what"><b>{e(c["title"])}</b> {e(first_sentence(c["summary"])[0])}</span>'
            f'<span class="tags"><i class="chip cat">{e(CATEGORY_LABEL.get(c["category"], c["category"]))}</i></span>'
            f'<span class="members">{member_chips(c["members"])}</span></li>'
            for c in card["rows"]
        )
        head_bits = f'<span class="count">{len(card["rows"])}</span>'
        body = f'<ul class="rows-list">{rows}</ul>'
    elif k == "outside":
        rows = "".join(
            f'<li><a class="path" href="#f-{file_anchor(f["path"])}">{e(f["path"])}</a>'
            f'<span class="delta"><b class="add">+{f["added"]}</b> <b class="del">−{f["deleted"]}</b></span></li>'
            for f in card["rows"]
        )
        notes = "".join(f'<p class="warn">{e(n)}</p>' for n in card.get("notes") or [])
        head_bits = f'<span class="count">{len(card["rows"])}</span>'
        body = f'{notes}<ul class="rows-list files">{rows}</ul>'
    elif k == "skipped":
        rows = "".join(
            f'<li><span class="what"><b>{e(str(it.get("label", it["id"])))}</b> {e(first_sentence((it.get("cause") or {}).get("summary", ""))[0])}</span></li>'
            for it in card["rows"]
        )
        head_bits = f'<span class="count">{len(card["rows"])}</span>'
        body = f'<ul class="rows-list">{rows}</ul>'
    status = '<span class="chip open">open</span>' if card.get("status") == "open" else ""
    return (
        f'<article class="card k-{k}" id="d-{card["key"]}" data-key="{card["key"]}" data-title="{e(card["title"])}" tabindex="-1">'
        f'<header class="chead"><h3>{e(card["title"])}</h3>{head_bits}{status}<span class="state" aria-live="polite"></span></header>'
        f"{body}{decide_html()}</article>"
    )


def strip_path(evidence):
    """Evidence without the file it starts with: 'run/a.json: SN 81.91 ...' gives 'SN 81.91 ...'."""
    return re.sub(r"^\S+\.\w+(?: \([^)]*\))?:\s+", "", str(evidence))


def file_anchor(path):
    return hashlib.sha1(path.encode()).hexdigest()[:10]


def highlight_lines(path, text):
    """One HTML string per line of a file, coloured when Pygments knows the language."""
    if highlight is not None:
        try:
            lexer = get_lexer_for_filename(path, stripnl=False)
            out = highlight(text, lexer, HtmlFormatter(nowrap=True))
            lines = out.split("\n")
            if lines and lines[-1] == "":
                lines.pop()
            return lines
        except ClassNotFound:
            pass
    return [e(ln) for ln in text.split("\n")[: None if not text.endswith("\n") else -1]]


def whole_file_html(path, text):
    lines = highlight_lines(path, text)
    cut = len(lines) > MAX_EMBED_LINES
    body = "".join(f'<span class="l">{ln}</span>' for ln in lines[:MAX_EMBED_LINES])
    note = f'<p class="cut">First {MAX_EMBED_LINES} of {len(lines)} lines.</p>' if cut else ""
    return f'<pre class="code">{body}</pre>{note}'


def diff_html(diff):
    out, old, new, started, n = [], 0, 0, False, 0
    for ln in diff.split("\n"):
        if ln.startswith("@@"):
            m = re.match(r"^@@ -(\d+)(?:,\d+)? \+(\d+)", ln)
            old, new, started = (int(m.group(1)), int(m.group(2)), True) if m else (old, new, True)
            out.append(f'<span class="l hunk">{e(ln)}</span>')
            continue
        if not started or ln.startswith("\\"):
            continue
        n += 1
        if n > MAX_EMBED_LINES:
            break
        if ln.startswith("+"):
            out.append(f'<span class="l add" data-n="{new}">{e(ln[1:])}</span>')
            new += 1
        elif ln.startswith("-"):
            out.append(f'<span class="l del" data-n="{old}">{e(ln[1:])}</span>')
            old += 1
        else:
            out.append(f'<span class="l" data-n="{new}">{e(ln[1:])}</span>')
            old += 1
            new += 1
    return f'<pre class="code diff">{"".join(out)}</pre>'


def file_html(ctx, f, opened):
    path = f["path"]
    delta = f'<span class="delta"><b class="add">+{f["added"]}</b>{f" <b class=del>−{f["deleted"]}</b>" if f["deleted"] else ""}</span>'
    link = f'<a class="gh" href="{e(gh_blob(ctx, path))}" rel="noopener">GitHub</a>'
    if f["status"] == "D":
        body = '<p class="cut">Deleted.</p>'
    elif f["binary"]:
        body = '<p class="cut">Binary file.</p>'
    elif f["status"] == "A":
        body = whole_file_html(path, ctx["repo_obj"].show(ctx["head"], path) or "")
    else:
        body = diff_html(ctx["repo_obj"].git("diff", "--no-renames", "-U3", ctx["base"], ctx["head"], "--", path))
    tag = {"A": "new", "D": "deleted"}.get(f["status"], "changed")
    return (
        f'<details class="file" id="f-{file_anchor(path)}"{" open" if opened else ""}><summary><span class="path">{e(f["_rel"])}</span>'
        f'<span class="chip">{tag}</span>{delta}{link}</summary>{body}</details>'
    )


def code_html(ctx, files, folders):
    by = {g[0]: [] for g in GROUPS}
    for f in files:
        cat, folder = classify(f["path"], folders)
        f["_cat"] = cat
        f["_rel"] = f["path"][len(folder) + 1:] if folder and f["path"].startswith(folder + "/") else f["path"]
        by[cat].append(f)
    total = sum(f["added"] + f["deleted"] for f in files) or 1
    segs, legend = "", ""
    for cat, title, _ in GROUPS:
        n = sum(f["added"] + f["deleted"] for f in by[cat])
        if not by[cat]:
            continue
        segs += f'<span class="seg c-{cat}" style="flex:{max(n, total * 0.004):.0f}" title="{e(title)}: {n:,} lines"></span>'
        legend += f'<span class="lg"><i class="dot c-{cat}"></i>{e(title)} <b>{n:,}</b> lines, {len(by[cat])} files</span>'
    out = [f'<div class="vbar sizebar" role="img" aria-label="Changed lines by kind">{segs}</div><div class="legend">{legend}</div>']
    first = True
    for cat, title, shown in GROUPS:
        fs = by[cat]
        if not fs:
            continue
        n = sum(f["added"] + f["deleted"] for f in fs)
        if shown:
            fs.sort(key=lambda f: (-f["added"] - f["deleted"]) if cat != "shared" else 0)
            body = "".join(file_html(ctx, f, opened=(first and i == 0 and cat != "shared")) for i, f in enumerate(fs))
            first = False
            out.append(f'<h3 class="ghead">{e(title)} <span class="count">{len(fs)} files, {n:,} lines</span></h3>{body}')
        elif cat == "generated":
            out.append(f'<h3 class="ghead">{e(title)} <span class="count">{len(fs)} files, {n:,} lines, not shown</span></h3>')
        else:
            rows = "".join(
                f'<li><a class="path" href="{e(gh_blob(ctx, f["path"]))}" rel="noopener">{e(f["_rel"])}</a>'
                f'<span class="delta"><b class="add">+{f["added"]}</b></span></li>' for f in fs
            )
            out.append(
                f'<details class="group"><summary><h3 class="ghead">{e(title)} <span class="count">{len(fs)} files, {n:,} lines, on GitHub</span></h3></summary>'
                f'<ul class="rows-list files">{rows}</ul></details>'
            )
    return "".join(out), by


def paper_html(ctx, folder, results, base_results, files, shared, conflict_notes, images, idx):
    items = [it for it in results["items"] if isinstance(it, dict) and it.get("id")]
    old = {it.get("id"): it for it in (base_results or {}).get("items", []) if isinstance(it, dict)}
    if base_results:
        for it in items:
            it["_changed"] = old.get(it["id"]) != {k: v for k, v in it.items() if k != "_changed"}
    paper = results.get("paper") or {}
    pid = str(paper.get("id") or folder)
    counts = {v: sum(1 for it in items if it.get("verdict") == v) for v in VERDICTS}
    cards = decision_cards(pid, items, shared if idx == 0 else [], conflict_notes if idx == 0 else [])
    card_of = {}
    for c in cards:
        if c["kind"] == "cause":
            for m in c["members"]:
                card_of[m["id"]] = c["key"]
        elif c["kind"] == "explained":
            for sub in c["rows"]:
                for m in sub["members"]:
                    card_of[m["id"]] = c["key"]
        elif c["kind"] == "skipped":
            for m in c["rows"]:
                card_of[m["id"]] = c["key"]
    tree = ctx["repo_obj"].ls(ctx["head"], folder + "/")
    stations = figure_stations(folder, items, tree, images)
    others = [it for it in items if it.get("kind") != "figure"]
    groups = [("table", "Tables"), ("value", "Numbers in the text"), ("code_check", "Checks")]
    numbers = ""
    for kind, title in groups:
        its = [it for it in others if it.get("kind") == kind]
        if its:
            blocks = "".join(f'<div class="nblock">{("<h4>" + e(token(it)) + "</h4>") if kind == "table" else ""}{item_row(it, card_of)}</div>' for it in its)
            numbers += f'<h3 class="ghead">{title} <span class="count">{len(its)}</span></h3>{blocks}'
    rest = [it for it in others if it.get("kind") not in dict(groups)]
    if rest:
        numbers += '<h3 class="ghead">Other</h3>' + "".join(item_row(it, card_of) for it in rest)
    doi = str(paper.get("doi") or "")
    cite = e(str(paper.get("citation") or ""))
    if re.match(r"^10\.\d{4,9}/\S+$", doi):
        cite = f'<a href="https://doi.org/{e(doi)}" rel="noopener">{cite or e(doi)}</a>'
    n_open = sum(1 for c in cards if c.get("status") == "open")
    changed = sum(1 for it in items if it.get("_changed"))
    changed_note = f'<p class="note">This change touches {changed} of {len(items)} items; they are marked <span class="chip new">changed here</span>.</p>' if base_results and changed else ""
    nav = (
        f'<nav class="tabs" aria-label="Sections"><a href="#decisions-{idx}">Decisions <b>{len(cards)}</b></a>'
        f'<a href="#figures-{idx}">Figures <b>{len(stations)}</b></a><a href="#numbers-{idx}">Tables and numbers <b>{len(others)}</b></a>'
        f'<a href="#code">Code</a></nav>'
    )
    html_out = (
        f'<section class="paper" data-paper="{e(pid)}"><div class="phead"><p class="pid"><span class="pmc">{e(pid)}</span> {cite}</p>'
        f'<h1>{e(str(paper.get("title") or folder))}</h1>{verdict_bar(counts)}{changed_note}{nav}</div>'
        f'<section id="decisions-{idx}" class="sec"><h2>Decisions <span class="count">{n_open} open</span></h2>'
        f'<div class="cards">{"".join(card_html(ctx, folder, c) for c in cards)}</div></section>'
        f'<section id="figures-{idx}" class="sec"><h2>Figures</h2>{"".join(station_html(s, card_of) for s in stations) or "<p class=note>No figure items.</p>"}</section>'
        f'<section id="numbers-{idx}" class="sec"><h2>Tables and numbers</h2>{numbers or "<p class=note>No table or number items.</p>"}</section></section>'
    )
    return html_out, {"id": pid, "title": str(paper.get("title") or folder), "counts": counts, "cards": [c["key"] for c in cards], "open": n_open}


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>{title}</title>
<link rel="stylesheet" href="{root}assets/review.css">
</head>
<body{attrs}>
{body}
<script src="{root}assets/review.js"></script>
</body>
</html>
"""


def ref_line(ctx):
    r = ctx["ref"]
    bits = []
    if r.get("number"):
        bits.append(f'<a href="{e(r["url"])}" rel="noopener">#{r["number"]}</a>')
    if r.get("branch"):
        bits.append(f'<span class="mono">{e(r["branch"])}</span>')
    bits.append(f'<span class="mono">{e(ctx["head"][:7])}</span>')
    if r.get("author"):
        bits.append(e(r["author"]))
    if r.get("updated"):
        bits.append(e(r["updated"][:10]))
    chips = ""
    if r.get("draft"):
        chips += '<span class="chip">draft</span>'
    if r.get("checks"):
        chips += f'<span class="chip ci-{e(r["checks"])}">checks {e(r["checks"])}</span>'
    return " · ".join(bits) + (" " + chips if chips else "")


def build_review(repo, repo_name, ref, base_ref, outdir, others=()):
    """Write one review page; returns the summary the index needs."""
    head = repo.sha(ref["git"])
    base = repo.git("merge-base", base_ref, head).strip()
    files = changed_files(repo, base, head)
    papers = find_papers(repo, head, files)
    folders = [p[0] for p in papers]
    ctx = {"repo": repo_name, "repo_obj": repo, "head": head, "base": base, "ref": ref}
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    images = Images(repo, head, outdir)
    for f in files:
        f["_cat"], _ = classify(f["path"], folders)
    shared = [f for f in files if f["_cat"] == "shared"]
    notes = []
    main_conf = conflicts(repo, base_ref, head)
    if main_conf:
        notes.append(f"Conflicts with {base_ref.split('/')[-1]} on " + ", ".join(main_conf[:6]) + ".")
    clash, by_files = [], {}
    for o in others:
        c = conflicts(repo, head, o["sha"])
        if c:
            clash.append((o["label"], c))
            by_files.setdefault(tuple(c[:6]), []).append(o["label"])
    for names, labels in by_files.items():
        notes.append(f"Conflicts with {', '.join(labels)} on {', '.join(names)}. Merge one at a time.")
    sections, summaries = [], []
    for idx, (folder, path, results) in enumerate(papers):
        base_results = None
        for cand in (path, f"{folder}/results.json", f"{folder}/figure-reproduction/results.json"):
            base_results = load_json(repo, base, cand)
            if base_results:
                break
        sec, summary = paper_html(ctx, folder, results, base_results, files, shared, notes, images, idx)
        sections.append(sec)
        summaries.append(summary)
    generic = ""
    if not papers:
        card = {"kind": "outside", "title": "Changed files", "rows": [f for f in files if f["_cat"] == "shared"], "notes": notes,
                "key": card_key(repo_name, ref["slug"], "files", *[f["path"] for f in files])}
        generic = (
            f'<section class="paper"><div class="phead"><h1>{e(ref.get("title") or ref["label"])}</h1>'
            '<p class="note">No Paper2Repro results.json in this change, so there is no paper to lay it out by.</p></div>'
            f'<section class="sec"><h2>Decisions</h2><div class="cards">{card_html(ctx, "", card)}</div></section></section>'
        )
        summaries.append({"id": "", "title": ref.get("title") or ref["label"], "counts": {}, "cards": [card["key"]], "open": 0})
    code, by = code_html(ctx, files, folders)
    target = ref.get("url") or f"https://github.com/{repo_name}/compare/{base_ref.split('/')[-1]}...{ref.get('branch', head)}"
    body = (
        f'<header class="top"><div class="wrap"><a class="back" href="../">All reviews</a>'
        f'<span class="refline">{e(repo_name)} · {ref_line(ctx)}</span></div></header>'
        f'<main class="wrap">{"".join(sections)}{generic}'
        f'<section id="code" class="sec"><h2>Code</h2>{code}</section></main>'
        f'<div class="bar"><div class="wrap"><span class="progress"><b class="done">0</b> of <b class="all">0</b> decided</span>'
        f'<span class="grow"></span><button type="button" class="copy">Copy review</button>'
        f'<a class="btn" href="{e(target)}" rel="noopener">Open on GitHub</a></div></div>'
    )
    title = " ".join(s["id"] for s in summaries if s["id"]) or ref["label"]
    attrs = f' data-repo="{e(repo_name)}" data-label="{e(ref["label"])}" data-sha="{e(head[:7])}" data-page="review"'
    (outdir / "index.html").write_text(PAGE.format(title=e(f"{title} · {ref['label']}"), root="../", attrs=attrs, body=body), encoding="utf-8")
    lines = {cat: sum(f["added"] + f["deleted"] for f in fs) for cat, fs in by.items()}
    return {
        "slug": ref["slug"], "label": ref["label"], "ref": ref, "head": head, "papers": summaries,
        "files": len(files), "lines": lines, "clash": clash, "main_conflict": bool(main_conf),
    }


def index_html(repo_name, reviews, built, run_url):
    cards = []
    for r in reviews:
        ref = r["ref"]
        p = r["papers"][0]
        counts = {v: sum(pp["counts"].get(v, 0) for pp in r["papers"]) for v in VERDICTS}
        keys = ",".join(k for pp in r["papers"] for k in pp["cards"])
        total = sum(r["lines"].values())
        code = r["lines"].get("method", 0) + r["lines"].get("analysis", 0)
        chips = ""
        if ref.get("draft"):
            chips += '<span class="chip">draft</span>'
        if ref.get("checks"):
            chips += f'<span class="chip ci-{e(ref["checks"])}">checks {e(ref["checks"])}</span>'
        if r["main_conflict"]:
            chips += '<span class="chip warn">conflicts with main</span>'
        ids = " ".join(pp["id"] for pp in r["papers"] if pp["id"])
        who = " · ".join(x for x in (ref.get("author"), (ref.get("updated") or "")[:10]) if x)
        bar = verdict_bar(counts) if sum(counts.values()) else ""
        cards.append(
            f'<a class="rcard" href="{e(r["slug"])}/" data-keys="{e(keys)}">'
            f'<div class="rtop"><span class="pmc">{e(ids or "No paper")}</span><span class="rref">{e(r["label"])}</span></div>'
            f'<h2>{e(p["title"])}</h2>{bar}'
            f'<p class="facts"><span class="progress"><b class="done">0</b> of <b class="all">{len(keys.split(",")) if keys else 0}</b> decided</span>'
            f'<span>{sum(pp["open"] for pp in r["papers"])} open causes</span><span>{code:,} lines of method and analysis in {total:,}</span></p>'
            f'<p class="who">{e(who)} {chips}</p></a>'
        )
    run = f' · <a href="{e(run_url)}" rel="noopener">build log</a>' if run_url else ""
    clashing = [r for r in reviews if r["clash"]]
    clash_note = ""
    if clashing:
        names = []
        for r in clashing:
            for _, fs in r["clash"]:
                names += [f for f in fs if f not in names]
        clash_note = (
            f'<p class="warn">{len(clashing)} of these conflict with each other on {e(", ".join(names[:4]))}'
            f'{" and more" if len(names) > 4 else ""}. Merge one at a time.</p>'
        )
    body = (
        f'<header class="top"><div class="wrap"><span class="refline">{e(repo_name)} · built {e(built)}{run}</span></div></header>'
        f'<main class="wrap"><div class="phead"><h1>Reproductions to review</h1>'
        f'<p class="note">{len(reviews)} open. Your decisions stay in this browser until you copy them to GitHub.</p>{clash_note}</div>'
        f'<div class="rgrid">{"".join(cards) or "<p class=note>Nothing is open.</p>"}</div></main>'
    )
    return PAGE.format(title=e(f"Reviews · {repo_name}"), root="", attrs=f' data-repo="{e(repo_name)}" data-page="index"', body=body)


# ------------------------------------------------------------------- the refs


def api(path, token):
    req = urllib.request.Request(f"https://api.github.com{path}", headers={
        "Accept": "application/vnd.github+json", "User-Agent": "review-site", "X-GitHub-Api-Version": "2022-11-28",
        **({"Authorization": f"Bearer {token}"} if token else {}),
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def checks_state(repo_name, sha, token):
    try:
        runs = api(f"/repos/{repo_name}/commits/{sha}/check-runs?per_page=100", token).get("check_runs", [])
    except (urllib.error.URLError, ValueError, OSError):
        return None
    if not runs:
        return None
    if any(r.get("status") != "completed" for r in runs):
        return "running"
    bad = {"failure", "timed_out", "cancelled", "action_required", "startup_failure"}
    return "failed" if any(r.get("conclusion") in bad for r in runs) else "passed"


def slug_of(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "ref"


def collect_refs(repo, repo_name, args, token):
    """The pull requests and branches to review, each as a dict with the git ref to read."""
    if args.prs_json:
        pulls = json.loads(Path(args.prs_json).read_text())
    else:
        pulls = api(f"/repos/{repo_name}/pulls?state=open&per_page=100", token)
    extra = [x.strip() for x in (args.extra or "").split(",") if x.strip()]
    for x in [x for x in extra if x.isdigit()]:
        if not any(str(p["number"]) == x for p in pulls) and not args.prs_json:
            pulls.append(api(f"/repos/{repo_name}/pulls/{x}", token))
    refs, pr_shas = [], set()
    for p in pulls:
        n = p["number"]
        local = f"refs/review/pr-{n}"
        if not args.no_fetch:
            repo.git("fetch", "--quiet", "origin", f"+refs/pull/{n}/head:{local}")
        if not repo.ok("rev-parse", "--verify", "--quiet", local):
            print(f"skip #{n}: no local ref {local}", file=sys.stderr)
            continue
        sha = repo.sha(local)
        pr_shas.add(sha)
        refs.append({
            "git": local, "slug": f"pr-{n}", "label": f"#{n}", "number": n, "title": p.get("title", ""),
            "author": (p.get("user") or {}).get("login", ""), "branch": (p.get("head") or {}).get("ref", ""),
            "updated": p.get("updated_at", ""), "draft": bool(p.get("draft")),
            "url": p.get("html_url") or f"https://github.com/{repo_name}/pull/{n}",
            "checks": None if args.prs_json else checks_state(repo_name, sha, token),
        })
    names = [x for x in extra if not x.isdigit()]
    if args.branches:
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=args.max_age_days)
        base_ref = f"origin/{args.base}"
        base_tree = repo.git("rev-parse", f"{base_ref}^{{tree}}").strip()
        # the head of every pull request, open or closed: a branch that is still at the head of a
        # closed pull request is finished
        closed = set()
        if not args.no_fetch:
            listing = repo.git("ls-remote", "origin", "refs/pull/*/head", check=False)
            closed = {ln.split("\t")[0] for ln in listing.splitlines() if ln.strip()} - pr_shas
        fmt = "%(refname)%09%(objectname)%09%(committerdate:iso8601-strict)"
        for ln in repo.git("for-each-ref", f"--format={fmt}", "refs/remotes/origin").splitlines():
            name, sha, when = ln.split("\t")
            short = name[len("refs/remotes/origin/"):]
            if short in ("HEAD", args.base) or sha in pr_shas or sha in closed or short in names:
                continue
            if datetime.datetime.fromisoformat(when) < cutoff or not repo.ok("merge-base", base_ref, sha):
                continue  # old, or no history in common (a branch of assets)
            if repo.ok("merge-base", "--is-ancestor", sha, base_ref):
                continue  # merged
            merged = repo.git("merge-tree", "--write-tree", base_ref, sha, check=False).split("\n")[0].strip()
            if merged == base_tree:
                continue  # merged by squash or rebase: it adds nothing to the base
            names.append(short)
    for name in names:
        git_ref = f"refs/remotes/origin/{name}" if repo.ok("rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{name}") else name
        if not repo.ok("rev-parse", "--verify", "--quiet", f"{git_ref}^{{commit}}"):
            print(f"skip branch {name}: not found", file=sys.stderr)
            continue
        sha = repo.sha(git_ref)
        if sha in pr_shas:
            continue
        who, when = repo.git("log", "-1", "--format=%an%x09%cI", sha).strip().split("\t")
        refs.append({
            "git": git_ref, "slug": "branch-" + slug_of(name), "label": name, "branch": name, "title": name,
            "author": who, "updated": when, "checks": None if args.prs_json else checks_state(repo_name, sha, token),
        })
    return refs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", required=True, help="owner/name of the repository to review")
    ap.add_argument("--clone", required=True, help="where its clone is, or where to put one")
    ap.add_argument("--out", required=True, help="folder to write the site to")
    ap.add_argument("--base", default="main", help="branch the changes are compared with")
    ap.add_argument("--extra", default="", help="more pull request numbers or branch names, comma separated")
    ap.add_argument("--no-branches", dest="branches", action="store_false", help="leave out branches that have no pull request")
    ap.add_argument("--max-age-days", type=int, default=45, help="leave out branches with no commit in this many days")
    ap.add_argument("--prs-json", help="read the open pull requests from this file, not from GitHub")
    ap.add_argument("--no-fetch", action="store_true", help="use the refs the clone already has")
    ap.add_argument("--run-url", default="", help="link to the build log")
    args = ap.parse_args(argv)

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    clone = Path(args.clone)
    if not (clone / ".git").exists():
        subprocess.run(["git", "clone", "--quiet", f"https://github.com/{args.repo}", str(clone)], check=True)
    repo = Repo(clone)
    if not args.no_fetch:
        repo.git("fetch", "--quiet", "--prune", "origin")
    base_ref = f"origin/{args.base}"
    refs = collect_refs(repo, args.repo, args, token)
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    (out / "assets").mkdir(parents=True)
    for name in ("review.css", "review.js"):
        shutil.copy(HERE / "assets" / name, out / "assets" / name)
    if highlight is not None:
        css = HtmlFormatter(style="default").get_style_defs(".code")
        dark = HtmlFormatter(style="github-dark").get_style_defs(".code")
        with open(out / "assets" / "review.css", "a", encoding="utf-8") as f:
            f.write("\n/* code colours (Pygments) */\n" + css + "\n@media (prefers-color-scheme: dark) {\n" + dark + "\n}\n")
    heads = [{"sha": repo.sha(r["git"]), "label": r["label"], "slug": r["slug"]} for r in refs]
    reviews = []
    for r in refs:
        others = [h for h in heads if h["slug"] != r["slug"]]
        try:
            reviews.append(build_review(repo, args.repo, r, base_ref, out / r["slug"], others))
            print(f"built {r['slug']}: {reviews[-1]['files']} files", file=sys.stderr)
        except GitError as err:
            print(f"skip {r['slug']}: {err}", file=sys.stderr)
    reviews.sort(key=lambda r: r["ref"].get("updated") or "", reverse=True)
    built = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    (out / "index.html").write_text(index_html(args.repo, reviews, built, args.run_url), encoding="utf-8")
    (out / ".nojekyll").write_text("")
    print(f"{len(reviews)} reviews in {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
