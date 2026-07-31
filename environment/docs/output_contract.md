Write exactly one Cypher query to /app/answer.cypher as plain text.

The query must be executable as-is against the database at /app/graph/argumentation.kuzu and must return rows with exactly seven columns named `candidate_set`, `live_internal_attacks`, `undefended_members`, `unattacked_outsiders`, `admissible`, `stable` and `maximal_admissible`, in any column order.

## Rows

Return exactly one row for every `CandidateSet` node in the graph. Every candidate set is reported, including a candidate set that has no members, a candidate set whose three counts are all zero, and a candidate set that fails every verdict. A candidate set reported twice is a failure, and a candidate set left out is a failure. Row order is not graded.

## Values

`candidate_set` is the `name` property of the candidate set.

`live_internal_attacks`, `undefended_members` and `unattacked_outsiders` are counts. Return them as integer-valued expressions; they are compared after rendering as decimal text. Each is an exact count, never rounded and never approximated, so there is no tolerance anywhere in the comparison.

`admissible`, `stable` and `maximal_admissible` are booleans. Return them as boolean-valued expressions; they are compared after rendering as the text `True` or `False`.

No column may be null or empty for any row. The result is compared exactly, as an unordered set of rows.

## Trying a query

Use `/app/bin/runquery.sh 'YOUR QUERY HERE'` to execute a query against the same database and inspect its output while working. The runner prints a header row followed by tab separated result rows and applies a wall clock timeout to any single query.

Use `/app/bin/list_schema.sh` to print the size of each node and relationship table in the database.
