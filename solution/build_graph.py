"""Deterministic generator for the abstract-argumentation graph.

Builds a Kuzu database of argumentation frameworks, their claims, the
objections raised in them, and the candidate sets under review. An objection is
raised by one claim and is directed either at a claim or at another objection.
The same generator produces the committed visible instance, the hidden-seed
instance the verifier grades against, and the metamorphic variant.

Every framework is independent: claims, objections and candidate sets never
cross a framework boundary. A fixed roster of designed archetypes guarantees
that all three instances really contain the situations the audit turns on: an
undercut chain of every length up to the disclosed bound of three, a standing
objection whose only counter is an undercut rather than a counter-objection, a
superset whose standing set differs from the subset's, parallel objections
between the same pair of claims, and the classical Dung situations of a
self-objecting claim, an odd cycle, and a maximal set with an inadmissible
superset. Randomized frameworks are layered on top so the hidden instance is a
genuinely different graph rather than a relabelling of the visible one.

Visible and hidden instances draw their names from disjoint syllable blocks, so
no claim, objection, framework or candidate set name occurs in both.

After the database is written it is compacted through EXPORT DATABASE /
IMPORT DATABASE into a fresh directory. Kuzu preallocates large mostly-empty
pages, and an uncompacted database of this size ships tens of megabytes, far
more than the instance carries and large enough to break sandbox upload.

Determinism: a given seed always yields the same frameworks, claims,
objections, candidate sets and therefore the same certificate for every set.
The Kuzu database files themselves are not byte-reproducible across runs,
because the engine lays out pages with run-dependent internal state, so the
graphs are generated once and committed as frozen artifacts rather than rebuilt
during verification. The verifier reads only the committed databases.

Usage: python3 build_graph.py <output-db-path> <seed> [block]
"""

import os
import random
import shutil
import sys
import tempfile

import kuzu

# Two disjoint first-syllable blocks. The visible instance draws from block 0
# and the hidden instance from block 1, so the two graphs share no name.
_SYL1_BLOCKS = [
    ["ka", "lo", "mi", "ne", "ro", "su", "ta", "vi", "ze", "bu", "de", "fa"],
    ["gi", "ha", "ju", "ky", "na", "pe", "qi", "sy", "tu", "va", "wo", "xe"],
]

_SYL2 = [
    "ban",
    "dor",
    "fex",
    "gil",
    "hum",
    "jav",
    "kor",
    "lyn",
    "mor",
    "nix",
    "pol",
    "rus",
    "sen",
    "tiv",
    "vok",
    "wen",
    "yth",
    "zad",
]

# The audit's disclosed bound: no objection sits under a chain of more than
# this many undercuts. The designed roster exhibits chains of every length from
# one to this bound, so an audit that stops short of it is wrong on the graph.
MAX_UNDERCUT_CHAIN = 3


class Namer:
    """Hands out unique, seed-dependent names from one syllable block."""

    def __init__(self, rng, block):
        self.pool = [a + b for a in _SYL1_BLOCKS[block] for b in _SYL2]
        rng.shuffle(self.pool)
        self.index = 0

    def take(self, prefix):
        word = self.pool[self.index]
        self.index += 1
        return f"{prefix}_{word}"


def _claims(namer, keys):
    return {key: namer.take("claim") for key in keys}


def _fw(namer, claims, objections, sets, archetype):
    return {
        "name": namer.take("forum"),
        "args": list(claims.values()),
        "objections": objections,
        "sets": sets,
        "archetype": archetype,
    }


# ---------------------------------------------------------------------------
# Designed archetypes carrying the undercut mechanics.
# ---------------------------------------------------------------------------


def _undercut_rescue_framework(namer):
    """A two-deep undercut chain: the rescued objection still stands.

    o1 objects to b; o2 undercuts o1; o3 undercuts o2. With every raiser
    present, o3 stands, so o2 falls, so o1 stands again after all. Dropping the
    raiser of o3 leaves o2 standing and o1 fallen; dropping the raiser of o2
    leaves o1 standing for a different reason. The three candidate sets
    separate a one-step reading, a raiser-blind reading, and the truth.
    """
    n = _claims(namer, ["a", "b", "c", "d"])
    o1 = namer.take("objection")
    o2 = namer.take("objection")
    o3 = namer.take("objection")
    objections = [
        (o1, n["a"], "claim", n["b"]),
        (o2, n["c"], "objection", o1),
        (o3, n["d"], "objection", o2),
    ]
    sets = [
        (namer.take("set"), [n["a"], n["b"], n["c"], n["d"]]),
        (namer.take("set"), [n["a"], n["b"], n["c"]]),
        (namer.take("set"), [n["a"], n["b"]]),
        (namer.take("set"), [n["c"], n["d"]]),
    ]
    return _fw(namer, n, objections, sets, "_undercut_rescue_framework")


