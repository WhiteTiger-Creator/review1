# Input format

The program takes two arguments: the directory holding the tables and the path
to a query file. Queries are handled in file order.

## Tables

Each table is a file named `<name>.csv` in the data directory. Its first line
is a header naming the feature columns and then the label column. Every later
line is one example: one integer per feature column followed by the integer
class label. Feature values and class labels both start at zero. Examples are
indexed from zero in the order they appear after the header.

The same layout serves both roles. A query names one table the model is fitted
on and one table of held out examples classified through it.

## Query lines

One query per line, blank lines ignored, exactly three whitespace separated
fields:

```
<qid> <train> <probe>
```

- `qid` is an opaque identifier echoed at the start of every output line.
- `train` names the table the model is fitted on, without its `.csv` suffix.
- `probe` names the table of held out examples.

## Refused queries

A refused query emits `<qid> REJECT` as its only line. A query is refused when
the line does not have exactly three fields; either named table does not exist;
the training table holds fewer than two examples or fewer than two distinct
class labels; the probe table is empty; either table carries fewer than two
feature columns; or the two tables do not carry the same number of columns.
