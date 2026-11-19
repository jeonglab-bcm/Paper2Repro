// The browser side: read a pull request or branch from GitHub, draw it with core.js, and
// keep the reviewer's decisions in this browser.

import * as core from "./core.js";

const API = "https://api.github.com";
const RAW = "https://raw.githubusercontent.com";
const DEFAULT_REPO = document.body.dataset.repo || "";
const app = document.getElementById("app");

const store = {
  get(k) { try { return JSON.parse(localStorage.getItem(k) || "null"); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private window: keep going */ } },
  del(k) { try { localStorage.removeItem(k); } catch { /* same */ } },
};
const token = () => store.get("rv:token") || "";

// ------------------------------------------------------------------ GitHub

class GitHubError extends Error {
  constructor(status, message, wantsToken = false) {
    super(message);
    this.status = status;
    this.wantsToken = wantsToken;
  }
}
const cache = new Map(); // what GitHub answered in this tab: path (and tag) → {at, data}
const FRESH_MS = 20000;
/**
 * GitHub's answer to a GET. An answer this tab already has is used again, with two exceptions.
 * `fresh` is for what changes while a page is open (the head of a pull request, the list of what
 * is open): it is asked again once the answer is 20 seconds old. `tag` is for what depends on a
 * commit (the files of a pull request): the answer for another tag is not used.
 * The browser's own cache is passed by, as it keeps GitHub's answers for a minute.
 */
