Exact definitions of every column the audit must produce, referenced by the question in instruction.md. These restate the semantics of abstract argumentation with recursive attack, so that the audit applies them exactly as written rather than from memory of the plain Dung setting. Read all of them before deciding any of them: the columns are not independent, and the last one is not settled by the candidate set being certified alone.

## Standing

An objection is raised by one claim and is directed either at a claim or at another objection. An objection directed at another objection is said to undercut it.

Whether an objection counts at all is decided one candidate set at a time.

An objection **stands** under a candidate set when no objection that undercuts it is both raised by a member of that set and itself standing under that set.

Three things follow and each carries weight. The test is recursive: an undercut only brings its target down while the undercut itself is standing, so an undercut that has itself been brought down leaves its target standing after all. The test is relative to the set: an undercut raised by a claim outside the set does nothing whatever, so the same objection can stand under one candidate set and have fallen under another candidate set of the same framework. And the test terminates: no objection in this graph sits under a chain of more than three undercuts, and no objection undercuts one that directly or indirectly undercuts it.

An objection that stands and is directed at a claim is said to strike that claim. An objection that has fallen strikes nothing and defends nothing. Every column below is computed over standing objections only.

## live_internal_attacks

The number of standing objections whose raiser is a member of the candidate set and whose struck claim is also a member of that set. The two members need not be distinct, so a claim that objects to itself contributes whenever it is a member. Objections are counted one by one, so two distinct objections raised by the same claim against the same claim contribute two.

A candidate set is conflict free exactly when this count is zero.

## undefended_members

A member is **defended** by its candidate set when, for every standing objection struck at it, some member of the set raises a standing objection that strikes the raiser of that objection. The defender is any member and need not be the struck member itself; a member that cannot object to its own objector is still defended as long as another member does. A member no standing objection strikes is defended vacuously.

This column counts members, not objections: it is the number of members of the candidate set that are not defended by it.

## admissible

A candidate set is admissible when live_internal_attacks and undefended_members are both zero. A candidate set with no members is therefore admissible whenever it is conflict free.

## unattacked_outsiders

The number of claims of the candidate set's framework that are not members of the set and that no member strikes with a standing objection. This column counts claims.

## stable

A candidate set is stable when live_internal_attacks and unattacked_outsiders are both zero. Conflict-freeness is required for stability exactly as it is required for admissibility: a set that covers every claim outside it but holds an internal standing objection is not stable. In a framework with no claims at all, the set with no members is stable.

## maximal_admissible

A candidate set is maximal admissible when it is admissible and no other candidate set of the same framework is both admissible and a strict superset of it.

Four parts of this definition each carry weight. The comparison is made only against the candidate sets present in the graph for that framework, not against every subset that could be written down. The superset must itself be admissible, so a strict superset that is not admissible does not cost a set its maximality. The containment must be strict, so a different candidate set with exactly the same members is not a strict superset, and two candidate sets with identical members receive identical verdicts. And the superset's admissibility is decided under the superset's own standing objections, not under the smaller set's: the two sets have different members, so they can disagree about which objections stand, and a rival judged on the wrong set's standing is a rival that does not exist. A candidate set that is not admissible is never maximal admissible, whatever its supersets look like.
