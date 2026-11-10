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
const cache = new Map();
async function api(path) {
  if (cache.has(path)) return cache.get(path);
  const headers = { Accept: "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28" };
  if (token()) headers.Authorization = `Bearer ${token()}`;
  let res;
  try {
    res = await fetch(API + path, { headers });
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
  cache.set(path, data);
  return data;
}
async function apiAll(path, pages = 30) {
  const out = [];
  for (let page = 1; page <= pages; page++) {
    const part = await api(`${path}${path.includes("?") ? "&" : "?"}per_page=100&page=${page}`);
    out.push(...part);
    if (part.length < 100) break;
  }
  return out;
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
    const pr = await api(`${base}/pulls/${link.number}`);
    apiFiles = await apiAll(`${base}/pulls/${link.number}/files`);
    baseSha = pr.base.sha;
    review = {
      label: `#${pr.number}`, title: pr.title, url: pr.html_url, number: pr.number, branch: pr.head.ref,
      author: pr.user && pr.user.login, updated: pr.updated_at, draft: pr.draft, sha: pr.head.sha,
      notes: pr.mergeable_state === "dirty" ? [`Conflicts with ${pr.base.ref}. It needs an update before it can merge.`] : [],
    };
  } else {
    const info = await api(base);
    const baseRef = link.base || info.default_branch;
    // a tree link can end in a path: try the whole text as the branch, then without its last parts
    let branch = link.branch, cmp = null, last = null;
    for (let i = 0; i < 5 && branch; i++) {
      try {
        cmp = await api(`${base}/compare/${core.encPath(baseRef)}...${core.encPath(branch)}`);
        break;
      } catch (err) {
        last = err;
        if (err.status !== 404 || !branch.includes("/")) break;
        branch = branch.slice(0, branch.lastIndexOf("/"));
      }
    }
    if (!cmp) throw last;
    const open = await api(`${base}/pulls?state=open&head=${encodeURIComponent(`${owner}:${branch}`)}`).catch(() => []);
    if (open.length) return loadReview({ owner, repo, kind: "pull", number: open[0].number });
    const tip = cmp.commits && cmp.commits.length ? cmp.commits[cmp.commits.length - 1] : await api(`${base}/commits/${core.encPath(branch)}`);
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
      if (!mine.some((p) => p.includes("/published/"))) {
        // a change to a paper that is already in the repository: its published figures are not in the change
        const dir = await api(`${base}/contents/${core.encPath(folder)}/figure-reproduction/published?ref=${review.sha}`).catch(() => []);
        mine = mine.concat((Array.isArray(dir) ? dir : []).map((d) => d.path));
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
  if (!link || link.kind === "repo") return home(link ? `${link.owner}/${link.repo}` : DEFAULT_REPO);
  const name = link.kind === "pull" ? `#${link.number}` : link.branch;
  messagePage(`Reading ${name} of ${link.owner}/${link.repo} from GitHub…`, { busy: true });
  window.scrollTo(0, 0);
  try {
    const { review, c } = await loadReview(link);
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
    wireReview(review, c, summary);
    remember(review, route, summary);
    if (location.hash) document.getElementById(location.hash.slice(1))?.scrollIntoView();
  } catch (err) {
    if (!(err instanceof GitHubError)) console.error(err);
    messagePage(err instanceof GitHubError ? err.message : `This page could not be drawn: ${err.message}`, { wantsToken: err.wantsToken });
  }
}

function remember(review, route, summary) {
  const keys = summary.papers.flatMap((p) => p.cards);
  store.set(`rv:sum:${review.repo}:${review.label}`, { sha: review.sha, keys });
  const label = `${review.repo} ${review.label}` + (summary.papers[0] && summary.papers[0].id ? ` · ${summary.papers[0].id}` : "");
  const recent = (store.get("rv:recent") || []).filter((r) => r.route !== route);
  recent.unshift({ route, label });
  store.set("rv:recent", recent.slice(0, 8));
}

async function home(repo) {
  const draw = (pulls, error) => {
    const typed = app.querySelector(".paste input")?.value || "";
    mount(core.homeHtml({ repo, pulls, recent: store.get("rv:recent") || [], error }));
    const input = app.querySelector(".paste input");
    input.value = typed;
    if (window.matchMedia("(pointer: fine)").matches) input.focus();
  };
  draw(null, "");
  if (!repo) return;
  const mine = shown;
  let pulls;
  try {
    pulls = await api(`/repos/${repo}/pulls?state=open&sort=updated&direction=desc&per_page=50`);
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
  if (shown !== mine) return;
  draw(pulls, "");
  const [owner, name] = repo.split("/");
  app.querySelectorAll(".rcard").forEach(async (card) => {
    const sum = store.get(`rv:sum:${repo}:#${card.dataset.number}`);
    const progress = card.querySelector(".progress");
    if (sum && sum.keys.length) {
      const done = sum.keys.filter((k) => decision(repo, k).d).length;
      progress.innerHTML = `<b>${done}</b> of <b>${sum.keys.length}</b> decided` + (sum.sha !== card.dataset.sha ? " · changed since you opened it" : "");
      card.classList.add(done === sum.keys.length ? "alldone" : done ? "started" : "seen");
    } else {
      progress.textContent = "Not opened yet";
    }
    const id = /PMC\d+/i.exec(card.dataset.title + " " + card.dataset.ref);
    if (!id || !card.dataset.sha) return;
    const folder = id[0].toUpperCase(), c = { owner, repo: name, sha: card.dataset.sha };
    const text = (await rawText(c, `${folder}/results.json`)) || (await rawText(c, `${folder}/figure-reproduction/results.json`));
    const results = text && core.parseResults(text);
    if (!results || !card.isConnected) return;
    const counts = Object.fromEntries(core.VERDICTS.map((v) => [v, results.items.filter((it) => it && it.verdict === v).length]));
    card.querySelector(".rbar").innerHTML = core.verdictBar(counts);
    card.querySelector(".pmc").textContent = folder;
    if (results.paper && results.paper.title) card.querySelector("h2").textContent = results.paper.title;
  });
}

// ------------------------------------------------------------- decisions

const dkey = (repo, k) => `rv:${repo}:${k}`;
const decision = (repo, k) => store.get(dkey(repo, k)) || {};

function wireReview(review, c, summary) {
  const repo = review.repo;
  const cards = [...app.querySelectorAll(".card")];
  const grow = (ta) => { ta.style.height = "auto"; ta.style.height = Math.max(36, ta.scrollHeight + 2) + "px"; };
  const paint = (card) => {
    const s = decision(repo, card.dataset.key);
    card.dataset.d = s.d || "";
    card.querySelectorAll(".decide button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.d === s.d)));
    const ta = card.querySelector("textarea");
    if (document.activeElement !== ta) { ta.value = s.note || ""; if (ta.value) grow(ta); }
    card.querySelector(".state").textContent = s.d === "ok" ? "Accepted" : s.d === "work" ? "Needs work" : "";
  };
  const progress = () => {
    app.querySelector(".bar .done").textContent = cards.filter((x) => decision(repo, x.dataset.key).d).length;
    app.querySelector(".bar .all").textContent = cards.length;
  };
  const decide = (card, d) => {
    const s = decision(repo, card.dataset.key);
    s.d = s.d === d ? "" : d;
    store.set(dkey(repo, card.dataset.key), s);
    card.classList.remove("peek");
    paint(card);
    progress();
    if (s.d === "work") card.querySelector("textarea").focus();
  };
  cards.forEach((card) => {
    paint(card);
    card.querySelectorAll(".decide button").forEach((b) => b.addEventListener("click", () => decide(card, b.dataset.d)));
    const ta = card.querySelector("textarea");
    ta.addEventListener("input", () => {
      const s = decision(repo, card.dataset.key);
      s.note = ta.value;
      store.set(dkey(repo, card.dataset.key), s);
      grow(ta);
    });
    card.querySelector(".chead").addEventListener("click", () => { if (card.dataset.d === "ok") card.classList.toggle("peek"); });
  });
  progress();
  const reveal = () => {
    const t = location.hash && document.getElementById(location.hash.slice(1));
    if (t && t.classList.contains("card")) t.classList.add("peek");
  };
  reveal();
  wireReview.reveal = reveal;
  wireReview.keys = (ev) => {
    const at = cards.indexOf(document.activeElement.closest ? document.activeElement.closest(".card") : null);
    if (ev.key === "j" || ev.key === "k") {
      const next = at === -1 ? cards[0] : cards[Math.max(0, Math.min(cards.length - 1, at + (ev.key === "j" ? 1 : -1)))];
      if (next) { next.focus({ preventScroll: true }); next.scrollIntoView({ block: "center" }); }
      ev.preventDefault();
    } else if ((ev.key === "a" || ev.key === "w") && at !== -1) {
      decide(cards[at], ev.key === "a" ? "ok" : "work");
      ev.preventDefault();
    }
  };

  // the review as text for GitHub
  const reviewText = () => {
    const out = [];
    app.querySelectorAll(".paper").forEach((p) => {
      out.push(`### Review of ${p.dataset.paper || review.label} at ${review.sha.slice(0, 7)} (${review.label})`, "");
      const groups = { work: [], ok: [], "": [] };
      p.querySelectorAll(".card").forEach((x) => {
        const s = decision(repo, x.dataset.key);
        groups[s.d || ""].push({ title: x.dataset.title, note: (s.note || "").trim() });
      });
      for (const [title, rows] of [["Needs work", groups.work], ["Accepted", groups.ok], ["Not decided", groups[""]]]) {
        if (!rows.length) continue;
        out.push(`**${title} (${rows.length})**`, ...rows.map((r) => `- **${r.title}**` + (r.note ? ": " + r.note.replace(/\s*\n\s*/g, " ") : "")), "");
      }
    });
    out.push(`_From the review page: ${location.href.split("#")[0]}_`);
    return out.join("\n");
  };
  const copy = app.querySelector(".copy");
  copy.addEventListener("click", () => {
    const text = reviewText();
    const done = () => {
      copy.textContent = "Copied";
      copy.classList.add("flash");
      setTimeout(() => { copy.textContent = "Copy review"; copy.classList.remove("flash"); }, 1600);
    };
    const fallback = () => dialog((d) => {
      const ta = document.createElement("textarea");
      ta.value = text;
      ta.readOnly = true;
      d.append(ta);
      setTimeout(() => ta.select());
    });
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, fallback);
    else fallback();
  });

  // figure viewers
  const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  app.querySelectorAll(".viewer").forEach((v) => {
    let timer = null;
    const stage = v.querySelector(".stage"), range = v.querySelector(".swipe");
    v.querySelectorAll(".modes button").forEach((b) => b.addEventListener("click", () => {
      v.dataset.mode = b.dataset.m;
      v.querySelectorAll(".modes button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      clearInterval(timer);
      v.classList.remove("b");
      if (b.dataset.m === "blink" && !still) timer = setInterval(() => { if (v.isConnected) v.classList.toggle("b"); else clearInterval(timer); }, 800);
    }));
    if (range) range.addEventListener("input", () => stage.style.setProperty("--cut", range.value + "%"));
    stage.addEventListener("click", (ev) => { if (v.dataset.mode === "blink" && ev.target !== range) v.classList.toggle("b"); });
    const first = stage.querySelector("img");
    const size = () => { if (first.naturalWidth) stage.style.setProperty("--ar", `${first.naturalWidth} / ${first.naturalHeight}`); };
    first.addEventListener("load", size);
    size();
  });
  // a picture of a private repository cannot come from raw.githubusercontent.com: ask the API
  app.querySelectorAll("img[data-path]").forEach((img) => img.addEventListener("error", async () => {
    if (!token() || img.dataset.tried) return;
    img.dataset.tried = "1";
    try {
      const r = await fetch(`${API}/repos/${c.owner}/${c.repo}/contents/${core.encPath(img.dataset.path)}?ref=${c.sha}`, {
        headers: { Accept: "application/vnd.github.raw+json", Authorization: `Bearer ${token()}` },
      });
      if (r.ok) img.src = URL.createObjectURL(await r.blob());
    } catch { /* stays broken */ }
  }, { once: true }));

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

  // checks of the head commit, when GitHub has some
  api(`/repos/${c.owner}/${c.repo}/commits/${c.sha}/check-runs?per_page=100`).then((data) => {
    const runs = data.check_runs || [], slot = app.querySelector(".refline .ci");
    if (!runs.length || !slot) return;
    const bad = ["failure", "timed_out", "cancelled", "action_required", "startup_failure"];
    const state = runs.some((r) => r.status !== "completed") ? "running" : runs.some((r) => bad.includes(r.conclusion)) ? "failed" : "passed";
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
      "A fine-grained token with read-only access is enough.</p>" +
      '<input type="password" class="tok" autocomplete="off" placeholder="github_pat_…" aria-label="GitHub token">' +
      '<p class="row"><button type="button" class="btn save">Save</button> <button type="button" class="btn forget">Remove the token</button></p>');
    d.querySelector(".tok").value = token();
    d.querySelector(".save").addEventListener("click", () => {
      const v = d.querySelector(".tok").value.trim();
      if (v) store.set("rv:token", v); else store.del("rv:token");
      cache.clear();
      d.close();
      render();
    });
    d.querySelector(".forget").addEventListener("click", () => { store.del("rv:token"); cache.clear(); d.close(); render(); });
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
  if (href.startsWith("#d-")) document.getElementById(href.slice(1))?.classList.add("peek"); // a folded decision opens
});
document.addEventListener("keydown", (ev) => {
  if (ev.metaKey || ev.ctrlKey || ev.altKey || /^(TEXTAREA|INPUT|SELECT)$/.test(ev.target.tagName) || !app.querySelector(".card")) return;
  wireReview.keys?.(ev);
});
window.addEventListener("hashchange", () => wireReview.reveal?.());
window.addEventListener("popstate", () => { if (location.search !== shown) render(); });
render();
