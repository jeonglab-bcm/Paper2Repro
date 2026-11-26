---
name: paper2revise
description: Review and revise a Paper2Repro pull request until a blind review finds no blocking problem. Blind reviewers check that every figure is on the published frame and matches, and that no sentence claims more than the numbers; a fixer repairs each finding on the pull-request branch; a full clean rerun gates every round. Use to verify, review, revise or finish a reproduction pull request in fossil.
---

# Paper2Revise

Paper2Repro pull requests stop short. Two gaps recur. Figures score well but do not match when you look at them, and verdicts or prose claim more than the numbers support. Paper2Revise closes these gaps after the pull request is open and does not rely on the session that wrote it.

Run it unattended with [review_pr.py](scripts/review_pr.py) (Claude Agent SDK, on the lab server, started by the fossil workflow in [assets/fossil-paper2revise.yml](assets/fossil-paper2revise.yml); setup in [deploy.md](references/deploy.md)). Run it by hand in Claude Code by following the same loop below.

## The loop

A script runs the loop. An agent cannot end a round early; only the gate and a fresh blind review end it.

| Step | Who | Done when |
| --- | --- | --- |
| 1. Gate | Script, no model | Clean worktree at the pull-request head; the one-command Nextflow run and `check_results.py` (and `check_package.py` for a Python package) all exit 0. Failures become blocking `pipeline` findings. |
| 2. Blind review | Two fresh agents, read-only | Each returns findings as JSON. [Figures reviewer](references/review-figures.md) and [claims reviewer](references/review-claims.md). |
| 3. Decide | Script ([findings.py](scripts/findings.py)) | `clean`: gate passes and no blocking finding. `human`: every blocking finding is one the fixer already flagged `needs_human`. Otherwise go on. |
| 4. Fix | One agent, full tools | Every blocking finding has a result: `fixed` with what changed, or `needs_human` with at least two tested hypotheses ([fix-rules.md](references/fix-rules.md)). The orchestrator asks again for any finding left without one. |
| 5. Push | Script | Commit and push to the pull-request branch. Back to step 1. |

Stop at `clean`, at `human`, after 5 rounds, or at the cost cap ($50 for the whole run, all rounds). Then:

- Post one comment on the pull request: the rounds, what was fixed, what is left and why.
- Label the pull request `paper2revise-clean` or `needs-human`.
- Run the [lessons step](references/lessons.md): turn this run's findings into rule changes for Paper2Repro, and open or update one pull request in Paper2Repro with them.

## Blindness

A reviewer that reads the author's reasoning tends to agree with it. So each reviewer:

- starts fresh every round (no memory of earlier rounds or of the fixer);
- works in a throwaway copy with `<id>/session/` deleted (ledger, conversation, earlier review rounds);
- gets the paper, the published figures, the committed outputs, the fresh rerun and the write-ups, and nothing that says what to conclude;
- cannot edit files.

## Rules

- Never change input data to make a figure match. Never loosen a pass mark, remove a control or edit a verdict by hand.
- A figure that does not match is not resolved by lowering its verdict. The fixer keeps working; when the plausible hypotheses are tested and none closes the gap, it flags `needs_human`. A human decides on a downgrade.
- Prose follows `results.json`, never the reverse.
- Every fix is checked by a reviewer who did not make it: the next round's blind review.

## Files

- [references/review-figures.md](references/review-figures.md): the figures reviewer's brief.
- [references/review-claims.md](references/review-claims.md): the claims reviewer's brief.
- [references/fix-rules.md](references/fix-rules.md): the fixer's brief.
- [references/lessons.md](references/lessons.md): the lessons step's brief.
- [references/deploy.md](references/deploy.md): lab-server runner, secrets, workflow, cost.
- [scripts/review_pr.py](scripts/review_pr.py): the orchestrator.
- [scripts/findings.py](scripts/findings.py): finding keys, merging, the round decision, the summary comment.
- [assets/fossil-paper2revise.yml](assets/fossil-paper2revise.yml): the workflow to copy into fossil.