def _undercut_depth_three_framework(namer):
    """A three-deep undercut chain, the disclosed bound.

    An audit that unrolls the standing test to two levels reads the bottom
    objection as standing when it has in fact fallen.
    """
    n = _claims(namer, ["p", "q", "r", "t", "u"])
    o1 = namer.take("objection")
    o2 = namer.take("objection")
    o3 = namer.take("objection")
    o4 = namer.take("objection")
    objections = [
        (o1, n["p"], "claim", n["q"]),
        (o2, n["r"], "objection", o1),
        (o3, n["t"], "objection", o2),
        (o4, n["u"], "objection", o3),
    ]
    sets = [
        (namer.take("set"), [n["p"], n["q"], n["r"], n["t"], n["u"]]),
        (namer.take("set"), [n["p"], n["q"], n["r"], n["t"]]),
        (namer.take("set"), [n["q"], n["r"], n["u"]]),
    ]
    return _fw(namer, n, objections, sets, "_undercut_depth_three_framework")


def _undercut_defence_framework(namer):
    """Defence by undercutting the objection rather than by counter-objection.

    y objects to x and nothing objects to y, so no counter-objection is
    available. z undercuts that objection, so a set holding x and z leaves x
    with no standing objection at all and is admissible, while the set holding
    only x is not.
    """
    n = _claims(namer, ["x", "y", "z", "w"])
    o1 = namer.take("objection")
    o2 = namer.take("objection")
    objections = [
        (o1, n["y"], "claim", n["x"]),
        (o2, n["z"], "objection", o1),
    ]
    sets = [
        (namer.take("set"), [n["x"]]),
        (namer.take("set"), [n["x"], n["z"]]),
        (namer.take("set"), [n["x"], n["z"], n["w"]]),
        (namer.take("set"), [n["y"]]),
    ]
    return _fw(namer, n, objections, sets, "_undercut_defence_framework")


def _superset_own_standing_framework(namer):
    """The superset must be judged on its own standing objections.

    x objects to a; y undercuts that objection; c undercuts y's undercut. The
    set holding a and y is admissible, because y's undercut brings x's
    objection down. Adding c revives x's objection, so the larger set is not
    admissible and the smaller set keeps its maximality. An audit that reuses
    the smaller set's standing objections to judge the larger one sees an
    admissible superset that does not exist.
    """
    n = _claims(namer, ["a", "y", "c", "x"])
    o1 = namer.take("objection")
    o2 = namer.take("objection")
    o3 = namer.take("objection")
    objections = [
        (o1, n["x"], "claim", n["a"]),
        (o2, n["y"], "objection", o1),
        (o3, n["c"], "objection", o2),
    ]
    sets = [
        (namer.take("set"), [n["a"], n["y"]]),
        (namer.take("set"), [n["a"], n["y"], n["c"]]),
        (namer.take("set"), [n["a"]]),
        (namer.take("set"), [n["y"], n["c"]]),
    ]
    return _fw(namer, n, objections, sets, "_superset_own_standing_framework")


def _parallel_objection_framework(namer):
    """Two distinct objections raised between the same pair of claims.

    Both stand, so the internal count is two rather than one, and one of them
    is separately undercut so the count is sensitive to the standing test.
    """
    n = _claims(namer, ["m", "k", "j"])
    o1 = namer.take("objection")
    o2 = namer.take("objection")
    o3 = namer.take("objection")
    o4 = namer.take("objection")
    objections = [
        (o1, n["m"], "claim", n["k"]),
        (o2, n["m"], "claim", n["k"]),
        (o3, n["j"], "objection", o2),
        (o4, n["k"], "claim", n["j"]),
    ]
    sets = [
        (namer.take("set"), [n["m"], n["k"]]),
        (namer.take("set"), [n["m"], n["k"], n["j"]]),
        (namer.take("set"), [n["m"]]),
    ]
    return _fw(namer, n, objections, sets, "_parallel_objection_framework")


# ---------------------------------------------------------------------------
# Classical Dung archetypes, with no undercuts, so the plain readings of
# conflict-freeness, defence, stability and maximality stay load-bearing.
# ---------------------------------------------------------------------------


