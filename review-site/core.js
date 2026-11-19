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

/** What an item is about, without where it is: "Fig. 2a, ROC curves of scheme I" gives "ROC curves of scheme I". */
function partOf(item) {
  const label = String(item.label ?? ""), t = token(item);
  // after "Fig. 2" comes the panel letter, when there is one: "a, ROC curves"
  const rest = (label.startsWith(t) ? label.slice(t.length).replace(/^[A-Za-z]?(?=[,:\s]|$)/, "") : label).replace(/^[\s,:]+/, "");
  return rest || String(item.id ?? "");
}

const sameAs = (v) => (v === "exact" ? "agrees" : v);

const SUPP_ID_RE = new RegExp("^(?:" + [
  "(?:fig(?:ure)?|tab(?:le)?)[-_. ]?s[-_. ]?\\d", // figS1, table_s2
  "s[-_. ]?(?:fig(?:ure)?|tab(?:le)?)[-_. ]?\\d", // sfig1, s.table2
  "s\\d+[-_. ]?(?:fig|tab|file|text|data)", // s1_fig
  "supp(?:l(?:ement(?:ary|al)?)?)?(?:[-_. ]|fig|tab|file|data|\\d|$)", // supp.fig1, supplementary_table_2
  "additional[-_. ]?(?:file|fig|tab|data|\\d)",
  "ext(?:ended)?[-_. ]?(?:data[-_. ]?)?(?:fig|tab|\\d)", "ed[-_. ]?(?:fig|tab)", "appendix",
].join("|") + ")", "i");
const SUPP_LABEL_RE = new RegExp("^(?:" + [
  "supp(?:l(?:ement(?:ary|al)?)?)?\\b", // Supplementary Fig. 1, Supp. Table 2
  "additional\\s+(?:file|fig|table|data)", "extended\\s+data", "appendix\\b",
  "(?:fig(?:ure|s)?|tab(?:le)?)\\.?\\s*s\\s?\\d", // Fig. S1, Table S2
  "s\\d+\\s+(?:fig|table|file|text|data|appendix)", // S1 Fig, as PLOS names it
  "fig(?:ure)?\\.?\\s*\\d+\\w*\\s*[\u2014\u2013-]\\s*figure supplement", // Figure 3—figure supplement 1
].join("|") + ")", "i");
/**
 * Whether a result is of the paper's supplement, by its id or by how its label starts: figS1,
 * supp.table2, "Fig. S3", "Supplementary Table 2", "Additional file 4", "S1 Fig". A main figure
 * that draws data of the supplement ("Fig. 9b, PDR histogram of Additional File 4") is not.
 */
export const isSupplementary = (item) => SUPP_ID_RE.test(String(item.id ?? "")) || SUPP_LABEL_RE.test(String(item.label ?? "").trim());
/**
 * Whether the review asks about a result. It asks about the paper's main figures and tables.
 * Supplementary results, numbers in the text and checks stay in results.json and are listed
 * below the tables, with no decision.
 */
export const inReview = (item) => (item.kind === "figure" || item.kind === "table") && !isSupplementary(item);
const listed = (results) => (results.items || []).filter((it) => it && typeof it === "object" && it.id !== undefined && it.id !== null);

/**
 * What the reviewer is asked about one figure or one table, right below it. items are the
 * results it holds (the curves of a figure, or the one table). The answer is a verdict of the
 * reviewer's own (Agrees, Partly, Differs), or OK / Not OK where there is no result to judge.
 */
export function unitOf(paperId, id, title, items) {
  const judged = items.filter((it) => it.verdict !== "not_attempted" && it.kind !== "code_check");
  const ask = judged.length ? "verdict" : "ok";
  const kinds = [...new Set(judged.map((it) => sameAs(it.verdict)))];
  const given = ask !== "verdict" ? "" : kinds.length === 1 ? kinds[0] : "mixed";
  let givenText = "";
  if (ask === "verdict") {
    const all = items.map((it) => it.verdict);
    givenText = new Set(all).size === 1 ? VERDICT_LABEL[all[0]] || String(all[0])
      : VERDICTS.filter((v) => all.includes(v)).map((v) => `${all.filter((x) => x === v).length} ${VERDICT_LABEL[v].toLowerCase()}`).join(", ");
  }
  const sign = items.map((it) => [it.id, it.verdict, squash((it.cause || {}).summary), (it.cause || {}).status ?? ""].join("|"));
  return { key: cardKey(paperId, "unit", id, ...sign), title, ask, given, givenText, items };
}

// --------------------------------------------------------- the reviewer's side

/** What a reviewer can say in one decision, as the page names it. */
export const SAID_LABEL = { ...VERDICT_LABEL, ok: "OK", no: "Not OK", pr: "as the pull request says" };

/**
 * How what the reviewer said (v) stands against the pull request: "" (nothing said), "same",
 * "change", or "unknown" for a verdict kept by an older version of the page, which did not keep
 * what the pull request said.
 */
export function standOf(unit, v) {
  if (!v) return "";
  if (v === "pr" || v === "ok") return "same";
  if (v === "no") return "change";
  if (unit.given === undefined) return "unknown";
  return v === unit.given ? "same" : "change";
}

/**
 * What a review says to GitHub, from the decisions: REQUEST_CHANGES when one of them is to change,
 * APPROVE when all are decided and stand as the pull request says, and COMMENT while something is
 * not decided (or was decided in an older version of the page, which did not keep what the pull
 * request said). An approval says that the pull request's verdicts are right, also where a verdict
 * is Differs: it does not say that the paper came back.
 */
