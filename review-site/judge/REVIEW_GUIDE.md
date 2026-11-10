# How to judge a reproduction

The AI judge reads this file and gives each result a first verdict. A person can then change it
on the review page. Change the words below to change how the AI judges.

## The three verdicts

- **Agrees.** The reproduction supports the same conclusion as the paper. Small gaps are fine
  when a different random split, software version or reading of a printed figure can explain
  them.
- **Partly.** Some parts support the paper's conclusion and other parts do not. Or the direction
  is the same but the gap is too large to be noise.
- **Differs.** The reproduction does not support the paper's conclusion, or the main number is
  clearly different.

## Rules

1. Judge the conclusion, not every printed digit. If most values match and the others are
   close, the verdict is Agrees.
2. Look at the size of each gap next to the size of the value. A gap of 0.02 on a value of
   0.90 is small. A gap of 14 points on an accuracy of 80 is large.
3. A value the paper prints wrongly (it contradicts the paper's own numbers) does not count
   against the reproduction.
4. For a figure, compare the shape, the level and the order of the curves. Line width, colour
   and font do not matter.
5. When a method the paper compares with scores better in our run than in the paper, check
   whether the paper's main claim still holds. If it holds, that is Partly at worst.
6. If the evidence is not enough to judge, say Partly and say what is missing.