async function api(path, { fresh = false, tag = "" } = {}) {
  const key = tag ? `${path} @${tag}` : path, hit = cache.get(key);
  if (hit && !(fresh && Date.now() - hit.at > FRESH_MS)) return hit.data;
  const headers = { Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28" };
  if (token()) headers.Authorization = `Bearer ${token()}`;
  let res;
  try {
    res = await fetch(API + path, { headers, cache: "no-cache" });
  } catch {
    throw new GitHubError(0, "Cannot reach GitHub. Check the network and try again.");
  }
  if (!res.ok) {
    if ((res.status === 403 || res.status === 429) && res.headers.get("x-ratelimit-remaining") === "0") {
      const reset = Number(res.headers.get("x-ratelimit-reset"));
      const when = reset ? new Date(reset * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "later";
      throw new GitHubError(res.status, token() ? `GitHub's request limit is used up until ${when}.` : `GitHub's limit for requests without a token is used up until ${when}. Add a GitHub token to go on now.`, !token());
    }
    if (res.status === 401) throw new GitHubError(401, "GitHub refused the token. Replace or remove it.", true);
    if (res.status === 404) throw new GitHubError(404, token() ? "GitHub does not find it. Check the link." : "GitHub does not find it. Check the link, or add a GitHub token if the repository is private.", !token());
    throw new GitHubError(res.status, `GitHub answered ${res.status}.`, res.status === 403 && !token());
  }
  const data = await res.json();
  cache.set(key, { at: Date.now(), data });
  return data;
}
async function apiAll(path, { pages = 30, tag = "" } = {}) {
  const out = [];
  for (let page = 1; page <= pages; page++) {
    const part = await api(`${path}${path.includes("?") ? "&" : "?"}per_page=100&page=${page}`, { tag });
    out.push(...part);
    if (part.length < 100) break;
  }
  return out;
}
/** The reader's GitHub login as the browser keeps it with the token; "" with no token, or before GitHub was asked. */
const meKept = () => (token() ? (store.get("rv:me") || {}).login || "" : "");
/**
 * The login the token belongs to, asked of GitHub once (1 request) and kept until the token changes.
 * "" with no token, or when GitHub does not say: the page then goes on without it.
 */
async function whoAmI() {
  if (!token()) return "";
  const kept = store.get("rv:me");
  if (kept) return kept.login || "";
  let login = "";
  try {
    login = String((await api("/user")).login || "");
  } catch {
    /* a token that does not say who it is */
  }
  store.set("rv:me", { login });
  return login;
}
/** A change on GitHub with the reviewer's token: a review submitted (POST) or its text edited (PUT). Gives GitHub's answer. */
async function write(method, path, body) {
  let res;
  try {
    res = await fetch(API + path, {
      method, cache: "no-cache", body: JSON.stringify(body),
      headers: { Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json", Authorization: `Bearer ${token()}` },
    });
  } catch {
    throw new GitHubError(0, "Cannot reach GitHub.");
  }
  if (!res.ok) throw new GitHubError(res.status, `GitHub answered ${res.status}.`);
  return res.json();
}
const rawUrl = (c, path) => `${RAW}/${c.owner}/${c.repo}/${c.sha}/${core.encPath(path)}`;
let rawWorks = true;
/**
 * A file's text at a commit; null when it is not there. It comes from raw.githubusercontent.com,
 * which GitHub does not count. The API is asked instead for a private repository (with a token),
 * or when the browser cannot read that host at all.
 */
async function rawText(c, path) {
  if (rawWorks) {
    try {
      const r = await fetch(rawUrl(c, path));
      if (r.ok) return await r.text();
      if (!token()) return null;
    } catch {
      rawWorks = false;
    }
  }
  try {
    const r = await fetch(`${API}/repos/${c.owner}/${c.repo}/contents/${core.encPath(path)}?ref=${c.sha}`, {
      headers: { Accept: "application/vnd.github.raw+json", ...(token() ? { Authorization: `Bearer ${token()}` } : {}) },
    });
    return r.ok ? await r.text() : null;
  } catch {
    return null;
  }
}

/** Everything one review page needs, from a parsed link. */
async function loadReview(link) {
  const { owner, repo } = link;
  const base = `/repos/${owner}/${repo}`;
  let review, baseSha, apiFiles;
  if (link.kind === "pull") {
    const pr = await api(`${base}/pulls/${link.number}`, { fresh: true });
    apiFiles = await apiAll(`${base}/pulls/${link.number}/files`, { tag: pr.head.sha });
    baseSha = pr.base.sha;
    review = {
      label: `#${pr.number}`, title: pr.title, url: pr.html_url, number: pr.number, branch: pr.head.ref,
      author: pr.user && pr.user.login, updated: pr.updated_at, draft: pr.draft, sha: pr.head.sha, reviewers: core.reviewersOf(pr),
      notes: pr.mergeable_state === "dirty" ? [`Conflicts with ${pr.base.ref}. It needs an update before it can merge.`] : [],
    };
  } else {
    const info = await api(base);
    const baseRef = link.base || info.default_branch;
    // a tree link can end in a path: try the whole text as the branch, then without its last parts
    let branch = link.branch, cmp = null, last = null;
    for (let i = 0; i < 5 && branch; i++) {
      try {
        cmp = await api(`${base}/compare/${core.encPath(baseRef)}...${core.encPath(branch)}`, { fresh: true });
        break;
      } catch (err) {
        last = err;
        if (err.status !== 404 || !branch.includes("/")) break;
        branch = branch.slice(0, branch.lastIndexOf("/"));
      }
    }
    if (!cmp) throw last;
    const open = await api(`${base}/pulls?state=open&head=${encodeURIComponent(`${owner}:${branch}`)}`, { fresh: true }).catch(() => []);
    if (open.length) return loadReview({ owner, repo, kind: "pull", number: open[0].number });
    const tip = cmp.commits && cmp.commits.length ? cmp.commits[cmp.commits.length - 1] : await api(`${base}/commits/${core.encPath(branch)}`, { fresh: true });
    apiFiles = cmp.files || [];
    baseSha = cmp.merge_base_commit && cmp.merge_base_commit.sha;
    review = {
      label: branch, title: branch, branch, sha: tip.sha, notes: [],
      url: `https://github.com/${owner}/${repo}/compare/${core.encPath(baseRef)}...${core.encPath(branch)}`,
      author: tip.commit && tip.commit.author && tip.commit.author.name, updated: tip.commit && tip.commit.author && tip.commit.author.date,
    };
    if (apiFiles.length >= 300) review.notes.push("GitHub lists only the first 300 changed files of a branch. Open a pull request to see all of them.");
  }
  review.repo = `${owner}/${repo}`;
  review.files = core.normalizeFiles(apiFiles);
  const c = { owner, repo, sha: review.sha };
  const tree = review.files.filter((f) => f.status !== "D").map((f) => f.path);
  review.papers = [];
  for (const folder of core.paperCandidates(review.files).slice(0, 8)) {
    for (const path of [`${folder}/results.json`, `${folder}/figure-reproduction/results.json`]) {
      const text = await rawText(c, path);
      const results = text && core.parseResults(text);
      if (!results) continue;
      const baseText = baseSha ? await rawText({ owner, repo, sha: baseSha }, path) : null;
      let mine = tree.filter((p) => p.startsWith(folder + "/"));
      // A change holds only the files it touches. A change to a paper that is already in the repository does not
      // hold its published figures, or holds some of them: where a figure has none, the folders are read.
      const listed = async (dir) => {
        const list = await api(`${base}/contents/${core.encPath(dir)}?ref=${review.sha}`).catch(() => []);
        return (Array.isArray(list) ? list : []).map((d) => d.path);
      };
      if ((baseText || !mine.some((p) => p.includes("/published/"))) && core.withoutOriginal(folder, results, mine).any) {
        mine = mine.concat(await listed(`${folder}/figure-reproduction/published`));
        // some papers keep the published picture next to ours, as fig1_published.png
        const lone = baseText ? core.withoutOriginal(folder, results, mine).ours[0] : null;
        if (lone) mine = mine.concat(await listed(lone.slice(0, lone.lastIndexOf("/"))));
      }
      // and its results may list no picture of ours: those are found by name, in the folders they are written to
      for (const dir of baseText ? ["figure-reproduction/output/figures", "figure-reproduction/output"] : []) {
        if (!core.withoutOriginal(folder, results, mine).undrawn) break;
        mine = mine.concat(await listed(`${folder}/${dir}`));
      }
      review.papers.push({ folder, path, results, baseResults: baseText ? core.parseResults(baseText) : null, tree: mine });
      break;
    }
  }
  return { review, c };
}

// ----------------------------------------------------------------- pages

let shown = null; // the address (search part) of what is on the page
function mount(html) {
  app.innerHTML = html;
}

// A page that stays open: when the reader comes back to it, GitHub is asked whether what it
// shows is still the latest. The first page is drawn again; a review says that there is a new
// commit and waits for the reader, who may be in the middle of it.
let current = null; // what is on the page: {refresh()} for the first page, {link, sha, head()} for a review
let asked = 0;      // when GitHub was last asked
// Each asking is one of the 60 requests an hour GitHub allows without a token: then every 5 minutes at most, with a token every minute.
const recheckMs = () => (token() ? 60000 : 300000);
function showing(what) {
  current = what;
  asked = Date.now();
  document.querySelector(".stale")?.remove();
}
async function recheck() {
  const mine = current;
  if (!mine || document.visibilityState !== "visible" || Date.now() - asked < recheckMs()) return;
  asked = Date.now();
  try {
    if (mine.refresh) return void (await mine.refresh());
    const sha = await mine.head();
    if (current !== mine || !sha || sha === mine.sha || document.querySelector(".stale")) return;
    const bar = document.createElement("div");
    bar.className = "stale";
    bar.setAttribute("role", "status");
    bar.innerHTML = `<span>There is a new commit, <b class="mono">${core.esc(sha.slice(0, 7))}</b>. This page shows <b class="mono">${core.esc(mine.sha.slice(0, 7))}</b>. Your decisions are kept.</span>` +
      '<button type="button" class="btn now">Show the latest</button><button type="button" class="linkish later">Later</button>';
    bar.querySelector(".now").addEventListener("click", () => render());
    bar.querySelector(".later").addEventListener("click", () => bar.remove()); // it is said again the next time the reader comes back
    document.body.append(bar);
  } catch { /* GitHub did not answer: the page stays, and the next return asks again */ }
}
document.addEventListener("visibilitychange", recheck);
window.addEventListener("focus", recheck);
window.addEventListener("pageshow", (ev) => { if (ev.persisted) recheck(); });
function go(route) {
  history.pushState({}, "", route || "./");
  render();
}
function messagePage(text, { wantsToken = false, busy = false } = {}) {
  mount('<header class="top"><div class="wrap"><a class="back" href="./">All reviews</a></div></header>' +
    `<main class="wrap"><div class="phead"><p class="${busy ? "note busy" : "problem"}" role="${busy ? "status" : "alert"}">${core.esc(text)}</p>` +
    (wantsToken ? '<p><button type="button" class="btn token">Add a GitHub token</button></p>' : "") + "</div></main>");
}

async function render() {
  const mine = (shown = location.search);
  const link = core.parseRoute(location.search, DEFAULT_REPO);
  if (new URLSearchParams(location.search).has("url")) {
    history.replaceState({}, "", link ? core.routeOf(link) : "./");
    shown = location.search;
  }
  document.title = "Reproduction review";
  document.body.classList.remove("deck");
  showing(null);
  if (!link || link.kind === "repo") return home(link ? `${link.owner}/${link.repo}` : DEFAULT_REPO);
  const name = link.kind === "pull" ? `#${link.number}` : link.branch;
  messagePage(`Reading ${name} of ${link.owner}/${link.repo} from GitHub…`, { busy: true });
  window.scrollTo(0, 0);
  try {
    const { review, c } = await loadReview(link);
    review.me = await whoAmI(); // whose review requests are "yours", and whether the pull request is the reader's own
    if (shown !== mine && shown !== location.search) return; // the reader moved on
    const ctx = {
      img: (path) => rawUrl(c, path),
      blob: (path) => `https://github.com/${c.owner}/${c.repo}/blob/${c.sha}/${core.encPath(path)}`,
    };
    const { html, summary } = core.reviewHtml(review, ctx);
    mount(html);
    document.title = `${summary.papers.map((p) => p.id).filter(Boolean).join(" ") || review.label} · ${review.label}`;
    const route = core.routeOf(review.number ? { ...link, kind: "pull", number: review.number } : { ...link, branch: review.branch });
    if (route !== location.search) { history.replaceState({}, "", route + location.hash); shown = location.search; }
    summary.units = remember(review, route, summary);
    wireReview(review, c, summary);
    const repoPath = `/repos/${c.owner}/${c.repo}`;
    showing({
      link, sha: review.sha,
      head: async () => (review.number ? (await api(`${repoPath}/pulls/${review.number}`, { fresh: true })).head.sha
        : (await api(`${repoPath}/commits/${core.encPath(review.branch)}`, { fresh: true })).sha),
    });
    if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView();
  } catch (err) {
    if (!(err instanceof GitHubError)) console.error(err);
    messagePage(err instanceof GitHubError ? err.message : `This page could not be drawn: ${err.message}`, { wantsToken: err.wantsToken });
  }
}

const sumKey = (repo, label) => `rv:sum:${repo}:${label}`;
const sentKey = (repo, label) => `rv:sent:${repo}:${label}`;
/**
 * Whether the review went out, and whether a decision changed after that. how is "added" when the
 * page submitted it as a review of the pull request (kept: {at, sig, id, url, sha, state}), and
 * "copied" when it went to the clipboard ({at, sig}): the page cannot know that it was pasted.
 */
function sentOf(repo, label, keys) {
  const sent = store.get(sentKey(repo, label));
  if (!sent) return { state: "no" };
  const when = new Date(sent.at).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
  return { state: sent.sig === core.reviewSig(keys, (k) => said(repo, k)) ? "yes" : "stale", when, how: sent.url ? "added" : "copied" };
}

/**
 * Keeps what this review asks, and gives its units with what changed since the reviewer decided:
 * `before` on a figure or table that the pull request changed after a decision (it asks again),
 * and `redrawn` on one whose pictures were drawn again while the decision still stands.
 */
function remember(review, route, summary) {
  const key = sumKey(review.repo, review.label), old = store.get(key);
  const was = new Map(((old && old.units) || []).map((u) => [u.title, u]));
  const units = summary.units.map((u) => {
    const w = was.get(u.title);
    if (!w) return u;
    const now = said(review.repo, u.key);
    if (w.key === u.key) {
      const redrawn = w.pics && u.pics && w.pics !== u.pics && now.v ? { sha: old.sha } : w.redrawn;
      return { ...u, ...(w.before && !now.v ? { before: w.before } : {}), ...(redrawn && now.v ? { redrawn } : {}) };
    }
    const then = said(review.repo, w.key);
    if (then.v || then.note) return { ...u, before: { v: then.v, note: then.note, given: w.given, givenText: w.givenText, sha: old.sha } };
    return w.before && !now.v ? { ...u, before: w.before } : u;
  });
  store.set(key, { sha: review.sha, keys: summary.keys, units });
  const label = `${review.repo} ${review.label}` + (summary.papers[0] && summary.papers[0].id ? ` · ${summary.papers[0].id}` : "");
  const recent = (store.get("rv:recent") || []).filter((r) => r.route !== route);
  recent.unshift({ route, label });
  store.set("rv:recent", recent.slice(0, 8));
  return units;
}

const homeResults = new Map(); // "owner/repo@sha" → {folder, results} or null: the results.json of a pull request of the first page
/** Where each open pull request stands for this reviewer: its number → core.standing(), with what is known besides. */
function standings(repo, pulls) {
  const out = new Map();
  for (const p of pulls) {
    const label = `#${p.number}`, sha = p.head && p.head.sha, sum = store.get(sumKey(repo, label));
    const st = core.standing(sum, (k) => said(repo, k), sha);
    if (["changes", "agreed", "reviewed"].includes(st.state)) st.sent = sentOf(repo, label, sum.keys);
    const hit = homeResults.get(`${repo}@${sha}`);
    if (st.state === "updated" && hit) st.again = core.paperUnits(hit.folder, hit.results).filter((u) => !said(repo, u.key).v).length;
    out.set(p.number, st);
  }
  return out;
}

async function home(repo) {
  const run = (home.run = {}); // a later visit of the first page takes over
  const draw = (pulls, error) => {
    const typed = app.querySelector(".paste input")?.value || "";
    mount(core.homeHtml({ repo, pulls, recent: store.get("rv:recent") || [], error, mine: pulls ? standings(repo, pulls) : undefined, me: meKept() }));
    const input = app.querySelector(".paste input");
    input.value = typed;
    if (window.matchMedia("(pointer: fine)").matches) input.focus();
  };
  draw(null, "");
  if (!repo) return;
  const mine = shown;
  const listPath = `/repos/${repo}/pulls?state=open&sort=updated&direction=desc&per_page=50`;
  const sigOf = (list) => list.map((p) => [p.number, p.head && p.head.sha, p.title, p.draft, core.reviewersOf(p).join(",")].join(" ")).join("|");
  let pulls;
  try {
    pulls = await api(listPath, { fresh: true });
  } catch (err) {
    if (shown !== mine) return;
    const note = app.querySelector(".home-note");
    if (note) {
      note.className = "problem";
      note.textContent = err.message;
      if (err.wantsToken) note.insertAdjacentHTML("afterend", '<p><button type="button" class="btn token">Add a GitHub token</button></p>');
    }
    return;
  }
  if (shown !== mine || home.run !== run) return;
  draw(pulls, "");
  showing({
    refresh: async () => {
      const next = await api(listPath, { fresh: true });
      if (home.run === run && sigOf(next) !== sigOf(pulls)) home(repo);
    },
  });
  const [owner, name] = repo.split("/");
  // what the pull request itself says: its verdicts, the paper's name
  const fill = (card) => {
    const hit = homeResults.get(`${repo}@${card.dataset.sha}`);
    if (!hit) return;
    const counts = Object.fromEntries(core.VERDICTS.map((v) => [v, hit.results.items.filter((it) => it && it.verdict === v).length]));
    card.querySelector(".rbar").innerHTML = core.verdictBar(counts);
    card.querySelector(".pmc").textContent = hit.folder;
    if (hit.results.paper && hit.results.paper.title) card.querySelector("h2").textContent = hit.results.paper.title;
  };
  const redraw = () => {
    const slot = app.querySelector(".pulls");
    slot.innerHTML = core.pullsHtml(repo, pulls, standings(repo, pulls), meKept());
    slot.querySelectorAll(".rcard").forEach(fill);
  };
  app.querySelectorAll(".rcard").forEach(fill);
  // with a token, GitHub says who reads (asked once): then the cards name the reader's own review requests
  if (token() && !store.get("rv:me")) whoAmI().then((login) => { if (login && home.run === run && app.querySelector(".pulls")) redraw(); });
  pulls.forEach(async (p) => {
    const sha = p.head && p.head.sha, at = `${repo}@${sha}`;
    const id = /PMC\d+/i.exec(`${p.title} ${p.head && p.head.ref}`);
    if (!id || !sha || homeResults.has(at)) return;
    const folder = id[0].toUpperCase(), c = { owner, repo: name, sha };
    const text = (await rawText(c, `${folder}/results.json`)) || (await rawText(c, `${folder}/figure-reproduction/results.json`));
    const results = text && core.parseResults(text);
    homeResults.set(at, results ? { folder, results } : null);
    if (!results || home.run !== run || !app.querySelector(".pulls")) return;
    // a review kept by an older version of the page did not keep what the pull request says of each decision: the results tell
    const key = sumKey(repo, `#${p.number}`), sum = store.get(key);
    const old = sum && !sum.units && Array.isArray(sum.keys) && sum.sha === sha;
    if (old) {
      const by = new Map(core.paperUnits(folder, results).map((u) => [u.key, u]));
      store.set(key, { ...sum, units: sum.keys.map((k) => by.get(k) || { key: k }) });
    }
    if (old || (sum && sum.sha !== sha)) redraw();
    else fill(app.querySelector(`.rcard[data-number="${p.number}"]`));
  });
}

// ------------------------------------------------------------- decisions

const dkey = (repo, k) => `rv:${repo}:${k}`;
const decision = (repo, k) => store.get(dkey(repo, k)) || {};

/**
 * What the reviewer said in one box: {v, note}. v is a verdict (agrees, partly, differs), "pr"
 * (as the pull request says), or "ok" / "no". Decisions saved by older versions keep their note only.
 */
const said = (repo, k) => { const s = decision(repo, k); return { v: ["agrees", "partly", "differs", "pr", "ok", "no"].includes(s.v) ? s.v : "", note: s.note || "" }; };
const LABEL = core.SAID_LABEL;
/** Whether what the reviewer said is what the pull request says. */
const agreesWithPr = (box, v) => core.standOf({ given: box.dataset.given }, v) === "same";

function wireReview(review, c, summary) {
  const repo = review.repo;
  const boxes = [...app.querySelectorAll(".dbox")];
  const grow = (ta) => { ta.style.height = "auto"; ta.style.height = Math.max(36, ta.scrollHeight + 2) + "px"; };
  const open = () => boxes.filter((x) => !said(repo, x.dataset.key).v);
  const unitOf = (box) => summary.units.find((u) => u.key === box.dataset.key) || {};
  const saveUnits = () => store.set(sumKey(repo, review.label), { sha: review.sha, keys: summary.keys, units: summary.units });
  // what the pull request changed since the reviewer decided: said above the question, until it is decided again or seen
  const paintAgain = (box, s) => {
    const u = unitOf(box), line = box.querySelector(".again"), b = u.before;
    line.textContent = "";
    // ours as it was at the commit of the decision, where the figure has a picture of ours
    const asItWas = (sha) => {
      const viewer = box.closest(".station")?.querySelector(".viewer:not(.solo)");
      if (!viewer || !sha) return;
      const show = document.createElement("button");
      show.type = "button";
      show.className = "linkish wasthen";
      show.textContent = "Show ours as it was";
      show.addEventListener("click", () => viewer.showWas(sha, "Ours when you decided"));
      line.append(show, " ");
    };
    if (b && !s.v) {
      const did = !b.v ? "you left a comment" : core.standOf({ given: b.given }, b.v) === "same" ? "you accepted it" : `you said ${LABEL[b.v]}`;
      line.textContent = `Changed since you decided, at ${String(b.sha || "").slice(0, 7)}. Then ${b.givenText ? `the pull request said ${b.givenText} and ` : ""}${did}${b.note ? `: “${b.note}”` : ""}. It asks again. `;
      asItWas(b.sha);
    } else if (u.redrawn && s.v) {
      line.textContent = `Drawn again since you decided, at ${String(u.redrawn.sha || "").slice(0, 7)}. Your decision is kept. `;
      asItWas(u.redrawn.sha);
      const seen = document.createElement("button");
      seen.type = "button";
      seen.className = "linkish seen";
      seen.textContent = "Seen";
      seen.addEventListener("click", () => { delete u.redrawn; saveUnits(); paint(box); paintMap(); });
      line.append(seen);
    }
    line.hidden = !line.textContent;
    return !line.hidden;
  };
  const paint = (box) => {
    const s = said(repo, box.dataset.key);
    box.dataset.v = s.v;
    box.dataset.same = String(agreesWithPr(box, s.v));
    const again = paintAgain(box, s);
    const block = box.closest(".station, .nblock, .outside");
    if (block) block.dataset.mine = !s.v ? (again ? "again" : "") : agreesWithPr(box, s.v) ? "same" : "change";
    const same = !!s.v && agreesWithPr(box, s.v), change = !!s.v && !same;
    // Revise is open while the reviewer picks a verdict of their own, and stays open once there is one
    const differs = box.dataset.ask === "verdict" && (change || box.dataset.open === "1");
    box.querySelectorAll(".decide [data-v]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.v === "same" ? same : b.dataset.v === s.v)));
    box.querySelector(".differ")?.setAttribute("aria-pressed", String(differs));
    const panel = box.querySelector(".mine");
    if (panel) panel.hidden = !differs;
    // the reason shows where the reviewer revises the verdict; a comment on what is accepted is one click away
    const ta = box.querySelector("textarea"), noted = differs || change || !!s.note || box.dataset.note === "1";
    ta.hidden = !noted;
    ta.placeholder = differs || change ? "Why? For the author" : "Comment for the author";
    box.querySelector(".addnote").hidden = !(same && !noted);
    if (document.activeElement !== ta) ta.value = s.note;
    if (noted && ta.value) grow(ta);
    box.querySelector(".state").textContent = !s.v ? "" : s.v === "pr" ? "You accept what the pull request says" : box.dataset.ask === "ok" ? LABEL[s.v]
      : agreesWithPr(box, s.v) ? `You accept: ${LABEL[s.v]}` : `You say: ${LABEL[s.v]}`;
  };
  const rest = app.querySelector(".restbar");
  // the decisions at a glance, apart by how they stand; a name goes to its figure or table
  const maps = [...app.querySelectorAll(".rmap")];
  // The review goes out with one button, named for what it does next. With a token it is submitted as a review
  // of the pull request, and the name says what the review does there: Approve, Request changes or Comment on
  // GitHub. Update review: the text of the review the page submitted at this commit is edited. Open review: that
  // review is as the decisions are now. Add review: no token, so it is copied. A branch has no pull request.
  const sends = [...app.querySelectorAll(".send")], sendNotes = [...app.querySelectorAll(".sendnote")];
  const sigNow = () => core.reviewSig(summary.keys, (k) => said(repo, k));
  const sentNow = () => store.get(sentKey(repo, review.label)) || {};
  // GitHub takes no approval and no request for changes from the author of a pull request: theirs is a comment
  let own = !!review.me && !!review.author && review.me.toLowerCase() === review.author.toLowerCase();
  const eventNow = () => (own ? "COMMENT" : core.reviewEvent(summary.units, (k) => said(repo, k)));
  const paintSend = () => {
    const s = sentNow(), here = !!review.number && !!s.url && s.sha === review.sha, event = eventNow();
    const label = !review.number ? ["Copy review"] : !token() ? ["Add review"] : here && s.sig === sigNow() ? ["Open review"]
      : here && s.state === event ? ["Update review"] : [core.EVENT_LABEL[event], " on GitHub"];
    sends.forEach((b) => {
      if (b.disabled || b.classList.contains("flash")) return;
      b.textContent = label[0];
      if (label[1]) { // where it goes is left out where the bar is narrow
        const where = document.createElement("span");
        where.className = "where";
        where.textContent = label[1];
        b.append(where);
      }
      b.dataset.event = label[1] ? event : "";
    });
  };
  /** What happened to the review, said by the button: text, a link to GitHub, and how to let the page add it itself. */
  const say = (text, link = null, hint = "") => sendNotes.forEach((n) => {
    n.textContent = text;
    if (link) {
      const a = document.createElement("a");
      Object.assign(a, { href: link.href, target: "_blank", rel: "noopener", textContent: link.label });
      n.append(" ", a, ".");
    }
    if (hint) {
      const b = document.createElement("button");
      Object.assign(b, { type: "button", className: "linkish token", textContent: hint === "add" ? "Add a GitHub token" : "Change the token" });
      n.append(" ", b, hint === "add" ? " that may write, and the page submits the review itself." : " for one with Pull requests: write, and the page submits the review itself.");
    }
    n.hidden = !text;
  });
  const paintMap = () => {
    const sent = sentOf(repo, review.label, summary.keys);
    const foot = sent.state === "yes" ? `Review ${sent.how} ${sent.when}. Nothing changed since.` : sent.state === "stale" ? `Your decisions changed since you ${sent.how} the review (${sent.when}).` : "";
    const html = core.mapHtml(summary.units, (k) => said(repo, k), foot);
    maps.forEach((m) => { m.innerHTML = html; });
    paintSend();
  };
  maps.forEach((m) => m.addEventListener("click", (ev) => {
    const chip = ev.target.closest("[data-key]"), box = chip && boxes.find((x) => x.dataset.key === chip.dataset.key);
    if (!box) return;
    if (deck.on) deck.show(deck.cards.findIndex((x) => x.contains(box)));
    else goTo(box);
  }));
  const progress = () => {
    say(""); // what the button said about the review is of before this decision
    const left = open().length;
    const change = boxes.filter((x) => { const v = said(repo, x.dataset.key).v; return v && !agreesWithPr(x, v); }).length;
    app.querySelector(".bar .chg").textContent = change ? ` · ${change} to change` : "";
    paintMap();
    app.querySelector(".bar .done").textContent = boxes.length - left;
    app.querySelector(".bar .all").textContent = boxes.length;
    app.querySelector(".next").hidden = !left;
    rest.hidden = !left;
    rest.querySelector(".restnote").textContent = left === 1 ? "1 is not decided yet." : `${left} are not decided yet.`;
  };
  boxes.forEach((box) => {
    paint(box);
    const decide = (v, opened) => {
      box.dataset.open = opened ? "1" : "";
      const u = unitOf(box);
      if (v && u.redrawn) { delete u.redrawn; saveUnits(); } // looked at again
      store.set(dkey(repo, box.dataset.key), { ...said(repo, box.dataset.key), v });
      paint(box);
      progress();
    };
    box.querySelectorAll(".decide [data-v]").forEach((b) => b.addEventListener("click", () => {
      const s = said(repo, box.dataset.key), inPanel = !!b.closest(".mine");
      // Accept: the pull request's own verdict where it gives one. A second click takes a decision back.
      const v = b.dataset.v !== "same" ? b.dataset.v : ["agrees", "partly", "differs"].includes(box.dataset.given) ? box.dataset.given : "pr";
      const on = b.getAttribute("aria-pressed") === "true";
      decide(on ? "" : v, inPanel);
      // the reason is next; on a touch screen the keyboard would cover the card, so there it waits for a tap
      if (!on && (inPanel || v === "no") && window.matchMedia("(pointer: fine)").matches) box.querySelector("textarea").focus({ preventScroll: true });
      passOn(box);
    }));
    // Revise: the reviewer's own verdict and the reason show; what was accepted is taken back
    box.querySelector(".differ")?.addEventListener("click", (ev) => decide("", ev.currentTarget.getAttribute("aria-pressed") !== "true"));
    box.querySelector(".addnote").addEventListener("click", () => {
      box.dataset.note = "1";
      paint(box);
      box.querySelector("textarea").focus({ preventScroll: true });
    });
    const ta = box.querySelector("textarea");
    ta.addEventListener("input", () => {
      const s = said(repo, box.dataset.key);
      s.note = ta.value;
      store.set(dkey(repo, box.dataset.key), s);
      grow(ta);
      paintMap();
    });
  });
  // What is accepted is passed: on a card the next card comes, on the page the next figure or table
  // that is not decided comes to the top. What is revised stays, for its verdict and reason.
  const passOn = (box) => {
    if (deck.on) return deck.decided(box);
    const s = said(repo, box.dataset.key);
    if (!s.v || !agreesWithPr(box, s.v) || s.note.trim()) return;
    const next = boxes.slice(boxes.indexOf(box) + 1).find((x) => !said(repo, x.dataset.key).v);
    if (!next) return;
    next.focus({ preventScroll: true });
    (next.closest(".station, .nblock, .outside") || next).scrollIntoView({ behavior: still ? "auto" : "smooth", block: "start" });
  };
  // the box the reviewer was in last: "next" goes on from there, also after a click on the button itself
  let last = null;
  boxes.forEach((box) => box.addEventListener("focusin", () => { last = box; }));
  const goTo = (box) => { if (box) { box.focus({ preventScroll: true }); box.scrollIntoView({ block: "center" }); } };
  app.querySelector(".next").addEventListener("click", () => {
    const left = open(), at = boxes.indexOf(last);
    goTo(left.find((x) => boxes.indexOf(x) > at) || left[0]);
  });
  // everything not decided: as the pull request says (its own verdict where it gives one, OK where the question is OK)
  app.querySelectorAll(".rest").forEach((b) => b.addEventListener("click", () => {
    for (const box of open()) {
      const v = box.dataset.ask === "ok" ? "ok" : ["agrees", "partly", "differs"].includes(box.dataset.given) ? box.dataset.given : "pr";
      store.set(dkey(repo, box.dataset.key), { ...said(repo, box.dataset.key), v });
      box.dataset.open = "";
      paint(box);
    }
    progress();
    deck.refresh();
  }));

  // On a phone the review is a deck of cards, like flashcards: one figure or table fills the
  // screen with its verdict buttons below it, and a verdict brings the next card.
  const narrow = window.matchMedia("(max-width: 700px)");
  const deck = {
    on: false, at: 0,
    cards: [...app.querySelectorAll(".station, .nblock, .outside")].filter((x) => x.querySelector(".dbox")),
    bar: app.querySelector(".deckbar"), end: app.querySelector(".deckend"),
    box(i) { return this.cards[i] && this.cards[i].querySelector(".dbox"); },
    refresh() {
      if (!this.on) return;
      const end = this.at >= this.cards.length, left = open().length, all = this.cards.length;
      this.cards.forEach((x, k) => x.classList.toggle("current", k === this.at));
      this.end.hidden = !end;
      this.bar.querySelector(".dtitle").textContent = end ? "Done" : this.box(this.at).dataset.title;
      this.bar.querySelector(".dcount").textContent = end ? "" : `${this.at + 1} / ${all}`;
      this.bar.querySelector(".dprev").disabled = this.at === 0;
      this.bar.querySelector(".dnext").disabled = end;
      this.bar.querySelector(".dprog i").style.width = `${all ? ((all - left) / all) * 100 : 0}%`;
      this.end.querySelector(".dsum").textContent = left ? `${all - left} of ${all} decided. ${left} ${left === 1 ? "is" : "are"} not decided yet.` : `All ${all} decided.`;
      this.end.querySelector(".dfirst").parentElement.hidden = !left;
      this.end.querySelector(".rest").parentElement.hidden = !left;
    },
    show(i) {
      this.at = Math.max(0, Math.min(this.cards.length, i));
      this.refresh();
      const card = this.cards[this.at];
      if (!card) return;
      card.querySelectorAll(".views, .irow, .ofiles").forEach((x) => { x.scrollTop = 0; });
      // one picture at a time: the overlap first, as it shows both
      card.querySelectorAll(".viewer").forEach((v) => { if (!["pub", "ours", "overlay"].includes(v.dataset.mode)) v.setMode(v.querySelector('.pick [data-m="overlay"]') ? "overlay" : v.querySelector(".pick button")?.dataset.m || "ours"); });
    },
    enter() {
      this.on = true;
      document.body.classList.add("deck");
      const first = this.cards.findIndex((x) => !said(repo, x.querySelector(".dbox").dataset.key).v);
      this.show(first === -1 ? this.cards.length : first);
    },
    leave() {
      this.on = false;
      document.body.classList.remove("deck");
      this.end.hidden = true;
      this.cards.forEach((x) => x.classList.remove("current"));
      app.querySelectorAll(".viewer").forEach((v) => v.setMode("side"));
    },
    // a verdict as the pull request says goes straight on; a change stays, for the comment that says why
    decided(box) {
      if (!this.on) return;
      this.refresh();
      const s = said(repo, box.dataset.key);
      if (s.v && agreesWithPr(box, s.v) && !s.note.trim()) {
        const at = this.at;
        setTimeout(() => { if (this.on && this.at === at && this.box(at) === box && said(repo, box.dataset.key).v) this.show(at + 1); }, 350);
      }
    },
  };
  const wantsCards = () => narrow.matches && store.get("rv:view") !== "page" && deck.cards.length > 0;
  deck.bar.querySelector(".dprev").addEventListener("click", () => deck.show(deck.at - 1));
  deck.bar.querySelector(".dnext").addEventListener("click", () => deck.show(deck.at + 1));
  deck.bar.querySelector(".dpage").addEventListener("click", () => { store.set("rv:view", "page"); deck.leave(); });
  app.querySelector(".dcards").addEventListener("click", () => { store.del("rv:view"); deck.enter(); });
  deck.end.querySelector(".dfirst").addEventListener("click", () => deck.show(deck.cards.findIndex((x) => !said(repo, x.querySelector(".dbox").dataset.key).v)));
  boxes.forEach((box) => box.querySelector(".dgo").addEventListener("click", () => deck.show(deck.at + 1)));
  narrow.onchange = () => { if (!app.contains(deck.bar)) return; if (wantsCards() && !deck.on) deck.enter(); else if (!narrow.matches && deck.on) deck.leave(); };
  progress();
  wireReview.keys = (ev) => {
    if (ev.key !== "j" && ev.key !== "k") return;
    const at = boxes.indexOf(last);
    goTo(at === -1 ? boxes[0] : boxes[Math.max(0, Math.min(boxes.length - 1, at + (ev.key === "j" ? 1 : -1)))]);
    ev.preventDefault();
  };

  // the review as text for GitHub: what to change first, what is accepted last
  const reviewText = () => {
    const paper = summary.papers.map((p) => p.id).filter(Boolean).join(", ") || review.label;
    const out = [`### Review of ${paper} at ${review.sha.slice(0, 7)} (${review.label})`, ""];
    const change = [], notOk = [], noted = [], fine = [], undecided = [];
    for (const x of boxes) {
      const s = said(repo, x.dataset.key), note = s.note.trim().replace(/\s*\n\s*/g, " ");
      const title = `**${x.dataset.title}**`, given = x.dataset.givenText;
      if (!s.v) undecided.push(`- ${title}${note ? ": " + note : ""}`);
      else if (s.v === "no") notOk.push(`- ${title}${note ? ": " + note : ""}`);
      else if (!agreesWithPr(x, s.v)) change.push(`- ${title}: ${given} → ${LABEL[s.v]}.${note ? " " + note : ""}`);
      else if (note) noted.push(`- ${title}${given ? ` (${given})` : ""}: ${note}`);
      else fine.push(x.dataset.title + (given ? ` (${given})` : ""));
    }
    for (const [title, rows] of [["Verdicts to change", change], ["Not OK", notOk], ["Accepted, with a comment", noted]]) {
      if (rows.length) out.push(`**${title} (${rows.length})**`, ...rows, "");
    }
    if (fine.length) out.push(`**Accepted (${fine.length}):** ${fine.join("; ")}`, "");
    if (undecided.length) out.push(`**Not decided (${undecided.length})**`, ...undecided, "");
    out.push(`_From the review page: ${location.href.split("#")[0]}_`);
    return out.join("\n");
  };
  const copyText = (text) => (navigator.clipboard && navigator.clipboard.writeText ? navigator.clipboard.writeText(text).then(() => true, () => false) : Promise.resolve(false));
  // the clipboard is closed to the page: the text, to copy by hand
  const showText = (text) => dialog((d) => {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.readOnly = true;
    d.append(ta);
    setTimeout(() => ta.select());
  });
  const openTab = (url) => { const tab = window.open(url, "_blank"); if (tab) tab.opener = null; };
  const flash = (b, label) => {
    b.textContent = label;
    b.classList.add("flash");
    setTimeout(() => { b.classList.remove("flash"); paintSend(); }, 1600);
  };
  /**
   * The review as a review of the pull request, at the commit that was read. The text of the one the page
   * submitted at this commit with the same event is edited (id); otherwise a new one is submitted: what a
   * submitted review does (approve, request changes, comment) cannot be changed on GitHub.
   */
  const postReview = async (text, event, id) => {
    const reviews = `/repos/${c.owner}/${c.repo}/pulls/${review.number}/reviews`;
    if (id) {
      try {
        return { ...(await write("PUT", `${reviews}/${id}`, { body: text })), event, updated: true };
      } catch (err) {
        if (err.status !== 404) throw err; // the review is gone: a new one
      }
    }
    try {
      return { ...(await write("POST", reviews, { commit_id: review.sha, body: text, event })), event };
    } catch (err) {
      // 422 to an approval or a request for changes: the pull request is the reader's own. Then it is a comment.
      if (err.status !== 422 || event === "COMMENT") throw err;
      return { ...(await write("POST", reviews, { commit_id: review.sha, body: text, event: "COMMENT" })), event: "COMMENT", asAuthor: true };
    }
  };
  sends.forEach((send) => send.addEventListener("click", async () => {
    const text = reviewText(), sig = sigNow(), s = sentNow(), pull = `#${review.number}`;
    // kept, so the first page can say whether this review went out and whether it changed after
    const keep = (more = {}) => { store.set(sentKey(repo, review.label), { at: Date.now(), sig, ...more }); paintMap(); };
    const copy = async () => {
      const ok = await copyText(text);
      if (ok) flash(send, "Copied"); else showText(text);
      keep();
      return ok;
    };
    if (!review.number) return void (await copy(), say(""));
    const here = !!s.url && s.sha === review.sha, event = eventNow();
    if (here && s.sig === sig) {
      openTab(s.url);
      return say(`Your review is on ${pull} as it is here.`, { href: s.url, label: "Open it on GitHub" });
    }
    let why = "";
    if (token()) {
      sends.forEach((b) => { b.disabled = true; });
      const edits = here && s.state === event;
      send.textContent = edits ? "Updating…" : "Submitting…";
      let made = null, failed = null;
      try {
        made = await postReview(text, event, edits ? s.id : null);
      } catch (err) {
        failed = err;
      }
      sends.forEach((b) => { b.disabled = false; });
      if (made) {
        if (made.asAuthor) own = true;
        keep({ id: made.id, url: made.html_url, sha: review.sha, state: made.event });
        flash(send, made.updated ? "Updated" : "Submitted");
        openTab(made.html_url);
        const does = made.event !== "COMMENT" ? `and ${core.EVENT_DOES[made.event]}`
          : own ? "as a comment: GitHub takes no approval and no request for changes from the author of a pull request" : "as a comment: not everything is decided yet";
        return say(made.updated ? `Your review on ${pull} is updated.` : `Your review is on ${pull} ${does}.`, { href: made.html_url, label: "Open it on GitHub" });
      }
      paintSend();
      // 401: the token is refused. 403, 404: it may read and not write. Then the review is copied, as with no token.
      if (![401, 403, 404].includes(failed.status)) return say(`${failed instanceof GitHubError ? failed.message : "GitHub could not be asked."} The review is not added.`);
      why = failed.status === 401 ? "GitHub refused the token" : "The token may not review on this repository";
    }
    // no token, or one that may not write: the review is copied, and the pull request opens for it to be pasted
    const box = `${review.url}#issuecomment-new`;
    if (await copy()) openTab(box);
    say(`${why ? `${why}, so the review is copied` : "The review is copied"}. Paste it in the comment box of ${pull}.`, { href: box, label: `Open ${pull}` }, why ? "change" : "add");
  }));

  // a picture of a private repository cannot come from raw.githubusercontent.com: ask the API
  const viaApi = (img) => img.addEventListener("error", async () => {
    if (!token() || img.dataset.tried === img.src) return;
    img.dataset.tried = img.src;
    try {
      const r = await fetch(`${API}/repos/${c.owner}/${c.repo}/contents/${core.encPath(img.dataset.path)}?ref=${img.dataset.sha || c.sha}`, {
        headers: { Accept: "application/vnd.github.raw+json", Authorization: `Bearer ${token()}` },
      });
      if (r.ok) { const url = URL.createObjectURL(await r.blob()); img.dataset.tried = url; img.src = url; }
    } catch { /* stays broken */ }
  });
  // figure viewers
  const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  app.querySelectorAll(".viewer").forEach((v) => {
    let timer = null;
    const stage = v.querySelector(".stage"), range = v.querySelector(".swipe");
    v.setMode = (m) => {
      v.dataset.mode = m;
      v.querySelectorAll(".modes button, .pick button").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset.m === m)));
      v.querySelectorAll(".versions button").forEach((x) => x.setAttribute("aria-current", String(m === "was" ? x.dataset.sha === v.dataset.was : !!x.dataset.now)));
      clearInterval(timer);
      v.classList.remove("b");
      if (m === "blink" && !still) timer = setInterval(() => { if (v.isConnected) v.classList.toggle("b"); else clearInterval(timer); }, 800);
    };
    v.querySelectorAll(".modes button, .pick button").forEach((b) => b.addEventListener("click", () => { delete v.dataset.flip; v.setMode(b.dataset.m); }));
    // Ours as it was at another commit, in the place of ours. While it is up, a click on the picture goes between it and ours as it is now.
    const ours = stage.querySelector("figure.ours img");
    v.showWas = (sha, caption) => {
      let fig = stage.querySelector("figure.was");
      if (!fig) {
        fig = document.createElement("figure");
        fig.className = "was";
        fig.innerHTML = '<figcaption></figcaption><img alt="">';
        stage.insertBefore(fig, range);
        viaApi(fig.querySelector("img"));
      }
      fig.querySelector("figcaption").textContent = caption;
      const img = fig.querySelector("img");
      img.alt = caption;
      img.dataset.path = ours.dataset.path;
      img.dataset.sha = sha;
      img.src = rawUrl({ owner: c.owner, repo: c.repo, sha }, ours.dataset.path);
      v.dataset.was = sha;
      v.dataset.flip = "1";
      v.setMode("was");
      v.scrollIntoView({ block: "nearest" });
    };
    const earlier = v.querySelector(".earlier"), versions = v.querySelector(".versions");
    if (earlier) earlier.addEventListener("click", async () => {
      earlier.disabled = true;
      earlier.textContent = "Reading the versions…";
      try {
        const path = earlier.dataset.path, commits = `/repos/${c.owner}/${c.repo}/commits`;
        // the commits that wrote the picture, and the commits of the change from its head back (asked once for
        // the review): where a version is among them is how many commits ago it was
        const [wrote, line] = await Promise.all([api(`${commits}?path=${encodeURIComponent(path)}&sha=${c.sha}&per_page=12`), api(`${commits}?sha=${c.sha}&per_page=100`).catch(() => [])]);
        const at = new Map(line.map((x, i) => [x.sha, i]));
        const when = (iso) => new Date(iso).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
        versions.innerHTML = core.versionsHtml(wrote.map((x) => ({
          sha: x.sha, when: when((x.commit.committer || x.commit.author).date), message: x.commit.message.split("\n")[0],
          ago: at.has(x.sha) ? at.get(x.sha) : null, src: rawUrl({ ...c, sha: x.sha }, path),
        })), { path, beyond: line.length >= 100 ? line.length : 0 });
        versions.querySelectorAll("img").forEach(viaApi);
        versions.hidden = false;
        earlier.parentElement.hidden = true;
      } catch (err) {
        earlier.disabled = false;
        earlier.textContent = `${err instanceof GitHubError ? err.message : "The versions could not be read."} Try again`;
      }
    });
    if (versions) versions.addEventListener("click", (ev) => {
      const b = ev.target.closest("button[data-sha]");
      if (!b) return;
      if (b.dataset.now) { delete v.dataset.flip; v.setMode("ours"); } else v.showWas(b.dataset.sha, b.dataset.ago ? `Ours, ${b.dataset.ago} (${b.dataset.when})` : `Ours on ${b.dataset.when}`);
    });
    if (range) range.addEventListener("input", () => stage.style.setProperty("--cut", range.value + "%"));
    // the pictures there are, each of which can show alone and large: original, ours, overlap
    const singles = [["pub", ".pub"], ["ours", ".ours"], ["overlay", ".ovl"]].filter(([, cls]) => stage.querySelector(`figure${cls}`)).map(([m]) => m);
    stage.addEventListener("click", (ev) => {
      if (ev.target === range || v.dataset.mode === "swipe") return;
      if (v.dataset.mode === "blink") return void v.classList.toggle("b");
      if (v.dataset.mode === "was") return void v.setMode("ours");
      if (v.dataset.mode === "ours" && v.dataset.flip) return void v.setMode("was");
      const at = singles.indexOf(v.dataset.mode);
      // a large picture (and a card's picture): a click shows the next one, so two can be told apart in place
      if (at !== -1) return void v.setMode(singles.length > 1 ? singles[(at + 1) % singles.length] : document.body.classList.contains("deck") ? singles[0] : "side");
      // side by side: the picture that is clicked opens large
      const fig = ev.target.closest("figure");
      if (!fig || document.body.classList.contains("deck")) return;
      v.setMode(fig.classList.contains("pub") ? "pub" : fig.classList.contains("ovl") ? "overlay" : "ours");
      v.scrollIntoView({ block: "nearest" });
    });
    const first = stage.querySelector("img");
    const size = () => {
      if (!first.naturalWidth) return;
      stage.style.setProperty("--ar", `${first.naturalWidth} / ${first.naturalHeight}`);
      const wide = first.naturalWidth / first.naturalHeight;
      stage.style.setProperty("--nw", `${first.naturalWidth}px`);
      stage.style.setProperty("--fit", wide >= 1 ? `calc(82vh * ${wide.toFixed(4)})` : "100%"); // a wide picture, large, fits the window
    };
    first.addEventListener("load", size);
    size();
  });
  app.querySelectorAll("img[data-path]").forEach(viaApi);

  // code: a new file is read when it is opened
  app.querySelectorAll("details.file").forEach((d) => {
    const load = async () => {
      const slot = d.querySelector(".lazy");
      if (!d.open || !slot || d.dataset.loading) return;
      d.dataset.loading = "1";
      const text = await rawText(c, d.dataset.path);
      if (text === null) { slot.textContent = "Could not read this file. Open it on GitHub."; slot.classList.remove("lazy"); return; }
      slot.outerHTML = core.wholeFileHtml(await codeLines(d.dataset.path, text));
    };
    d.addEventListener("toggle", load);
    load();
  });

  if (wantsCards()) deck.enter();

  // checks of the head commit, when GitHub has some
  api(`/repos/${c.owner}/${c.repo}/commits/${c.sha}/check-runs?per_page=100`).then((data) => {
    const runs = data.check_runs || [], slot = app.querySelector(".refline .ci");
    if (!runs.length || !slot) return;
    const bad = ["failure", "timed_out", "cancelled", "action_required", "startup_failure"];
    const state = runs.some((r) => r.status !== "completed") ? "running" : runs.some((r) => bad.includes(r.conclusion)) ? "failed" : "passed";
    if (state === "running") cache.delete(`/repos/${c.owner}/${c.repo}/commits/${c.sha}/check-runs?per_page=100`);
    slot.outerHTML = `<span class="chip ci-${state}">checks ${state}</span>`;
  }).catch(() => {});
}

let hljs = null;
async function codeLines(path, text) {
  const lang = core.languageOf(path);
  const plain = () => text.replace(/\n$/, "").split("\n").map(core.esc);
  if (!lang || text.length > 400000) return plain();
  try {
    if (!hljs) {
      const [main, groovy] = await Promise.all([import("./vendor/highlight-11.12.0.min.mjs"), import("./vendor/highlight-11.12.0-groovy.min.mjs")]);
      main.default.registerLanguage("groovy", groovy.default);
      hljs = main.default;
    }
    if (!hljs.getLanguage(lang)) return plain();
    return core.splitHighlighted(hljs.highlight(text.replace(/\n$/, ""), { language: lang, ignoreIllegals: true }).value);
  } catch {
    return plain();
  }
}

// --------------------------------------------------------- the whole page

function dialog(fill) {
  const d = document.createElement("dialog");
  fill(d);
  const close = document.createElement("button");
  close.type = "button";
  close.textContent = "Close";
  close.className = "btn";
  close.addEventListener("click", () => d.close());
  d.append(close);
  d.addEventListener("close", () => d.remove());
  document.body.append(d);
  d.showModal();
  return d;
}
function tokenDialog() {
  dialog((d) => {
    d.insertAdjacentHTML("beforeend",
      "<h3>GitHub token</h3><p class=\"note\">Without a token GitHub allows this page 60 requests an hour from your network. " +
      "A token lifts that, and lets the page read private repositories you can read. It stays in this browser and goes only to api.github.com. " +
      "A fine-grained token with read-only access is enough to read. For the page to submit your review to the pull request itself " +
      "(approve, request changes or comment), the token needs Pull requests: Read and write for that repository; with less, the review is copied for you to paste.</p>" +
      '<input type="password" class="tok" autocomplete="off" placeholder="github_pat_…" aria-label="GitHub token">' +
      '<p class="row"><button type="button" class="btn save">Save</button> <button type="button" class="btn forget">Remove the token</button></p>');
    d.querySelector(".tok").value = token();
    d.querySelector(".save").addEventListener("click", () => {
      const v = d.querySelector(".tok").value.trim();
      if (v) store.set("rv:token", v); else store.del("rv:token");
      store.del("rv:me");
      cache.clear();
      d.close();
      render();
    });
    d.querySelector(".forget").addEventListener("click", () => { store.del("rv:token"); store.del("rv:me"); cache.clear(); d.close(); render(); });
  });
}
function openLink(text) {
  const link = core.parseLink(text, DEFAULT_REPO);
  const note = app.querySelector(".paste-error");
  if (!link) {
    if (note) note.textContent = "That is not a GitHub pull request or branch link.";
    return false;
  }
  go(core.routeOf(link));
  return true;
}

document.addEventListener("submit", (ev) => {
  if (!ev.target.matches(".paste")) return;
  ev.preventDefault();
  openLink(ev.target.elements.link.value);
});
// pasting a link anywhere on the first page opens it at once
document.addEventListener("paste", (ev) => {
  if (!app.querySelector(".paste") || ev.target.closest("dialog")) return;
  const text = (ev.clipboardData || window.clipboardData).getData("text");
  const link = core.parseLink(text, "");
  if (link && link.kind !== "repo") { ev.preventDefault(); go(core.routeOf(link)); }
});
document.addEventListener("click", (ev) => {
  if (ev.target.closest(".token")) return tokenDialog();
  const a = ev.target.closest("a[href]");
  if (!a || ev.metaKey || ev.ctrlKey || ev.shiftKey || ev.button) return;
  const href = a.getAttribute("href");
  if (href === "./" || href.startsWith("?r=")) { ev.preventDefault(); go(href); return; }
});
document.addEventListener("keydown", (ev) => {
  if (ev.metaKey || ev.ctrlKey || ev.altKey || /^(TEXTAREA|INPUT|SELECT)$/.test(ev.target.tagName) || !app.querySelector(".dbox")) return;
  wireReview.keys?.(ev);
});
window.addEventListener("popstate", () => { if (location.search !== shown) render(); });
render();
