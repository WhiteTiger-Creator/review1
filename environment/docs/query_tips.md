General Cypher syntax notes for this Kuzu database, not specific to the question in instruction.md. Kuzu is pinned at version 0.6.1 and its dialect differs from other Cypher implementations in ways that are worth knowing before writing a long query.

## Aliasing and staging

Use `AS` to alias a returned expression, for example `RETURN s.name AS candidate_set`.

Use `WITH` to pass intermediate values, including boolean expressions and aggregate results, from one part of a query to the next. A `WITH` clause carries forward exactly the variables it names, so a variable that is not listed is no longer in scope after it.

Use `LIMIT` while exploring the graph interactively through `/app/bin/runquery.sh`, then remove it before writing the final query to `/app/answer.cypher`, since the requested output should include every matching row.

## Subqueries

`EXISTS { MATCH ... }` and `NOT EXISTS { MATCH ... }` are supported, and a subquery may correlate on a node variable bound in the enclosing scope. Such a subquery may carry its own `WHERE` clause, and it may itself contain a further `EXISTS` or `NOT EXISTS` subquery.

## A projection limit worth knowing about in advance

This is an engine limitation of Kuzu 0.6.1 rather than anything to do with the question being asked, and it is documented here so that it costs no time.

Kuzu 0.6.1 will reject a deeply nested `EXISTS` subquery when that subquery is evaluated as a projected expression, that is, when it appears directly in a `RETURN` or `WITH` list, and a node variable bound at a middle level of the nesting is referenced two levels further down. The error reads `Binder exception: Cannot evaluate expression with type PROPERTY`. The identical predicate is accepted when it appears in a `WHERE` clause instead. Shallower nesting in a projection is fine; it is the combination of projection and a middle-level variable used two levels down that the binder refuses.

The way around it is to stage the query rather than inline everything into one projection. Compute a value with `WITH`, and where a predicate is too deep to project, move it into a `WHERE` clause and recover what you need from it another way. `OPTIONAL MATCH` combined with a `WHERE` clause and then `count()` over the optionally matched variable is a standard staging device in this dialect: the `WHERE` clause of an `OPTIONAL MATCH` may hold arbitrarily deep subqueries, and counting the matches afterwards turns that predicate into a value the query can carry forward and test. A `count()` of zero means nothing satisfied the `WHERE` clause.

One further quirk of the same engine version: an aggregate result is sometimes not directly comparable in the clause that produces it. Rematerializing it with a trivial arithmetic identity, for example writing `(n + 0) = 0` rather than `n = 0`, is a known and harmless workaround.

## Miscellaneous

String property values are matched with curly brace syntax inside a node pattern, for example `(s:CandidateSet {name: 'set_example'})`, or with a `WHERE` clause using `s.name = 'set_example'`.

Boolean expressions may be combined with `AND`, `OR` and `NOT`, and a boolean-valued expression may be returned directly as a column.

List membership and list-comprehension syntax from other Cypher dialects is not available in Kuzu 0.6.1, and neither are recursive common table expressions. None of the constructs named in this file require them.

## Working in this environment

Why did my query through runquery.sh return nothing after a while? The runner applies a wall clock timeout to every invocation, so a query that never terminates gets killed and reported as a failure rather than hanging the session.

Why do I need to quote my query when calling runquery.sh? The whole query text is passed as a single shell argument, so wrap it in single quotes and use double quotes for any string literals inside the query itself.

Can I run more than one query while exploring? Yes, call /app/bin/runquery.sh as many times as needed with different query text before writing the final query to /app/answer.cypher.

Does column order in my RETURN clause matter? No, the seven required columns can be returned in any order, they only need to carry the names listed in /app/docs/output_contract.md.

Is the database at /app/graph/argumentation.kuzu writable? It is opened read only by every tool in this environment, so queries can only read data, never modify it.

Is the answer graded against my query text? No. The query is executed and only the rows it returns are compared against the expected result. The same query is also executed against further conforming instances of this schema, so an answer that restates the visible rows instead of deriving them does not pass.

Does the graph contain claims that object to themselves, or objections aimed at other objections? See /app/docs/relationship_types.md for how the objection relation is represented and /app/docs/extension_rules.md for what the definitions say about both cases. The audit must handle whatever the database actually contains.
