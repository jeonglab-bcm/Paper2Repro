// The rules and the HTML of a review. No browser and no network here, so Node can test it.
//
// A review is laid out by the paper: the decisions to make, each figure next to the
// published one, each table in the paper's shape, and the code of the method only.
// Every string that comes from the reviewed repository goes through esc().

export const VERDICTS = ["exact", "agrees", "partly", "inconclusive", "differs", "not_attempted"];
export const VERDICT_LABEL = {
  exact: "Exact", agrees: "Agrees", partly: "Partly", inconclusive: "Inconclusive",
  differs: "Differs", not_attempted: "Not attempted",
};
const SEVERITY = { differs: 4, inconclusive: 3, partly: 2, not_attempted: 1, agrees: 0, exact: 0 };
const CATEGORY_LABEL = {
  rendering_only: "Rendering only", paper_error: "Paper error", undocumented_setting: "Setting not stated",
  code_differs_from_paper: "Code differs from paper", code_does_not_run: "Code needed a fix",
  data_differs: "Data differ", data_unavailable: "Data not available",
  proprietary_software: "Software not available", nondeterminism: "Randomness", environment: "Environment",
  not_a_result: "Not a result", metric_resolution: "Metric cannot tell", unknown: "Cause unknown",
};
const SOURCE_LABEL = { our_choice: "Our choice", found_by_search: "Found by search", read_from_figure: "Read from figure" };
const RASTER = new Set(["png", "jpg", "jpeg", "gif", "webp"]);
const CODE_EXTS = new Set(["py", "r", "nf", "sh", "jl", "m", "c", "cc", "cpp", "h", "hpp", "rs", "pl", "js", "ts", "java", "f90", "go", "smk", "rmd", "qmd"]);
const GENERATED_PARTS = ["/output/", "/session/", "/published/", "/tutorial/", "/data/"];
const PLUMBING_RE = /^(check_|build_|compare_runs|readme_|pack_|fetch_|run_|make_|page_template|figures?\.|conftest|setup\.)/i;
export const GROUPS = [ // category, title, whether its code is shown on the page
  ["method", "Method", true],
  ["analysis", "Analysis", true],
  ["shared", "Outside the paper folder", true],
  ["tests", "Tests", false],
  ["plumbing", "Checks and plumbing", false],
  ["docs", "Documents", false],
  ["generated", "Outputs and records", false],
];
export const MAX_LINES = 1500;

const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
export function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ESC[c]);
}
const ext = (path) => (/\.([A-Za-z0-9]+)$/.exec(path.split("/").pop()) || [, ""])[1].toLowerCase();
const fmtInt = (n) => Number(n).toLocaleString("en-US");

// ------------------------------------------------------------------ links

