# Paper2Repro changelog

The version in [`VERSION`](VERSION) covers everything in this folder. Each release is tagged
`paper2repro-v<version>` at the merge on `main` that brought it in, so a reproduction can name the exact
skill it ran with.

Bump the version in any pull request that changes this folder, and add a row below. Leave the commit
as `-`. The release workflow tags the merge commit when the pull request lands. Before 1.0, a minor
bump is for a new phase, rule or output a reproduction must follow, and a patch is for wording, fixes
and examples that change nothing a reproduction produces.

| Version | Date | Commit on `main` | Pull request | What changed |
| --- | --- | --- | --- | --- |
| 0.4.0 | 2026-11-07 | 727d35e | #5 | Package the paper's method as a Python or R package with an executed tutorial; rules for other languages; R install through pak. |
| 0.3.0 | 2026-11-05 | 0e010bc | #6 | Claims in the paper's text are scored like figures and tables; gaps with several differing inputs. |
| 0.2.0 | 2026-11-03 | 77e217f | #4 | The fossil version: normalized `results.json` with computed verdicts, its checker, run comparison and the session ledger. |
| 0.1.0 | 2026-11-01 | 2d4cd82 | #1 | First release: reproduce a paper's figures and tables, Nextflow pipeline, figure comparison. |
