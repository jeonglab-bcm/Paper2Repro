// The rules of the review page, without a browser:  node --test review-site/tests/core.test.mjs
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
import * as core from "../core.js";

const { RESULTS } = createRequire(import.meta.url)("./fixture.cjs");

test("a pasted link is read as a pull request, a branch or a repository", () => {
  const pull = { owner: "o", repo: "r", kind: "pull", number: 40 };
  for (const text of ["https://github.com/o/r/pull/40", "github.com/o/r/pull/40/files#diff-1", " https://github.com/o/r/pull/40/commits/abc ", "o/r#40"]) {
    assert.deepEqual(core.parseLink(text), pull, text);
  }
  assert.deepEqual(core.parseLink("#40", "o/r"), pull);
  assert.deepEqual(core.parseLink("https://github.com/o/r/tree/claude/some-branch"), { owner: "o", repo: "r", kind: "branch", branch: "claude/some-branch" });
  assert.deepEqual(core.parseLink("https://github.com/o/r/compare/main...feature"), { owner: "o", repo: "r", kind: "branch", branch: "feature", base: "main" });
  assert.deepEqual(core.parseLink("https://github.com/o/r"), { owner: "o", repo: "r", kind: "repo" });
  assert.deepEqual(core.parseLink("o/r@my-branch"), { owner: "o", repo: "r", kind: "branch", branch: "my-branch" });
  assert.equal(core.parseLink("https://example.org/o/r/pull/40"), null);
  assert.equal(core.parseLink(""), null);
});

test("a review has an address that leaves in-page anchors free", () => {
  const branch = { owner: "o", repo: "r", kind: "branch", branch: "claude/a b" };
  assert.equal(core.routeOf({ owner: "o", repo: "r", kind: "pull", number: 40 }), "?r=o/r/pull/40");
  assert.equal(core.routeOf(branch), "?r=o/r/tree/claude/a%20b");
  assert.deepEqual(core.parseRoute(core.routeOf(branch)), branch);
  assert.deepEqual(core.parseRoute("?url=https://github.com/o/r/pull/40"), { owner: "o", repo: "r", kind: "pull", number: 40 });
  assert.equal(core.parseRoute(""), null);
});

test("printed tolerance is half a unit of the last printed digit", () => {
  const tol = { printed: true };
  assert.equal(core.fieldMatches({ expected: "81.91", observed: 81.912 }, tol), true);
  assert.equal(core.fieldMatches({ expected: "79.96", observed: 78.88 }, tol), false);
  assert.equal(core.fieldMatches({ expected: 0.5, observed: 0.503 }, { abs: 0.005 }), true);
  assert.equal(core.fmtObs(78.8765, "79.96"), "78.88");
  assert.equal(core.fmtObs(525, "525"), "525");
  assert.equal(core.fmtExp(0.773), "0.773");
});

test("results.json with NaN, as Python writes it, is read", () => {
  assert.equal(core.parseResults('{"items": [{"id": "a", "x": NaN, "y": [1, -Infinity]}]}').items[0].x, null);
  assert.equal(core.parseResults('{"items": [{"label": "NaN, as text"}]}').items[0].label, "NaN, as text");
  assert.equal(core.parseResults("not json"), null);
  assert.equal(core.parseResults('{"no": "items"}'), null);
});

test("fields are laid out as the paper's table, a series, or a list", () => {
  const [kind, { rows, cols, cells }] = core.shapeFields(core.fieldsOf(RESULTS.items[1]));
  assert.deepEqual([kind, rows, cols], ["matrix", ["A", "B"], ["ACC", "SN"]]);
  assert.ok(cells.get("A\x1fACC").error);
  assert.equal(cells.get("A\x1fSN").match, true);
  assert.equal(core.measureOf(RESULTS.items[1]), "2 of 3 as printed, 1 paper error");
  const series = Array.from({ length: 6 }, (_, i) => ({ name: `ACC at LG ${i + 1}`, a: 0.7 + i / 100, b: 0.71, match: false, error: null }));
  const [k2, data] = core.shapeFields(series);
  assert.equal(k2, "series");
  assert.equal(data.get("ACC at LG").length, 6);
  assert.equal(core.shapeFields([{ name: "one", a: 1, b: 1 }])[0], "list");
});

