// A small repository with one reproduction, for the tests: a pull request (branch "paper")
// that adds PMC1, and a branch "side" with no pull request and no paper.
const { execFileSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const zlib = require("zlib");

function png(w = 4, h = 3) {
  const chunk = (kind, data) => {
    const body = Buffer.concat([Buffer.from(kind), data]);
    const len = Buffer.alloc(4), crc = Buffer.alloc(4);
    len.writeUInt32BE(data.length);
    crc.writeUInt32BE(zlib.crc32(body) >>> 0);
    return Buffer.concat([len, body, crc]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0);
  ihdr.writeUInt32BE(h, 4);
  ihdr.set([8, 2, 0, 0, 0], 8);
  const raw = Buffer.concat(Array.from({ length: h }, () => Buffer.concat([Buffer.from([0]), Buffer.alloc(w * 3, 255)])));
  return Buffer.concat([Buffer.from("\x89PNG\r\n\x1a\n", "binary"), chunk("IHDR", ihdr), chunk("IDAT", zlib.deflateSync(raw)), chunk("IEND", Buffer.alloc(0))]);
}

const RESULTS = {
  schema: "paper2repro/results/v1",
  paper: { id: "PMC1", title: "A paper <script>alert(1)</script>", citation: "A et al. 2020", doi: "10.1000/x1" },
  items: [
    { id: "fig1.curve", label: "Fig. 1, the curve", kind: "figure", method: "pixels", verdict: "partly",
      pixels: { tolerance_px: 2, published_near_ours: 0.6, ours_near_published: 0.7, threshold: 0.75, controls: [{ name: "wrong", kind: "wrong_input", score: 0.3 }] },
      outputs: ["figure-reproduction/output/fig1_ours.png", "figure-reproduction/output/fig1_overlay.png"],
      cause: { category: "unknown", status: "open", summary: "Our curve is lower. Fig. 3 shows it too.", evidence: ["figure-reproduction/output/scores.json (gap)"],
        hypotheses: [{ hypothesis: "The database", test: "Rerun", result: "rejected" }, { hypothesis: "The seed", test: "Rerun", result: "rejected" }] } },
    { id: "table1", label: "Table 1, two methods", kind: "table", method: "values", verdict: "differs",
      values: { tolerance: { printed: true },
        fields: [{ name: "A ACC", expected: "79.96", observed: 78.88 }, { name: "A SN", expected: "81.91", observed: 81.912 },
          { name: "B ACC", expected: "70.00", observed: 71.5 }, { name: "B SN", expected: "60.0", observed: 60.04 }],
        exceptions: [{ field: "A ACC", category: "paper_error", evidence: "run/a.json: 79.91, not 79.96" }] },
      assumptions: [{ what: "UniRef100 for nr", source: "our_choice", sensitivity: "0.5 points" }],
      cause: { category: "unknown", status: "open", summary: "Within 2 points.",
        hypotheses: [{ hypothesis: "The seed", test: "Rerun", result: "rejected" }, { hypothesis: "The database", test: "Rerun", result: "rejected" }] } },
    { id: "text.n", label: "Number of chains", kind: "value", method: "values", verdict: "exact",
      values: { tolerance: { printed: true }, fields: [{ name: "chains", expected: "525", observed: 525 }] } },
    { id: "fig2", label: "Fig. 2, a drawing", kind: "figure", method: "none", verdict: "not_attempted",
      cause: { category: "not_a_result", status: "explained", summary: "A drawing." } },
  ],
};

function git(cwd, ...args) {
  const env = { ...process.env, GIT_AUTHOR_NAME: "t", GIT_AUTHOR_EMAIL: "t@example.org", GIT_COMMITTER_NAME: "t", GIT_COMMITTER_EMAIL: "t@example.org", HOME: cwd };
  execFileSync("git", ["-C", cwd, ...args], { env, stdio: "ignore" });
}

/** Makes the repository and returns {dir, clone, pulls, branches} for makeMock. */
function makeRepo() {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "review-site-"));
  const up = path.join(dir, "upstream");
  const write = (rel, data) => {
    fs.mkdirSync(path.dirname(path.join(up, rel)), { recursive: true });
    fs.writeFileSync(path.join(up, rel), data);
  };
  fs.mkdirSync(up);
  git(up, "init", "-q", "-b", "main");
  write("README.md", "# repo\n\nline\n");
  git(up, "add", "-A");
  git(up, "commit", "-q", "-m", "start");
  git(up, "checkout", "-q", "-b", "paper");
  write("PMC1/results.json", JSON.stringify(RESULTS).replace('"observed":60.04', '"observed":60.04,"spare":NaN'));
  write("PMC1/figure-reproduction/published/figure-1.png", png(8, 6));
  write("PMC1/figure-reproduction/published/evil.svg", "<svg onload='alert(1)'/>");
  write("PMC1/figure-reproduction/output/fig1_ours.png", png(8, 6));
  write("PMC1/figure-reproduction/output/fig1_overlay.png", png(8, 6));
  write("PMC1/package/src/m/core.py", 'def dt(x):\n    """Two\n    lines."""\n    return x  # <b>not html</b>\n');
  write("PMC1/figure-reproduction/pipeline/check_results.py", "print('zqxplumb')\n");
  write("README.md", "# repo\n\nline about PMC1\n");
  git(up, "add", "-A");
  git(up, "commit", "-q", "-m", "paper");
  git(up, "checkout", "-q", "main");
  git(up, "checkout", "-q", "-b", "side");
  write("tools.py", "x = 1\n");
  git(up, "add", "-A");
  git(up, "commit", "-q", "-m", "side");
  git(up, "checkout", "-q", "main");
  const clone = path.join(dir, "clone");
  execFileSync("git", ["clone", "-q", up, clone], { stdio: "ignore" });
  // a new commit on the pull request's branch, as its author would push; gives its sha
  let pushes = 0;
  const push = () => {
    git(up, "checkout", "-q", "paper");
    write(`PMC1/package/src/m/more${++pushes}.py`, "y = 2\n");
    git(up, "add", "-A");
    git(up, "commit", "-q", "-m", `more ${pushes}`);
    git(up, "checkout", "-q", "main");
    execFileSync("git", ["-C", clone, "fetch", "-q", "origin"], { stdio: "ignore" });
    return execFileSync("git", ["-C", clone, "rev-parse", "origin/paper"]).toString().trim();
  };
  return {
    dir, clone, push,
    pulls: [{ number: 7, title: "Reproduce PMC1: a paper", user: { login: "someone" }, head: { ref: "paper" }, updated_at: "2026-11-09T00:00:00Z", git: "origin/paper" }],
    branches: { side: "origin/side", paper: "origin/paper", "side/PMC1": null },
  };
}

module.exports = { RESULTS, makeRepo, png };
