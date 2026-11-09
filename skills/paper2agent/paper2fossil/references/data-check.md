# Do the data survive?

In fossil's audit, 96% of cited accessions still resolve, yet 81 of the 143 lost-software papers it checked have lost some of their inputs, usually an in-house set on a dead lab site. Another 15 have lost them all. Check the inputs of the main results, not just whether the paper mentions a dataset.

## Steps

1. **Name the inputs.** For each result in the inventory, find which dataset it was computed from, in the Methods, the figure captions and the supplement captions. Note the version or date when the paper gives one (GO release, BioGRID 2.0.35, NHANES 1999–2004).
2. **PMC supplements.** Download them from the PMC article page and open them. A caption that says "dataset" can be a file of results. Record the file, its size, and whether it holds inputs or outputs. Do not commit them anywhere.
3. **Accessions.** Resolve every GEO, SRA, ArrayExpress, PDB, UniProt, RefSeq or GenBank ID the results depend on. Record suppressed or replaced records (RefSeq XM_ and XP_ often are).
4. **Public datasets and archives.** Fetch the URL or the archived release. Note when the current release differs from the one used, and whether the old one is archived.
5. **Size and compute.** Estimate the download size, and anything that must be rebuilt (PSI-BLAST profiles against nr, genome indices). Put these in `gaps` and `effort`.

## Recording the outcome

`data_status`:

| Value | Meaning |
| --- | --- |
| `complete` | Every input of the main results can be obtained, in PMC or from public sources that work today |
| `partial` | Some inputs are lost. Say which results this affects, in `gaps` and in the validate rows. |
| `none_needed` | Simulation or theory only |
| `unavailable` | The core inputs are gone. Do not open an issue; tell the user. |

`inputs` lists each source with what it holds and its size. Write it so a reproducer can fetch it without rereading the paper.