test("files are sorted by what a reviewer reads", () => {
  const cases = {
    "PMC1/package/src/m/core.py": "method",
    "PMC1/figure-reproduction/pipeline/experiments.py": "analysis",
    "PMC1/figure-reproduction/main.nf": "analysis",
    "PMC1/figure-reproduction/pipeline/check_results.py": "plumbing",
    "PMC1/package/tests/test_m.py": "tests",
    "PMC1/package/src/m/data/x.pssm": "generated",
    "PMC1/figure-reproduction/output/run/a.json": "generated",
    "PMC1/results.json": "generated",
    "PMC1/session/conversation.md": "generated",
    "site/PMC1/index.html": "generated",
    "PMC1/README.md": "docs",
    "README.md": "shared",
    "site/index.html": "shared",
    "tools/x.py": "shared",
  };
  for (const [path, want] of Object.entries(cases)) assert.equal(core.classify(path, ["PMC1"])[0], want, path);
  const files = Object.keys(cases).concat(".github/workflows/x.yml").map((path) => ({ path }));
  assert.deepEqual(core.paperCandidates(files), ["PMC1", "tools"]);
});

test("the first sentence keeps abbreviations whole", () => {
  assert.equal(core.firstSentence("As Lou et al. 2014 define them. The rest.")[0], "As Lou et al. 2014 define them.");
  assert.equal(core.firstSentence("See Fig. 3 for it. More.")[0], "See Fig. 3 for it.");
});

test("items that share their hypotheses share a card; every cause has its own card", () => {
  const cards = core.causeCards("PMC1", RESULTS.items);
  assert.equal(cards.length, 1);
  assert.equal(cards[0].title, "Fig. 1 · Table 1");
  assert.equal(cards[0].verdict, "differs");
  assert.equal(cards[0].status, "open");
  assert.deepEqual(core.decisionCards("PMC1", RESULTS.items, [], []).map((c) => c.kind), ["cause", "choices", "errors", "skipped"]);
  // a difference with a tested cause is a card too, after the open ones
  const more = structuredClone(RESULTS.items);
  more.unshift({ id: "fig3", label: "Fig. 3", kind: "figure", method: "values", verdict: "partly", cause: { category: "nondeterminism", status: "explained", summary: "Seeds." } });
  assert.deepEqual(core.causeCards("PMC1", more).map((c) => [c.title, c.status]), [["Fig. 1 · Table 1", "open"], ["Fig. 3", "explained"]]);
  // two causes in one figure are told apart by the part they are about
  more.unshift({ id: "fig3.b", label: "Fig. 3b, panel b", kind: "figure", method: "values", verdict: "differs", cause: { category: "unknown", status: "open", summary: "Other." } });
  assert.deepEqual(core.causeCards("PMC1", more).map((c) => c.title), ["Fig. 1 · Table 1", "Fig. 3: panel b", "Fig. 3: fig3"]);
  const texts = [1, 2].map((n) => ({ id: `text.t${n}`, label: `GO counts ${n}`, kind: "value", method: "values", verdict: "differs", cause: { category: "unknown", status: "open", summary: `S${n}.` } }));
  assert.deepEqual(core.causeCards("PMC1", texts).map((c) => c.title), ["Text: GO counts 1", "Text: GO counts 2"]);
  assert.equal(core.cardKey("a", "b"), core.cardKey("a", "b"));
  assert.notEqual(core.cardKey("a", "b"), core.cardKey("a", "c"));
});

test("highlighted code is cut into lines that each close their spans", () => {
  const lines = core.splitHighlighted('<span class="k">def</span> f():\n    <span class="s">"""Two\n    lines."""</span>\n    x &lt; 1');
  assert.deepEqual(lines, [
    '<span class="k">def</span> f():',
    '    <span class="s">"""Two</span>',
    '<span class="s">    lines."""</span>',
    "    x &lt; 1",
  ]);
  assert.equal(core.languageOf("a/b/main.nf"), "groovy");
  assert.equal(core.languageOf("x.unknown"), null);
});

