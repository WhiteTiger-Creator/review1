"""Authoring-time sealer: build the graphs, generate the queries, prove the design.

Run from the task root inside the task image. It rebuilds all three committed
databases, regenerates the reference query and every wrong baseline, and then
refuses to write anything unless the whole design holds:

  * the reference Cypher agrees with the independent Python recomputation on
    the visible, hidden and metamorphic graphs;
  * every named wrong baseline diverges from the truth on both the visible and
    the hidden graph, and each one moves at least one verdict column, not only
    a count;
  * the shipped graphs really carry the structures the rules turn on, and the
    longest undercut chain equals the bound the reference query unrolls to;
  * no claim, objection, framework or candidate set name occurs in both the
    visible and the hidden instance.

It then writes tests/expected.py, holding the visible answer in plain text, the
hidden answer as a SHA-256 digest only, and the witness constants the verifier
asserts against.

Usage: python3 solution/seal.py
"""

import hashlib
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import kuzu
from build_graph import (
    HIDDEN_BLOCK,
    HIDDEN_SEED,
    MAX_UNDERCUT_CHAIN,
    VISIBLE_BLOCK,
    VISIBLE_SEED,
    build_from_spec,
    generate_spec,
    irrelevant_component_spec,
)
from gen_queries import NAIVE_FIXTURES, build_query
from reference_impl import (
    compute_reference,
    read_facts,
    undercut_chain_depth,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOLUTION = os.path.join(ROOT, "solution")
# Each wrong baseline is the reference query with one token changed, so they
# live here rather than in the agent-readable test directory. Only their
# executed results are frozen into tests/expected.py.
BASELINES = os.path.join(SOLUTION, "baselines")
FIXTURES = os.path.join(ROOT, "tests", "fixtures")

# The designed situation each wrong baseline is proven load-bearing against.
BASELINE_WITNESS = {
    "naive_all_objections_stand": "UNDERCUT_DEFENCE_SET",
    "naive_single_undercut": "RESCUE_ALL_RAISERS_SET",
    "naive_undercut_depth_two": "DEPTH_THREE_SET",
    "naive_undercut_ignores_raiser": "RESCUE_NO_TOP_RAISER_SET",
    "naive_shared_standing": "OWN_STANDING_MAXIMAL_SET",
    "naive_self_defence": "DEFENDED_BY_OTHER_SET",
    "naive_stable_without_conflict_free": "INTERNAL_OBJECTION_SET",
    "naive_superset_only_maximality": "INADMISSIBLE_SUPERSET_BASE",
    "naive_count_objection_pairs": "PARALLEL_OBJECTION_SET",
}
VISIBLE = os.path.join(ROOT, "environment", "graph", "argumentation.kuzu")
HIDDEN = os.path.join(FIXTURES, "hidden_graph", "argumentation.kuzu")
METAMORPHIC = os.path.join(FIXTURES, "metamorphic_graph", "argumentation.kuzu")

COLUMNS = (
    "candidate_set",
    "live_internal_attacks",
    "undefended_members",
    "unattacked_outsiders",
    "admissible",
    "stable",
    "maximal_admissible",
)
VERDICT_COLUMNS = {4, 5, 6}

# Counting objection pairs instead of objections is a real graded error, but it
# provably cannot move a verdict: the pair count is zero exactly when the
# objection count is, so every boolean derived from a zero test is unchanged.
# It is the one baseline exempt from the moves-a-verdict requirement.
COUNT_ONLY_BASELINES = {"naive_count_objection_pairs"}


def digest(rows):
    joined = "\n".join("\t".join(row) for row in sorted(rows))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def run_query(query, graph_path):
    db = kuzu.Database(graph_path, read_only=True, buffer_pool_size=512 * 1024 * 1024)
    conn = kuzu.Connection(db)
    result = conn.execute(query)
    names = result.get_column_names()
    index = [names.index(c) for c in COLUMNS]
    rows = set()
    while result.has_next():
        raw = result.get_next()
        rows.add(tuple(str(raw[i]) for i in index))
    del conn
    del db
    return rows


def diverging_columns(got, want):
    by_name_got = {r[0]: r for r in got}
    columns = set()
    rows = set()
    for row in want:
        other = by_name_got.get(row[0])
        if other is None:
            rows.add(row[0])
            continue
        for i in range(1, len(COLUMNS)):
            if other[i] != row[i]:
                columns.add(i)
                rows.add(row[0])
    return columns, rows


def fail(message):
    sys.stderr.write(f"SEAL FAILED: {message}\n")
    sys.exit(1)


def _set_names_by_archetype(frameworks):
    out = {}
    for fw in frameworks:
        out.setdefault(fw["archetype"], []).append([s[0] for s in fw["sets"]])
    return out


def main():
    print("building graphs")
    visible_spec = generate_spec(VISIBLE_SEED, VISIBLE_BLOCK)
    hidden_spec = generate_spec(HIDDEN_SEED, HIDDEN_BLOCK)
    meta_spec = irrelevant_component_spec(VISIBLE_SEED)
    build_from_spec(VISIBLE, visible_spec)
    build_from_spec(HIDDEN, hidden_spec)
    build_from_spec(METAMORPHIC, meta_spec)

    print("generating queries")
    subprocess.run(
        [sys.executable, os.path.join(SOLUTION, "gen_queries.py"), SOLUTION, BASELINES],
        check=True,
    )
    reference = build_query()

    print("recomputing ground truth")
    visible_truth = compute_reference(VISIBLE)
    hidden_truth = compute_reference(HIDDEN)
    meta_truth = compute_reference(METAMORPHIC)

    for label, path, truth in (
        ("visible", VISIBLE, visible_truth),
        ("hidden", HIDDEN, hidden_truth),
        ("metamorphic", METAMORPHIC, meta_truth),
    ):
        got = run_query(reference, path)
        if got != truth:
            fail(f"reference Cypher disagrees with the Python oracle on {label}")
        print(f"  reference == oracle on {label} ({len(got)} rows)")

    print("checking wrong baselines")
    naive_report = {}
    truth_by_name_early = {r[0]: r for r in visible_truth}
    for name in sorted(NAIVE_FIXTURES):
        with open(os.path.join(BASELINES, f"{name}.query"), encoding="utf-8") as fh:
            query = fh.read()
        got_v = run_query(query, VISIBLE)
        got_h = run_query(query, HIDDEN)
        if got_v == visible_truth:
            fail(f"{name} does not diverge on the visible graph")
        if got_h == hidden_truth:
            fail(f"{name} does not diverge on the hidden graph")
        cols, rows = diverging_columns(got_v, visible_truth)
        if name in COUNT_ONLY_BASELINES:
            if cols & VERDICT_COLUMNS:
                fail(f"{name} was expected to move counts only, but moved a verdict")
        elif not cols & VERDICT_COLUMNS:
            fail(f"{name} moves no verdict column on the visible graph")
        naive_report[name] = {
            "columns": sorted(COLUMNS[i] for i in cols),
            "rows": sorted(rows),
            "wrong_rows": sorted(got_v - visible_truth),
            "visible_digest": digest(got_v),
            "hidden_digest": digest(got_h),
            "by_name": {r[0]: r for r in got_v},
        }
        print(f"  {name}: columns={naive_report[name]['columns']} rows={len(rows)}")

    if set(BASELINE_WITNESS) != set(NAIVE_FIXTURES):
        fail("every wrong baseline needs a designed witness situation")

    print("checking structure")
    facts = read_facts(VISIBLE)
    depth = undercut_chain_depth(facts)
    if depth != MAX_UNDERCUT_CHAIN:
        fail(
            f"visible longest undercut chain is {depth}, expected {MAX_UNDERCUT_CHAIN}"
        )
    hidden_depth = undercut_chain_depth(read_facts(HIDDEN))
    if hidden_depth != MAX_UNDERCUT_CHAIN:
        fail(f"hidden longest undercut chain is {hidden_depth}")
    print(f"  longest undercut chain = {depth} on both graphs")

    def names_of(spec):
        out = set()
        for fw in spec:
            out.add(fw["name"])
            out.update(fw["args"])
            out.update(o[0] for o in fw["objections"])
            out.update(s[0] for s in fw["sets"])
        return out

    overlap = names_of(visible_spec) & names_of(hidden_spec)
    if overlap:
        fail(
            f"visible and hidden share {len(overlap)} names, e.g. {sorted(overlap)[:3]}"
        )
    print("  visible and hidden instances are identity-disjoint")

    by_arch = _set_names_by_archetype(visible_spec)
    truth_by_name = {r[0]: r for r in visible_truth}

    witnesses = {
        "RESCUE_ALL_RAISERS_SET": by_arch["_undercut_rescue_framework"][0][0],
        "RESCUE_NO_TOP_RAISER_SET": by_arch["_undercut_rescue_framework"][0][1],
        "RESCUE_NO_CUTTER_SET": by_arch["_undercut_rescue_framework"][0][2],
        "DEPTH_THREE_SET": by_arch["_undercut_depth_three_framework"][0][0],
        "UNDERCUT_DEFENCE_SET": by_arch["_undercut_defence_framework"][0][1],
        "UNDERCUT_UNDEFENDED_SET": by_arch["_undercut_defence_framework"][0][0],
        "OWN_STANDING_MAXIMAL_SET": by_arch["_superset_own_standing_framework"][0][0],
        "OWN_STANDING_RIVAL_SET": by_arch["_superset_own_standing_framework"][0][1],
        "PARALLEL_OBJECTION_SET": by_arch["_parallel_objection_framework"][0][0],
        "INTERNAL_OBJECTION_SET": by_arch["_internal_objection_framework"][0][0],
        "DEFENDED_BY_OTHER_SET": by_arch["_defended_by_other_framework"][0][1],
        "INADMISSIBLE_SUPERSET_BASE": by_arch["_inadmissible_superset_framework"][0][0],
        "INADMISSIBLE_SUPERSET_SET": by_arch["_inadmissible_superset_framework"][0][1],
        "NON_MAXIMAL_SET": by_arch["_chain_framework"][0][3],
        "ADMISSIBLE_SUPERSET_SET": by_arch["_chain_framework"][0][4],
        "EMPTY_FRAMEWORK_SET": by_arch["_empty_framework"][0][0],
        "SELF_OBJECTION_SET": by_arch["_self_objection_framework"][0][1],
    }
    print("witness certificates")
    for key, name in witnesses.items():
        print(f"  {key:32s} {name:18s} {truth_by_name[name][1:]}")

    designed = sorted(
        truth_by_name[name]
        for archetype, names in by_arch.items()
        if archetype != "_random_framework"
        for group in names
        for name in group
    )
    if len(designed) >= len(visible_truth):
        fail("no candidate set is left over from the randomly generated frameworks")
    forbidden = sorted(
        {row for report in naive_report.values() for row in report["wrong_rows"]}
        - visible_truth
    )

    meta_extra = sorted(meta_truth - visible_truth)
    if {r[0] for r in meta_extra} != {"set_extra_alpha", "set_extra_beta"}:
        fail("metamorphic graph does not add exactly the disjoint framework's sets")
    if not visible_truth <= meta_truth:
        fail("metamorphic graph disturbed a pre-existing certificate")

    print("witness rows per wrong baseline")
    baseline_witness = {}
    for name, witness_key in sorted(BASELINE_WITNESS.items()):
        set_name = witnesses[witness_key]
        naive_row = naive_report[name]["by_name"][set_name]
        true_row = truth_by_name_early[set_name]
        if naive_row == true_row:
            fail(f"{name} agrees with the truth on its own witness {set_name}")
        baseline_witness[name] = (set_name, naive_row, true_row)
        print(f"  {name}: {set_name} {naive_row[1:]} != {true_row[1:]}")

    print("writing tests/expected.py")
    _write_expected(
        visible_truth,
        hidden_truth,
        meta_extra,
        designed,
        forbidden,
        witnesses,
        naive_report,
        baseline_witness,
    )

    print("writing literal_list fixture")
    _write_literal_list(visible_truth)
    with open(os.path.join(FIXTURES, "literal_list.query"), encoding="utf-8") as fh:
        literal = fh.read()
    if run_query(literal, VISIBLE) != visible_truth:
        fail("literal_list does not reproduce the visible answer it was copied from")
    if run_query(literal, HIDDEN) == hidden_truth:
        fail("literal_list survives the hidden graph, so it is not anti-hardcoding")
    print("  literal_list matches visible and fails hidden")

    print("SEAL OK")
    return 0


def _fmt_rows(rows):
    return "".join(f"    {row!r},\n" for row in rows)


def _write_expected(
    visible,
    hidden,
    meta_extra,
    designed,
    forbidden,
    witnesses,
    naive_report,
    baseline_witness,
):
    naive_columns = {
        name: report["columns"] for name, report in sorted(naive_report.items())
    }
    naive_visible = {
        name: report["visible_digest"] for name, report in sorted(naive_report.items())
    }
    naive_hidden = {
        name: report["hidden_digest"] for name, report in sorted(naive_report.items())
    }
    body = f'''"""Frozen ground truth for the verifier.

Written by solution/seal.py at authoring time. The verifier grades against
these values and never recomputes the answer, so no runnable solver ships in
the test directory.

The visible answer is held in plain text: the agent has both the visible graph
and the complete rules, so it is not secret, and keeping it readable makes a
failure report legible. The hidden answer is held only as a SHA-256 digest over
its sorted rows, so it cannot be copied out of the verifier; only a query that
genuinely derives it can reproduce the digest.

The named wrong baselines are each the reference query with one rule bent, so
the queries themselves stay under solution/baselines/ and only their executed
results are recorded here. solution/seal.py re-runs all of them against both
graphs and refuses to write this file unless every one still diverges.
"""

COLUMNS = {COLUMNS!r}

# The certificate every candidate set of the visible graph carries.
EXPECTED_ROWS = [
{_fmt_rows(sorted(visible))}]

# The hidden-seed answer, as an uninvertible digest over its sorted rows.
HIDDEN_DIGEST = {digest(hidden)!r}
HIDDEN_ROW_COUNT = {len(hidden)}

# Adding one disjoint framework leaves every existing certificate alone and
# contributes exactly these rows.
METAMORPHIC_EXTRA_ROWS = [
{_fmt_rows(meta_extra)}]

# Certificates carried by candidate sets of the designed archetypes.
DESIGNED_ROWS = [
{_fmt_rows(designed)}]

# Certificates that some shortcut reading of the rules emits and that the full
# rule set forbids. Each was produced by a committed wrong baseline and checked
# absent from the truth.
FORBIDDEN_ROWS = [
{_fmt_rows(forbidden)}]

# The columns each named wrong baseline actually moves on the visible graph.
NAIVE_COLUMNS = {naive_columns!r}

# Digests of what each wrong baseline returns, on each graph.
NAIVE_VISIBLE_DIGEST = {naive_visible!r}
NAIVE_HIDDEN_DIGEST = {naive_hidden!r}

# The designed situation that proves each wrong baseline load-bearing, as
# (candidate set, the row the baseline emits, the row the rules require).
BASELINE_WITNESS_ROWS = {baseline_witness!r}

# The digest of the visible answer, for comparing against the baselines above.
VISIBLE_DIGEST = {digest(visible)!r}

'''
    for key, name in witnesses.items():
        body += f"{key} = {name!r}\n"
    with open(
        os.path.join(ROOT, "tests", "expected.py"), "w", encoding="utf-8", newline="\n"
    ) as fh:
        fh.write(body)


def _write_literal_list(visible):
    """A hardcoded row list: right on the graph it was copied from, wrong elsewhere."""
    # Kuzu list literals must be homogeneous, so every field is carried as text;
    # the verifier compares rendered text, so this still reproduces the answer.
    tuples = ",\n  ".join(
        "[" + ", ".join(f"'{field}'" for field in r) + "]" for r in sorted(visible)
    )
    query = (
        "UNWIND [\n  " + tuples + "\n] AS row\n"
        "RETURN row[1] AS candidate_set,\n"
        "       row[2] AS live_internal_attacks,\n"
        "       row[3] AS undefended_members,\n"
        "       row[4] AS unattacked_outsiders,\n"
        "       row[5] AS admissible,\n"
        "       row[6] AS stable,\n"
        "       row[7] AS maximal_admissible\n"
    )
    with open(
        os.path.join(FIXTURES, "literal_list.query"),
        "w",
        encoding="utf-8",
        newline="\n",
    ) as fh:
        fh.write(query)


if __name__ == "__main__":
    sys.exit(main())
