# Review site

Paste a pull request or branch link and see the reproduction, laid out by the paper and not
by files.

A Paper2Repro pull request has tens of thousands of lines, and most of them are outputs. The
page shows what a reviewer has to judge:

- **Figures.** Three pictures at once, each named above it: the **Original** (the published
  figure), **Ours**, and the **Overlap** (both drawn on top of each other). A click on a
  picture opens it large, alone, as wide as the block; a click on the large one shows the next,
  so two can be told apart in place. **Swipe** and **Blink** compare the original and ours.
  **Earlier versions of ours**, below the pictures, shows our picture as each commit that wrote
  it left it, the newest first. Each one is named by how many commits before the head of the
  pull request it was written ("3 commits ago"), with its date and message. A version opens
  large in the place of ours, named the same way, and a click on the picture goes between it
  and ours as it is now, so a redraw can be seen (1 request a figure and 1 for the review, when
  asked; "commits ago" counts back through the 100 latest commits).
- **Tables.** In the shape of the paper's table, the paper's value over ours.
- **The main figures and tables only.** The page asks about the figures and tables of the paper's
  main text. Supplementary results, numbers in the text and checks stay in `results.json`; the
  page lists them below the tables under **Not asked**, closed, with their verdicts and with no
  decision, and does not count them. A result is supplementary by its id or by how its label
  starts (`figS1`, `supp.table2`, "Fig. S3", "Supplementary Table 2", "Additional file 4",
  "S1 Fig").
- **The decision, right below each figure and each table.** "The pull request says Partly
  (56% within 2 px, pass 90%)." with **Accept** and **Revise**. Where the result is not a plain
  match, one sentence says why, before the buttons; the rest of it is in the details.
  - **Accept** is one click: the pull request's verdict stands, and the next figure or table
    that is not decided comes to the top.
  - **Revise** opens your own verdict (the two the pull request did not give, of **Agrees**,
    **Partly** and **Differs**) and a box for the reason. Nothing is decided until you pick the
    verdict.
  - Where there is nothing to judge (a figure that was not attempted) the question is
    **OK** or **Not OK**, and Not OK opens the reason.
  - What you accepted can still get a comment: **Add a comment**.

  There is no separate list of decisions.
