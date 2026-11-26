# Lessons

You turn one Paper2Revise run into changes to the Paper2Repro skill, so the next reproduction gets it right the first time. You work in a clone of Paper2Repro at `{p2r}` on the branch `{branch}`.

## What you have

`{rounds_path}` holds every round of the run: the findings, the fixer's results and the final state. The reproduction is `{paper_id}` in fossil, pull request `{pr_url}`.

## What to do

1. Group the findings by cause, not by item. A cause is a gap in the rules: a check that `definition-of-done.md` does not list, a rule `figure-matching.md` states vaguely, a step that `check_results.py` could enforce but does not.
2. Keep only causes that a rule change would have prevented. Drop one-off mistakes that an existing rule already forbids clearly; for those, check the rule is easy to find and say so in one line.
3. For each kept cause, make the smallest change that would have caught it:
   - a line in `skills/paper2agent/paper2repro/references/definition-of-done.md`, with the past failure that motivates it (the file's style: "Each one is here because a past reproduction missed it");
   - or a sharper sentence in the reference that owns the rule;
   - or, only when it is mechanical and small, a check in a script with a test.
4. Do not duplicate a rule that already exists. Do not rewrite sections. Match the files' voice: short, active, present tense.
5. Add one line to `skills/paper2agent/paper2revise/references/lessons-log.md`: date, paper, pull request, the causes, and the files you changed.
6. Commit with a message that names the paper and the causes.

Return a short summary: the causes and the files changed, or "no rule change" with the reason.
