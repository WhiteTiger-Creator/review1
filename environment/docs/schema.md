Abstract argumentation graph schema, loaded into an embedded Kuzu database at /app/graph/argumentation.kuzu.

Node table `Framework`: `id` (INT64), `name` (STRING). One argumentation framework under audit.

Node table `Argument`: `id` (INT64), `name` (STRING). One abstract claim, that is, a proposition whose internal structure is deliberately not modelled.

Node table `Attack`: `id` (INT64), `name` (STRING). One objection. An objection is a node rather than an edge, because an objection can itself be the target of another objection. Every objection is raised by exactly one claim and is directed at exactly one target, which is either a claim or another objection.

Node table `CandidateSet`: `id` (INT64), `name` (STRING). One set of claims submitted for review.

Every node table exposes `id` and `name` as regular properties, reachable with the usual dot syntax, for example `s.name` or `a.id`.

## Independence of frameworks

Each `Framework` is self-contained. Every `Argument` belongs to exactly one framework, every `CandidateSet` belongs to exactly one framework, and every member of a candidate set is a claim of that same framework. No objection ever crosses a framework boundary. A framework may contain no claims at all.

## Shape of the instance

A `CandidateSet` may have any number of members, including none. Two distinct candidate sets in the same framework may have exactly the same members. An `Argument` may be a member of several candidate sets, of one, or of none.

Two distinct objections may be raised by the same claim against the same claim. They are separate `Attack` nodes and they are separate objections.

The undercut relation between objections is acyclic, and no objection in this instance sits under a chain of more than three undercuts. That is a fact about the data these audits run on, recorded here so the audit knows the recursive standing test in /app/docs/extension_rules.md terminates and how far the chains it must follow actually reach.