export function reviewEvent(units, said) {
  let open = 0;
  for (const u of units) {
    const how = standOf(u, said(u.key).v);
    if (how === "change") return "REQUEST_CHANGES";
    if (how !== "same") open++;
  }
  return open || !units.length ? "COMMENT" : "APPROVE";
}
/** The button that sends a review with each event, and what the review then does, after "Your review is on #7 and". */
export const EVENT_LABEL = { APPROVE: "Approve", REQUEST_CHANGES: "Request changes", COMMENT: "Comment" };
export const EVENT_DOES = { APPROVE: "approves it", REQUEST_CHANGES: "requests changes", COMMENT: "is a comment" };

/** Who GitHub says is asked to review a pull request: the logins of its requested reviewers, then its teams. */
export const reviewersOf = (p) => [...((p && p.requested_reviewers) || []).map((u) => u && u.login), ...((p && p.requested_teams) || []).map((t) => t && (t.name || t.slug))]
  .filter(Boolean).map(String);
const sameLogin = (a, b) => !!a && !!b && String(a).toLowerCase() === String(b).toLowerCase();
/** "Review asked of you and alice": the names as GitHub gives them, the reader first and as "you". Empty when nobody is asked. */
export function askedText(names, me = "") {
  const mine = names.some((n) => sameLogin(n, me)), rest = names.filter((n) => !sameLogin(n, me));
  const all = [...(mine ? ["you"] : []), ...rest];
  if (!all.length) return "";
  return `Review asked of ${all.length > 1 ? `${all.slice(0, -1).join(", ")} and ${all.at(-1)}` : all[0]}`;
}

/** What the browser keeps of a unit, to say later where its pull request stands. */
export const slimUnit = (u) => ({ key: u.key, title: u.title, ask: u.ask, given: u.given, givenText: u.givenText, pics: u.pics || "" });

/**
 * Where a pull request stands for this reviewer, from what the browser kept of it.
 * sum is {sha, keys, units} as kept when its review was last opened (null: never), said(key)
 * gives {v, note}, and sha is the head of the pull request now. state is one of:
 *   new       not opened               seen      opened, nothing decided
 *   started   some decided             updated   it changed after the reviewer decided
 *   changes   all decided, some to change        agreed   all decided, as the pull request says
 *   reviewed  all decided, kept by an older version: not known whether something is to change
 */
export function standing(sum, said, sha) {
  const units = !sum ? [] : sum.units || (sum.keys || []).map((key) => ({ key }));
  const out = { state: "new", done: 0, all: units.length, change: [], unknown: 0 };
  if (!units.length) return out;
  for (const u of units) {
    const how = standOf(u, said(u.key).v);
    if (!how) continue;
    out.done++;
    if (how === "change") out.change.push(u.title || "");
    if (how === "unknown") out.unknown++;
  }
  out.state = !out.done ? "seen" : sha && sum.sha !== sha ? "updated" : out.done < out.all ? "started"
    : out.change.length ? "changes" : out.unknown ? "reviewed" : "agreed";
  return out;
}

/** A name for a set of decisions as they are now: it changes when a verdict or a comment does. */
export function reviewSig(keys, said) {
  return cardKey(...keys.map((k) => { const s = said(k); return `${k}|${s.v || ""}|${String(s.note || "").trim()}`; }));
}

// -------------------------------------------------------------------- files

