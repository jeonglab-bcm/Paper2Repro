# Skill regression tests

These tests check that a change to `skills/paper2agent` does not make the skill worse at reproducing a paper whose answers we already know.

## How it works

1. `blind_skill.py` installs the skill from the current commit. It replaces the worked example for the test paper with a stub and removes every sentence that contains one of that paper's answers. It fails if any answer marker is still present.
2. The workflow deletes the checkout, so the agent cannot read the full worked example.
3. Claude Code runs the prompt in `<case>/prompt.md` on its own. It must write `result.json` in a fixed format. `<case>/settings.json` blocks the agent from fetching the existing reproduction.
4. `score.py` checks `result.json` against `<case>/expected.json` and checks the transcript for access to the existing reproduction.

## Case: PMC4081639 (Yu & Shaw 2014)

| Check | Kind | Pass condition |
| --- | --- | --- |
| Table 1 ψ (4 sites) | hard | Rounds to the printed value, within 0.1% of the reference fit, and is not the printed value copied back |
| Fig. 2 grid | hard | 300 points from 1e-11 to 1e-10 (the grid found from the published curve) |
| Fig. 2 render | hard | The file exists |
| No leak | hard | The transcript does not mention `jeonglab-bcm/fossil` |
| Fig. 2 values identical to reference | reported | Count of points equal to the reference series, which is identical to the paper on x86_64 |
| Skill version | reported | Commit, checksum of the checkout and checksum of the blinded copy that the agent used, from `skill_checksum.py` before the run |
| Skill checksum in result.json | reported | Equals the checksum of the installed skill |
| compare_figure metrics, cost, turns, time | reported | |

Once a few baseline runs exist, a reported metric can become a hard check.

## Session log

`session_log.py` turns the agent's stream-json transcript into a record of the session: the conversation, every tool call (input, output, error, duration), subagent work, and token use and cost per model. The workflow writes the summary to the job summary and puts `session.html` (a searchable timeline), `session.md`, `session.json` and `summary.md` in the run artifact under `out/session/`.

```bash
python3 tests/skill-regression/session_log.py summary transcript.jsonl              # one session
python3 tests/skill-regression/session_log.py summary runs/*/out/transcript.jsonl   # compare sessions
python3 tests/skill-regression/session_log.py render transcript.jsonl --out view   # write the viewer
```

Totals come from Claude Code's final `result` event and include subagents. If the run is cut off before that event (time limit, cancel), the totals come from the stream instead: the summary says so, cost is not available, and output tokens are undercounted.

To compare past runs: `gh run download <run id> -n skill-regression-pmc4081639 -D runs/<run id>` for each run, then `summary` on the transcripts.

## Run

```bash
python3 tests/skill-regression/test_score.py        # harness unit tests, free and fast
python3 tests/skill-regression/test_session_log.py
python3 skills/paper2agent/scripts/test_skill_checksum.py
```

The end-to-end run is `.github/workflows/skill-regression.yml`. It needs the repository secret `ANTHROPIC_API_KEY`. It runs weekly, on manual dispatch (with model and budget inputs), and on pull requests that have the `skill-regression` label. The score and the session summary go to the job summary. The project, transcript, score and session log are uploaded as an artifact.

To score a local run:

```bash
python3 tests/skill-regression/score.py --case tests/skill-regression/pmc4081639 \
  --project <project dir> --transcript <stream-json transcript> [--skill-version skill-version.json]
```

## Add a case

Add a directory with `expected.json`, `prompt.md` and `settings.json`. Extend `score.py` if the case needs new checks. Add a job or matrix entry to the workflow.