def _chain_framework(namer):
    """d objects to c, c to b, b to a. {d} loses maximality to {d,b}."""
    n = _claims(namer, ["a", "b", "c", "d"])
    objections = [
        (namer.take("objection"), n["d"], "claim", n["c"]),
        (namer.take("objection"), n["c"], "claim", n["b"]),
        (namer.take("objection"), n["b"], "claim", n["a"]),
    ]
    sets = [
        (namer.take("set"), [n["a"], n["c"]]),
        (namer.take("set"), [n["a"]]),
        (namer.take("set"), [n["a"], n["b"]]),
        (namer.take("set"), [n["d"]]),
        (namer.take("set"), [n["d"], n["b"]]),
    ]
    return _fw(namer, n, objections, sets, "_chain_framework")


def _self_objection_framework(namer):
    """p objects to itself and to q. No stable set; the empty set is maximal."""
    n = _claims(namer, ["p", "q"])
    objections = [
        (namer.take("objection"), n["p"], "claim", n["p"]),
        (namer.take("objection"), n["p"], "claim", n["q"]),
    ]
    sets = [
        (namer.take("set"), []),
        (namer.take("set"), [n["p"]]),
        (namer.take("set"), [n["q"]]),
        (namer.take("set"), [n["p"], n["q"]]),
    ]
    return _fw(namer, n, objections, sets, "_self_objection_framework")


def _inadmissible_superset_framework(namer):
    """{g} stays maximal: its only strict superset is undefended."""
    n = _claims(namer, ["g", "h", "k"])
    objections = [(namer.take("objection"), n["k"], "claim", n["h"])]
    sets = [
        (namer.take("set"), [n["g"]]),
        (namer.take("set"), [n["g"], n["h"]]),
        (namer.take("set"), [n["h"]]),
    ]
    return _fw(namer, n, objections, sets, "_inadmissible_superset_framework")


def _mutual_objection_framework(namer):
    """An even cycle: two stable sets, and the empty set is not maximal."""
    n = _claims(namer, ["a", "b"])
    objections = [
        (namer.take("objection"), n["a"], "claim", n["b"]),
        (namer.take("objection"), n["b"], "claim", n["a"]),
    ]
    sets = [
        (namer.take("set"), []),
        (namer.take("set"), [n["a"]]),
        (namer.take("set"), [n["b"]]),
        (namer.take("set"), [n["a"], n["b"]]),
    ]
    return _fw(namer, n, objections, sets, "_mutual_objection_framework")


def _defended_by_other_framework(namer):
    """{x,z} is admissible only because z defends x; x cannot defend itself."""
    n = _claims(namer, ["x", "y", "z"])
    objections = [
        (namer.take("objection"), n["y"], "claim", n["x"]),
        (namer.take("objection"), n["z"], "claim", n["y"]),
    ]
    sets = [
        (namer.take("set"), [n["x"]]),
        (namer.take("set"), [n["x"], n["z"]]),
        (namer.take("set"), [n["y"]]),
    ]
    return _fw(namer, n, objections, sets, "_defended_by_other_framework")


def _odd_cycle_framework(namer):
    """a to b to c to a. No stable set; only the empty set is admissible."""
    n = _claims(namer, ["a", "b", "c"])
    objections = [
        (namer.take("objection"), n["a"], "claim", n["b"]),
        (namer.take("objection"), n["b"], "claim", n["c"]),
        (namer.take("objection"), n["c"], "claim", n["a"]),
    ]
    sets = [
        (namer.take("set"), []),
        (namer.take("set"), [n["a"]]),
        (namer.take("set"), [n["b"], n["c"]]),
    ]
    return _fw(namer, n, objections, sets, "_odd_cycle_framework")


def _internal_objection_framework(namer):
    """{s,t} covers every outsider yet holds an internal objection."""
    n = _claims(namer, ["s", "t", "u"])
    objections = [
        (namer.take("objection"), n["s"], "claim", n["t"]),
        (namer.take("objection"), n["s"], "claim", n["u"]),
    ]
    sets = [
        (namer.take("set"), [n["s"], n["t"]]),
        (namer.take("set"), [n["s"]]),
        (namer.take("set"), [n["t"], n["u"]]),
    ]
    return _fw(namer, n, objections, sets, "_internal_objection_framework")


def _duplicate_set_framework(namer):
    """Two candidate sets with identical members receive identical verdicts."""
    n = _claims(namer, ["a", "b"])
    sets = [
        (namer.take("set"), [n["a"]]),
        (namer.take("set"), [n["a"]]),
        (namer.take("set"), [n["a"], n["b"]]),
    ]
    return _fw(namer, n, [], sets, "_duplicate_set_framework")