/** GitHub's list of changed files as {path, added, deleted, status A|M|D, patch}. */
export function normalizeFiles(apiFiles) {
  return (apiFiles || []).map((f) => ({
    path: f.filename, added: f.additions || 0, deleted: f.deletions || 0,
    status: f.status === "added" ? "A" : f.status === "removed" ? "D" : "M", patch: f.patch || "", sha: f.sha || "",
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

/**
 * The figure a picture shows, from its file name: "1", "2a", "s3"; null when the name does not
 * say. Papers name the published pictures in several ways: figure-1.png, fig2a.jpg,
 * fig1_published.png, and as the journal does (pcbi.1000660.g001.png, elife-12345-fig2-v1.jpg).
 */
export function figureKeyOf(path) {
  const stem = String(path).split("/").pop().replace(/\.[^.]+$/, "").toLowerCase();
  const m = /^fig(?:ure)?[-_. ]?(s?)0*(\d+)([a-z]*)(?:[-_. ](?:published|ours|overlay))?$/.exec(stem) ||
    /(?:^|[-_. ])(?:fig(?:ure)?|g|f)[-_. ]?(s?)0*(\d+)([a-z]?)(?:[-_. ](?:v\d+|html|large|hires|orig(?:inal)?|published))*$/.exec(stem);
  return m ? m[1] + m[2] + m[3] : null;
}
/** Whether a path is a picture of the paper's own figure: in a published/ folder, or named fig1_published.png next to ours. */
const isPublished = (p) => RASTER.has(ext(p)) && (p.includes("/published/") || /[-_.]published\.[A-Za-z]+$/.test(p));

/** Figure items grouped by figure number, each with its published picture and our renders (as paths). */
export function figureStations(folder, items, tree) {
  // a published/ folder first: it is where the paper's own figures belong
  const published = tree.filter(isPublished).map((p) => [figureKeyOf(p), p]).filter(([k]) => k !== null)
    .sort((x, y) => Number(y[1].includes("/published/")) - Number(x[1].includes("/published/")));
  const findPublished = (stemKey) => {
    for (const key of [stemKey, stemKey.replace(/[a-z]+$/, "")]) {
      const hit = published.find(([k]) => k === key);
      if (hit) return hit[1];
    }
    return null;
  };
  // one picture of ours (a path below the paper folder), with its overlap among `outs` and the paper's own figure
  const add = (st, o, outs) => {
    if (st.renders.some((r) => r.oursRel === o)) return;
    const stem = o.split("/").pop().replace(/\.[^.]+$/, "").replace(/_ours$/, "");
    const overlay = outs.find((x) => x.split("/").pop().startsWith(stem + "_overlay"));
    const m = /^fig(?:ure)?[-_. ]?(s?)0*(\d+)([a-z]*)/.exec(stem.toLowerCase());
    st.renders.push({ oursRel: o, label: stem, ours: `${folder}/${o}`, overlay: overlay ? `${folder}/${overlay}` : null, published: m ? findPublished(m[1] + m[2] + m[3]) : null });
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
    for (const o of ours) add(st, o, outs);
  }
  // A figure whose results list no picture: ours are found by their names among the paths, fig2_ours.png for
  // the whole of Fig. 2, or its panels (fig2a_ours.png, ...) when there is no picture of the whole.
  const rel = (p) => p.slice(folder.length + 1);
  const named = tree.filter((p) => p.startsWith(folder + "/") && RASTER.has(ext(p)) && /[-_.]ours\.[A-Za-z]+$/.test(p)).map((p) => [figureKeyOf(p), rel(p)]).filter(([k]) => k !== null);
  const beside = tree.filter((p) => p.startsWith(folder + "/") && RASTER.has(ext(p)) && p.includes("overlay")).map(rel);
  for (const st of stations.values()) {
    if (!st.renders.length && figKey(st.items[0].id) && st.items.some((it) => it.verdict !== "not_attempted")) {
      const whole = named.filter(([k]) => k === st.key), panels = named.filter(([k]) => k.startsWith(st.key) && /^[a-z]+$/.test(k.slice(st.key.length)));
      for (const [, o] of (whole.length ? whole : panels).sort((x, y) => x[1].localeCompare(y[1]))) add(st, o, beside.filter((x) => x.slice(0, x.lastIndexOf("/")) === o.slice(0, o.lastIndexOf("/"))));
      st.found = st.renders.length > 0; // by name, not listed in results.json
    }
    if (!st.renders.length) st.publishedOnly = findPublished(st.key);
  }
  return [...stations.values()];
}
/**
 * What of a paper's figures is not among the paths of tree: `any` when a figure has no published
 * picture at all, `ours`, our pictures that have nothing to stand next to, and `undrawn` when a
 * figure that was attempted has no picture of ours.
 */
export function withoutOriginal(folder, results, tree) {
  const stations = figureStations(folder, listed(results).filter(inReview), tree);
  const ours = stations.flatMap((st) => st.renders.filter((r) => !r.published).map((r) => r.ours));
  const undrawn = stations.some((st) => !st.renders.length && st.items.some((it) => it.verdict !== "not_attempted"));
  return { any: ours.length > 0 || stations.some((st) => !st.renders.length && !st.publishedOnly), ours, undrawn };
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
/** How to show a list of fields: as the paper's table, or as a list. */
export function shapeFields(fs) {
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
/** One result as a row. aside: a result the review does not ask about, with its whole name and its numbers closed. */
function itemRow(item, aside = false) {
  const changed = item._changed ? '<span class="chip new">changed here</span>' : "";
  const p = pixelScore(item);
  const detail = item.method === "check" ? `<p class="detail">${esc((item.check || {}).detail)}</p>` : "";
  let body = fieldsHtml(item);
  if (body) body = `<details class="ibody"${aside || item.verdict === "exact" || item.verdict === "agrees" ? "" : " open"}><summary>Numbers</summary>${body}</details>`;
  return `<div class="irow" id="i-${esc(item.id)}"><div class="ihead">${stamp(item.verdict)}<span class="ilabel">${esc(aside ? String(item.label ?? item.id) : shortLabel(item))}</span>${changed}` +
    `${scoreBar(p)}<span class="meas">${p ? "" : esc(measureOf(item))}</span></div>${detail}${body}</div>`;
}
const imgTag = (ctx, path, alt) => `<img src="${esc(ctx.img(path))}" data-path="${esc(path)}" alt="${esc(alt)}" loading="lazy">`;
/**
 * The pictures of one figure. All of them show at once, each named above it: the original (the
 * published figure), ours, and the overlap (both drawn on top of each other), so nothing to
 * compare is behind a button. The other views are for a closer look.
 */
function viewerHtml(ctx, render, title) {
  const fig = (cls, path, name, alt) => `<figure class="${cls}"><figcaption>${name}</figcaption>${imgTag(ctx, path, `${title}, ${alt}`)}</figure>`;
  let layers = "";
  if (render.published) layers += fig("pub", render.published, "Original", "original");
  layers += fig("ours", render.ours, "Ours", "ours");
  if (render.overlay) layers += fig("ovl", render.overlay, "Overlap", "original and ours on top of each other");
  const n = (render.published ? 1 : 0) + 1 + (render.overlay ? 1 : 0);
  // each picture can be seen large, one at a time: by its name here, or by a click on it
  const single = [...(render.published ? [["pub", "Original"]] : []), ["ours", "Ours"], ...(render.overlay ? [["overlay", "Overlap"]] : [])];
  const modes = [["side", "Side by side"], ...(single.length > 1 ? single : []), ...(render.published ? [["swipe", "Swipe"], ["blink", "Blink"]] : [])];
  const buttons = modes.length < 2 ? "" : `<div class="modes" role="group" aria-label="View">${modes.map(([m, label], i) => `<button type="button" data-m="${m}"${i === 0 ? ' aria-pressed="true"' : ""}>${label}</button>`).join("")}</div>`;
  const slider = render.published ? '<input type="range" class="swipe" min="0" max="100" value="50" aria-label="Swipe between the original and ours">' : "";
  // on a card (a phone) one picture shows at a time: its name picks it, a tap on the picture goes to the next
  const pick = single.length < 2 ? "" : `<div class="pick" role="group" aria-label="Picture">${single.map(([m, label]) => `<button type="button" data-m="${m}">${label}</button>`).join("")}</div>`;
  // the commits that wrote our picture are read when the reviewer asks: what it was before can then be seen in its place
  const earlier = `<p class="hist"><button type="button" class="linkish earlier" data-path="${esc(render.ours)}">Earlier versions of ours</button></p><ul class="versions" hidden></ul>`;
  return `<div class="viewer" data-mode="side" data-n="${n}">${buttons}${pick}<div class="stage">${layers}${slider}</div>${earlier}</div>`;
}
/**
 * How far back a commit is from the head of the change: "the latest commit", "1 commit ago",
 * "3 commits ago". ago is its place among the commits of the change, the head being 0, or null
 * when it is not among the ones that were read: then "more than 100 commits ago" where beyond
 * says how many were read, and "" where the commits could not be read at all.
 */
export function agoText(ago, beyond = 0) {
  if (ago === 0) return "the latest commit";
  if (Number.isInteger(ago) && ago > 0) return `${ago} commit${ago === 1 ? "" : "s"} ago`;
  return beyond ? `more than ${beyond} commits ago` : "";
}
/**
 * The versions of one picture of ours, newest first, each as a picture with how long ago it was:
 * [{sha, when, message, ago, src}]. when is the date as the reader's clock says it, ago as for
 * agoText, src the address of the picture at that commit. The first is the one the page shows.
 * path is the picture's path, for a picture that has to be read through the API.
 */
export function versionsHtml(versions, { path = "", beyond = 0 } = {}) {
  const ago = (x) => agoText(x.ago, beyond);
  const wrote = (x) => (x.ago === 0 ? "by the latest commit" : ago(x)); // after "written"
  if (versions.length < 2) {
    const x = versions[0];
    return `<li class="only">Ours has one version${x ? `, written ${esc(x.when)}${wrote(x) ? ` (${wrote(x)})` : ""}` : ""}. There is nothing earlier to compare it with.</li>`;
  }
  const cut = (text) => (text.length > 96 ? text.slice(0, 95).trimEnd() + "…" : text);
  return `<li class="vhead">Ours was written ${versions.length} times. Each picture is ours as that commit left it, the newest first. A click opens it in the place of ours; a click on the large picture goes between it and ours as it is now.</li>` +
    versions.map((x, i) => {
      const now = i === 0, name = now ? "As it is now" : ago(x) || x.when;
      const when = now ? `Written ${wrote(x) ? `${wrote(x)}, ` : ""}${x.when}` : ago(x) ? x.when : "";
      const pic = x.src ? `<img src="${esc(x.src)}" data-path="${esc(path)}" data-sha="${esc(x.sha)}" alt="Ours, ${esc(now ? "as it is now" : name)}" loading="lazy">` : "";
      return `<li><button type="button" data-sha="${esc(x.sha)}" data-when="${esc(x.when)}" data-ago="${esc(now ? "" : ago(x))}"${now ? ' data-now="1" aria-current="true"' : ""}>${pic}` +
        `<b class="vago${now ? " vnow" : ""}">${esc(name)}</b>${when ? `<span class="vwhen">${esc(when)}</span>` : ""}<span class="vmsg">${esc(cut(String(x.message || "")))}</span></button></li>`;
    }).join("");
}
function stationHtml(ctx, folder, st) {
  const counts = {};
  for (const it of st.items) counts[it.verdict] = (counts[it.verdict] || 0) + 1;
  const dots = VERDICTS.filter((v) => counts[v]).map((v) => `<i class="dot v-${v}" title="${counts[v]} ${VERDICT_LABEL[v].toLowerCase()}"></i>`.repeat(counts[v])).join("");
  let views = st.renders.map((r) => (st.renders.length > 1 ? `<p class="rlabel">${esc(r.label)}</p>` : "") + viewerHtml(ctx, r, st.title)).join("");
  if (st.found) views += '<p class="note found">These pictures of ours are found by their names: results.json lists none for this figure.</p>';
  if (!views && st.publishedOnly) views = `<div class="viewer solo"><div class="stage solo"><figure class="pub"><figcaption>Original; there is no figure of ours</figcaption>${imgTag(ctx, st.publishedOnly, st.title + ", original")}</figure></div></div>`;
  // what the pull request measured for each curve, and why: there for who wants it, closed, below the question.
  // A figure with no picture at all has nothing else to show, so it starts open.
  const n = st.items.length;
  const details = `<details class="info"${views ? "" : " open"}><summary>Details: what the pull request measured${n > 1 ? ` for its ${n} results` : ""}, and why</summary>` +
    `<div class="rows">${st.items.map(itemRow).join("")}</div>${whyHtml(ctx, folder, st.unit)}</details>`;
  // The rows of the details are closed, so the question itself says what was measured (one result) and why
  // the result is not a plain match. Open details say it already.
  const at = views ? { measure: n === 1 ? measureOf(st.items[0]) : "", because: becauseHtml(st.unit) } : {};
  return `<section class="station" id="fig-${esc(st.key)}"><header class="shead"><h3>${esc(st.title)}</h3><span class="dots">${dots}</span></header>` +
    `${views ? `<div class="views">${views}</div>` : ""}${boxHtml(st.unit, details, at)}</section>`;
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
/** Why the results of one figure or table are not a plain match: causes, the choices made, the paper's own errors. */
function whyHtml(ctx, folder, unit) {
  const out = [], causes = new Map();
  for (const it of unit.items) {
    if (!it.cause) continue;
    const summary = squash(it.cause.summary), k = summary || String(it.id);
    if (!causes.has(k)) causes.set(k, { cause: it.cause, summary, items: [] });
    causes.get(k).items.push(it);
  }
  for (const { cause, summary, items } of causes.values()) {
    const [lead, rest] = firstSentence(summary);
    const who = items.length < unit.items.length ? `<b>${esc(items.map(shortLabel).join("; "))}:</b> ` : "";
    const chips = `<span class="chip cat">${esc(CATEGORY_LABEL[cause.category] || cause.category || "")}</span>` + (cause.status === "open" ? '<span class="chip open">open</span>' : "");
    const hyps = cause.hypotheses || [], ruled = hyps.filter((h) => h.result === "rejected").length;
    let more = rest ? `<details class="more"><summary>More</summary><p>${esc(rest)}</p></details>` : "";
    if (hyps.length) {
      more += `<details class="hyps"><summary>${ruled ? `${ruled} of ${hyps.length} tested causes ruled out` : `${hyps.length} tested causes`}</summary><ul>` +
        hyps.map((h) => `<li class="h-${esc(h.result)}"><span class="hres">${esc(h.result)}</span><span class="hyp">${esc(h.hypothesis)}</span><span class="test">${esc(h.test)}</span></li>`).join("") + "</ul></details>";
    }
    if ((cause.evidence || []).length) more += `<details class="hyps"><summary>Evidence</summary><ul class="ev">${evidenceHtml(ctx, folder, cause.evidence)}</ul></details>`;
    out.push(`<div class="cause"><p class="lead">${who}${esc(lead)} ${chips}</p>${more}</div>`);
  }
  const choices = new Map();
  for (const it of unit.items) {
    for (const a of it.assumptions || []) if (a.source in SOURCE_LABEL && !choices.has(squash(a.what))) choices.set(squash(a.what), a);
  }
  if (choices.size) {
    out.push(`<details class="hyps"><summary>${choices.size} choice${choices.size === 1 ? "" : "s"} the paper does not give</summary><ul class="rows-list">` +
      [...choices].map(([what, a]) => `<li><span class="what">${esc(what)}</span><span class="sens">${esc(a.sensitivity ?? "")}</span><span class="tags"><i class="chip cat">${SOURCE_LABEL[a.source]}</i></span></li>`).join("") + "</ul></details>");
  }
  const errors = unit.items.flatMap((it) => ((it.values || {}).exceptions || []).filter((x) => x.category === "paper_error"));
  if (errors.length) {
    out.push(`<details class="hyps"><summary>${errors.length} value${errors.length === 1 ? "" : "s"} the paper prints that ${errors.length === 1 ? "does" : "do"} not follow from its own numbers</summary><ul class="rows-list">` +
      errors.map((x) => `<li><span class="what"><i class="chip">${esc(x.field)}</i></span><span class="sens">${esc(stripPath(x.evidence))}</span></li>`).join("") + "</ul></details>");
  }
  return out.join("");
}
/**
 * The reviewer's decisions at a glance, apart by how they stand: what is not decided, what the
 * reviewer wants changed, and what is accepted. Each name goes to its figure or table.
 * units: [{key, title, given, givenText}] in the order of the page; said(key) gives {v, note}.
 */
export function mapHtml(units, said, foot = "") {
  const rows = { open: [], change: [], same: [] };
  for (const u of units) {
    const s = said(u.key), how = standOf(u, s.v) || "open";
    let text = esc(u.title);
    if (how === "change") text += `: ${u.givenText ? `${esc(u.givenText)} → ` : ""}${SAID_LABEL[s.v]}`;
    const note = String(s.note || "").trim();
    if (note) text += ` <i class="pen" title="${esc(note)}">with a comment</i>`;
    if (u.before && how === "open") text += ' <i class="pen new">changed since you decided</i>';
    if (u.redrawn && how !== "open") text += ' <i class="pen new">drawn again</i>';
    rows[how === "change" || how === "open" ? how : "same"].push(`<button type="button" class="mchip" data-key="${esc(u.key)}">${text}</button>`);
  }
  const row = (cls, title, chips) => (chips.length ? `<div class="mrow m-${cls}"><span class="mname">${title} <b>${chips.length}</b></span><span class="mchips">${chips.join("")}</span></div>` : "");
  return '<h3 class="mhead">Your review</h3>' + row("open", "Not decided", rows.open) + row("change", "To change", rows.change) + row("same", "Accepted", rows.same) +
    (foot ? `<p class="mfoot">${esc(foot)}</p>` : "");
}
/**
 * Why the results of one figure or table are not a plain match, in one sentence each: what the
 * reviewer has to know to answer. The whole of it is in the details.
 */
function becauseHtml(unit) {
  const causes = new Map();
  for (const it of unit.items) {
    const lead = it.cause ? firstSentence(it.cause.summary)[0] : "";
    if (!lead) continue;
    if (!causes.has(lead)) causes.set(lead, []);
    causes.get(lead).push(it);
  }
  if (!causes.size) return "";
  const rows = [...causes].slice(0, 3).map(([lead, its]) => `<li>${its.length < unit.items.length ? `<b>${esc(its.map(shortLabel).join("; "))}:</b> ` : ""}${esc(lead)}</li>`);
  const more = causes.size - rows.length;
  return `<ul class="because">${rows.join("")}${more > 0 ? `<li class="rest">and ${more} more in the details</li>` : ""}</ul>`;
}
const COMMENT = '<textarea rows="1" placeholder="Comment for the author" aria-label="Comment for the author" hidden></textarea>';
/**
 * The decision that sits right below a figure or a table. One click passes what the reviewer
 * agrees with: Accept (the pull request's verdict stands), or OK where there is no verdict.
 * Revise opens the reviewer's own verdict and the reason; Not OK opens the reason. The closed
 * details come last. measure and because say, at the question, what the pull request measured
 * and why the result is not a plain match.
 */
function boxHtml(unit, details = "", { measure = "", because = "" } = {}) {
  let ask, mine = "";
  if (unit.ask === "verdict") {
    const others = ["agrees", "partly", "differs"].filter((v) => v !== unit.given);
    ask = `<span class="ask">The pull request says <b>${esc(unit.givenText)}</b>${unit.items.length > 1 ? ` for ${esc(unit.title)}` : ""}${measure ? ` <span class="meas">(${esc(measure)})</span>` : ""}.</span>${because}` +
      '<span class="opts"><button type="button" data-v="same">Accept</button><button type="button" class="differ">Revise</button></span>';
    mine = `<div class="mine" hidden><span class="ask">Your verdict:</span><span class="opts">${others.map((v) => `<button type="button" data-v="${v}">${VERDICT_LABEL[v]}</button>`).join("")}</span></div>`;
  } else {
    ask = `<span class="ask">Is this OK?</span>${because}<span class="opts"><button type="button" data-v="ok">OK</button><button type="button" data-v="no">Not OK</button></span>`;
  }
  // .again: what changed since the reviewer decided, said by the app from what the browser kept
  return `<div class="dbox" id="d-${unit.key}" data-key="${unit.key}" data-title="${esc(unit.title)}" data-ask="${unit.ask}" data-given="${esc(unit.given)}" data-given-text="${esc(unit.givenText)}" tabindex="-1">` +
    `${unit.notes || ""}<p class="again" hidden></p><footer class="decide">${ask}${mine}${COMMENT}<span class="state" aria-live="polite"></span>` +
    `<button type="button" class="linkish addnote" hidden>Add a comment</button><button type="button" class="dgo">Next</button></footer>${details}</div>`;
}
export const fileAnchor = (path) => cardKey("file", path).slice(0, 10);
const delta = (f) => `<span class="delta"><b class="add">+${f.added}</b>${f.deleted ? ` <b class="del">−${f.deleted}</b>` : ""}</span>`;

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
function codeHtml(ctx, files, folders, outsideBox) {
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
      const head = `<h3 class="ghead">${title} <span class="count">${fs.length} files, ${fmtInt(n)} lines</span></h3>`;
      const list = fs.map((f, i) => fileHtml(ctx, f, first && i === 0 && cat !== "shared")).join("");
      out.push(cat === "shared" ? `<div class="outside">${head}<div class="ofiles">${list}</div>${outsideBox}</div>` : head + list);
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

/**
 * One paper's results as what a reviewer decides on, in the order of the page: each main figure,
 * then each main table. aside holds the results the review does not ask about (inReview).
 * tree (the paths of the change) finds the pictures.
 */
export function paperLayout(folder, results, tree = [], blobs = new Map()) {
  const all = listed(results), items = all.filter(inReview), aside = all.filter((it) => !inReview(it));
  const pid = String((results.paper || {}).id || folder);
  const stations = figureStations(folder, items, tree);
  for (const st of stations) {
    st.unit = unitOf(pid, "fig-" + st.key, st.title, st.items);
    // a name for our pictures as they are in this change: another one when a picture is drawn again
    const drawn = st.renders.flatMap((r) => [r.ours, r.overlay]).map((path) => blobs.get(path)).filter(Boolean);
    st.unit.pics = drawn.length ? cardKey(...drawn) : "";
  }
  const tables = items.filter((it) => it.kind === "table");
  const times = new Map();
  for (const it of tables) times.set(token(it), (times.get(token(it)) || 0) + 1);
  const titleOf = (it) => {
    if (times.get(token(it)) < 2) return token(it);
    const part = partOf(it);
    return `${token(it)}: ${part.length > 48 ? part.slice(0, 47).trimEnd() + "…" : part}`;
  };
  const blocks = tables.map((it) => ({ it, unit: unitOf(pid, String(it.id), titleOf(it), [it]) }));
  return { pid, all, aside, stations, blocks, units: [...stations.map((st) => st.unit), ...blocks.map((b) => b.unit)] };
}
/** The decisions a paper's results ask for, as the browser keeps them. */
export const paperUnits = (folder, results) => paperLayout(folder, results).units.map(slimUnit);

const MAP_SLOT = '<section class="rmap" aria-label="Your review"></section>';
function paperHtml(ctx, paper, idx, blobs) {
  const { folder, results, baseResults, tree } = paper;
  const { pid, all: items, aside, stations, blocks, units } = paperLayout(folder, results, tree, blobs);
  if (baseResults) {
    const old = new Map((baseResults.items || []).map((it) => [it && it.id, JSON.stringify(it)]));
    for (const it of items) it._changed = old.get(it.id) !== JSON.stringify(it);
  }
  const meta = results.paper || {};
  const counts = Object.fromEntries(VERDICTS.map((v) => [v, items.filter((it) => it.verdict === v).length]));
  const tables = blocks.map(({ it, unit }) => {
    const why = whyHtml(ctx, folder, unit);
    return `<div class="nblock"><h4>${esc(token(it))}</h4>${itemRow(it)}` +
      `${boxHtml(unit, why ? `<details class="info"><summary>Details: why</summary>${why}</details>` : "", { because: becauseHtml(unit) })}</div>`;
  }).join("");
  // what the review does not ask about: as the pull request gives it, closed, with no decision
  let rest = "";
  if (aside.length) {
    const n = { supp: 0, text: 0, check: 0, other: 0 };
    for (const it of aside) n[isSupplementary(it) ? "supp" : it.kind === "value" ? "text" : it.kind === "code_check" ? "check" : "other"]++;
    const names = [[n.supp, "supplementary result"], [n.text, "number", " in the text"], [n.check, "check"], [n.other, "other result"]]
      .filter(([k]) => k).map(([k, one, after = ""]) => `${k} ${one}${k === 1 ? "" : "s"}${after}`);
    rest = `<details class="aside" id="aside-${idx}"><summary>Not asked: ${names.length > 1 ? `${names.slice(0, -1).join(", ")} and ${names.at(-1)}` : names[0]}</summary>` +
      '<p class="note">The review asks about the main figures and tables of the paper. These are as the pull request gives them, with no decision to make.</p>' +
      aside.map((it) => {
        const why = whyHtml(ctx, folder, { items: [it] });
        return `<div class="ablock">${itemRow(it, true)}${why ? `<details class="info"><summary>Details: why</summary>${why}</details>` : ""}</div>`;
      }).join("") + "</details>";
  }
  const doi = String(meta.doi || "");
  let cite = esc(meta.citation || "");
  if (/^10\.\d{4,9}\/\S+$/.test(doi)) cite = `<a href="https://doi.org/${esc(doi)}" rel="noopener">${cite || esc(doi)}</a>`;
  const changed = items.filter((it) => it._changed).length;
  const changedNote = baseResults && changed ? `<p class="note">This change touches ${changed} of ${items.length} items; they are marked <span class="chip new">changed here</span>.</p>` : "";
  const nav = `<nav class="tabs" aria-label="Sections"><a href="#figures-${idx}">Figures <b>${stations.length}</b></a>` +
    `<a href="#tables-${idx}">Tables <b>${blocks.length}</b></a><a href="#code">Code</a></nav>`;
  const html = `<section class="paper" data-paper="${esc(pid)}"><div class="phead"><p class="pid"><span class="pmc">${esc(pid)}</span> ${cite}</p>` +
    `<h1>${esc(meta.title || folder)}</h1>${verdictBar(counts)}${changedNote}${nav}${idx === 0 ? MAP_SLOT : ""}</div>` +
    `<section id="figures-${idx}" class="sec"><h2>Figures</h2>${stations.map((st) => stationHtml(ctx, folder, st)).join("") || '<p class="note">No main figure in results.json.</p>'}</section>` +
    `<section id="tables-${idx}" class="sec"><h2>Tables</h2>${tables || '<p class="note">No main table in results.json.</p>'}</section>${rest}</section>`;
  return [html, { id: pid, title: String(meta.title || folder), counts, units: units.map(slimUnit) }];
}

/**
 * The page of one pull request or branch. Each figure and each table has its decision right
 * below it; what changed outside the paper folder has its decision in the code section.
 * review: {repo, label, title, url, number, branch, author, updated, draft, sha, notes, files, papers}
 * ctx: {img(path), blob(path)} give the addresses of a picture and of a file on GitHub.
 */
export function reviewHtml(review, ctx) {
  const folders = review.papers.map((p) => p.folder);
  for (const f of review.files) f.cat = classify(f.path, folders)[0];
  const shared = review.files.filter((f) => f.cat === "shared");
  const sections = [], summaries = [];
  const blobs = new Map(review.files.filter((f) => f.sha).map((f) => [f.path, f.sha]));
  review.papers.forEach((paper, idx) => {
    const [html, summary] = paperHtml(ctx, paper, idx, blobs);
    sections.push(html);
    summaries.push(summary);
  });
  if (!review.papers.length) {
    sections.push(`<section class="paper"><div class="phead"><h1>${esc(review.title || review.label)}</h1>` +
      '<p class="note">No Paper2Repro results.json in this change, so there is no paper to lay it out by. The changed files are below.</p></div></section>');
    summaries.push({ id: "", title: review.title || review.label, counts: {}, units: [] });
  }
  const notes = (review.notes || []).map((n) => `<p class="warn">${esc(n)}</p>`).join("");
  let outsideBox = "", outside = null;
  if (shared.length) {
    const unit = {
      key: cardKey(review.repo, review.label, "outside", ...shared.map((f) => f.path + f.added + f.deleted)),
      title: review.papers.length ? "Changes outside the paper folder" : "Changed files", ask: "ok", given: "", givenText: "", items: [], notes,
    };
    outsideBox = boxHtml(unit);
    outside = slimUnit(unit);
  }
  const [code, by] = codeHtml(ctx, review.files, folders, outsideBox);
  const bits = [];
  if (review.number) bits.push(`<a href="${esc(review.url)}" rel="noopener">#${review.number}</a>`);
  if (review.branch) bits.push(`<span class="mono">${esc(review.branch)}</span>`);
  bits.push(`<span class="mono">${esc(review.sha.slice(0, 7))}</span>`);
  if (review.author) bits.push(esc(review.author));
  if (review.updated) bits.push(esc(review.updated.slice(0, 10)));
  const asked = askedText(review.reviewers || [], review.me);
  if (asked) bits.push(`<span class="asked${(review.reviewers || []).some((n) => sameLogin(n, review.me)) ? " you" : ""}">${esc(asked.charAt(0).toLowerCase() + asked.slice(1))}</span>`);
  const chips = (review.draft ? '<span class="chip">draft</span>' : "") + '<span class="ci"></span>';
  // a pull request takes the review; a branch has none, so its review is copied. The app names the button for what it does next.
  const send = review.number ? "Add review" : "Copy review";
  const html = `<header class="top"><div class="wrap"><a class="back" href="./">All reviews</a><span class="refline">${esc(review.repo)} · ${bits.join(" · ")} ${chips}</span></div></header>` +
    `<main class="wrap">${sections.join("")}<section id="code" class="sec"><h2>Code</h2>${shared.length ? "" : notes}${code}</section>` +
    '<div class="restbar" hidden><span class="restnote"></span><button type="button" class="btn rest">Accept these as the pull request says</button></div></main>' +
    '<div class="deckbar"><button type="button" class="dprev" aria-label="Previous card">‹</button><span class="dtitle"></span><span class="dcount"></span>' +
    '<button type="button" class="dnext" aria-label="Next card">›</button><button type="button" class="linkish dpage">Whole page</button><span class="dprog"><i></i></span></div>' +
    `<div class="deckend" hidden><div><p class="dhead">That was the last card</p><p class="dsum"></p>${MAP_SLOT}` +
    '<p><button type="button" class="btn dfirst">Go to the first one not decided</button></p>' +
    '<p><button type="button" class="btn rest">Accept these as the pull request says</button></p>' +
    `<p><button type="button" class="send">${send}</button> <a class="btn" href="${esc(review.url)}" rel="noopener">GitHub</a></p><p class="sendnote" role="status" hidden></p></div></div>` +
    '<div class="bar"><div class="wrap"><span class="progress"><b class="done">0</b> of <b class="all">0</b> decided<span class="chg"></span></span>' +
    '<button type="button" class="btn next">Next not decided</button><button type="button" class="btn dcards">Cards</button><span class="grow"></span>' +
    `<button type="button" class="send">${send}</button><a class="btn" href="${esc(review.url)}" rel="noopener">GitHub</a></div><p class="sendnote" role="status" hidden></p></div>`;
  const lines = Object.fromEntries(Object.entries(by).map(([cat, fs]) => [cat, fs.reduce((n, f) => n + f.added + f.deleted, 0)]));
  const units = summaries.flatMap((p) => p.units).concat(outside ? [outside] : []);
  return { html, summary: { papers: summaries, units, keys: units.map((u) => u.key), files: review.files.length, lines, sha: review.sha } };
}

const HOME_GROUPS = [["todo", "To review"], ["changes", "Changes requested"], ["agreed", "Accepted"]];
const STATE = { // state of standing(): [the group it is listed in, its name on the card]
  new: ["todo", "Not opened"], seen: ["todo", "Not started"], started: ["todo", "In progress"], updated: ["todo", "Changed since your review"],
  changes: ["changes", "Changes requested"], agreed: ["agreed", "Accepted"], reviewed: ["agreed", "Reviewed"],
};
/** What a card of the first page says of the reviewer's own decisions. */
function standingFacts(st) {
  if (st.state === "new") return '<span class="progress">Not opened yet</span>';
  let out = `<span class="progress"><b>${st.done}</b> of <b>${st.all}</b> decided${st.state === "updated" ? " before it changed" : ""}</span>`;
  if (st.state === "updated" && st.again !== undefined) out += `<span class="ragain">${st.again ? `${st.again} to decide again` : "nothing in the paper to decide again"}</span>`;
  if (st.change.length) {
    const names = st.change.filter(Boolean), more = st.change.length - Math.min(names.length, 4);
    out += `<span class="rchange">${st.change.length} to change${names.length ? `: ${esc(names.slice(0, 4).join(", "))}${more ? ` and ${more} more` : ""}` : ""}</span>`;
  }
  if (st.sent) {
    // added: the page put it on the pull request. copied: it went to the clipboard, and the page cannot know that it was pasted
    const did = st.sent.how === "added" ? "added" : "copied";
    const text = { yes: `Review ${did} ${st.sent.when}`, stale: `Decisions changed since you ${did} the review`, no: "Review not added yet" }[st.sent.state];
    out += `<span class="rsent${st.sent.state === "yes" ? "" : " todo"}">${esc(text)}</span>`;
  }
  return out;
}
/**
 * The open pull requests, apart by where each stands for this reviewer: to review, changes
 * requested, accepted. mine: number → standing(), with sent {state, when} and again where known.
 * me: the reader's GitHub login, where a token says it: their own review requests are named and come first.
 */
export function pullsHtml(repo, pulls, mine = new Map(), me = "") {
  const [owner, name] = repo.split("/");
  const stOf = (p) => mine.get(p.number) || { state: "new", done: 0, all: 0, change: [] };
  const forMe = (p) => reviewersOf(p).some((n) => sameLogin(n, me));
  const card = (p) => {
    const st = stOf(p), who = [p.user && p.user.login, (p.updated_at || "").slice(0, 10)].filter(Boolean).join(" · ");
    const asked = askedText(reviewersOf(p), me);
    return `<a class="rcard s-${st.state}" href="${routeOf({ owner, repo: name, kind: "pull", number: p.number })}" data-number="${p.number}" data-sha="${esc(p.head && p.head.sha)}" data-title="${esc(p.title)}" data-ref="${esc(p.head && p.head.ref)}">` +
      `<div class="rtop"><span class="pmc"></span><span class="rref">#${p.number}</span><span class="grow"></span><span class="rstate">${STATE[st.state][1]}</span></div><h2>${esc(p.title)}</h2><div class="rbar"></div>` +
      `<p class="facts">${standingFacts(st)}</p><p class="who">${esc(who)} ${p.draft ? '<span class="chip">draft</span>' : ""}</p>` +
      `${asked ? `<p class="asked${forMe(p) ? " you" : ""}">${esc(asked)}</p>` : ""}</a>`;
  };
  return HOME_GROUPS.map(([key, title]) => {
    // in each group, the pull requests that wait for the reader come first
    const ps = pulls.filter((p) => STATE[stOf(p).state][0] === key).sort((a, b) => Number(forMe(b)) - Number(forMe(a)));
    return ps.length ? `<section class="rgroup g-${key}"><h3 class="ghead">${title} <span class="count">${ps.length}</span></h3><div class="rgrid">${ps.map(card).join("")}</div></section>` : "";
  }).join("");
}

/** The first page: a box to paste a link into, and what is open in the usual repository. */
export function homeHtml({ repo, pulls, recent, error, mine, me }) {
  const list = pulls && pulls.length ? pullsHtml(repo, pulls, mine, me) : `<p class="note home-note">${pulls ? "Nothing is open." : "Loading…"}</p>`;
  const recents = (recent || []).map((r) => `<li><a href="${esc(r.route)}">${esc(r.label)}</a></li>`).join("");
  return '<header class="top"><div class="wrap"><span class="refline">Reproduction review</span><span class="grow"></span><button type="button" class="linkish token">GitHub token</button></div></header>' +
    '<main class="wrap"><div class="phead"><h1>Paste a pull request or branch link</h1>' +
    '<form class="paste"><input type="text" name="link" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="https://github.com/owner/repo/pull/40" aria-label="Pull request or branch link"><button type="submit">Review</button></form>' +
    `<p class="note paste-error" role="alert">${esc(error || "")}</p></div>` +
    (repo ? `<section class="sec"><h2>Open in ${esc(repo)} <span class="count">${pulls ? pulls.length : ""}</span></h2><div class="pulls">${list}</div></section>` : "") +
    (recents ? `<section class="sec"><h2>Recent</h2><ul class="recent">${recents}</ul></section>` : "") + "</main>";
}
