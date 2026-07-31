Relationship tables in the abstract argumentation graph.

`IN_FRAMEWORK` connects an `Argument` to a `Framework`: `(:Argument)-[:IN_FRAMEWORK]->(:Framework)` means the claim belongs to that framework. Every claim has exactly one such edge.

`SET_OF` connects a `CandidateSet` to a `Framework`: `(:CandidateSet)-[:SET_OF]->(:Framework)` means the candidate set is a set of claims drawn from that framework. Every candidate set has exactly one such edge.

`MEMBER` connects an `Argument` to a `CandidateSet`: `(:Argument)-[:MEMBER]->(:CandidateSet)` means the claim is a member of that candidate set. A candidate set with no incoming `MEMBER` edge is the empty set, which is a legitimate candidate set and must still be reported.

`RAISES` connects an `Argument` to an `Attack`: `(:Argument)-[:RAISES]->(:Attack)` means the claim is the one raising that objection. Every objection has exactly one such edge, so every objection has exactly one raiser.

`STRIKES` connects an `Attack` to an `Argument`: `(:Attack)-[:STRIKES]->(:Argument)` means the objection is directed at that claim. This is a defeat relation asserted between two propositions; it does not model reachability, transport, or containment, and it is not transitive. If one claim objects to `b` and `b` objects to `c`, that says nothing whatsoever about the first claim and `c`.

`UNDERCUTS` connects an `Attack` to an `Attack`: `(:Attack)-[:UNDERCUTS]->(:Attack)` means the first objection is directed at the second objection rather than at any claim. An objection raised against an objection disputes that the objection carries, not the claim it was aimed at.

Every objection carries exactly one of `STRIKES` or `UNDERCUTS`, never both and never neither.

The objection relation is directed and is not assumed to be symmetric. One claim may object to another without any objection coming back, and both directions may also be present as two separate objections. A claim may object to itself, represented by an objection whose raiser and struck claim are the same node.

None of the relationship tables carry properties. Direction matters for every relationship listed above; Kuzu treats MATCH patterns as directed unless the query author writes them otherwise.
