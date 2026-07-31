"""Emit the reference Cypher and every graded-wrong baseline from one builder.

The reference query and each named wrong baseline differ only in the flags
passed to `build_query`, so a wrong baseline is provably the reference with one
rule bent rather than an unrelated query that happens to disagree.

That same property is why the baselines are written under solution/ and not
into the test directory: each is the reference query with a single token
changed, so shipping them where the agent can read them would hand over the
answer. seal.py executes them here at authoring time and freezes only their
results into tests/expected.py.

Usage: python3 gen_queries.py <solution-dir> <baseline-dir>
"""

import itertools
import os
import sys

STAND_DEPTH = 3


class _Vars:
    def __init__(self):
        self.counter = itertools.count()

    def take(self, stem):
        return f"{stem}{next(self.counter)}"


def _and(parts):
    return " AND ".join(p for p in parts if p)


def _stands(target, setvar, depth, ignore_membership, v):
    """Predicate text for `target` still standing under the set `setvar`.

    An objection stands unless some objection undercutting it is raised by a
    member of the set and is itself standing. Unrolling that to `depth` levels
    is exact whenever no objection carries a longer chain of undercuts.
    """
    if depth <= 0:
        return None
    raiser = v.take("ur")
    cutter = v.take("uc")
    conditions = []
    if not ignore_membership:
        conditions.append(f"EXISTS {{ MATCH ({raiser})-[:MEMBER]->({setvar}) }}")
    deeper = _stands(cutter, setvar, depth - 1, ignore_membership, v)
    if deeper is not None:
        conditions.append(deeper)
    joined = _and(conditions)
    body = f" WHERE {joined}" if joined else ""
    return (
        f"NOT EXISTS {{ MATCH ({target})<-[:UNDERCUTS]-"
        f"({cutter}:Attack)<-[:RAISES]-({raiser}:Argument){body} }}"
    )


def _internal_count(setvar, standvar, depth, ignore_membership, count_pairs, v):
    """Standing objections with both ends inside `setvar`."""
    if count_pairs:
        src = v.take("ps")
        tgt = v.take("pt")
        obj = v.take("po")
        stands = _stands(obj, standvar, depth, ignore_membership, v)
        reach = (
            f"EXISTS {{ MATCH ({src})-[:RAISES]->({obj}:Attack)"
            f"-[:STRIKES]->({tgt}){_where(stands)} }}"
        )
        return (
            f"COUNT {{ MATCH ({src}:Argument), ({tgt}:Argument)\n"
            f"    WHERE EXISTS {{ MATCH ({src})-[:MEMBER]->({setvar}) }}\n"
            f"      AND EXISTS {{ MATCH ({tgt})-[:MEMBER]->({setvar}) }}\n"
            f"      AND {reach} }}"
        )
    src = v.take("is")
    obj = v.take("io")
    tgt = v.take("it")
    conditions = _and(
        [
            f"EXISTS {{ MATCH ({src})-[:MEMBER]->({setvar}) }}",
            f"EXISTS {{ MATCH ({tgt})-[:MEMBER]->({setvar}) }}",
            _stands(obj, standvar, depth, ignore_membership, v),
        ]
    )
    return (
        f"COUNT {{ MATCH ({src}:Argument)-[:RAISES]->({obj}:Attack)"
        f"-[:STRIKES]->({tgt}:Argument)\n"
        f"    WHERE {conditions} }}"
    )


def _where(predicate):
    return f" WHERE {predicate}" if predicate else ""


def _undefended_body(setvar, standvar, depth, ignore_membership, self_defence, v):
    """Members of `setvar` carrying a standing objection the set does not answer."""
    member = v.take("dm")
    atk = v.take("da")
    obj = v.take("do")
    defender = v.take("dd")
    cobj = v.take("dc")
    stands_obj = _stands(obj, standvar, depth, ignore_membership, v)
    stands_cobj = _stands(cobj, standvar, depth, ignore_membership, v)
    if self_defence:
        defence = (
            f"MATCH ({member})-[:RAISES]->({cobj}:Attack)-[:STRIKES]->({atk})"
            f"{_where(stands_cobj)}"
        )
    else:
        answered = _and(
            [f"EXISTS {{ MATCH ({defender})-[:MEMBER]->({setvar}) }}", stands_cobj]
        )
        defence = (
            f"MATCH ({defender}:Argument)-[:RAISES]->({cobj}:Attack)"
            f"-[:STRIKES]->({atk}){_where(answered)}"
        )
    unanswered = _and([stands_obj, f"NOT EXISTS {{ {defence} }}"])
    return (
        f"MATCH ({member}:Argument)-[:MEMBER]->({setvar})\n"
        f"    WHERE EXISTS {{ MATCH ({atk}:Argument)-[:RAISES]->({obj}:Attack)"
        f"-[:STRIKES]->({member})\n"
        f"                   WHERE {unanswered} }}"
    )


def _outsiders_body(setvar, framework, depth, ignore_membership, v):
    """Claims of the framework outside `setvar` that no member strikes."""
    out = v.take("oa")
    mem = v.take("om")
    obj = v.take("oo")
    covered = _and(
        [
            f"EXISTS {{ MATCH ({mem})-[:MEMBER]->({setvar}) }}",
            _stands(obj, setvar, depth, ignore_membership, v),
        ]
    )
    return (
        f"MATCH ({out}:Argument)-[:IN_FRAMEWORK]->({framework})\n"
        f"    WHERE NOT EXISTS {{ MATCH ({out})-[:MEMBER]->({setvar}) }}\n"
        f"      AND NOT EXISTS {{ MATCH ({mem}:Argument)-[:RAISES]->({obj}:Attack)"
        f"-[:STRIKES]->({out})\n"
        f"                        WHERE {covered} }}"
    )