test("a patch is drawn with the line numbers of each side", () => {
  const html = core.diffHtml("@@ -2,3 +2,3 @@ # repo\n \n-line\n+line <b>\n\\ No newline at end of file");
  assert.match(html, /<span class="l del" data-n="3">line<\/span>/);
  assert.match(html, /<span class="l add" data-n="3">line &lt;b&gt;<\/span>/);
  assert.doesNotMatch(html, /No newline/);
});

function review() {
  const results = structuredClone(RESULTS);
  const files = core.normalizeFiles([
    { filename: "PMC1/results.json", status: "added", additions: 90, deletions: 0 },
    { filename: "PMC1/figure-reproduction/published/figure-1.png", status: "added", additions: 0, deletions: 0 },
    { filename: "PMC1/figure-reproduction/output/fig1_ours.png", status: "added", additions: 0, deletions: 0 },
    { filename: "PMC1/package/src/m/core.py", status: "added", additions: 4, deletions: 0, patch: "@@ -0,0 +1,4 @@\n+def dt(x):" },
    { filename: "PMC1/figure-reproduction/pipeline/check_results.py", status: "added", additions: 1, deletions: 0 },
    { filename: "README.md", status: "modified", additions: 1, deletions: 1, patch: "@@ -1,3 +1,3 @@\n # repo\n \n-line\n+line about PMC1" },
  ]);
  return {
    repo: "o/r", label: "#7", title: "Reproduce PMC1", url: "https://github.com/o/r/pull/7", number: 7, branch: "paper", author: "some<one>",
    updated: "2026-11-09T00:00:00Z", sha: "a".repeat(40), notes: ["Conflicts with main. It needs an update before it can merge."], files,
    papers: [{ folder: "PMC1", path: "PMC1/results.json", results, baseResults: null, tree: files.map((f) => f.path) }],
  };
}
const ctx = { img: (p) => `https://raw.example/${p}`, blob: (p) => `https://github.com/o/r/blob/sha/${p}` };