- **Details, closed.** One line below the question opens what the pull request measured (each
  curve's score against the pass mark and the best control, the numbers) and why the result
  is not a plain match (the cause and what was tested, the choices the paper does not give,
  the values the paper prints that contradict its own numbers). The page draws no charts of
  its own.
- **Your review, at a glance.** Below the paper's title, your decisions apart: **Not decided**,
  **To change** (`Fig. 2: Partly → Agrees`) and **Accepted**. A name goes to its figure or table.
  Each figure and table also says **Not decided**, **Accepted** or **To change** at its top.
- **Code.** The method and the analysis in full, changes outside the paper folder as a diff
  with its own OK or Not OK. Checks, tests and documents are linked. Outputs are counted and
  not shown.

## Use

1. Open the site. The first page lists the open pull requests of the usual repository, apart by
   where each stands for you (see below).
2. Paste a link, anywhere on that page: `https://github.com/owner/repo/pull/40`, a branch
   (`.../tree/my-branch`), a comparison (`.../compare/main...my-branch`), or `owner/repo#40`.
3. Below each figure and table, press **Accept** to pass it, or **Revise** to give your own
   verdict and the reason. **Next not decided** in the bar at the bottom jumps to the next
   one, and at the end one button accepts everything you left open as the pull request says.
   Decisions stay in your browser.
4. The button at the bottom sends your review to the pull request, the verdicts you want
   changed first (`Fig. 2: Partly → Agrees. <your comment>`), and opens it on GitHub in a new
   tab.
   - **With a GitHub token that may write** (fine-grained: Pull requests, read and write) the
     page submits a review of the pull request, at the commit you read, so GitHub takes you off
     the list of those it waits for. The button is named for what the review does, before you
     press it:

     | Button | When | On GitHub |
     | --- | --- | --- |
     | **Approve on GitHub** | all decided, all as the pull request says | an approval |
     | **Request changes on GitHub** | a verdict is yours and not the pull request's, or one is Not OK | changes requested |
     | **Comment on GitHub** | something is not decided yet, or the pull request is your own | a comment |

     An approval says that the pull request's verdicts are right, also where a verdict is
     Differs. It does not say that the paper came back. Where a repository asks for an approval
     before a merge, this approval counts.
   - **After that** the button says **Open review** while the review is as your decisions are,
     and **Update review** once a decision changed and the review still does the same: that
     edits its text. GitHub does not let a submitted review change from a comment to an
     approval, or from an approval to a request for changes, so then the page submits a new
     review.
   - **Your own pull request.** GitHub takes no approval from the author of a pull request, so
     the review of your own is a comment. The page knows whose it is from the token; where it
     does not, GitHub refuses the approval and the page submits the comment.
   - **With no token, or one that may only read,** the button is **Add review**: the page
     copies the review and opens the pull request at its comment box, where you paste it.
   - A branch with no pull request has nothing to review: the button is **Copy review**.

## The first page: where each pull request stands

The open pull requests are in three groups, by your decisions in this browser:

| Group | On the card | When |
| --- | --- | --- |
| **To review** | Not opened | you have not opened it |
| | Not started | opened, nothing decided |
| | In progress | some decided; "4 of 13 decided" |
| | Changed since your review | it has new commits since you decided; the card says how many figures and tables ask again |
| **Changes requested** | Changes requested | all decided, and at least one verdict is yours and not the pull request's, or is Not OK; "2 to change: Fig. 1, Fig. 3" |
| **Accepted** | Accepted | all decided, all as the pull request says |

Each card names who GitHub says is asked to review ("Review asked of alice and bob"). With a
token the page knows who you are (1 request, asked once): your own review requests read "you",
and their cards come first in each group.

A card in the last two groups also says whether the review went out: **Review added** with the
time when the page submitted it to the pull request, **Review copied** when it went to the clipboard,
**Review not added yet**, or **Decisions changed since you added the review**. The page does not
read the pull request's comments, so of a copied review it cannot know that you pasted it.

Decisions stay in the browser where you made them. A phone and a computer each keep their own, so
a pull request you reviewed on one is "Not opened" on the other.

A review has its own address, `?r=owner/repo/pull/40`, to bookmark or send.
`?url=<a GitHub link>` opens the same page.

## The latest commit

A review is read at the commit the pull request has when you open it: the page asks GitHub each
time, and does not take the answer from the browser's cache, which keeps GitHub's answers for a
minute. The commit is in the bar at the top, with who is asked to review.

A page that stays open asks again when you come back to its tab or window, at most every 5
minutes, or every minute with a GitHub token.

- **The first page** is drawn again when the list changed. A pull request with a new commit
  moves to **To review** as "Changed since your review".
- **A review** says "There is a new commit" with **Show the latest** and **Later**. It does not
  redraw by itself, as you may be in the middle of it. Your decisions are kept.

A decision is kept by what it is about. When the pull request changes, a figure or table whose
verdicts and explanations did not change keeps your decision, and one that changed asks again.

What changed since you decided is said at its figure or table, and by its name in the list of
your review:

- **Changed since you decided.** The verdict or the explanation changed, so it asks again. The
  line says what the pull request said then and what you answered, with your comment.
- **Drawn again since you decided.** Our picture changed and the verdict and explanation did
  not. Your decision is kept; **Seen**, or deciding again, puts the line away.

Both say the commit you decided at, and **Show ours as it was** opens our picture of that commit
in the place of ours. The page knows this from what the browser kept when you
last opened the review, so it starts with the first visit after this was added.

Keys: `j` and `k` move between decisions.

## On a phone: cards

On a screen up to 700 px wide the review is a deck of cards, like flashcards. One figure or
table fills the screen, with its verdict buttons below it.

- **One picture at a time.** Original, Ours and Overlap are three tabs; the overlap shows
  first, and a tap on the picture goes to the next one.
- **Accept brings the next card.** **Revise** stays on the card and opens your verdict and the
  reason below the picture; so does Not OK. **Next** goes on from there.
- **‹ and ›** in the bar at the top go back and forward. The bar shows where you are
  ("2 / 13") and how much is decided.
- **The last card** says what is left, lists your decisions apart (not decided, to change,
  accepted; a name goes to its card), accepts the rest as the pull request says if you want, and
  has the button that sends the review.
- **Whole page** in the bar shows the page as on a computer; **Cards** in the bottom bar
  brings the cards back. The choice is remembered.

## How it works

The site is static files. Your browser asks GitHub: the REST API for the pull request and its
changed files (3 or 4 requests a review), and `raw.githubusercontent.com` for `results.json`,
the pictures and the code. There is no server and no build for each pull request. The page
writes to GitHub in one case only: your review, as a review of the pull request, when you press
the button that sends it with a token that may write.

- **Request limit.** Without a token GitHub allows 60 API requests an hour for each network
  address, which an office can share. Opening the first page is 1 request, a review 3 or 4 the
  first time and 1 after that while its commit is the same, and asking for a new commit is 1. **GitHub token** on the first page saves a token in your
  browser; it goes only to `api.github.com` and lifts the limit to 5,000. Read-only access is
  enough to read; the page needs Pull requests: read and write to submit your review itself.
- **Private repositories** need that token. This path is written but not tested.
- **A branch** shows its first 300 changed files (GitHub's limit for a comparison). A pull
  request shows all of them.
- **The original of a figure** is a picture in the paper folder that is named for its figure:
  in `published/` as `figure-1.png`, `fig2a.jpg` or as the journal names it
  (`pcbi.1000660.g001.png`), or next to ours as `fig1_published.png`. A figure with no such
  picture shows ours and the overlap only. For a change to a paper that is already in the
  repository the page reads the folder, as the change does not hold the pictures (1 request,
  2 when they are next to ours).
- **Our pictures** are the ones each figure lists in `results.json`. Where a figure that was
  attempted lists none, the page takes the pictures named for it (`fig2_ours.png`, or its
  panels `fig2a_ours.png`, ... when there is no picture of the whole) and says so below them.
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