def _empty_framework(namer):
    """A framework with no claims: its empty set is vacuously everything."""
    return {
        "name": namer.take("forum"),
        "args": [],
        "objections": [],
        "sets": [(namer.take("set"), [])],
        "archetype": "_empty_framework",
    }


DESIGNED = [
    _undercut_rescue_framework,
    _undercut_depth_three_framework,
    _undercut_defence_framework,
    _superset_own_standing_framework,
    _parallel_objection_framework,
    _chain_framework,
    _self_objection_framework,
    _inadmissible_superset_framework,
    _mutual_objection_framework,
    _defended_by_other_framework,
    _odd_cycle_framework,
    _internal_objection_framework,
    _duplicate_set_framework,
    _empty_framework,
]


def _random_framework(namer, rng):
    """A random framework with random claim objections and random undercuts.

    Undercuts are only ever raised against an objection created earlier in the
    list, which keeps the undercut relation acyclic by construction, and the
    generator refuses any undercut that would push a chain past the disclosed
    bound.
    """
    size = rng.randint(4, 6)
    args = [namer.take("claim") for _ in range(size)]
    objections = []
    depth = {}
    for src in args:
        for dst in args:
            if src == dst:
                if rng.random() < 0.10:
                    name = namer.take("objection")
                    objections.append((name, src, "claim", dst))
                    depth[name] = 0
                continue
            if rng.random() < 0.20:
                name = namer.take("objection")
                objections.append((name, src, "claim", dst))
                depth[name] = 0
    targetable = [o[0] for o in objections]
    for _ in range(rng.randint(1, 3)):
        if not targetable:
            break
        victim = rng.choice(targetable)
        if depth[victim] + 1 > MAX_UNDERCUT_CHAIN:
            continue
        name = namer.take("objection")
        objections.append((name, rng.choice(args), "objection", victim))
        depth[name] = depth[victim] + 1
        targetable.append(name)
    sets = []
    for _ in range(rng.randint(2, 3)):
        base_size = rng.randint(0, min(3, size))
        base = sorted(rng.sample(args, base_size))
        sets.append((namer.take("set"), base))
        remaining = [a for a in args if a not in base]
        if remaining and rng.random() < 0.7:
            grown = sorted([*base, rng.choice(remaining)])
            sets.append((namer.take("set"), grown))
    return {
        "name": namer.take("forum"),
        "args": args,
        "objections": objections,
        "sets": sets,
        "archetype": "_random_framework",
    }


def generate_spec(seed, block=0):
    rng = random.Random(seed)
    namer = Namer(rng, block)
    order = list(DESIGNED)
    rng.shuffle(order)
    frameworks = [builder(namer) for builder in order]
    frameworks.extend(_random_framework(namer, rng) for _ in range(rng.randint(2, 3)))
    rng.shuffle(frameworks)
    return frameworks


DDL = [
    "CREATE NODE TABLE Framework(id INT64, name STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE Argument(id INT64, name STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE Attack(id INT64, name STRING, PRIMARY KEY(id))",
    "CREATE NODE TABLE CandidateSet(id INT64, name STRING, PRIMARY KEY(id))",
    "CREATE REL TABLE IN_FRAMEWORK(FROM Argument TO Framework)",
    "CREATE REL TABLE SET_OF(FROM CandidateSet TO Framework)",
    "CREATE REL TABLE MEMBER(FROM Argument TO CandidateSet)",
    "CREATE REL TABLE RAISES(FROM Argument TO Attack)",
    "CREATE REL TABLE STRIKES(FROM Attack TO Argument)",
    "CREATE REL TABLE UNDERCUTS(FROM Attack TO Attack)",
]


