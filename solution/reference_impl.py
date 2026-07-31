"""Independent recomputation of the audit certificate from the raw graph.

This is the authoring-time ground truth. It pulls only raw facts (claims and
their framework, the objections with their raiser and target, the candidate
sets and their members) and recomputes every column with plain Python. It never
executes the reference Cypher, so a blind spot shared between the reference
query and a submitted query cannot let a wrong answer pass.

The method is deliberately different from the reference query's. The query
unrolls the standing test to the disclosed bound of three undercuts; this module
resolves it as an unbounded memoized recursion over the undercut relation and
therefore also serves as the proof that the bounded unroll is exact on the
shipped graphs.

Columns produced, straight from the disclosed rules:
  live_internal_attacks  standing objections whose raiser and target are both
                         members; parallel objections count separately
  undefended_members     members carrying a standing objection whose raiser no
                         member strikes with a standing objection
  unattacked_outsiders   non-members of the framework that no member strikes
                         with a standing objection
  admissible             both of the first two counts are zero
  stable                 the first and third counts are zero
  maximal_admissible     admissible, and no other candidate set of the same
                         framework is admissible under its own standing
                         objections and a strict superset
"""

import kuzu


def _rows(conn, query):
    result = conn.execute(query)
    out = []
    while result.has_next():
        out.append(result.get_next())
    return out


def read_facts(graph_path):
    db = kuzu.Database(graph_path, read_only=True, buffer_pool_size=512 * 1024 * 1024)
    conn = kuzu.Connection(db)
    set_name = {
        r[0]: r[1] for r in _rows(conn, "MATCH (s:CandidateSet) RETURN s.id, s.name")
    }
    arg_framework = {
        r[0]: r[1]
        for r in _rows(
            conn,
            "MATCH (a:Argument)-[:IN_FRAMEWORK]->(f:Framework) RETURN a.id, f.id",
        )
    }
    set_framework = {
        r[0]: r[1]
        for r in _rows(
            conn,
            "MATCH (s:CandidateSet)-[:SET_OF]->(f:Framework) RETURN s.id, f.id",
        )
    }
    raiser = {
        r[1]: r[0]
        for r in _rows(
            conn, "MATCH (a:Argument)-[:RAISES]->(o:Attack) RETURN a.id, o.id"
        )
    }
    strikes = {
        r[0]: r[1]
        for r in _rows(
            conn, "MATCH (o:Attack)-[:STRIKES]->(b:Argument) RETURN o.id, b.id"
        )
    }
    undercuts = {
        r[0]: r[1]
        for r in _rows(
            conn, "MATCH (o:Attack)-[:UNDERCUTS]->(p:Attack) RETURN o.id, p.id"
        )
    }
    membership = {sid: set() for sid in set_name}
    for aid, sid in _rows(
        conn, "MATCH (a:Argument)-[:MEMBER]->(s:CandidateSet) RETURN a.id, s.id"
    ):
        membership[sid].add(aid)
    del conn
    del db

    undercutters_of = {}
    for cutter, victim in undercuts.items():
        undercutters_of.setdefault(victim, []).append(cutter)

    return {
        "set_name": set_name,
        "arg_framework": arg_framework,
        "set_framework": set_framework,
        "raiser": raiser,
        "strikes": strikes,
        "undercutters_of": undercutters_of,
        "membership": membership,
    }


def standing_objections(facts, members):
    """Resolve the standing status of every objection under one candidate set.

    An objection stands unless some objection that undercuts it is both raised
    by a member of the set and itself standing. The undercut relation is
    acyclic, so the recursion terminates without a depth bound.
    """
    raiser = facts["raiser"]
    undercutters_of = facts["undercutters_of"]
    memo = {}

    def stands(oid):
        cached = memo.get(oid)
        if cached is not None:
            return cached
        result = True
        for cutter in undercutters_of.get(oid, ()):
            if raiser.get(cutter) in members and stands(cutter):
                result = False
                break
        memo[oid] = result
        return result

    for oid in facts["raiser"]:
        stands(oid)
    return memo


def undercut_chain_depth(facts):
    """Longest chain of undercuts standing over any single objection."""
    undercutters_of = facts["undercutters_of"]
    memo = {}

    def height(oid):
        cached = memo.get(oid)
        if cached is not None:
            return cached
        best = 0
        for cutter in undercutters_of.get(oid, ()):
            best = max(best, 1 + height(cutter))
        memo[oid] = best
        return best

    return max((height(oid) for oid in facts["raiser"]), default=0)


def _counts(facts, sid):
    members = facts["membership"][sid]
    standing = standing_objections(facts, members)
    raiser = facts["raiser"]
    strikes = facts["strikes"]

    live_strikes = [
        oid for oid, target in strikes.items() if standing[oid] and target is not None
    ]

    internal = sum(
        1 for oid in live_strikes if raiser[oid] in members and strikes[oid] in members
    )

    struck_by_member = {strikes[oid] for oid in live_strikes if raiser[oid] in members}

    undefended = 0
    for member in members:
        attackers = {raiser[oid] for oid in live_strikes if strikes[oid] == member}
        if any(attacker not in struck_by_member for attacker in attackers):
            undefended += 1

    fid = facts["set_framework"][sid]
    outside = {
        aid for aid, afid in facts["arg_framework"].items() if afid == fid
    } - members
    outsiders = sum(1 for o in outside if o not in struck_by_member)

    return internal, undefended, outsiders


def compute_reference(graph_path):
    facts = read_facts(graph_path)
    per_set = {sid: _counts(facts, sid) for sid in facts["set_name"]}
    admissible = {sid: (c[0] == 0 and c[1] == 0) for sid, c in per_set.items()}

    sets_of_framework = {}
    for sid, fid in facts["set_framework"].items():
        sets_of_framework.setdefault(fid, []).append(sid)

    membership = facts["membership"]
    answer = set()
    for sid, name in facts["set_name"].items():
        internal, undefended, outsiders = per_set[sid]
        maximal = admissible[sid]
        if maximal:
            for other in sets_of_framework[facts["set_framework"][sid]]:
                if other == sid or not admissible[other]:
                    continue
                if membership[sid] < membership[other]:
                    maximal = False
                    break
        answer.add(
            (
                name,
                str(internal),
                str(undefended),
                str(outsiders),
                str(admissible[sid]),
                str(internal == 0 and outsiders == 0),
                str(maximal),
            )
        )
    return answer


if __name__ == "__main__":
    import sys

    for row in sorted(compute_reference(sys.argv[1])):
        print("\t".join(row))