def build_query(
    depth=STAND_DEPTH,
    ignore_membership=False,
    shared_standing=False,
    self_defence=False,
    stable_ignores_conflict=False,
    superset_only=False,
    count_pairs=False,
):
    v = _Vars()
    internal = _internal_count("s", "s", depth, ignore_membership, count_pairs, v)
    undefended = _undefended_body("s", "s", depth, ignore_membership, self_defence, v)
    outsiders = _outsiders_body("s", "f", depth, ignore_membership, v)

    stable_expr = (
        "(unattacked_outsiders + 0) = 0"
        if stable_ignores_conflict
        else "(live_internal_attacks + 0) = 0 AND (unattacked_outsiders + 0) = 0"
    )

    # The cheap structural tests are stated before the standing-sensitive
    # admissibility tests, so the expensive predicate is only ever evaluated
    # for candidate sets that really are strict supersets.
    sub = v.take("sa")
    sup = v.take("sb")
    covers_subset = (
        f"NOT EXISTS {{ MATCH ({sub}:Argument)-[:MEMBER]->(s)\n"
        f"                     WHERE NOT EXISTS {{ MATCH ({sub})-[:MEMBER]->(t) }} }}"
    )
    adds_a_member = (
        f"EXISTS {{ MATCH ({sup}:Argument)-[:MEMBER]->(t)\n"
        f"                 WHERE NOT EXISTS {{ MATCH ({sup})-[:MEMBER]->(s) }} }}"
    )
    competitor = ["t.id <> s.id", covers_subset, adds_a_member]
    if not superset_only:
        stand_for_t = "s" if shared_standing else "t"
        rival_src = v.take("rs")
        rival_obj = v.take("ro")
        rival_tgt = v.take("rt")
        rival_conflict = _and(
            [
                f"EXISTS {{ MATCH ({rival_src})-[:MEMBER]->(t) }}",
                f"EXISTS {{ MATCH ({rival_tgt})-[:MEMBER]->(t) }}",
                _stands(rival_obj, stand_for_t, depth, ignore_membership, v),
            ]
        )
        competitor.append(
            f"NOT EXISTS {{ MATCH ({rival_src}:Argument)-[:RAISES]->"
            f"({rival_obj}:Attack)-[:STRIKES]->({rival_tgt}:Argument)\n"
            f"                     WHERE {rival_conflict} }}"
        )
        rival_undefended = _undefended_body(
            "t", stand_for_t, depth, ignore_membership, self_defence, v
        )
        competitor.append(f"NOT EXISTS {{ {rival_undefended} }}")

    joined_competitor = "\n    AND ".join(competitor)
    return f"""MATCH (s:CandidateSet)-[:SET_OF]->(f:Framework)
WITH s, f,
  {internal} AS live_internal_attacks,
  COUNT {{ {undefended} }} AS undefended_members,
  COUNT {{ {outsiders} }} AS unattacked_outsiders
WITH s, f, live_internal_attacks, undefended_members, unattacked_outsiders,
  ((live_internal_attacks + 0) = 0 AND (undefended_members + 0) = 0) AS adm,
  ({stable_expr}) AS stb
OPTIONAL MATCH (t:CandidateSet)-[:SET_OF]->(f)
  WHERE {joined_competitor}
WITH s, live_internal_attacks, undefended_members, unattacked_outsiders, adm, stb,
     count(t) AS n_super
RETURN s.name AS candidate_set,
       live_internal_attacks AS live_internal_attacks,
       undefended_members AS undefended_members,
       unattacked_outsiders AS unattacked_outsiders,
       adm AS admissible,
       stb AS stable,
       (adm AND (n_super + 0) = 0) AS maximal_admissible
"""


NAIVE_FIXTURES = {
    "naive_all_objections_stand": {"depth": 0},
    "naive_single_undercut": {"depth": 1},
    "naive_undercut_depth_two": {"depth": 2},
    "naive_undercut_ignores_raiser": {"ignore_membership": True},
    "naive_shared_standing": {"shared_standing": True},
    "naive_self_defence": {"self_defence": True},
    "naive_stable_without_conflict_free": {"stable_ignores_conflict": True},
    "naive_superset_only_maximality": {"superset_only": True},
    "naive_count_objection_pairs": {"count_pairs": True},
}


def main():
    if len(sys.argv) != 3:
        sys.stderr.write("usage: gen_queries.py <solution-dir> <fixtures-dir>\n")
        return 2
    solution_dir, fixtures_dir = sys.argv[1], sys.argv[2]
    os.makedirs(fixtures_dir, exist_ok=True)
    with open(
        os.path.join(solution_dir, "answer_correct.cypher"), "w", encoding="utf-8"
    ) as fh:
        fh.write(build_query())
    for name, flags in NAIVE_FIXTURES.items():
        with open(
            os.path.join(fixtures_dir, f"{name}.query"), "w", encoding="utf-8"
        ) as fh:
            fh.write(build_query(**flags))
    sys.stderr.write(f"wrote reference + {len(NAIVE_FIXTURES)} wrong baselines\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
