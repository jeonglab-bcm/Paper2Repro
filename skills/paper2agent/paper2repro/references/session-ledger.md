# Recording the session

Each reproduction records what it cost: how many prompts the person typed, how many model responses and tool calls it took, and how many tokens. That turns "one shot" into something measured and lets runs be compared.

## Kickoff prompt

Start a new session (not a continued one) in the repository, with only this as the first message:

```text
Reproduce <PMCID> (<DOI or URL>) with the paper2repro skill. Follow its definition of done.
Work on branch <pmcid>-<short-name> and open one pull request at the end.
```

Add anything the person already knows (a mirror for the supplements, figures to skip), but nothing that a rerun would not have. Every later message the person sends counts as an intervention in the ledger, and that count is the measure of how close to one shot the run came.

## Writing the ledger

At the end, before the final commit:

```bash
python3 <skill>/scripts/session_ledger.py --out <PMCID>/session
```

It reads this session's transcript (`~/.claude/projects/<project-slug>/<session-id>.jsonl`, and subagent transcripts in `<session-id>/`) and writes:

- `ledger.json`: session id, start and end, wall-clock minutes, models, human prompts (and how many were sent mid-turn), assistant responses (API calls), tool calls by name, and tokens (input, cache write, cache read, output, thinking within output), for the session, its subagents and both together. If Claude Code wrote its own running cost record, it is copied in as `cost_state`.
- `conversation.md`: every human prompt and every reply in order, each tool call as one line (its description, not its output). Thinking is left out; strings that look like credentials are masked.

Without `--session-id` it takes the newest transcript of the current project folder, which in a fresh session is this one. Token totals count each conversation response once, using its final usage record. Claude Code's own record (`cost_state`, written at the end of each turn) also counts side requests that never appear as responses in the transcript, so it can run a few percent higher. In the session that built this skill the two were identical at the end of the first turn; by the end of the third, Claude Code's record held about 1,000 more input tokens and 5% more cache reads. Report both.

After the pull request is open and CI is green, run it again and push the updated ledger, so the record includes the CI work.

## Keeping it current automatically (optional)

A Stop hook rewrites the ledger after every turn, so it survives a session that ends abruptly. In `.claude/settings.json`:

```json
{
  "hooks": {
    "Stop": [
      {"hooks": [{"type": "command",
        "command": "python3 \"$CLAUDE_PROJECT_DIR\"/.claude/skills/paper2repro/scripts/session_ledger.py --from-hook --out \"$CLAUDE_PROJECT_DIR\"/.paper2repro/session"}]}
    ]
  }
}
```

Git-ignore `.paper2repro/` and copy its contents into `<PMCID>/session/` at the end.

## Caveats

- A cloud session's container is deleted after the session: commit the ledger before it ends.
- The transcript holds the person's prompts verbatim; read `conversation.md` before committing it and remove anything that should not be public.
- Cache reads dominate the token count of long sessions; compare runs on all four token columns, not the total alone.
