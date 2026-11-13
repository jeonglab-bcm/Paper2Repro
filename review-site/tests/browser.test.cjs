// The app in a real browser, with GitHub answered from a local clone (mock-github.cjs).
//
//   node review-site/tests/browser.test.cjs                 the small repository of fixture.cjs
//   REVIEW_CLONE=work/fossil REVIEW_REPO=jeonglab-bcm/fossil REVIEW_PULLS=pulls.json \
//     node review-site/tests/browser.test.cjs               every pull request of a real clone
//
// Needs Playwright with Chromium. pulls.json: [{number, title, user: {login}, head: {ref}, git}].
const assert = require("assert");
const fs = require("fs");
const http = require("http");
const path = require("path");
const { chromium } = require("playwright");
const { makeMock } = require("./mock-github.cjs");
const { makeRepo } = require("./fixture.cjs");

const ROOT = path.resolve(__dirname, "..");
const MIME = { ".html": "text/html", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css" };

/** Serves the app; the first page lists the open pull requests of `repo`. */
function serve(repo) {
  const server = http.createServer((req, res) => {
    const rel = decodeURIComponent(new URL(req.url, "http://x").pathname).replace(/^\/+/, "") || "index.html";
    const file = path.join(ROOT, rel);
    if (!file.startsWith(ROOT) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { "content-type": MIME[path.extname(file)] || "application/octet-stream" });
    const body = fs.readFileSync(file);
    res.end(rel === "index.html" ? body.toString().replace(/data-repo="[^"]*"/, `data-repo="${repo}"`) : body);
  });
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server)));
}
async function open(browser, mock, viewport = { width: 1280, height: 1000 }) {
  const ctx = await browser.newContext({ viewport, permissions: ["clipboard-read", "clipboard-write"] });
  await ctx.route(/^https:\/\/(api\.github\.com|raw\.githubusercontent\.com)\//, mock.handle);
  const page = await ctx.newPage();
  page.errors = [];
  page.on("pageerror", (err) => page.errors.push(String(err)));
  page.on("console", (m) => { if (m.type() === "error" && !/404|403/.test(m.text())) page.errors.push(m.text()); });
  return page;
}
const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
const picturesLoaded = (page) => page.evaluate(async () => {
  const imgs = [...document.querySelectorAll(".stage img")];
  imgs.forEach((i) => { i.loading = "eager"; });
  await Promise.all(imgs.map((i) => i.complete ? null : new Promise((r) => { i.onload = i.onerror = r; })));
  return { all: imgs.length, ok: imgs.filter((i) => i.naturalWidth > 0).length };
});

async function small(browser, base) {
  const repo = makeRepo();
  const mock = makeMock({ clone: repo.clone, owner: "o", repo: "r", pulls: repo.pulls, branches: repo.branches });
  const page = await open(browser, mock);
  const step = async (name, fn) => { try { await fn(); console.log("ok  ", name); } catch (err) { console.log("FAIL", name); throw err; } };

  await step("the first page has a box for a link and lists what is open", async () => {
    await page.goto(base);
    await page.waitForSelector(".rcard");
    assert.equal(await page.locator(".paste input").count(), 1);
    assert.equal(await page.locator(".rcard").count(), 1);
    await page.waitForSelector(".rcard .vbar");
    assert.equal(await page.locator(".rcard .pmc").textContent(), "PMC1");
    assert.equal(await page.locator(".rcard .progress").textContent(), "Not opened yet");
  });

  await step("a link that is not GitHub's is refused with a reason", async () => {
    await page.locator(".paste input").fill("https://example.org/x");
    await page.locator(".paste button").click();
    assert.match(await page.locator(".paste-error").textContent(), /not a GitHub/);
  });

  await step("a pasted pull request link opens its review", async () => {
    await page.locator(".paste input").fill("https://github.com/o/r/pull/7/files");
    await page.locator(".paste button").click();
    await page.waitForSelector(".dbox");
    assert.equal(new URL(page.url()).search, "?r=o/r/pull/7");
    assert.equal(await page.locator(".dbox").count(), 5);
    assert.equal(await page.locator("h1").textContent(), "A paper <script>alert(1)</script>");
    assert.equal(await page.locator("script").count(), 1); // app.js only
    assert.equal(await page.locator(".refline .chip.ci-passed").count(), 1);
    assert.deepEqual(await picturesLoaded(page), { all: 3, ok: 3 });
    assert.equal(await page.locator(".matrix td.err").count(), 1);
  });

  await step("the method's file is read and coloured, the shared file is a diff", async () => {
    const file = page.locator('details.file[data-path="PMC1/package/src/m/core.py"]');
    await file.locator("pre.code .l").first().waitFor();
    assert.equal(await file.locator("pre.code .l").count(), 4);
    assert.ok((await file.locator(".hljs-keyword").count()) > 0);
    assert.match(await file.locator("pre.code").textContent(), /<b>not html<\/b>/);
    assert.equal(await page.locator('details.file[data-path="README.md"] .l.add').count(), 1);
    assert.equal(await page.locator('details.file[data-path$="check_results.py"]').count(), 0);
  });

  await step("each figure and table has its decision below it, and there is no section of decisions", async () => {
    assert.equal(await page.locator(".dbox").count(), 5);
    assert.equal(await page.locator("#fig-1 .dbox").count(), 1);
    assert.equal(await page.locator("#fig-2 .dbox").count(), 1);
    assert.equal(await page.locator("#i-table1 + .dbox").count(), 1);
    assert.equal(await page.locator("#code .dbox").count(), 1);
    assert.deepEqual(await page.locator("h2").allTextContents(), ["Figures", "Tables and numbers", "Code"]);
    assert.deepEqual(await page.locator(".tabs a").evaluateAll((as) => as.map((a) => a.childNodes[0].textContent.trim())), ["Figures", "Tables and numbers", "Code"]);
    // a figure block is the pictures, then the question; what was measured and why stays closed
    const gap = await page.evaluate(() => {
      const st = document.querySelector("#fig-1"), box = st.querySelector(".dbox");
      return Math.round(box.getBoundingClientRect().top - st.querySelector(".views").getBoundingClientRect().bottom);
    });
    assert.ok(gap >= 0 && gap < 40, `gap ${gap}`);
    assert.equal(await page.locator("#fig-1 .irow").isVisible(), false);
    assert.equal(await page.locator("svg").count(), 0);
    await page.locator("#fig-1 details.info > summary").click();
    assert.equal(await page.locator("#fig-1 .irow").isVisible(), true);
    assert.match(await page.locator("#fig-1 details.info").textContent(), /Our curve is lower\./);
    await page.locator("#fig-1 details.info > summary").click();
    // a table shows its numbers, then the question
    assert.equal(await page.locator("#i-table1 .matrix").isVisible(), true);
  });

  await step("a verdict of your own and a comment are kept and counted", async () => {
    const fig = page.locator("#fig-1 .dbox"), table = page.locator("#i-table1 + .dbox"), drawing = page.locator("#fig-2 .dbox");
    assert.match(await fig.locator(".ask").textContent(), /The pull request says Partly\. Your verdict:/);
    await fig.locator('button[data-v="agrees"]').click();
    assert.equal(await fig.locator(".state").textContent(), "You say: Agrees");
    await fig.locator("textarea").fill("The curve agrees within noise.");
    await table.locator('button[data-v="differs"]').click(); // the same as the pull request
    assert.equal(await table.locator(".state").textContent(), "You agree: Differs");
    assert.equal(await drawing.locator(".ask").textContent(), "Is this OK?");
    await drawing.locator('button[data-v="no"]').click();
    await drawing.locator("textarea").fill("Draw it.");
    assert.equal(await drawing.locator(".state").textContent(), "Not OK");
    assert.equal(await page.locator(".bar .done").textContent(), "3");
    assert.equal(await page.locator(".bar .all").textContent(), "5");
    await page.locator(".copy").click();
    await page.waitForTimeout(150);
    const text = await page.evaluate(() => navigator.clipboard.readText());
    assert.match(text, /### Review of PMC1 at [0-9a-f]{7} \(#7\)/);
    assert.match(text, /\*\*Verdicts to change \(1\)\*\*\n- \*\*Fig\. 1\*\*: Partly → Agrees\. The curve agrees within noise\./);
    assert.match(text, /\*\*Not OK \(1\)\*\*\n- \*\*Fig\. 2\*\*: Draw it\./);
    assert.match(text, /\*\*Agreed \(1\):\*\* Table 1 \(Differs\)/);
    assert.match(text, /\*\*Not decided \(2\)\*\*\n- \*\*Text\*\*\n- \*\*Changes outside the paper folder\*\*/);
  });

  await step("the next one not decided is one click away, and the rest can follow the pull request", async () => {
    await page.locator(".next").click();
    assert.equal(await page.evaluate(() => document.activeElement.dataset.title), "Text");
    await page.locator(".next").click();
    assert.equal(await page.evaluate(() => document.activeElement.dataset.title), "Changes outside the paper folder");
    assert.equal(await page.locator(".restnote").textContent(), "2 are not decided yet.");
    await page.locator(".rest").click();
    assert.equal(await page.locator("#i-text\\.n + .dbox .state").textContent(), "You agree: Agrees"); // the pull request says Exact
    assert.equal(await page.locator("#code .dbox .state").textContent(), "OK");
    assert.equal(await page.locator(".bar .done").textContent(), "5");
    assert.equal(await page.locator(".restbar").isVisible(), false);
    assert.equal(await page.locator(".next").isVisible(), false);
    await page.reload();
    await page.waitForSelector(".dbox");
    assert.equal(await page.locator(".bar .done").textContent(), "5");
    assert.equal(await page.locator("#fig-1 .dbox .state").textContent(), "You say: Agrees");
    assert.equal(await page.locator("#fig-1 .dbox textarea").inputValue(), "The curve agrees within noise.");
    await page.locator(".back").click();
    await page.waitForSelector(".rcard .progress b");
    assert.equal(await page.locator(".rcard .progress").textContent(), "5 of 5 decided");
    assert.match(await page.locator(".recent").textContent(), /o\/r #7 · PMC1/);
  });

  await step("a decision saved by an older version keeps its comment and asks again", async () => {
    await page.evaluate(() => {
      const key = Object.keys(localStorage).find((k) => k.startsWith("rv:o/r:") && JSON.parse(localStorage[k]).v === "ok");
      localStorage.setItem(key, JSON.stringify({ d: "ok", note: "an old note" }));
    });
    await page.locator(".rcard").click();
    await page.waitForSelector(".dbox");
    const old = page.locator("#code .dbox");
    assert.equal(await old.locator(".state").textContent(), "");
    assert.equal(await old.locator("textarea").inputValue(), "an old note");
    assert.equal(await page.locator(".bar .done").textContent(), "4");
    await page.locator(".back").click();
    await page.waitForSelector(".rcard");
  });

  await step("the figure can be swiped, blinked and overlaid", async () => {
    await page.locator(".rcard").click();
    await page.waitForSelector(".viewer");
    const v = page.locator("#fig-1 .viewer");
    await v.locator('button[data-m="swipe"]').click();
    await v.locator(".swipe").fill("20");
    assert.equal(await v.locator(".stage").evaluate((el) => el.style.getPropertyValue("--cut")), "20%");
    assert.equal(await v.locator(".stage").evaluate((el) => el.style.getPropertyValue("--ar")), "8 / 6");
    await v.locator('button[data-m="overlay"]').click();
    assert.equal(await v.locator(".ovl").isVisible(), true);
    assert.equal(await v.locator(".pub").isVisible(), false);
  });

  await step("a link pasted anywhere on the first page opens at once", async () => {
    await page.goto(base);
    await page.waitForSelector(".rcard");
    await page.evaluate(() => {
      const data = new DataTransfer();
      data.setData("text", "https://github.com/o/r/tree/side");
      document.body.dispatchEvent(new ClipboardEvent("paste", { clipboardData: data, bubbles: true, cancelable: true }));
    });
    await page.waitForSelector(".dbox");
    assert.equal(new URL(page.url()).search, "?r=o/r/tree/side");
    assert.match(await page.locator(".note").first().textContent(), /No Paper2Repro results.json/);
    assert.equal(await page.locator('details.file[data-path="tools.py"]').count(), 1);
  });

  await step("a branch that has a pull request opens as that pull request", async () => {
    await page.goto(base + "?url=" + encodeURIComponent("https://github.com/o/r/tree/paper"));
    await page.waitForSelector(".dbox");
    assert.equal(new URL(page.url()).search, "?r=o/r/pull/7");
  });

  await step("a tree link that ends in a path still finds its branch", async () => {
    await page.goto(base + "?url=" + encodeURIComponent("https://github.com/o/r/tree/side/PMC1"));
    await page.waitForSelector(".dbox");
    assert.equal(new URL(page.url()).search, "?r=o/r/tree/side");
  });

  await step("what GitHub does not find is said, with the way to add a token", async () => {
    await page.goto(base + "?r=o/r/pull/999");
    await page.waitForSelector(".problem");
    assert.match(await page.locator(".problem").textContent(), /does not find it/);
    assert.equal(await page.locator(".token").count(), 1);
  });

  await step("a used-up request limit is said, and a token can be saved", async () => {
    mock.state.rateLimited = true;
    await page.goto(base + "?r=o/r/tree/side");
    await page.waitForSelector(".problem");
    assert.match(await page.locator(".problem").textContent(), /limit for requests without a token is used up until/);
    mock.state.rateLimited = false;
    await page.locator(".token").click();
    await page.locator("dialog .tok").fill("github_pat_test");
    await page.locator("dialog .save").click();
    await page.waitForSelector(".dbox");
    assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem("rv:token"))), "github_pat_test");
  });

  await step("a phone-wide page does not scroll sideways", async () => {
    await page.setViewportSize({ width: 390, height: 844 });
    for (const q of ["", "?r=o/r/pull/7"]) {
      await page.goto(base + q);
      await page.waitForSelector(q ? ".dbox" : ".rcard");
      assert.equal(await overflow(page), 0, q || "first page");
    }
  });

  assert.deepEqual(page.errors, []);
  fs.rmSync(repo.dir, { recursive: true, force: true });
}