def _write(conn, frameworks):
    arg_id = {}
    set_id = {}
    att_id = {}
    for fid, fw in enumerate(frameworks):
        conn.execute(f"CREATE (:Framework {{id: {fid}, name: '{fw['name']}'}})")
    for fw in frameworks:
        for name in fw["args"]:
            arg_id[name] = len(arg_id)
            conn.execute(f"CREATE (:Argument {{id: {arg_id[name]}, name: '{name}'}})")
        for att in fw["objections"]:
            att_id[att[0]] = len(att_id)
            conn.execute(f"CREATE (:Attack {{id: {att_id[att[0]]}, name: '{att[0]}'}})")
        for set_name, _members in fw["sets"]:
            set_id[set_name] = len(set_id)
            conn.execute(
                f"CREATE (:CandidateSet {{id: {set_id[set_name]}, name: '{set_name}'}})"
            )
    for fid, fw in enumerate(frameworks):
        for name in fw["args"]:
            conn.execute(
                "MATCH (a:Argument), (f:Framework) "
                f"WHERE a.id = {arg_id[name]} AND f.id = {fid} "
                "CREATE (a)-[:IN_FRAMEWORK]->(f)"
            )
        for att_name, src, kind, target in fw["objections"]:
            conn.execute(
                "MATCH (a:Argument), (o:Attack) "
                f"WHERE a.id = {arg_id[src]} AND o.id = {att_id[att_name]} "
                "CREATE (a)-[:RAISES]->(o)"
            )
            if kind == "claim":
                conn.execute(
                    "MATCH (o:Attack), (b:Argument) "
                    f"WHERE o.id = {att_id[att_name]} AND b.id = {arg_id[target]} "
                    "CREATE (o)-[:STRIKES]->(b)"
                )
            else:
                conn.execute(
                    "MATCH (o:Attack), (p:Attack) "
                    f"WHERE o.id = {att_id[att_name]} AND p.id = {att_id[target]} "
                    "CREATE (o)-[:UNDERCUTS]->(p)"
                )
        for set_name, members in fw["sets"]:
            conn.execute(
                "MATCH (s:CandidateSet), (f:Framework) "
                f"WHERE s.id = {set_id[set_name]} AND f.id = {fid} "
                "CREATE (s)-[:SET_OF]->(f)"
            )
            for name in members:
                conn.execute(
                    "MATCH (a:Argument), (s:CandidateSet) "
                    f"WHERE a.id = {arg_id[name]} AND s.id = {set_id[set_name]} "
                    "CREATE (a)-[:MEMBER]->(s)"
                )


VISIBLE_SEED = 20260728
VISIBLE_BLOCK = 0
HIDDEN_SEED = 88131977
HIDDEN_BLOCK = 1


def irrelevant_component_spec(seed):
    """The visible instance plus one disjoint framework.

    Frameworks are independent by construction, so adding a whole new framework
    is a metamorphic transformation with a proven effect: every certificate of
    every pre-existing candidate set is unchanged, and exactly the new
    framework's own candidate sets are added.
    """
    frameworks = generate_spec(seed, VISIBLE_BLOCK)
    frameworks.append(
        {
            "name": "forum_disjoint_extra",
            "args": ["claim_extra_x", "claim_extra_y"],
            "objections": [
                ("objection_extra_one", "claim_extra_x", "claim", "claim_extra_y")
            ],
            "sets": [
                ("set_extra_alpha", ["claim_extra_x"]),
                ("set_extra_beta", ["claim_extra_y"]),
            ],
            "archetype": "_disjoint_extra",
        }
    )
    return frameworks


def build_from_spec(db_path, frameworks):
    staging = tempfile.mkdtemp(prefix="argbuild-")
    raw_path = os.path.join(staging, "raw.kuzu")
    export_path = os.path.join(staging, "export")
    db = kuzu.Database(raw_path, buffer_pool_size=512 * 1024 * 1024)
    conn = kuzu.Connection(db)
    for statement in DDL:
        conn.execute(statement)
    _write(conn, frameworks)
    conn.execute(f"EXPORT DATABASE '{export_path}'")
    del conn
    del db

    if os.path.exists(db_path):
        shutil.rmtree(db_path)
    parent = os.path.dirname(os.path.abspath(db_path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    db2 = kuzu.Database(db_path, buffer_pool_size=512 * 1024 * 1024)
    conn2 = kuzu.Connection(db2)
    conn2.execute(f"IMPORT DATABASE '{export_path}'")
    del conn2
    del db2
    shutil.rmtree(staging, ignore_errors=True)
    return frameworks


def build(db_path, seed, block=0):
    return build_from_spec(db_path, generate_spec(seed, block))


def main():
    if len(sys.argv) not in (3, 4):
        sys.stderr.write("usage: build_graph.py <output-db-path> <seed> [block]\n")
        return 2
    block = int(sys.argv[3]) if len(sys.argv) == 4 else 0
    frameworks = build(sys.argv[1], int(sys.argv[2]), block)
    total_sets = sum(len(f["sets"]) for f in frameworks)
    total_obj = sum(len(f["objections"]) for f in frameworks)
    sys.stderr.write(
        f"built {len(frameworks)} frameworks, {total_obj} objections, "
        f"{total_sets} candidate sets\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
