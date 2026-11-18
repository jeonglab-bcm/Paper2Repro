# Is the software really lost?

A wrong "lost" wastes a reproducer's week and can be embarrassing. RPISeq (PMC3322362) was recorded as lost after registry and web searches, and a reproducer later found its feature code and training data in the lab's successor tool, `Dobbs-Lab/RPIMotif`, a repository named after a different tool. Search the way that would have found it.

Two more nearly went out as lost while their code was live (2026-11-18):

- **E-Predict (PMC1242213).** The paper's `http://derisilab.ucsf.edu/epredict/` timed out, but the full source was at `https://derisilab.ucsf.edu/software/epredict/` on the same site. Only bio.tools' homepage knew the new path, and bio.tools' free-text search buried the entry under thousands of others.
- **N-of-1-pathways (PMC4215042).** The lab moved from `lussierlab.org` to `lussiergroup.org` and kept its page paths. The paper's link answered 404; the group's 2017 MixEnrich paper gave the new domain.

A dead link means the address is gone, not the software. `check_software.py` now tries the other scheme, the parent paths and the host's root page, looks up bio.tools by exact name and ID and checks each homepage, and tries the paper's paths on any new lab domain that later papers by the same authors link to. Every live result is listed under `likely_moved`.

## Where to look, in order

1. **The paper's own links.** These are in the abstract, the availability, implementation or software section, and the supplement. Run `check_software.py --url` on each one. A link that answers can still be dead (a parked domain, a hijacked page, a generic lab homepage), so open the live ones. A link that fails while its host still answers usually means the page moved on the same site: look at the site's software or tools page. Timeouts and 502–504 are "no answer", not "gone"; try again later before you rely on them.
2. **The Wayback Machine.** A capture of the download page may hold the code itself, or name the archive and version. Open the capture closest to the publication year.
3. **The supplement.** Code is sometimes hidden in a RAR, ZIP, `.RData`, binary or PDF. The audit found 4 papers recorded as lost whose code was in the supplement after all.
4. **Registries.** CRAN (including archived packages), Bioconductor, PyPI, bio.tools and Bioconda. `check_software.py --name` covers all but Bioconda; search `bioconda-recipes` by hand.
5. **Code hosts.** GitHub, GitLab, Bitbucket, SourceForge, and the Google Code archive (`code.google.com/archive/p/<name>`).
6. **The authors.** Look up the first and last authors' current lab pages and their GitHub organizations. Labs change domain when they move institution or rename themselves; `check_software.py` finds new domains in later papers by the same authors and tries the paper's paths on them, but check the lab's current site by hand as well. Look for successor tools from the same lab and read their code for the paper's feature names or file formats. This step found RPISeq.
7. **Papers that cite it.** A later paper that "used the original implementation of X" may say where it got it. Europe PMC's citations of the paper are a quick list.
8. **Ask-only.** "Available from the authors on request" counts as lost unless a public copy exists.

## When a hit counts

A hit is the paper's software only if one of these holds:

- the same authors or lab publish it;
- it names or cites the paper;
- its code matches the paper's method (same features, file formats or parameters).

A tool with the same name from someone else is not a hit. A later reimplementation by the same lab is not the lost code. Note it as useful for checking the method, as #22 did for BioSeq-Analysis2.0.

## Recording the outcome

`software.status`:

| Status | Meaning | Issue? |
| --- | --- | --- |
| `lost` | Nothing runnable from the authors survives in public. Includes binaries that no longer run on any available platform. | yes |
| `partly_found` | Some pieces survive (feature code, a trained model, part of the data) but not the method end to end. Say exactly what was found and where. | yes |
| `moved` | The software lives on somewhere and runs, or could. | no: report the home to the user |

`software.evidence` has one row per place checked: `where`, `finding` and `checked` (the date, YYYY-MM-DD). Include the places that turned up nothing. "No entry in CRAN, Bioconductor, PyPI or bio.tools" is evidence, and it tells the next person what not to repeat.
