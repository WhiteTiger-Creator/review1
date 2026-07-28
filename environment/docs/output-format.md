# Output format

Plain text on standard output, one line per reported quantity, in query order.
Every line starts with the query identifier. A query reports the edges it kept,
then the fitted structure, then one line per held out example. There are four
line shapes.

## A kept dependence

```
<qid> E <a> <b> S <n>/<d>
```

One line per edge the structure keeps, ordered by the lower feature number then
the higher. `a` and `b` are the two feature numbers and the value after `S` is
the pair's score.

## The fitted structure

```
<qid> T <p0> <p1> ...
```

One entry per feature in feature order, each the number of that feature's
parent, or minus one for the feature at the root.

## A held out example

```
<qid> P <i> C <c> W <n>/<d>
```

`i` is the example's row number in the probe table, `c` is the class predicted
for it, and the value after `W` is the winning class score.

## A refused query

```
<qid> REJECT
```

## Rendering

Scores are exact rationals written as a numerator, a single slash and a
denominator, always in lowest terms with a positive denominator, so zero is
`0/1`. The denominator is always written, including when it is one: a score of
eight is rendered `8/1`, never `8`. Nothing is rounded and no decimal point appears. Fields are separated by
single spaces and no line carries trailing whitespace. The shipped example
outputs show the canonical rendering.
