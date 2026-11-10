# Review site

One page per reproduction to review, laid out by the paper and not by files.

A Paper2Repro pull request has tens of thousands of lines, and most of them are outputs. The
page shows what a reviewer has to judge:

- **Decisions.** One card per open cause, with the paper's numbers next to ours and the
  causes that were tested. Then the choices the paper does not give, the values the paper
  prints that contradict its own numbers, the changes outside the paper folder, and what was
  not attempted. Each card takes **Accept** or **Needs work** and a note.
- **Figures.** The published figure next to ours: side by side, swipe, blink or overlay. Each
  curve has its score against the pass mark and the best control.
- **Tables and numbers.** In the shape of the paper's table, the paper's value over ours.
- **Code.** The method and the analysis in full, changes outside the paper folder as a diff.
  Checks, tests and documents are linked. Outputs are counted and not shown.

An index page lists every open pull request and every recent branch that has none.

## Use

1. Open **Actions → Review site → Run workflow**. The pages are rebuilt for what is open now.
2. Open the site and decide. Decisions stay in your browser.
3. **Copy review** puts your decisions on the clipboard as text. Paste it in the pull request.

A decision is kept by what its card says. After a rebuild, a card that did not change keeps
your decision, and a card that changed asks again.

Keys: `j` and `k` move between decisions, `a` accepts, `w` marks needs work.

## Set up

1. Put `review-site/` and `.github/workflows/review-site.yml` on the default branch of the
   repository that hosts the site.
2. In that repository: **Settings → Pages → Source: GitHub Actions**.
3. To review a private repository, add a secret `REVIEW_TOKEN` that can read it.

The site of a public repository is public. The pages hold nothing that the reviewed
repository does not already show.

## Run it yourself

```bash
pip install pygments
python3 review-site/review_site.py --repo jeonglab-bcm/fossil --clone work/fossil --out _site
python3 -m http.server -d _site 8000
```

`--extra 34,some-branch` adds a closed pull request or an old branch. `--no-branches` leaves
out branches without a pull request. `--prs-json` and `--no-fetch` build without the network.

## What it reads

`<paper>/results.json` (schema `paper2repro/results/v1`) of each paper folder the change
touches, the pictures its items name, and `git diff` against the point where the change left
`main`. Nothing from the reviewed repository is run. Its text is escaped and only raster
pictures are copied, because a pull request can come from anyone.

## Tests

```bash
python3 review-site/tests/test_review_site.py
```
