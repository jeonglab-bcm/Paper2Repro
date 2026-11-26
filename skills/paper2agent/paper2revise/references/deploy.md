# Deploy

Paper2Revise runs on the lab server as a GitHub Actions self-hosted runner for fossil. A new reproduction pull request starts it; the run uses the Claude API through the Claude Agent SDK.

## Lab server

1. Make a dedicated user (for example `paper2revise`). The agents run with `bypassPermissions`, so this user must own nothing else: no other repositories, no SSH keys, no access to the other services on the server.
2. Install the toolchain that fossil papers need, the same as the paper workflows use: Python 3.11+, [uv](https://docs.astral.sh/uv/), Git, `gh`, Java 21, Nextflow, R, LaTeX and Poppler (see the Paper2Repro README, "Prerequisites").
3. Register a runner for `jeonglab-bcm/fossil` (fossil, Settings, Actions, Runners, New self-hosted runner) as that user, with the extra label `paper2revise`. Install it as a service.
4. The Claude Agent SDK ships the Claude Code CLI it drives; nothing else to install.

## Secrets (fossil, Settings, Secrets and variables, Actions)

| Secret | What | Scope |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Claude API key for the run | A workspace with a spend limit |
| `FOSSIL_BOT_TOKEN` | Pushes fixes, comments, labels in fossil | Fine-grained token or GitHub App on fossil only: Contents and Pull requests read and write |
| `PAPER2REPRO_BOT_TOKEN` | Opens the lessons pull request | Fine-grained token on Paper2Repro only: Contents and Pull requests read and write |

Pushes with `GITHUB_TOKEN` do not start other workflows, so the paper's CI would not run on the fixes. That is why the run pushes with `FOSSIL_BOT_TOKEN`.

## Workflow

Copy [assets/fossil-paper2revise.yml](../assets/fossil-paper2revise.yml) to fossil as `.github/workflows/paper2revise.yml`. It runs when:

- a pull request that changes a `PMC*/` folder opens or reopens;
- someone adds the label `rereview` to such a pull request.

Pushes to the branch (including Paper2Revise's own) do not start it.

## Cost and limits

| Setting | Default | Flag |
| --- | --- | --- |
| Model, all agents | `claude-opus-5-5` | `--model` |
| Effort | `high` | `--effort` |
| Cost cap, whole run | $50 | `--budget` |
| Rounds | 5 | `--rounds` |
| Times the fixer is sent back for unanswered findings | 2 per round | `--nudges` |
| Nextflow rerun timeout | 4 h | `--gate-timeout` |

The cap is enforced per agent call with the SDK's `max_budget_usd`, from what is left; $3 is kept for the lessons step. A round does not start with less than $4 left.

## Run it by hand

From a fossil checkout on the pull request's branch:

```bash
uv run --no-project --with-requirements ~/Paper2Repro/skills/paper2agent/paper2revise/assets/requirements.txt python ~/Paper2Repro/skills/paper2agent/paper2revise/scripts/review_pr.py --repo . --pr 35 --p2r ~/Paper2Repro --no-push
```

`--no-push` commits locally and prints the comment, without pushing, labelling or opening the lessons pull request.

## What a run leaves

- On the pull request: fix commits, `<id>/session/review/paper2revise.json` (every round's gate, findings and fixer results), one comment, and the label `paper2revise-clean` or `needs-human`.
- In Paper2Repro: commits on `paper2revise/lessons` and one open pull request for them.
- In the Actions run: each agent's result (`agents/*.json`, with its session id and cost) and the gate logs.