async function real(browser, base) {
  const [owner, repo] = process.env.REVIEW_REPO.split("/");
  const pulls = JSON.parse(fs.readFileSync(process.env.REVIEW_PULLS, "utf8"));
  const mock = makeMock({ clone: process.env.REVIEW_CLONE, owner, repo, pulls });
  const page = await open(browser, mock);
  const shots = process.env.REVIEW_SHOTS;
  await page.goto(base);
  await page.waitForFunction((n) => document.querySelectorAll(".rcard .vbar").length === n, pulls.length, { timeout: 60000 });
  console.log(JSON.stringify({ firstPage: await page.locator(".rcard").count(), apiCalls: mock.state.calls, overflow: await overflow(page) }));
  if (shots) await page.screenshot({ path: path.join(shots, "app-home.png") });
  for (const p of pulls) {
    const before = mock.state.calls, t0 = Date.now();
    await page.setViewportSize({ width: 1280, height: 1000 });
    await page.goto(`${base}?url=${encodeURIComponent(`https://github.com/${owner}/${repo}/pull/${p.number}`)}`);
    await page.waitForSelector(".dbox", { timeout: 120000 });
    await page.locator("details.file[open] pre.code .l").first().waitFor({ timeout: 30000 }).catch(() => {});
    const pics = await picturesLoaded(page);
    const wide = await overflow(page);
    if (shots) await page.screenshot({ path: path.join(shots, `app-pr-${p.number}.png`) });
    await page.setViewportSize({ width: 390, height: 844 });
    const narrow = await overflow(page);
    const facts = {
      pr: p.number, decisions: await page.locator(".dbox").count(), figures: await page.locator(".station").count(),
      inFigures: await page.locator(".station .dbox").count(), inTables: await page.locator(".nblock .dbox").count(),
      pictures: `${pics.ok}/${pics.all}`, files: await page.locator("details.file").count(),
      apiCalls: mock.state.calls - before, seconds: ((Date.now() - t0) / 1000).toFixed(1), overflow: [wide, narrow],
    };
    console.log(JSON.stringify(facts));
    assert.equal(pics.ok, pics.all, `#${p.number}: every picture loads`);
    assert.deepEqual([wide, narrow], [0, 0], `#${p.number}: no sideways scroll`);
  }
  assert.deepEqual(page.errors, []);
}

(async () => {
  const server = await serve(process.env.REVIEW_REPO || "o/r");
  const base = `http://127.0.0.1:${server.address().port}/`;
  const browser = await chromium.launch();
  try {
    await (process.env.REVIEW_CLONE ? real : small)(browser, base);
    console.log("ALL OK");
  } catch (err) {
    console.error(err);
    process.exitCode = 1;
  } finally {
    await browser.close();
    server.close();
  }
})();
