# Publishing

## Licenses

- Read the paper's copyright line. For "all rights reserved", do not commit the PDF, supplement archives, full-text conversions or page renders to a public repository. Commit only the figures that the comparison needs, with a notice. Ask the user before you publish any of these.
- Check each data license. Apache-2.0 data (for example, the CRAN package HMP 2.0.1) needs a copy of the license text next to the redistributed files.
- Link to the authors' code (for example, GPL-2 packages); do not copy it into the repository. Keep decompiled code local.
- Put every exclusion in `.gitignore` so later commits cannot add it by mistake.

## Pipeline

Use a workflow engine (Nextflow in the worked example) with one process per step.

- Declare inputs and outputs. Scripts read and write their working directory and find their code next to the script file. Use environment variables or arguments for other locations.
- Set `process.stageInMode = 'copy'`. With symlinked inputs, a script that writes a file with the name of an input overwrites the original file in the repository. This happened once in the worked example. Do not give an input and an output the same name; use `stageAs` if needed.
- Groovy keywords such as `native` are not valid `emit` names.
- End with a check step. Compare the run with the committed results. Fail on the claims that must hold (for example, table values at the published precision). Report the rest.
- Commit intermediate inputs that come from tools you cannot redistribute, and say where they came from.

## Continuous integration

- Run the pipeline on the paper's architecture. GitHub `ubuntu-24.04` runners are x86_64.
- Install only what the steps use. For tikzDevice output: `texlive-latex-base`, `texlive-pictures`, `preview-latex-style` and `poppler-utils`. Add R and Python packages, Java and Nextflow.
- Pin package versions or use a container image. An unpinned plotting package can move text by some pixels.
- Write the check report to the job summary and upload the results as an artifact.

## Site

- Build static pages with embedded images, so canvas views work offline and on GitHub Pages.
- Per figure, show the comparison views, sizes, resolution, panel fill, difference metrics and data provenance. Put tables in the journal's format, published next to reproduced.
- Deploy with a GitHub Pages workflow. Check that the deployed page agrees with the pipeline output.

## Self-review

After you open the pull request, post a review on it. List the items you did not reproduce, the largest risks, the fitted parameters, the mistakes that you fixed, and the open checks. Close each open check with a comment when CI answers it.

Write the review in ASD-STE100 style:

- Keep instructions to 20 words or fewer and descriptions to 25 words or fewer.
- Use the active voice and the present tense.
- Write one instruction in each step. Number the steps.
- Use simple, unambiguous words. Give each word one meaning.
- Lead with the problem in bold, then the facts, then the action.