test("the page is laid out by the paper, and text from the repository is escaped", () => {
  const { html, summary } = core.reviewHtml(review(), ctx);
  assert.ok(!html.includes("<script>alert(1)</script>"));
  assert.ok(html.includes("A paper &lt;script&gt;alert(1)&lt;/script&gt;"));
  assert.ok(html.includes("some&lt;one&gt;"));
  assert.ok(html.includes('id="fig-1"'));
  assert.ok(html.includes("Fig. 1 · Table 1"));
  assert.ok(html.includes("2 of 2 tested causes ruled out"));
  assert.ok(html.includes('<th scope="row">A</th>'));
  assert.ok(html.includes("paper error"));
  assert.ok(html.includes("Conflicts with main"));
  assert.equal((html.match(/<article class="card/g) || []).length, 5); // cause, choices, errors, outside, not attempted
  assert.equal(summary.papers[0].cards.length, 5);
  // a cause asks for the reviewer's own verdict, the other cards ask whether they are OK
  assert.match(html, /data-verdict="differs" data-members="\[&quot;fig1.curve&quot;,&quot;table1&quot;\]"/);
  assert.ok(html.includes("The pull request says <b>Differs</b>. Your verdict:"));
  assert.equal((html.match(/<button type="button" data-v="agrees">Agrees<\/button>/g) || []).length, 1);
  assert.equal((html.match(/Is this OK\?/g) || []).length, 4);
  assert.ok(!html.includes("Needs work") && !html.includes("Accept"));
  // the evidence comes first: figures, then tables and numbers, then the decisions, then the code
  const at = ['id="figures-0"', 'id="numbers-0"', 'id="decisions-0"', 'id="code"'].map((x) => html.indexOf(x));
  assert.ok(at.every((x, i) => x > 0 && (i === 0 || x > at[i - 1])), String(at));
  assert.deepEqual(summary.papers[0].counts, { exact: 1, agrees: 0, partly: 1, inconclusive: 0, differs: 1, not_attempted: 1 });
});

test("the AI judge's first verdict is shown on its card and on the rows it is about", () => {
  const judge = { judged_at: "2026-11-10T12:00:00Z", model: "claude-opus-5-5", guide: { text: "Judge the <conclusion>.", edit: "https://github.com/o/r/edit/main/REVIEW_GUIDE.md" },
    papers: [{ id: "PMC1", folder: "PMC1", cards: [
      { members: ["fig1.curve", "table1"], verdict: "agrees", reason: "Within <noise>." },
      { members: ["nothing"], verdict: "differs", reason: "No such card." },
      { members: ["text.n"], verdict: "exact", reason: "Not a verdict the judge may give." },
    ] }] };
  assert.deepEqual([...core.judgeOf(judge, "PMC1", "PMC1")], [["fig1.curve\x1ftable1", { verdict: "agrees", reason: "Within <noise>." }], ["nothing", { verdict: "differs", reason: "No such card." }]]);
  assert.equal(core.judgeOf(null, "PMC1", "PMC1").size, 0);
  const { html } = core.reviewHtml({ ...review(), judge, judgeOn: true }, ctx);
  assert.ok(html.includes('<p class="ai"><span class="aitag">AI judge</span><b>Agrees.</b> Within &lt;noise&gt;.</p>'));
  assert.ok(html.includes('data-ai="agrees" data-verdict="differs"'));
  assert.ok(html.includes('<button type="button" data-v="agrees" class="aipick"'));
  assert.equal((html.match(/class="aipick"/g) || []).length, 1);
  assert.equal((html.match(/<span class="chip ai"[^>]*>AI: Agrees<\/span>/g) || []).length, 2); // both rows say something else
  assert.ok(html.includes("gave a first verdict on <b>1</b> result by your guide. <b>1</b> differs from the pull request."));
  assert.ok(html.includes('<pre class="guide">Judge the &lt;conclusion&gt;.</pre>'));
  assert.ok(html.includes('<a href="https://github.com/o/r/edit/main/REVIEW_GUIDE.md" rel="noopener">Change the guide</a>'));
  // a link that is not GitHub's is not made into a link
  const odd = core.reviewHtml({ ...review(), judge: { ...judge, guide: { text: "x", edit: "javascript:alert(1)" } }, judgeOn: true }, ctx).html;
  assert.ok(!odd.includes("javascript:") && !odd.includes("Change the guide"));
  // not judged yet, and a site without an AI judge
  assert.ok(core.reviewHtml({ ...review(), judge: null, judgeOn: true }, ctx).html.includes("The AI judge has not looked at this commit yet."));
  const off = core.reviewHtml(review(), ctx).html;
  assert.ok(!off.includes("AI judge") && !off.includes("aipick"));
});

test("pictures come from the commit, published next to ours", () => {
  const { html } = core.reviewHtml(review(), ctx);
  assert.ok(html.includes('<figure class="pub"><img src="https://raw.example/PMC1/figure-reproduction/published/figure-1.png"'));
  assert.ok(html.includes('<figure class="ours"><img src="https://raw.example/PMC1/figure-reproduction/output/fig1_ours.png"'));
  assert.ok(html.includes('<figure class="ovl">'));
  assert.ok(!html.includes(".svg"));
});

test("only the method and what is shared is shown as code", () => {
  const { html, summary } = core.reviewHtml(review(), ctx);
  assert.match(html, /<details class="file"[^>]*data-path="PMC1\/package\/src\/m\/core.py" data-status="A" open>/);
  assert.match(html, /data-path="README.md" data-status="M">.*<span class="l add" data-n="3">line about PMC1<\/span>/s);
  assert.doesNotMatch(html, /<details class="file"[^>]*check_results.py/); // listed with a link, not shown
  assert.ok(html.includes("pipeline/check_results.py"));
  assert.equal(summary.lines.method, 4);
  assert.equal(summary.lines.generated, 90);
});

test("a change without a paper still gets a page", () => {
  const r = review();
  r.papers = [];
  const { html } = core.reviewHtml(r, ctx);
  assert.ok(html.includes("No Paper2Repro results.json"));
  assert.equal((html.match(/<article class="card/g) || []).length, 1);
});

test("the first page lists what is open, each with its address", () => {
  const html = core.homeHtml({ repo: "o/r", pulls: [{ number: 7, title: "Reproduce <PMC1>", user: { login: "x" }, head: { sha: "abc", ref: "paper" }, updated_at: "2026-11-09" }], recent: [] });
  assert.ok(html.includes('href="?r=o/r/pull/7"'));
  assert.ok(html.includes("Reproduce &lt;PMC1&gt;"));
  assert.ok(html.includes('class="paste"'));
});
