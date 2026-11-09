# candidate.json and the issue

`render_issue.py` builds every issue from `candidate.json`, so nominations look the same as fossil's existing issues (#15–#24) and none skips a section. [example-candidate.json](../assets/example-candidate.json) is a filled example.

## Fields

| Field | Required | Content |
| --- | --- | --- |
| `schema` | yes | `paper2fossil/candidate/v1` |
| `from_catalog` | no | `true` if the paper came from fossil's audit catalog; the banner then cites the audit |
| `paper.pmcid`, `pmid`, `doi`, `title`, `year` | yes, except `pmid` | From `resolve_ids.py`, not typed |
| `paper.short` | yes | A short description of the method for the title, e.g. `DNA-binding proteins by SVM and PSSM distance transformation` |
| `paper.authors_short` | yes | `Xu et al.`, `Bleakley & Yamanishi` |
| `paper.citation` | yes | Full citation: all authors (or the first six and "et al."), title, *journal* in italics, volume:pages (year) |
| `paper.rcr` | no | iCite RCR |
| `ids` | yes | The JSON `resolve_ids.py --json` wrote. Its status must be `ok` and its PMCID and DOI must equal `paper`'s. |
| `duplicates` | yes | The JSON `check_duplicates.py --json` wrote. Its status must be `none_found`, for this PMCID. |
| `software.status` | yes | `lost` or `partly_found` ([software-search.md](software-search.md)) |
| `software.summary` | yes | One to three sentences: what the paper pointed to, what happened to it, and anything found later |
| `software.evidence` | yes | `[{where, finding, checked}]`, one per place checked, including the ones that found nothing |
| `data_status` | yes | `complete`, `partial` or `none_needed` ([data-check.md](data-check.md)) |
| `validate` | yes | `[{item, published}]`, one row per figure, table or claim to compare against, with the published numbers copied from the paper |
| `validate_notes` | no | A paragraph under the table: inconsistencies in the paper, items that are not results, what level of agreement to expect |
| `inputs` | yes | List of input sources (what, where, size) |
| `gaps` | no | List of missing settings, changed databases, unpublished splits or seeds, supplement defects |
| `effort` | yes | An estimate, written as one: "about 3 days" |
| `plan` | yes | The full reproduction plan in Markdown (below) |

## The plan

The plan goes in the issue, in a collapsed section, so the person who claims the paper has everything without another file. (Whether plans should also be committed to fossil's `availability-audit/reproduction_plans/` is an open question for the reviewers of this skill.) It follows the pilot plans in that folder:

1. **Inventory:** a table with every figure, table and quantitative claim in the text. Columns: item, kind, regenerable (`exact`, `approximate`, `no`, `not-a-result`), inputs, and why.
   - `exact`: deterministic, with all inputs and parameters given.
   - `approximate`: stochastic steps, unspecified seeds, newer database or tool versions, or parameters only partly given.
   - `no`: an input or a step is missing.
   - `not-a-result`: a schematic, diagram, screenshot or worked example.
2. **Method details:** what the paper states and what it leaves out (parameters, preprocessing, versions).
3. **Steps:** an ordered plan, core results first.
4. **Reported numbers:** every number to compare against, with the page or table it comes from. Use the paper's printed precision.
5. **Risks:** what will probably keep a result from matching, and what to do then.

Write only what the paper, its supplement or a source you opened says. If a setting is not stated, say "not stated". Never fill it in from what is usual, and never estimate a number. The banner warns that nothing was run. It does not excuse invented content.

## The rendered issue

Title: `Reproduce <PMCID>: <short> (<authors_short> <year>)`. The body has these sections, in order:

1. the AI-generated-spec warning;
2. the claim rule;
3. **Paper**: link, citation, DOI, RCR;
4. **Software** status and summary;
5. **What to validate** table and notes;
6. **Inputs**;
7. **Known gaps**;
8. **Estimated effort**;
9. **Reproduction plan** (collapsed);
10. **Where we looked for the software** (the evidence table);
11. **How to take this paper**: read and check the spec, use Paper2Repro, one PR in `<PMCID>/` with `Closes #<issue>`, no paper files.

No parent issue and no labels are set. GitHub limits a body to 65,536 characters. If the plan is too long, shorten the prose, not the inventory.