/** A pasted GitHub link (or "owner/repo#40", "#40", "owner/repo@branch") as {owner, repo, kind, ...}. */
export function parseLink(text, defaultRepo = "") {
  const t = String(text || "").trim().replace(/^<|>$/g, "");
  if (!t) return null;
  let m = /^(?:https?:\/\/)?(?:www\.)?github\.com\/([^/\s#?]+)\/([^/\s#?]+)(?:\/([^?#]*))?/i.exec(t);
  if (m) {
    const owner = m[1], repo = m[2].replace(/\.git$/, ""), rest = (m[3] || "").replace(/\/+$/, "");
    let r;
    if ((r = /^pull\/(\d+)/.exec(rest))) return { owner, repo, kind: "pull", number: Number(r[1]) };
    if ((r = /^tree\/(.+)$/.exec(rest))) return { owner, repo, kind: "branch", branch: safeDecode(r[1]) };
    if ((r = /^compare\/(?:(.+?)\.\.\.?)?(.+)$/.exec(rest))) {
      return { owner, repo, kind: "branch", branch: safeDecode(r[2]), ...(r[1] ? { base: safeDecode(r[1]) } : {}) };
    }
    return { owner, repo, kind: "repo" };
  }
  const [dOwner, dRepo] = defaultRepo.split("/");
  if ((m = /^([\w.-]+)\/([\w.-]+)#(\d+)$/.exec(t))) return { owner: m[1], repo: m[2], kind: "pull", number: Number(m[3]) };
  if ((m = /^([\w.-]+)\/([\w.-]+)@(\S+)$/.exec(t))) return { owner: m[1], repo: m[2], kind: "branch", branch: m[3] };
  if ((m = /^#?(\d+)$/.exec(t)) && dRepo) return { owner: dOwner, repo: dRepo, kind: "pull", number: Number(m[1]) };
  if ((m = /^([\w.-]+)\/([\w.-]+)$/.exec(t)) && !dRepo) return { owner: m[1], repo: m[2], kind: "repo" };
  if (dRepo && /^[\w./-]+$/.test(t)) return { owner: dOwner, repo: dRepo, kind: "branch", branch: t };
  return null;
}
function safeDecode(s) {
  try { return decodeURIComponent(s); } catch { return s; }
}
export const encPath = (p) => String(p).split("/").map(encodeURIComponent).join("/");

/** The address of a review inside the app: "?r=owner/repo/pull/40". In-page anchors stay free. */
export function routeOf(link) {
  if (!link) return "./";
  const base = `?r=${link.owner}/${link.repo}`;
  if (link.kind === "pull") return `${base}/pull/${link.number}`;
  if (link.kind === "branch") return `${base}/tree/${encPath(link.branch)}`;
  return base;
}
/** The review a page address asks for: ?r=owner/repo/pull/40, or ?url=<a GitHub link>. */
export function parseRoute(search, defaultRepo = "") {
  const q = new URLSearchParams(search || "");
  if (q.get("url")) return parseLink(q.get("url"), defaultRepo);
  const m = /^([^/]+)\/([^/]+)(?:\/(pull|tree)\/(.+))?$/.exec(q.get("r") || "");
  if (!m) return null;
  if (m[3] === "pull") return /^\d+$/.test(m[4]) ? { owner: m[1], repo: m[2], kind: "pull", number: Number(m[4]) } : null;
  if (m[3] === "tree") return { owner: m[1], repo: m[2], kind: "branch", branch: m[4] };
  return { owner: m[1], repo: m[2], kind: "repo" };
}

// ------------------------------------------------------------------ values

/** results.json as Python writes it: NaN and Infinity are allowed there, not in JSON. */
export function parseResults(text) {
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    try {
      data = JSON.parse(text.replace(/(?<=[:\[,]\s*)(-?Infinity|NaN)(?=\s*[,\]}])/g, "null"));
    } catch {
      return null;
    }
  }
  return data && typeof data === "object" && Array.isArray(data.items) ? data : null;
}

export function number(v) {
  if (typeof v === "number") return v;
  if (typeof v !== "string" || !v.trim()) return null;
  const n = Number(v.replace(/,/g, ""));
  return Number.isNaN(n) ? null : n;
}
function printedDecimals(expected) {
  const s = String(expected).replace(/,/g, "").trim();
  if (/e/i.test(s)) return null;
  return s.includes(".") ? s.split(".")[1].length : 0;
}
/** Half a unit in the last printed digit, as Paper2Repro's check_results.py. */
function printedTolerance(expected) {
  const s = String(expected).replace(/,/g, "").trim().toLowerCase();
  if (s.includes("e")) {
    const [mant, exp] = s.split("e");
    const dec = mant.includes(".") ? mant.split(".")[1].length : 0;
    return 0.5 * 10 ** (Number(exp) - dec);
  }
  return 0.5 * 10 ** -(s.includes(".") ? s.split(".")[1].length : 0);
}
export function fieldMatches(f, tol) {
  const t = f.tolerance || tol || {};
  const a = number(f.expected), b = number(f.observed);
  if (a === null || b === null) return f.expected === f.observed;
  if (Number.isNaN(a) || Number.isNaN(b)) return false;
  let allowed = 1e-12;
  if (t.printed) allowed += printedTolerance(f.expected);
  allowed += (t.abs || 0) + (t.rel || 0) * Math.abs(a);
  return Math.abs(a - b) <= allowed;
}
const fmtG = (x, digits) => String(Number(x.toPrecision(digits)));
export function fmtExp(v) {
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : fmtG(v, 6);
  return String(v);
}
export function fmtObs(obs, exp) {
  const b = number(obs);
  if (b === null) return String(obs);
  if (typeof exp === "string" && number(exp) !== null) {
    const dec = printedDecimals(exp);
    if (dec !== null) return b.toFixed(dec);
  }
  return Number.isInteger(b) ? String(b) : fmtG(b, 4);
}
/** The item's fields, each with whether it matches and whether the paper is in error. */
export function fieldsOf(item) {
  const v = item.values || {};
  const errors = new Map((v.exceptions || []).filter((x) => x.category === "paper_error").map((x) => [x.field, x]));
  return (v.fields || []).map((f) => {
    const name = String(f.name ?? "");
    const a = number(f.expected), b = number(f.observed);
    const gap = a !== null && b !== null && !Number.isNaN(a) && !Number.isNaN(b) ? Math.abs(a - b) / (a ? Math.abs(a) : 1) : null;
    return { name, exp: fmtExp(f.expected), obs: fmtObs(f.observed, f.expected), a, b, match: fieldMatches(f, v.tolerance), error: errors.get(name) || null, gap };
  });
}
export function pixelScore(item) {
  const p = item.pixels;
  if (!p) return null;
  const shares = [number(p.published_near_ours), number(p.ours_near_published)].filter((x) => x !== null);
  if (!shares.length) return null;
  const controls = (p.controls || []).map((c) => ({ score: number(c.score) || 0, name: c.name || "" }));
  controls.sort((x, y) => y.score - x.score);
  return { s: Math.min(...shares), t: number(p.threshold) || 0, tol: number(p.tolerance_px) || 0, control: controls[0] || null };
}
export function measureOf(item) {
  if (item.method === "values") {
    const fs = fieldsOf(item), counted = fs.filter((f) => !f.error), errs = fs.length - counted.length;
    const hits = counted.filter((f) => f.match).length;
    return `${hits} of ${counted.length} as printed` + (errs ? `, ${errs} paper error${errs !== 1 ? "s" : ""}` : "");
  }
  if (item.method === "pixels") {
    const p = pixelScore(item);
    return p ? `${(p.s * 100).toFixed(0)}% within ${p.tol} px, pass ${(p.t * 100).toFixed(0)}%` : "";
  }
  if (item.method === "check") return item.check && item.check.passed ? "check passed" : "check failed";
  return "";
}

// ---------------------------------------------------------------- the paper

const FIG_RE = /^fig(?:ure)?[-_. ]?(s?\d+)/i;
const TAB_RE = /^tab(?:le)?[-_. ]?(s?\d+)/i;
export const figKey = (id) => (FIG_RE.exec(id) || [, null])[1]?.toLowerCase() ?? null;

/** A short name for where an item is in the paper: "Fig. 3", "Table 1", "Text". */
export function token(item) {
  const id = String(item.id ?? "");
  let m;
  if ((m = FIG_RE.exec(id))) return `Fig. ${m[1].toUpperCase()}`;
  if ((m = TAB_RE.exec(id))) return `Table ${m[1].toUpperCase()}`;
  const known = { text: "Text", data: "Data", code: "Code", package: "Package", port: "Port" };
  return known[id.split(".")[0].toLowerCase()] || String(item.label ?? id).split(",")[0];
}
function tokens(items, limit = 5) {
  const seen = [];
  for (const it of items) if (!seen.includes(token(it))) seen.push(token(it));
  return seen.length <= limit ? seen : [...seen.slice(0, limit - 1), `+${seen.length - limit + 1}`];
}
export function firstSentence(text) {
  const t = String(text ?? "").split(/\s+/).filter(Boolean).join(" ");
  const m = /^(.*?[.!?])\s+(?=[A-Z(])(.*)$/.exec(t);
  return m ? [m[1], m[2]] : [t, ""];
}
/** A stable name for a card, from what it says: a decision is kept until the card changes. */
export function cardKey(...parts) {
  const s = parts.map(String).join("\x1f");
  let h1 = 0x811c9dc5, h2 = 0x01000193;
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    h1 = Math.imul(h1 ^ c, 0x01000193);
    h2 = Math.imul(h2 ^ c, 0x85ebca6b) + 0x9e3779b9;
  }
  return ((h1 >>> 0).toString(16).padStart(8, "0") + (h2 >>> 0).toString(16).padStart(8, "0")).slice(0, 12);
}
const squash = (s) => String(s ?? "").split(/\s+/).filter(Boolean).join(" ");

/** One card per open cause; items that share their tested hypotheses share a card. */
export function causeCards(paperId, items) {
  const groups = new Map();
  for (const it of items) {
    const c = it.cause;
    if (!c || it.verdict === "not_attempted") continue;
    if ((SEVERITY[it.verdict] || 0) < 2 && c.status !== "open") continue;
    const hyps = c.hypotheses || [];
    const key = hyps.length ? "h\x1f" + hyps.map((h) => String(h.hypothesis ?? "")).sort().join("\x1f") : "s\x1f" + String(c.summary ?? "");
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(it);
  }
  const open = [], explained = [];
  for (const members of groups.values()) {
    const lead = members.find((m) => (m.kind === "table" || m.kind === "value") && fieldsOf(m).length) || members[0];
    const cause = lead.cause;
    const isOpen = members.some((m) => (m.cause || {}).status === "open");
    const worst = members.map((m) => m.verdict).reduce((a, b) => ((SEVERITY[b] || 0) > (SEVERITY[a] || 0) ? b : a));
    const nums = [], seen = new Set();
    for (const m of members) {
      for (const f of fieldsOf(m)) {
        if (f.match || f.error || seen.has(f.name) || f.gap === null) continue;
        seen.add(f.name);
        nums.push(f);
      }
    }
    nums.sort((a, b) => b.gap - a.gap);
    const summaries = [];
    for (const m of members) {
      const s = squash((m.cause || {}).summary);
      if (s && !summaries.some((x) => x[1] === s)) summaries.push([m.label ?? m.id, s]);
    }
    const card = {
      kind: "cause", title: tokens(members).join(" · "), status: isOpen ? "open" : "explained", verdict: worst,
      category: cause.category || "", summary: summaries.length ? summaries[0][1] : "", more: summaries.slice(1),
      nums: nums.slice(0, 6), hyps: cause.hypotheses || [], members, evidence: cause.evidence || [],
    };
    card.key = cardKey(paperId, "cause", card.title, card.summary, card.status);
    (isOpen ? open : explained).push(card);
  }
  open.sort((a, b) => (SEVERITY[b.verdict] || 0) - (SEVERITY[a.verdict] || 0) || b.members.length - a.members.length);
  return [open, explained];
}

export function decisionCards(paperId, items, sharedFiles, notes) {
  const [open, explained] = causeCards(paperId, items);
  const cards = [...open];
  const choices = [], seen = new Map();
  for (const it of items) {
    for (const a of it.assumptions || []) {
      if (!(a.source in SOURCE_LABEL)) continue;
      const what = squash(a.what);
      if (seen.has(what)) {
        if (!seen.get(what).where.includes(token(it))) seen.get(what).where.push(token(it));
        continue;
      }
      const row = { what, source: a.source, sensitivity: a.sensitivity ?? "", where: [token(it)] };
      seen.set(what, row);
      choices.push(row);
    }
  }
  if (choices.length) cards.push({ kind: "choices", title: "Choices the paper does not give", rows: choices, key: cardKey(paperId, "choices", ...choices.map((c) => c.what)) });
  const errors = [];
  for (const it of items) {
    for (const x of (it.values || {}).exceptions || []) {
      if (x.category === "paper_error") errors.push({ where: token(it), field: x.field ?? "", evidence: x.evidence ?? "" });
    }
  }
  if (errors.length) cards.push({ kind: "errors", title: "Values the paper prints that do not follow from its own numbers", rows: errors, key: cardKey(paperId, "errors", ...errors.map((x) => x.where + x.field)) });
  if (explained.length) cards.push({ kind: "explained", title: "Differences with a tested cause", rows: explained, key: cardKey(paperId, "explained", ...explained.map((c) => c.key)) });
  if (sharedFiles.length) cards.push({ kind: "outside", title: "Changes outside the paper folder", rows: sharedFiles, notes, key: cardKey(paperId, "outside", ...sharedFiles.map((f) => f.path + f.added + f.deleted)) });
  const skipped = items.filter((it) => it.verdict === "not_attempted");
  if (skipped.length) cards.push({ kind: "skipped", title: "Not attempted", rows: skipped, key: cardKey(paperId, "skipped", ...skipped.map((it) => it.id)) });
  return cards;
}

// -------------------------------------------------------------------- files

/** GitHub's list of changed files as {path, added, deleted, status A|M|D, patch}. */
export function normalizeFiles(apiFiles) {
  return (apiFiles || []).map((f) => ({
    path: f.filename, added: f.additions || 0, deleted: f.deletions || 0,
    status: f.status === "added" ? "A" : f.status === "removed" ? "D" : "M", patch: f.patch || "",
  }));
}

/** [category, paper folder] of a changed file. */
export function classify(path, folders) {
  const parts = path.split("/");
  if (parts[0] === "site") return parts.length > 2 && folders.includes(parts[1]) ? ["generated", parts[1]] : ["shared", null];
  if (!folders.includes(parts[0]) || parts.length === 1) return ["shared", null];
  const rel = "/" + parts.slice(1).join("/"), name = parts[parts.length - 1], e = ext(path);
  if (GENERATED_PARTS.some((p) => rel.includes(p)) || name === "results.json" || name === "results_notes.json" || e === "ipynb") return ["generated", parts[0]];
  if (e === "md" || name === "LICENSE") return ["docs", parts[0]];
  if (rel.includes("/tests/") || name.startsWith("test_")) return ["tests", parts[0]];
  if (CODE_EXTS.has(e)) {
    if (PLUMBING_RE.test(name) || rel.includes("/scripts/")) return ["plumbing", parts[0]];
    return [rel.includes("/package/") ? "method" : "analysis", parts[0]];
  }
  return ["plumbing", parts[0]];
}

/** Top-level folders a change touches that may hold a paper, in the order they appear. */
export function paperCandidates(files) {
  const tops = [];
  for (const f of files) {
    const parts = f.path.split("/");
    if (parts.length < 2) continue;
    const top = parts[0] === "site" && parts.length > 2 ? parts[1] : parts[0];
    if (!top.startsWith(".") && top !== "site" && !tops.includes(top)) tops.push(top);
  }
  return tops;
}

/** Figure items grouped by figure number, each with its published picture and our renders (as paths). */
export function figureStations(folder, items, tree) {
  const published = tree.filter((p) => p.includes("/published/") && RASTER.has(ext(p)));
  const findPublished = (stemKey) => {
    for (const key of [stemKey, stemKey.replace(/[a-z]+$/, "")]) {
      for (const p of published) {
        const stem = p.split("/").pop().replace(/\.[^.]+$/, "").toLowerCase();
        const m = /^fig(?:ure)?[-_. ]?(s?\d+[a-z]*)$/.exec(stem);
        if (m && m[1] === key) return p;
      }
    }
    return null;
  };
  const stations = new Map();
  for (const it of items) {
    if (it.kind !== "figure") continue;
    const id = String(it.id ?? ""), key = figKey(id) || id;
    if (!stations.has(key)) stations.set(key, { key, title: figKey(id) ? `Fig. ${key.toUpperCase()}` : String(it.label ?? key), items: [], renders: [] });
    const st = stations.get(key);
    st.items.push(it);
    const outs = (it.outputs || []).map(String).filter((o) => RASTER.has(ext(o)) && !o.includes(".."));
    let ours = outs.filter((o) => /_ours\.[A-Za-z]+$/.test(o));
    if (!ours.length) ours = outs.filter((o) => !o.includes("overlay"));
    for (const o of ours) {
      if (st.renders.some((r) => r.oursRel === o)) continue;
      const stem = o.split("/").pop().replace(/\.[^.]+$/, "").replace(/_ours$/, "");
      const overlay = outs.find((x) => x.split("/").pop().startsWith(stem + "_overlay"));
      const m = /^fig(?:ure)?[-_. ]?(s?\d+[a-z]*)/.exec(stem.toLowerCase());
      st.renders.push({ oursRel: o, label: stem, ours: `${folder}/${o}`, overlay: overlay ? `${folder}/${overlay}` : null, published: m ? findPublished(m[1]) : null });
    }
  }
  for (const st of stations.values()) if (!st.renders.length) st.publishedOnly = findPublished(st.key);
  return [...stations.values()];
}

// ----------------------------------------------------------------- drawing

const stamp = (v) => `<span class="stamp v-${esc(v)}">${esc(VERDICT_LABEL[v] || v)}</span>`;

export function verdictBar(counts) {
  const total = VERDICTS.reduce((n, v) => n + (counts[v] || 0), 0) || 1;
  const segs = VERDICTS.filter((v) => counts[v]).map((v) => `<span class="seg v-${v}" style="flex:${counts[v]}" title="${VERDICT_LABEL[v]}: ${counts[v]}"></span>`).join("");
  const legend = VERDICTS.filter((v) => counts[v]).map((v) => `<span class="lg"><i class="dot v-${v}"></i>${counts[v]} ${VERDICT_LABEL[v].toLowerCase()}</span>`).join("");
  return `<div class="vbar" role="img" aria-label="${total} items by verdict">${segs}</div><div class="legend">${legend}</div>`;
}
function scoreBar(p) {
  if (!p) return "";
  let marks = `<i class="tick pass" style="left:${(p.t * 100).toFixed(1)}%" title="Pass mark ${(p.t * 100).toFixed(0)}%"></i>`;
  if (p.control) marks += `<i class="tick ctl" style="left:${(p.control.score * 100).toFixed(1)}%" title="Best control (${esc(p.control.name)}): ${(p.control.score * 100).toFixed(0)}%"></i>`;
  return `<span class="score" title="Share of the curve within ${p.tol} px"><span class="track"><i class="fill" style="width:${(p.s * 100).toFixed(1)}%"></i>${marks}</span><b>${(p.s * 100).toFixed(0)}%</b></span>`;
}
function seriesSvg(points) {
  const xs = points.map((p) => p[0]), ys = points.flatMap((p) => [p[1], p[2]]);
  let lo = Math.min(...ys), hi = Math.max(...ys);
  const pad = (hi - lo) * 0.08 || Math.abs(hi) * 0.05 || 1;
  lo -= pad; hi += pad;
  const x0 = Math.min(...xs), x1 = Math.max(...xs), W = 300, H = 112, L = 40, R = 8, T = 8, B = 18;
  const px = (x) => L + ((x - x0) / (x1 - x0 || 1)) * (W - L - R);
  const py = (y) => T + ((hi - y) / (hi - lo || 1)) * (H - T - B);
  const line = (i, cls) => `<g class="${cls}"><polyline points="${points.map((p) => `${px(p[0]).toFixed(1)},${py(p[i]).toFixed(1)}`).join(" ")}"/>${points.map((p) => `<circle cx="${px(p[0]).toFixed(1)}" cy="${py(p[i]).toFixed(1)}" r="1.8"/>`).join("")}</g>`;
  return `<svg viewBox="0 0 ${W} ${H}" class="series" role="img"><line class="ax" x1="${L}" y1="${H - B}" x2="${W - R}" y2="${H - B}"/>` +
    `<text class="tk" x="${L - 4}" y="${(py(hi - pad) + 3).toFixed(1)}" text-anchor="end">${fmtG(hi - pad, 3)}</text>` +
    `<text class="tk" x="${L - 4}" y="${(py(lo + pad) + 3).toFixed(1)}" text-anchor="end">${fmtG(lo + pad, 3)}</text>` +
    `<text class="tk" x="${L}" y="${H - 5}">${x0}</text><text class="tk" x="${W - R}" y="${H - 5}" text-anchor="end">${x1}</text>` +
    `${line(1, "s-paper")}${line(2, "s-ours")}</svg>`;
}
/** How to draw a list of fields: as series, as the paper's table, or as a list. */
export function shapeFields(fs) {
  const series = new Map();
  for (const f of fs) {
    if (f.a === null || f.b === null) continue;
    const m = /^(.*?\D)\s*(-?\d+(?:\.\d+)?)$/.exec(f.name);
    if (!m) continue;
    const k = m[1].trim();
    if (!series.has(k)) series.set(k, []);
    series.get(k).push([Number(m[2]), f.a, f.b]);
  }
  const good = new Map();
  for (const [k, v] of series) {
    if (v.length >= 4 && new Set(v.map((p) => p[0])).size === v.length) good.set(k, v.sort((a, b) => a[0] - b[0]));
  }
  if (good.size && [...good.values()].reduce((n, v) => n + v.length, 0) >= 0.8 * fs.length) return ["series", good];
  const rows = [], cols = [], cells = new Map();
  let ok = true;
  for (const f of fs) {
    const i = f.name.lastIndexOf(" ");
    if (i < 0) { ok = false; break; }
    const r = f.name.slice(0, i).replace(/[,:]+$/, ""), c = f.name.slice(i + 1);
    if (!rows.includes(r)) rows.push(r);
    if (!cols.includes(c)) cols.push(c);
    cells.set(r + "\x1f" + c, f);
  }
  if (ok && cols.length >= 2 && cols.length <= 8 && rows.length >= 2 && cells.size >= 0.6 * rows.length * cols.length) {
    if (cols.every((c) => rows.filter((r) => cells.has(r + "\x1f" + c)).length >= 2)) return ["matrix", { rows, cols, cells }];
  }
  return ["list", fs];
}
function cellHtml(f) {
  if (!f) return '<td class="na"></td>';
  const cls = f.error ? "err" : f.match ? "ok" : "off";
  const title = f.error ? ` title="${esc(f.error.evidence)}"` : "";
  return `<td class="${cls}"${title}><span class="p">${esc(f.exp)}</span><span class="o">${esc(f.obs)}</span>${f.error ? '<i class="flag">paper error</i>' : ""}</td>`;
}
function fieldsHtml(item) {
  const fs = fieldsOf(item);
  if (!fs.length) return "";
  const [kind, data] = shapeFields(fs);
  if (kind === "series") {
    const charts = [...data].map(([name, pts]) => `<figure class="chart"><figcaption>${esc(name)}</figcaption>${seriesSvg(pts)}</figure>`).join("");
    return `<div class="charts">${charts}</div><div class="key"><span class="k-paper">paper</span><span class="k-ours">ours</span></div>`;
  }
  if (kind === "matrix") {
    const { rows, cols, cells } = data;
    const body = rows.map((r) => `<tr><th scope="row">${esc(r)}</th>${cols.map((c) => cellHtml(cells.get(r + "\x1f" + c))).join("")}</tr>`).join("");
    return `<div class="scroll"><table class="matrix"><thead><tr><th></th>${cols.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${body}</tbody></table></div>` +
      '<div class="key cells"><span>upper: paper</span><span class="o">lower: ours</span></div>';
  }
  return `<div class="scroll"><table class="matrix list"><tbody>${fs.map((f) => `<tr><th scope="row">${esc(f.name)}</th>${cellHtml(f)}</tr>`).join("")}</tbody></table></div>`;
}
function shortLabel(item) {
  let label = String(item.label ?? item.id ?? "");
  const t = token(item);
  if (label.startsWith(t)) label = label.slice(t.length).replace(/^[ ,:]+/, "") || label;
  return label.charAt(0).toUpperCase() + label.slice(1);
}
function itemRow(item, cardOf) {
  const why = cardOf.has(item.id) ? `<a class="why" href="#d-${cardOf.get(item.id)}">why</a>` : "";
  const changed = item._changed ? '<span class="chip new">changed here</span>' : "";
  const p = pixelScore(item);
  const detail = item.method === "check" ? `<p class="detail">${esc((item.check || {}).detail)}</p>` : "";
  let body = fieldsHtml(item);
  if (body) body = `<details class="ibody"${item.verdict === "exact" || item.verdict === "agrees" ? "" : " open"}><summary>Numbers</summary>${body}</details>`;
  return `<div class="irow" id="i-${esc(item.id)}"><div class="ihead">${stamp(item.verdict)}<span class="ilabel">${esc(shortLabel(item))}</span>${changed}` +
    `${scoreBar(p)}<span class="meas">${p ? "" : esc(measureOf(item))}</span>${why}</div>${detail}${body}</div>`;
}
const imgTag = (ctx, path, alt) => `<img src="${esc(ctx.img(path))}" data-path="${esc(path)}" alt="${esc(alt)}" loading="lazy">`;
function viewerHtml(ctx, render, title) {
  const modes = render.published ? [["side", "Side by side"], ["swipe", "Swipe"], ["blink", "Blink"]] : [["ours", "Ours"]];
  if (render.overlay) modes.push(["overlay", "Overlay"]);
  const buttons = modes.map(([m, label], i) => `<button type="button" data-m="${m}"${i === 0 ? ' aria-pressed="true"' : ""}>${label}</button>`).join("");
  let layers = "";
  if (render.published) layers += `<figure class="pub">${imgTag(ctx, render.published, title + ", published")}<figcaption>Published</figcaption></figure>`;
  layers += `<figure class="ours">${imgTag(ctx, render.ours, title + ", ours")}<figcaption>Ours</figcaption></figure>`;
  if (render.overlay) layers += `<figure class="ovl">${imgTag(ctx, render.overlay, title + ", overlay")}<figcaption>Overlay</figcaption></figure>`;
  const slider = render.published ? '<input type="range" class="swipe" min="0" max="100" value="50" aria-label="Swipe between published and ours">' : "";
  return `<div class="viewer" data-mode="${modes[0][0]}"><div class="modes" role="group" aria-label="View">${buttons}</div><div class="stage">${layers}${slider}</div></div>`;
}
function stationHtml(ctx, st, cardOf) {
  const counts = {};
  for (const it of st.items) counts[it.verdict] = (counts[it.verdict] || 0) + 1;
  const dots = VERDICTS.filter((v) => counts[v]).map((v) => `<i class="dot v-${v}" title="${counts[v]} ${VERDICT_LABEL[v].toLowerCase()}"></i>`.repeat(counts[v])).join("");
  let views = st.renders.map((r) => (st.renders.length > 1 ? `<p class="rlabel">${esc(r.label)}</p>` : "") + viewerHtml(ctx, r, st.title)).join("");
  if (!views && st.publishedOnly) views = `<div class="viewer solo"><div class="stage solo"><figure class="pub">${imgTag(ctx, st.publishedOnly, st.title + ", published")}<figcaption>Published; no render of ours</figcaption></figure></div></div>`;
  return `<section class="station" id="fig-${esc(st.key)}"><header class="shead"><h3>${esc(st.title)}</h3><span class="dots">${dots}</span></header>` +
    `<div class="sgrid">${views ? `<div class="views">${views}</div>` : ""}<div class="rows">${st.items.map((it) => itemRow(it, cardOf)).join("")}</div></div></section>`;
}
const stripPath = (evidence) => String(evidence ?? "").replace(/^\S+\.\w+(?: \([^)]*\))?:\s+/, "");
function evidenceHtml(ctx, folder, evidence) {
  return evidence.map((raw) => {
    const ev = String(raw);
    if (/^https?:\/\/\S+$/.test(ev)) return `<li><a href="${esc(ev)}" rel="noopener">${esc(ev)}</a></li>`;
    const path = ev.split(" ")[0].replace(/[:,]+$/, "");
    if (path.includes("/") && !path.includes("..")) return `<li><a href="${esc(ctx.blob(folder + "/" + path))}" rel="noopener">${esc(ev)}</a></li>`;
    return `<li>${esc(ev)}</li>`;
  }).join("");
}
const DECIDE = '<footer class="decide"><button type="button" data-d="ok">Accept</button><button type="button" data-d="work">Needs work</button>' +
  '<textarea rows="1" placeholder="Note for the author" aria-label="Note for the author"></textarea></footer>';
function numRows(nums) {
  if (!nums.length) return "";
  return '<div class="nums"><div class="num head"><span class="n"></span><span class="p">paper</span><span class="o">ours</span></div>' +
    nums.map((f) => `<div class="num"><span class="n">${esc(f.name)}</span><span class="p">${esc(f.exp)}</span><span class="o">${esc(f.obs)}</span></div>`).join("") + "</div>";
}
const memberChips = (members) => members.map((m) => `<a class="chip m v-${esc(m.verdict)}" href="#i-${esc(m.id)}">${esc(m.label ?? m.id)}</a>`).join("");
export const fileAnchor = (path) => cardKey("file", path).slice(0, 10);
const delta = (f) => `<span class="delta"><b class="add">+${f.added}</b>${f.deleted ? ` <b class="del">−${f.deleted}</b>` : ""}</span>`;

function cardHtml(ctx, folder, card) {
  const k = card.kind;
  let head = "", body = "";
  if (k === "cause") {
    const [lead, rest] = firstSentence(card.summary);
    const extra = card.more.map(([lbl, s]) => `<p><b>${esc(lbl)}:</b> ${esc(s)}</p>`).join("");
    const more = rest || extra ? `<details class="more"><summary>More</summary>${rest ? `<p>${esc(rest)}</p>` : ""}${extra}</details>` : "";
    let hyps = "";
    if (card.hyps.length) {
      const ruled = card.hyps.filter((h) => h.result === "rejected").length;
      const label = ruled ? `${ruled} of ${card.hyps.length} tested causes ruled out` : `${card.hyps.length} tested causes`;
      hyps = `<details class="hyps"><summary>${label}</summary><ul>${card.hyps.map((h) => `<li class="h-${esc(h.result)}"><span class="hres">${esc(h.result)}</span><span class="hyp">${esc(h.hypothesis)}</span><span class="test">${esc(h.test)}</span></li>`).join("")}</ul></details>`;
    }
    const ev = card.evidence.length ? `<details class="hyps"><summary>Evidence</summary><ul class="ev">${evidenceHtml(ctx, folder, card.evidence)}</ul></details>` : "";
    head = stamp(card.verdict) + `<span class="chip cat">${esc(CATEGORY_LABEL[card.category] || card.category)}</span>`;
    body = `<p class="lead">${esc(lead)}</p>${more}${numRows(card.nums)}${hyps}${ev}<div class="members">${memberChips(card.members)}</div>`;
  } else {
    let rows = "";
    if (k === "choices") {
      rows = card.rows.map((r) => `<li><span class="what">${esc(r.what)}</span><span class="sens">${esc(r.sensitivity)}</span><span class="tags"><i class="chip cat">${SOURCE_LABEL[r.source]}</i>${r.where.slice(0, 6).map((w) => `<i class="chip">${esc(w)}</i>`).join("")}</span></li>`).join("");
    } else if (k === "errors") {
      const by = new Map();
      for (const r of card.rows) by.set(r.where, [...(by.get(r.where) || []), r]);
      rows = [...by].map(([where, rs]) => `<li><span class="what"><b>${esc(where)}</b> ${rs.map((r) => `<i class="chip">${esc(r.field)}</i> `).join("")}</span>` +
        `<details class="hyps"><summary>How we know</summary><ul class="ev">${rs.map((r) => `<li>${esc(stripPath(r.evidence))}</li>`).join("")}</ul></details></li>`).join("");
    } else if (k === "explained") {
      rows = card.rows.map((c) => `<li>${stamp(c.verdict)}<span class="what"><b>${esc(c.title)}</b> ${esc(firstSentence(c.summary)[0])}</span>` +
        `<span class="tags"><i class="chip cat">${esc(CATEGORY_LABEL[c.category] || c.category)}</i></span><span class="members">${memberChips(c.members)}</span></li>`).join("");
    } else if (k === "outside") {
      rows = card.rows.map((f) => `<li><a class="path" href="#f-${fileAnchor(f.path)}">${esc(f.path)}</a>${delta(f)}</li>`).join("");
    } else if (k === "skipped") {
      rows = card.rows.map((it) => `<li><span class="what"><b>${esc(it.label ?? it.id)}</b> ${esc(firstSentence((it.cause || {}).summary)[0])}</span></li>`).join("");
    }
    const notes = (card.notes || []).map((n) => `<p class="warn">${esc(n)}</p>`).join("");
    head = `<span class="count">${card.rows.length}</span>`;
    body = `${notes}<ul class="rows-list${k === "outside" ? " files" : ""}">${rows}</ul>`;
  }
  const status = card.status === "open" ? '<span class="chip open">open</span>' : "";
  return `<article class="card k-${k}" id="d-${card.key}" data-key="${card.key}" data-title="${esc(card.title)}" tabindex="-1">` +
    `<header class="chead"><h3>${esc(card.title)}</h3>${head}${status}<span class="state" aria-live="polite"></span></header>${body}${DECIDE}</article>`;
}

/** A GitHub patch (the hunks of one file) as lines with their numbers. */
export function diffHtml(patch) {
  const out = [];
  let oldN = 0, newN = 0, started = false, n = 0;
  for (const ln of String(patch).split("\n")) {
    if (ln.startsWith("@@")) {
      const m = /^@@ -(\d+)(?:,\d+)? \+(\d+)/.exec(ln);
      if (m) { oldN = Number(m[1]); newN = Number(m[2]); }
      started = true;
      out.push(`<span class="l hunk">${esc(ln)}</span>`);
      continue;
    }
    if (!started || ln.startsWith("\\")) continue;
    if (++n > MAX_LINES) break;
    if (ln.startsWith("+")) out.push(`<span class="l add" data-n="${newN++}">${esc(ln.slice(1))}</span>`);
    else if (ln.startsWith("-")) out.push(`<span class="l del" data-n="${oldN++}">${esc(ln.slice(1))}</span>`);
    else { out.push(`<span class="l" data-n="${newN++}">${esc(ln.slice(1))}</span>`); oldN++; }
  }
  return `<pre class="code diff">${out.join("")}</pre>`;
}
/** Highlighted HTML cut into lines; a span that runs over a line end is closed and opened again. */
export function splitHighlighted(html) {
  const lines = [], open = [];
  let cur = "";
  const re = /<span[^>]*>|<\/span>|\n|[^<\n]+|</g;
  for (const m of html.matchAll(re)) {
    const tok = m[0];
    if (tok === "\n") {
      lines.push(cur + "</span>".repeat(open.length));
      cur = open.join("");
    } else {
      if (tok.startsWith("<span")) open.push(tok);
      else if (tok === "</span>") open.pop();
      cur += tok;
    }
  }
  if (cur !== open.join("")) lines.push(cur + "</span>".repeat(open.length));
  return lines;
}
/** A whole file as numbered lines; lineHtml holds one HTML string per line. */
export function wholeFileHtml(lineHtml) {
  const cut = lineHtml.length > MAX_LINES;
  return `<pre class="code">${lineHtml.slice(0, MAX_LINES).map((ln) => `<span class="l">${ln}</span>`).join("")}</pre>` +
    (cut ? `<p class="cut">First ${MAX_LINES} of ${lineHtml.length} lines.</p>` : "");
}
const HL_LANG = {
  py: "python", r: "r", rmd: "r", sh: "bash", sbatch: "bash", nf: "groovy", config: "groovy", js: "javascript", ts: "typescript",
  json: "json", yml: "yaml", yaml: "yaml", md: "markdown", c: "c", h: "c", cc: "cpp", cpp: "cpp", hpp: "cpp", rs: "rust",
  toml: "ini", cfg: "ini", html: "xml", css: "css", pl: "perl", java: "java", go: "go", smk: "python",
};
export const languageOf = (path) => HL_LANG[ext(path)] || null;

function fileHtml(ctx, f, opened) {
  let body;
  if (f.status === "D") body = '<p class="cut">Deleted.</p>';
  else if (f.status === "M") body = f.patch ? diffHtml(f.patch) : '<p class="cut">Too large to show here, or binary. Open it on GitHub.</p>';
  else body = '<p class="cut lazy">Loading…</p>';
  const tag = { A: "new", D: "deleted" }[f.status] || "changed";
  return `<details class="file" id="f-${fileAnchor(f.path)}" data-path="${esc(f.path)}" data-status="${f.status}"${opened ? " open" : ""}>` +
    `<summary><span class="path">${esc(f.rel)}</span><span class="chip">${tag}</span>${delta(f)}<a class="gh" href="${esc(ctx.blob(f.path))}" rel="noopener">GitHub</a></summary>${body}</details>`;
}
function codeHtml(ctx, files, folders) {
  const by = Object.fromEntries(GROUPS.map((g) => [g[0], []]));
  for (const f of files) {
    const [cat, folder] = classify(f.path, folders);
    f.cat = cat;
    f.rel = folder && f.path.startsWith(folder + "/") ? f.path.slice(folder.length + 1) : f.path;
    by[cat].push(f);
  }
  const lines = (fs) => fs.reduce((n, f) => n + f.added + f.deleted, 0);
  const total = lines(files) || 1;
  let segs = "", legend = "";
  for (const [cat, title] of GROUPS) {
    if (!by[cat].length) continue;
    const n = lines(by[cat]);
    segs += `<span class="seg c-${cat}" style="flex:${Math.max(n, total * 0.004).toFixed(0)}" title="${title}: ${fmtInt(n)} lines"></span>`;
    legend += `<span class="lg"><i class="dot c-${cat}"></i>${title} <b>${fmtInt(n)}</b> lines, ${by[cat].length} files</span>`;
  }
  const out = [`<div class="vbar sizebar" role="img" aria-label="Changed lines by kind">${segs}</div><div class="legend">${legend}</div>`];
  let first = true;
  for (const [cat, title, shown] of GROUPS) {
    const fs = by[cat];
    if (!fs.length) continue;
    const n = lines(fs);
    if (shown) {
      if (cat !== "shared") fs.sort((a, b) => b.added + b.deleted - (a.added + a.deleted));
      out.push(`<h3 class="ghead">${title} <span class="count">${fs.length} files, ${fmtInt(n)} lines</span></h3>` + fs.map((f, i) => fileHtml(ctx, f, first && i === 0 && cat !== "shared")).join(""));
      first = false;
    } else if (cat === "generated") {
      out.push(`<h3 class="ghead">${title} <span class="count">${fs.length} files, ${fmtInt(n)} lines, not shown</span></h3>`);
    } else {
      out.push(`<details class="group"><summary><h3 class="ghead">${title} <span class="count">${fs.length} files, ${fmtInt(n)} lines, on GitHub</span></h3></summary>` +
        `<ul class="rows-list files">${fs.map((f) => `<li><a class="path" href="${esc(ctx.blob(f.path))}" rel="noopener">${esc(f.rel)}</a>${delta(f)}</li>`).join("")}</ul></details>`);
    }
  }
  return [out.join(""), by];
}

function paperHtml(ctx, paper, shared, notes, idx) {
  const { folder, results, baseResults, tree } = paper;
  const items = results.items.filter((it) => it && typeof it === "object" && it.id !== undefined && it.id !== null);
  if (baseResults) {
    const old = new Map((baseResults.items || []).map((it) => [it && it.id, JSON.stringify(it)]));
    for (const it of items) it._changed = old.get(it.id) !== JSON.stringify(it);
  }
  const meta = results.paper || {}, pid = String(meta.id || folder);
  const counts = Object.fromEntries(VERDICTS.map((v) => [v, items.filter((it) => it.verdict === v).length]));
  const cards = decisionCards(pid, items, idx === 0 ? shared : [], idx === 0 ? notes : []);
  const cardOf = new Map();
  for (const c of cards) {
    if (c.kind === "cause") for (const m of c.members) cardOf.set(m.id, c.key);
    else if (c.kind === "explained") for (const sub of c.rows) for (const m of sub.members) cardOf.set(m.id, c.key);
    else if (c.kind === "skipped") for (const m of c.rows) cardOf.set(m.id, c.key);
  }
  const stations = figureStations(folder, items, tree);
  const others = items.filter((it) => it.kind !== "figure");
  const kinds = [["table", "Tables"], ["value", "Numbers in the text"], ["code_check", "Checks"]];
  let numbers = "";
  for (const [kind, title] of kinds) {
    const its = others.filter((it) => it.kind === kind);
    if (its.length) numbers += `<h3 class="ghead">${title} <span class="count">${its.length}</span></h3>` + its.map((it) => `<div class="nblock">${kind === "table" ? `<h4>${esc(token(it))}</h4>` : ""}${itemRow(it, cardOf)}</div>`).join("");
  }
  const rest = others.filter((it) => !kinds.some(([k]) => k === it.kind));
  if (rest.length) numbers += '<h3 class="ghead">Other</h3>' + rest.map((it) => itemRow(it, cardOf)).join("");
  const doi = String(meta.doi || "");
  let cite = esc(meta.citation || "");
  if (/^10\.\d{4,9}\/\S+$/.test(doi)) cite = `<a href="https://doi.org/${esc(doi)}" rel="noopener">${cite || esc(doi)}</a>`;
  const nOpen = cards.filter((c) => c.status === "open").length;
  const changed = items.filter((it) => it._changed).length;
  const changedNote = baseResults && changed ? `<p class="note">This change touches ${changed} of ${items.length} items; they are marked <span class="chip new">changed here</span>.</p>` : "";
  const nav = `<nav class="tabs" aria-label="Sections"><a href="#decisions-${idx}">Decisions <b>${cards.length}</b></a><a href="#figures-${idx}">Figures <b>${stations.length}</b></a>` +
    `<a href="#numbers-${idx}">Tables and numbers <b>${others.length}</b></a><a href="#code">Code</a></nav>`;
  const html = `<section class="paper" data-paper="${esc(pid)}"><div class="phead"><p class="pid"><span class="pmc">${esc(pid)}</span> ${cite}</p>` +
    `<h1>${esc(meta.title || folder)}</h1>${verdictBar(counts)}${changedNote}${nav}</div>` +
    `<section id="decisions-${idx}" class="sec"><h2>Decisions <span class="count">${nOpen} open</span></h2><div class="cards">${cards.map((c) => cardHtml(ctx, folder, c)).join("")}</div></section>` +
    `<section id="figures-${idx}" class="sec"><h2>Figures</h2>${stations.map((s) => stationHtml(ctx, s, cardOf)).join("") || '<p class="note">No figure items.</p>'}</section>` +
    `<section id="numbers-${idx}" class="sec"><h2>Tables and numbers</h2>${numbers || '<p class="note">No table or number items.</p>'}</section></section>`;
  return [html, { id: pid, title: String(meta.title || folder), counts, cards: cards.map((c) => c.key), open: nOpen }];
}

/**
 * The page of one pull request or branch.
 * review: {repo, label, title, url, number, branch, author, updated, draft, sha, notes, files, papers}
 * ctx: {img(path), blob(path)} give the addresses of a picture and of a file on GitHub.
 */
export function reviewHtml(review, ctx) {
  const folders = review.papers.map((p) => p.folder);
  for (const f of review.files) f.cat = classify(f.path, folders)[0];
  const shared = review.files.filter((f) => f.cat === "shared");
  const sections = [], summaries = [];
  review.papers.forEach((paper, idx) => {
    const [html, summary] = paperHtml(ctx, paper, shared, review.notes || [], idx);
    sections.push(html);
    summaries.push(summary);
  });
  if (!review.papers.length) {
    const card = { kind: "outside", title: "Changed files", rows: shared, notes: review.notes || [], key: cardKey(review.repo, review.label, "files", ...review.files.map((f) => f.path)) };
    sections.push(`<section class="paper"><div class="phead"><h1>${esc(review.title || review.label)}</h1>` +
      '<p class="note">No Paper2Repro results.json in this change, so there is no paper to lay it out by.</p></div>' +
      `<section class="sec"><h2>Decisions</h2><div class="cards">${cardHtml(ctx, "", card)}</div></section></section>`);
    summaries.push({ id: "", title: review.title || review.label, counts: {}, cards: [card.key], open: 0 });
  }
  const [code, by] = codeHtml(ctx, review.files, folders);
  const bits = [];
  if (review.number) bits.push(`<a href="${esc(review.url)}" rel="noopener">#${review.number}</a>`);
  if (review.branch) bits.push(`<span class="mono">${esc(review.branch)}</span>`);
  bits.push(`<span class="mono">${esc(review.sha.slice(0, 7))}</span>`);
  if (review.author) bits.push(esc(review.author));
  if (review.updated) bits.push(esc(review.updated.slice(0, 10)));
  const chips = (review.draft ? '<span class="chip">draft</span>' : "") + '<span class="ci"></span>';
  const html = `<header class="top"><div class="wrap"><a class="back" href="./">All reviews</a><span class="refline">${esc(review.repo)} · ${bits.join(" · ")} ${chips}</span></div></header>` +
    `<main class="wrap">${sections.join("")}<section id="code" class="sec"><h2>Code</h2>${code}</section></main>` +
    '<div class="bar"><div class="wrap"><span class="progress"><b class="done">0</b> of <b class="all">0</b> decided</span><span class="grow"></span>' +
    `<button type="button" class="copy">Copy review</button><a class="btn" href="${esc(review.url)}" rel="noopener">Open on GitHub</a></div></div>`;
  const lines = Object.fromEntries(Object.entries(by).map(([cat, fs]) => [cat, fs.reduce((n, f) => n + f.added + f.deleted, 0)]));
  return { html, summary: { papers: summaries, files: review.files.length, lines, sha: review.sha } };
}

/** The first page: a box to paste a link into, and what is open in the usual repository. */
export function homeHtml({ repo, pulls, recent, error }) {
  const cards = (pulls || []).map((p) => {
    const link = { owner: repo.split("/")[0], repo: repo.split("/")[1], kind: "pull", number: p.number };
    const who = [p.user && p.user.login, (p.updated_at || "").slice(0, 10)].filter(Boolean).join(" · ");
    return `<a class="rcard" href="${routeOf(link)}" data-number="${p.number}" data-sha="${esc(p.head && p.head.sha)}" data-title="${esc(p.title)}" data-ref="${esc(p.head && p.head.ref)}">` +
      `<div class="rtop"><span class="pmc"></span><span class="rref">#${p.number}</span></div><h2>${esc(p.title)}</h2><div class="rbar"></div>` +
      `<p class="facts"><span class="progress"></span></p><p class="who">${esc(who)} ${p.draft ? '<span class="chip">draft</span>' : ""}</p></a>`;
  }).join("");
  const recents = (recent || []).map((r) => `<li><a href="${esc(r.route)}">${esc(r.label)}</a></li>`).join("");
  return '<header class="top"><div class="wrap"><span class="refline">Reproduction review</span><span class="grow"></span><button type="button" class="linkish token">GitHub token</button></div></header>' +
    '<main class="wrap"><div class="phead"><h1>Paste a pull request or branch link</h1>' +
    '<form class="paste"><input type="text" name="link" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="https://github.com/owner/repo/pull/40" aria-label="Pull request or branch link"><button type="submit">Review</button></form>' +
    `<p class="note paste-error" role="alert">${esc(error || "")}</p></div>` +
    (repo ? `<section class="sec"><h2>Open in ${esc(repo)} <span class="count">${pulls ? pulls.length : ""}</span></h2><div class="rgrid">${cards || `<p class="note home-note">${pulls ? "Nothing is open." : "Loading…"}</p>`}</div></section>` : "") +
    (recents ? `<section class="sec"><h2>Recent</h2><ul class="recent">${recents}</ul></section>` : "") + "</main>";
}
