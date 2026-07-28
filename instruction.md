A Bayes classifier that treats every feature as independent given the class is
usually too crude, so this model is allowed one extra dependence per feature and
has to learn which feature each one should hang off. That structure learning is
the hard part, and it is a model selection judgment: the dependences have to
form a tree, so the strongest pairwise couplings compete against each other and
some are dropped simply because keeping them would close a cycle.

Pairs are scored by how far each class's joint table of two features departs
from what independence over that table's own margins would predict. The heaviest
pairs are kept in descending order, skipping any that would close a cycle, and
the surviving tree is rooted at feature zero so each unordered pair becomes a
parent and a child. Equal scoring pairs are settled by the pair itself: the one
whose lower numbered feature is smaller comes first, and if those match, the one
whose higher numbered feature is smaller.

Three things are reported. First, every dependence kept, with its score. Second,
the fitted structure as the parent of each feature. Third, for every held out
example, the class predicted and the winning class score, where a class score
multiplies its smoothed share of the training examples by each feature's
smoothed conditional share given the class and its parent's value. Every smoothed
conditional share adds one to its numerator and one single cardinality to its
denominator, and that cardinality is global rather than per feature: one more
than the largest value appearing anywhere in the feature columns of the training
table. The class prior instead adds the number of classes. The largest score
wins, and an exact tie goes to the lower numbered class. Every reported quantity
is an exact rational in lowest terms.

A query names the training table and the held out table. It is refused, emitting
one refusal line, when the line does not carry exactly three fields, when either
named table is missing, when the training table holds fewer than two examples or
fewer than two distinct classes, when the probe table is empty, when either table
carries fewer than two feature columns, or when the two tables disagree on how
many columns they carry.

The learning contract and grammars sit under /app/docs, with ten worked queries
under /app/examples. The model is written under /app/src.
