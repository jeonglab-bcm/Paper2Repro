# Claims in the text

Papers state their conclusions in sentences: a statistic computed from their tables ("RelEx F varies by 19 points between corpora"), a comparison ("co-occurrence beats RelEx on every corpus except LLL"), a significance call ("the correlation is not significant"). Phase 1 lists each one as a `value` item with an id `text.<name>`. A reader takes these sentences as the verdict on the paper, so they need the same rules as figures and tables. PMC2349296 needed a second pull request (fossil #31) because its first results page cited, as agreement, a column that copied one of the paper's rows into our run.

## Three kinds of number

| Kind | What it is | Where it goes in `results.json` |
| --- | --- | --- |
| Arithmetic check | Our code applied to the paper's own tables. It shows that we compute each statistic the way the paper did. It says nothing about our run. | One `check` item, `text.arithmetic`, with the count of claims that came back |
| Ours | Our code applied to our run. The only kind that sets a verdict. | The `observed` value of each `text.*` field |
| Sensitivity | Our run with one input replaced by the paper's value or by another version. It moves toward the paper by construction. | A hypothesis test in the item's `cause` |

Label each column with its kind wherever more than one kind is shown: tables, pages and READMEs. Never cite a sensitivity number as agreement. In PMC2349296 the first page said "Kendall p 0.083, as in the paper"; that value came from the sensitivity column, and our run gives 0.233.

## Steps

1. **Write each claim as fields before you compute ours.** Give the paper's printed value as a string and use `{"printed": true}`:
   - A number: `"expected": "13"`. For "about 0.08", use `"0.08"`.
   - A comparison: `"expected": "yes"`, and `observed` is `"yes"` or `"no"` from a comparison our code computes.
   - A significance call: `"expected": "not significant"`, and `observed` is computed from our p at the paper's α (0.05 unless the paper states another).
2. **Recompute every claim from the paper's own tables first.** If a claim does not come back, our formula is wrong: fix it. If our formula follows the methods and the text still disagrees with the paper's own tables, record a `paper_error` exception with evidence.
3. **Compute ours and let `check_results.py` set the verdict.** Do not widen a tolerance to turn a near miss into a match. A near miss is a field that does not match, with its gap explained in the cause.
4. **Record the parts of a comparison as fields too.** A comparison can hold while the numbers it compares do not. In PMC2349296 "RelEx varies more between corpora than between the methods" holds on our run (19.5 against 8.2 points), but the gap between the methods is 8.2 points against the paper's 13. With all three fields in one item, it is `partly`, not `exact`.
5. **Find the cause of each claim that does not match** with [mismatch-investigation.md](mismatch-investigation.md), section "When several inputs differ". Run the sensitivity variants there, as hypothesis tests.

## Writing it up

- Generate every sentence about a claim from `results.json`, as for figures. A sentence that cites a number cites the number from the "ours" kind, unless it says which other kind it is.
- End the claims section of the README and the results page with one line: the verdict on the paper's main claim, and the causes of the claims that do not match. PMC2349296: "The main finding of the paper holds. Some summary values do not agree. The two causes in item 5 explain these differences."
