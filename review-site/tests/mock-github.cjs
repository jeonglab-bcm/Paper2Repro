// A stand-in for api.github.com and raw.githubusercontent.com that answers from a local clone,
// in the shape GitHub answers. The browser tests route the two hosts here, so the app under
// test is the same code that runs against GitHub.
const { execFileSync } = require("child_process");

function git(dir, args, text = true) {
  const out = execFileSync("git", ["-C", dir, ...args], { maxBuffer: 512 * 1024 * 1024, stdio: ["ignore", "pipe", "ignore"] });
  return text ? out.toString("utf8") : out;
}
const TYPES = { png: "image/png", jpg: "image/jpeg", jpeg: "image/jpeg", gif: "image/gif", webp: "image/webp", svg: "image/svg+xml", json: "application/json" };

/** pulls: [{number, title, user: {login}, head: {ref}, updated_at, draft, git}] where git is the local ref of its head. */
/** judge: {at: "owner/repo/branch", file(sha) -> the AI judge's saved verdicts for that commit, or null}. */
function makeMock({ clone, owner, repo, pulls, base = "origin/main", defaultBranch = "main", branches = {}, judge = null }) {
  const sha = (ref) => git(clone, ["rev-parse", "--verify", `${ref}^{commit}`]).trim();
  const filesCache = new Map();
  const state = { calls: 0, rateLimited: false };

  function files(baseSha, headSha) {
    const key = `${baseSha}..${headSha}`;
    if (filesCache.has(key)) return filesCache.get(key);
    const st = git(clone, ["diff", "--name-status", "--no-renames", "-z", baseSha, headSha]).split("\0");
    const status = new Map();
    for (let i = 0; i + 1 < st.length; i += 2) status.set(st[i + 1], st[i]);
    const out = [];
    for (const rec of git(clone, ["diff", "--numstat", "--no-renames", "-z", baseSha, headSha]).split("\0")) {
      if (!rec) continue;
      const [a, d, ...rest] = rec.split("\t");
      const filename = rest.join("\t"), binary = a === "-";
      const f = {
        filename, status: { A: "added", D: "removed" }[status.get(filename)] || "modified",
        additions: binary ? 0 : Number(a), deletions: binary ? 0 : Number(d), changes: binary ? 0 : Number(a) + Number(d),
      };
      if (!binary && f.changes <= 3000) {
        const diff = git(clone, ["diff", "--no-renames", "-U3", baseSha, headSha, "--", filename]);
        const at = diff.indexOf("\n@@");
        if (at >= 0) f.patch = diff.slice(at + 1).replace(/\n$/, "");
      }
      out.push(f);
    }
    filesCache.set(key, out);
    return out;
  }
  function pullObject(p) {
    const head = sha(p.git), mb = git(clone, ["merge-base", base, head]).trim();
    return {
      number: p.number, title: p.title, user: p.user, draft: !!p.draft, updated_at: p.updated_at, state: "open",
      html_url: `https://github.com/${owner}/${repo}/pull/${p.number}`, mergeable_state: p.mergeable_state || "clean",
      head: { ref: (p.head && p.head.ref) || "", sha: head }, base: { ref: defaultBranch, sha: mb },
    };
  }

  async function handle(route) {
    const url = new URL(route.request().url());
    const cors = { "access-control-allow-origin": "*", "access-control-expose-headers": "x-ratelimit-remaining, x-ratelimit-reset" };
    const json = (status, body, headers = {}) => route.fulfill({ status, contentType: "application/json", headers: { ...cors, ...headers }, body: JSON.stringify(body) });
    try {
      if (url.hostname === "raw.githubusercontent.com") {
        const j = judge && new RegExp(`^/${judge.at}/judge/${owner}/${repo}/([0-9a-f]{40})\\.json$`).exec(url.pathname);
        if (j) {
          const body = judge.file(j[1]);
          return body ? json(200, body) : route.fulfill({ status: 404, headers: cors, body: "404: Not Found" });
        }
        const m = /^\/([^/]+)\/([^/]+)\/([0-9a-f]{40})\/(.+)$/.exec(decodeURIComponent(url.pathname));
        if (!m || m[1] !== owner || m[2] !== repo) return route.fulfill({ status: 404, headers: cors, body: "404: Not Found" });
        try {
          const body = git(clone, ["show", `${m[3]}:${m[4]}`], false);
          const ext = m[4].split(".").pop().toLowerCase();
          return route.fulfill({ status: 200, headers: cors, contentType: TYPES[ext] || "text/plain; charset=utf-8", body });
        } catch {
          return route.fulfill({ status: 404, headers: cors, body: "404: Not Found" });
        }
      }
      state.calls++;
      if (state.rateLimited) return json(403, { message: "API rate limit exceeded" }, { "x-ratelimit-remaining": "0", "x-ratelimit-reset": String(Math.floor(Date.now() / 1000) + 1800) });
      const path = decodeURIComponent(url.pathname), q = url.searchParams;
      const root = `/repos/${owner}/${repo}`;
      if (!path.startsWith(root)) return json(404, { message: "Not Found" });
      const rest = path.slice(root.length);
      let m;
      if (rest === "") return json(200, { default_branch: defaultBranch, private: false, full_name: `${owner}/${repo}` });
      if (rest === "/pulls") {
        let list = pulls.map(pullObject);
        if (q.get("head")) list = list.filter((p) => `${owner}:${p.head.ref}` === q.get("head"));
        return json(200, list);
      }
      if ((m = /^\/pulls\/(\d+)$/.exec(rest))) {
        const p = pulls.find((x) => x.number === Number(m[1]));
        return p ? json(200, pullObject(p)) : json(404, { message: "Not Found" });
      }
      if ((m = /^\/pulls\/(\d+)\/files$/.exec(rest))) {
        const p = pulls.find((x) => x.number === Number(m[1]));
        if (!p) return json(404, { message: "Not Found" });
        const o = pullObject(p), all = files(o.base.sha, o.head.sha);
        const per = Number(q.get("per_page") || 30), page = Number(q.get("page") || 1);
        return json(200, all.slice((page - 1) * per, page * per));
      }
      if ((m = /^\/compare\/(.+?)\.\.\.(.+)$/.exec(rest))) {
        const ref = branches[m[2]];
        if (!ref) return json(404, { message: "Not Found" });
        const head = sha(ref), mb = git(clone, ["merge-base", base, head]).trim();
        const [name, date] = git(clone, ["log", "-1", "--format=%an%x09%cI", head]).trim().split("\t");
        return json(200, { merge_base_commit: { sha: mb }, commits: head === mb ? [] : [{ sha: head, commit: { author: { name, date } } }], files: files(mb, head).slice(0, 300) });
      }
      if (/^\/commits\/[0-9a-f]{40}\/check-runs$/.test(rest)) return json(200, { total_count: 1, check_runs: [{ status: "completed", conclusion: "success" }] });
      if ((m = /^\/contents\/(.+)$/.exec(rest))) {
        const names = git(clone, ["ls-tree", "--name-only", q.get("ref"), m[1] + "/"]).split("\n").filter(Boolean);
        return names.length ? json(200, names.map((p) => ({ path: p, type: "file" }))) : json(404, { message: "Not Found" });
      }
      return json(404, { message: "Not Found" });
    } catch (err) {
      return json(500, { message: String(err.message || err) });
    }
  }
  return { handle, state };
}

module.exports = { makeMock, git };
