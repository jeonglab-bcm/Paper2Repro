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
| compare_figure metrics, cost, turns, time | reported | |

Once a few baseline runs exist, a reported metric can become a hard check.

## Run

```bash
python3 tests/skill-regression/test_score.py   # harness unit tests, free and fast
```

The end-to-end run is `.github/workflows/skill-regression.yml`. It needs the repository secret `ANTHROPIC_API_KEY`. It runs weekly, on manual dispatch (with model and budget inputs), and on pull requests that have the `skill-regression` label. The report goes to the job summary. The project, transcript and score are uploaded as an artifact.

To score a local run:

```bash
python3 tests/skill-regression/score.py --case tests/skill-regression/pmc4081639 \
  --project <project dir> --transcript <stream-json transcript>
```

## Add a case

Add a directory with `expected.json`, `prompt.md` and `settings.json`. Extend `score.py` if the case needs new checks. Add a job or matrix entry to the workflow.
