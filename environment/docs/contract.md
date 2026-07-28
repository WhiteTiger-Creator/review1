# Learning contract

The program fits a Bayes classifier that is allowed one extra dependence per
feature instead of assuming they are all independent given the class. Learning
which feature each one should hang off is the model selection step, and the
fitted structure plus the predictions it produces are what gets reported.

## Scoring a pair of features

For an unordered pair of features, and separately within each class, build the
table of joint counts of their values over the training examples of that class
and compare it with what independence would predict from that table's own row
and column totals. Each cell contributes the squared difference between its
observed and expected counts divided by its expected count, and a cell whose
expected count is zero contributes nothing. The pair's score is that sum added
up over every class. Scores are exact rationals and nothing is rounded.

## Choosing the structure

The extra dependences form a tree over the features: every feature but one gets
exactly one parent, and no cycles. The tree keeps the heaviest scoring pairs,
taken in descending score and skipped when they would close a cycle. Equal
scoring pairs are settled by the pair itself: the one whose lower numbered
feature is smaller comes first, and if those match, the one whose higher
numbered feature is smaller. The tree is
then rooted at feature zero and every edge is pointed away from that root, which
is what turns an unordered pair into a parent and a child.

## Predicting

A class score is its smoothed share of the training examples multiplied, for
each feature, by that feature's smoothed conditional share given the class and,
where it has one, given its parent's value in the example being classified. A
feature without a parent is conditioned on the class alone.

Each smoothed conditional share adds one to its numerator and one single
cardinality to its denominator. That cardinality is global, not per feature: it
is one more than the largest value appearing anywhere in the feature columns of
the training table, and the same number is added for every feature, every class
and every parent value. It is not the count of distinct values of the feature
being smoothed, nor the count of values surviving the conditioning. The class
prior is the exception: it adds one to its numerator and the number of classes
to its denominator. The predicted class is the one with the largest score, and when two classes
reach exactly the same score the lower numbered class is predicted.

## Refusal

A malformed query is refused. The input format notes list every condition.
