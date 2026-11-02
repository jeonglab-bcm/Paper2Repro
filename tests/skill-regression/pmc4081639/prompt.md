Use the paper2agent skill (its Paper2Repro component) to reproduce Figure 2 and Table 1 of this paper:

Yu P, Shaw CA. An efficient algorithm for accurate computation of the Dirichlet-multinomial log-likelihood function. Bioinformatics 30(11):1547-1554 (2014).
Paper and supplement: https://pmc.ncbi.nlm.nih.gov/articles/PMC4081639/

Output directory: {{PROJECT_DIR}}

Compare Figure 2 with the published figure pixel by pixel and deliver a rerunnable pipeline.

Rules for this run:

- This is an unattended run. Nobody will answer questions. Make reasonable decisions and record them in the project README.
- Work locally only. Do not create repositories, push, open issues or pull requests, or deploy a site.
- Derive every result from the paper, its supplement and its data. Do not search for or use existing reproductions of this paper.

When you finish, write `{{PROJECT_DIR}}/result.json` with this structure. Paths are relative to `{{PROJECT_DIR}}`.

```json
{
  "table1": {
    "saliva":  {"psi": <your fitted value, full double precision>},
    "throat":  {"psi": ...},
    "tongue":  {"psi": ...},
    "tonsils": {"psi": ...}
  },
  "fig2": {
    "data_csv": "<CSV with columns psi,error: the x and y values of the plotted Figure 2 series>",
    "render": "<your Figure 2 render, PNG or PDF>",
    "compare_report": "<report.json written by compare_figure.py, or null>"
  },
  "pipeline": {
    "command": "<the command that reruns the pipeline>"
  }
}
```

Report your computed values, not the values printed in the paper.
