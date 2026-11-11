# Review site

Paste a pull request or branch link and see the reproduction, laid out by the paper and not
by files.

A Paper2Repro pull request has tens of thousands of lines, and most of them are outputs. The
page shows what a reviewer has to judge:

- **Figures.** The published figure next to ours: side by side, swipe, blink or overlay. Each
  curve has its score against the pass mark and the best control.
- **Tables and numbers.** In the shape of the paper's table, the paper's value over ours.
- **The decision, right below each figure and each table.** Why the result is not a plain
  match (the cause and what was tested, the choices the paper does not give, the values the
  paper prints that contradict its own numbers), then the question: "The pull request says
  Partly. Your verdict:" with **Agrees**, **Partly** and **Differs**, and a comment box. Where
  there is nothing to judge (a figure that was not attempted, a check) the question is
  **OK** or **Not OK**. There is no separate list of decisions.
- **Code.** The method and the analysis in full, changes outside the paper folder as a diff
  with its own OK or Not OK. Checks, tests and documents are linked. Outputs are counted and
  not shown.

## Use

1. Open the site. The first page lists the open pull requests of the usual repository.
2. Paste a link, anywhere on that page: `https://github.com/owner/repo/pull/40`, a branch
   (`.../tree/my-branch`), a comparison (`.../compare/main...my-branch`), or `owner/repo#40`.
3. Decide below each figure and table. **Next not decided** in the bar at the bottom jumps to
   the next one, and at the end one button agrees with the pull request on everything you
   left open. Decisions stay in your browser.
4. **Copy review** puts your decisions on the clipboard as text, the verdicts you want changed
   first (`Fig. 2: Partly → Agrees. <your comment>`). Paste it in the pull request.

A review has its own address, `?r=owner/repo/pull/40`, to bookmark or send.
`?url=<a GitHub link>` opens the same page.

A decision is kept by what it is about. When the pull request changes, a figure or table whose
verdicts and explanations did not change keeps your decision, and one that changed asks again.

Keys: `j` and `k` move between decisions.

## How it works

The site is static files. Your browser asks GitHub: the REST API for the pull request and its
changed files (3 or 4 requests a review), and `raw.githubusercontent.com` for `results.json`,
the pictures and the code. There is no server and no build for each pull request.

- **Request limit.** Without a token GitHub allows 60 API requests an hour for each network
  address, which an office can share. **GitHub token** on the first page saves a token in your
  browser; it goes only to `api.github.com` and lifts the limit to 5,000.
- **Private repositories** need that token. This path is written but not tested.
- **A branch** shows its first 300 changed files (GitHub's limit for a comparison). A pull
  request shows all of them.
- **Conflicts** are GitHub's: the page says when a pull request conflicts with its base. It
  does not compare open pull requests with each other.

Nothing from the reviewed repository runs. Its text is escaped, only raster pictures are
shown, and the page's Content-Security-Policy allows scripts from the site alone and
connections to GitHub alone.

## Set up

1. Put `review-site/` and `.github/workflows/review-site.yml` on the default branch.
2. **Settings → Pages → Source: GitHub Actions.** The workflow publishes on each push that
   changes `review-site/`.
3. To list another repository on the first page, change `data-repo` in `index.html`.

The site of a public repository is public. It holds no data of its own.

## Run it yourself

```bash
python3 -m http.server -d review-site 8000
```

Then open `http://127.0.0.1:8000/`.

## Files

| File | What |
| --- | --- |
| `index.html` | the page shell and its Content-Security-Policy |
| `core.js` | the rules and the HTML: links, value matching, table shape, cause grouping, file sorting. No browser, no network |
| `app.js` | reads GitHub, keeps decisions, drives the figure viewers |
| `review.css` | the look, light and dark |
| `vendor/` | highlight.js 11.12.0 (BSD-3-Clause), served by the site itself |

## Tests

```bash
node --test review-site/tests/core.test.mjs
```

The browser test runs the app in Chromium with GitHub answered from a local clone
(`tests/mock-github.cjs`), so it needs Playwright:

```bash
node review-site/tests/browser.test.cjs
```

To run it on every pull request of a real clone, see the top of that file.
