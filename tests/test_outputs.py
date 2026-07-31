import os
import re

import pytest
from conftest import (
    ANSWER_PATH,
    APP,
    HIDDEN_GRAPH,
    METAMORPHIC_GRAPH,
    REQUIRED_COLUMNS,
    RUNNER,
    TESTS_DIR,
    VISIBLE_GRAPH,
    fixture_text,
    normalize_rows,
    rows_digest,
    run_query,
)
from expected import (
    ADMISSIBLE_SUPERSET_SET,
    BASELINE_WITNESS_ROWS,
    DEFENDED_BY_OTHER_SET,
    DEPTH_THREE_SET,
    DESIGNED_ROWS,
    EMPTY_FRAMEWORK_SET,
    EXPECTED_ROWS,
    FORBIDDEN_ROWS,
    HIDDEN_DIGEST,
    HIDDEN_ROW_COUNT,
    INADMISSIBLE_SUPERSET_BASE,
    INADMISSIBLE_SUPERSET_SET,
    INTERNAL_OBJECTION_SET,
    METAMORPHIC_EXTRA_ROWS,
    NAIVE_COLUMNS,
    NAIVE_HIDDEN_DIGEST,
    NAIVE_VISIBLE_DIGEST,
    NON_MAXIMAL_SET,
    OWN_STANDING_MAXIMAL_SET,
    OWN_STANDING_RIVAL_SET,
    PARALLEL_OBJECTION_SET,
    RESCUE_ALL_RAISERS_SET,
    RESCUE_NO_CUTTER_SET,
    RESCUE_NO_TOP_RAISER_SET,
    SELF_OBJECTION_SET,
    UNDERCUT_DEFENCE_SET,
    UNDERCUT_UNDEFENDED_SET,
    VISIBLE_DIGEST,
)

TRUTH = set(EXPECTED_ROWS)
BY_NAME = {row[0]: row for row in EXPECTED_ROWS}
BOOLEAN_VALUES = {"True", "False"}
COUNT_COLUMNS = (1, 2, 3)
VERDICT_COLUMNS = (4, 5, 6)

NAIVE_NAMES = sorted(NAIVE_COLUMNS)

# Vocabulary of the shipped graph. A real audit query has to name these; a
# hardcoded row list does not.
GRAPH_VOCABULARY = (
    "CandidateSet",
    "Argument",
    "Attack",
    "RAISES",
    "STRIKES",
    "UNDERCUTS",
    "MEMBER",
    "IN_FRAMEWORK",
    "SET_OF",
)


def _answer_text():
    with open(ANSWER_PATH, encoding="utf-8") as fh:
        return fh.read()


def _vocabulary_hits(text):
    return {term for term in GRAPH_VOCABULARY if term in text}


def _forbidden_paths(text):
    return set(re.findall(r"/(?:tests|solution)\b", text))


def _fixture_rows(name, graph):
    """Execute a committed fixture query and normalize its rows."""
    columns, rows, err = run_query(fixture_text(f"{name}.query"), graph)
    assert rows is not None, f"{name} failed to execute: {err}"
    return normalize_rows(columns, rows)


# ---- Zero-credit preconditions: artifact presence and transport contract. ----


def test_answer_file_exists():
    """The agent wrote a query to /app/answer.cypher."""
    assert os.path.exists(ANSWER_PATH)


def test_answer_file_not_empty():
    """The submitted answer file is not blank or whitespace only."""
    assert _answer_text().strip() != ""


def test_answer_executes_on_visible_graph(answer_visible_raw):
    """The submitted query runs without error against the committed visible graph."""
    _columns, rows, err = answer_visible_raw
    assert rows is not None, f"query execution failed: {err}"


def test_answer_returns_exact_column_set(answer_visible_raw):
    """The submitted query returns exactly the seven requested output columns."""
    columns, rows, err = answer_visible_raw
    assert rows is not None, err
    assert set(columns) == set(REQUIRED_COLUMNS)


def test_answer_returns_at_least_one_row(answer_visible_normalized):
    """The submitted query produces a non-empty result-set on the visible graph."""
    assert len(answer_visible_normalized) > 0


def test_answer_verdicts_are_boolean_text(answer_visible_normalized):
    """Every verdict column renders as the boolean text True or False."""
    for row in answer_visible_normalized:
        for index in VERDICT_COLUMNS:
            assert row[index] in BOOLEAN_VALUES


def test_answer_counts_are_non_negative_integers(answer_visible_normalized):
    """Every count column renders as a non-negative integer."""
    for row in answer_visible_normalized:
        for index in COUNT_COLUMNS:
            assert re.fullmatch(r"\d+", row[index]), row


def test_answer_reports_each_candidate_set_once(answer_visible_normalized):
    """No candidate set is reported under more than one certificate row."""
    names = [row[0] for row in answer_visible_normalized]
    assert len(names) == len(set(names))


# ---- Answer-file structural gate: the answer must be a query over this graph. ----


def test_answer_names_the_graph_vocabulary():
    """The submitted answer really queries this graph rather than restating rows."""
    hits = _vocabulary_hits(_answer_text())
    assert len(hits) >= 3, f"answer names too little of the graph schema: {hits}"


def test_answer_does_not_reference_the_verifier_or_solution():
    """The submitted answer does not read from the test or solution directories."""
    assert _forbidden_paths(_answer_text()) == set()


def test_structural_gate_rejects_a_hardcoded_row_list():
    """The structural gate is load-bearing: a literal row list fails it."""
    hits = _vocabulary_hits(fixture_text("literal_list.query"))
    assert len(hits) < 3


def test_verifier_runs_its_own_runner_not_the_agent_writable_one():
    """Grading never executes code the agent can rewrite."""
    assert os.path.isfile(RUNNER)
    assert os.path.abspath(RUNNER).startswith(os.path.abspath(TESTS_DIR) + os.sep)
    assert not os.path.abspath(RUNNER).startswith(os.path.abspath(APP) + os.sep)


# ---- Expected-value anchors on designed situations. ----


@pytest.mark.parametrize("expected_row", DESIGNED_ROWS)
def test_designed_anchor_certificate_present(answer_visible_normalized, expected_row):
    """A designed candidate set carries exactly its expected certificate."""
    assert tuple(expected_row) in answer_visible_normalized


@pytest.mark.parametrize(
    "expected_row", [r for r in EXPECTED_ROWS if r not in set(DESIGNED_ROWS)]
)
def test_random_framework_set_certificate_matches(
    answer_visible_normalized, expected_row
):
    """A candidate set from a randomly generated framework carries its certificate."""
    assert tuple(expected_row) in answer_visible_normalized


@pytest.mark.parametrize("wrong_row", FORBIDDEN_ROWS)
def test_forbidden_certificate_absent(answer_visible_normalized, wrong_row):
    """A certificate that a shortcut reading emits is absent from the answer."""
    assert tuple(wrong_row) not in answer_visible_normalized


# ---- Whole-result agreement on the visible graph. ----


def test_visible_result_set_matches_expected_exactly(answer_visible_normalized):
    """The submitted query's result-set equals the frozen visible answer."""
    assert answer_visible_normalized == TRUTH


def test_visible_result_has_no_extra_rows(answer_visible_normalized):
    """The submitted query returns no row absent from the frozen answer."""
    assert answer_visible_normalized - TRUTH == set()


def test_visible_result_is_missing_no_rows(answer_visible_normalized):
    """The submitted query omits no row present in the frozen answer."""
    assert TRUTH - answer_visible_normalized == set()


def test_visible_result_row_count_matches(answer_visible_normalized):
    """The submitted query returns one row per candidate set."""
    assert len(answer_visible_normalized) == len(EXPECTED_ROWS)


# ---- Named wrong baselines: each must separate through executed behavior. ----


@pytest.mark.parametrize("name", NAIVE_NAMES)
def test_named_wrong_baseline_diverges_on_visible_graph(name):
    """A named wrong baseline disagrees with the truth on the visible graph."""
    assert NAIVE_VISIBLE_DIGEST[name] != VISIBLE_DIGEST


@pytest.mark.parametrize("name", NAIVE_NAMES)
def test_named_wrong_baseline_diverges_on_hidden_graph(name):
    """A named wrong baseline disagrees with the truth on the hidden graph."""
    assert NAIVE_HIDDEN_DIGEST[name] != HIDDEN_DIGEST


@pytest.mark.parametrize("name", NAIVE_NAMES)
def test_named_wrong_baseline_moves_a_recorded_column(name):
    """Every named wrong baseline really moves at least one graded column."""
    moved = NAIVE_COLUMNS[name]
    assert moved
    assert set(moved) <= set(REQUIRED_COLUMNS[1:])


@pytest.mark.parametrize("name", NAIVE_NAMES)
def test_named_wrong_baseline_fails_its_designed_witness(name):
    """Each wrong baseline is wrong on the situation it was designed against."""
    set_name, naive_row, true_row = BASELINE_WITNESS_ROWS[name]
    assert tuple(true_row) == BY_NAME[set_name]
    assert tuple(naive_row) != tuple(true_row)


def test_frozen_visible_digest_matches_the_frozen_visible_rows():
    """The recorded visible digest really is the digest of the recorded answer."""
    assert rows_digest(TRUTH) == VISIBLE_DIGEST


def test_all_objections_standing_misreads_an_undercut_defence():
    """Ignoring undercuts denies a set defended only by an undercut."""
    _s, naive_row, _t = BASELINE_WITNESS_ROWS["naive_all_objections_stand"]
    assert BY_NAME[UNDERCUT_DEFENCE_SET][4] == "True"
    assert naive_row[4] == "False"


def test_single_undercut_reading_misses_the_rescued_objection():
    """A one-step standing test calls the rescued objection fallen."""
    _s, naive_row, _t = BASELINE_WITNESS_ROWS["naive_single_undercut"]
    assert BY_NAME[RESCUE_ALL_RAISERS_SET][1] == "1"
    assert naive_row[1] == "0"


def test_depth_two_reading_misses_the_three_deep_chain():
    """A two-step standing test is wrong where the chain runs three deep."""
    _s, naive_row, true_row = BASELINE_WITNESS_ROWS["naive_undercut_depth_two"]
    assert tuple(true_row) == BY_NAME[DEPTH_THREE_SET]
    assert tuple(naive_row) != tuple(true_row)


def test_raiser_blind_reading_misreads_a_set_without_the_raiser():
    """Counting undercuts whose raiser is absent changes a set's own verdicts."""
    _s, naive_row, true_row = BASELINE_WITNESS_ROWS["naive_undercut_ignores_raiser"]
    assert tuple(true_row) == BY_NAME[RESCUE_NO_TOP_RAISER_SET]
    assert tuple(naive_row) != tuple(true_row)


def test_shared_standing_reading_strips_a_deserved_maximality():
    """Judging a rival on the subset's standing invents an admissible superset."""
    _s, naive_row, _t = BASELINE_WITNESS_ROWS["naive_shared_standing"]
    assert BY_NAME[OWN_STANDING_MAXIMAL_SET][6] == "True"
    assert naive_row[6] == "False"


def test_self_defence_reading_denies_defence_by_another_member():
    """Requiring a member to answer its own objector wrongly denies admissibility."""
    _s, naive_row, _t = BASELINE_WITNESS_ROWS["naive_self_defence"]
    assert BY_NAME[DEFENDED_BY_OTHER_SET][4] == "True"
    assert naive_row[4] == "False"


def test_stable_without_conflict_free_accepts_an_internal_objection():
    """Skipping conflict-freeness calls a set with an internal objection stable."""
    _s, naive_row, _t = BASELINE_WITNESS_ROWS["naive_stable_without_conflict_free"]
    assert BY_NAME[INTERNAL_OBJECTION_SET][5] == "False"
    assert naive_row[5] == "True"


def test_superset_only_maximality_denies_a_deserved_maximality():
    """Ignoring whether a superset is admissible wrongly denies maximality."""
    _s, naive_row, _t = BASELINE_WITNESS_ROWS["naive_superset_only_maximality"]
    assert BY_NAME[INADMISSIBLE_SUPERSET_BASE][6] == "True"
    assert naive_row[6] == "False"


def test_pair_counting_reading_undercounts_parallel_objections():
    """Counting objecting pairs loses the second objection between one pair."""
    _s, naive_row, _t = BASELINE_WITNESS_ROWS["naive_count_objection_pairs"]
    assert BY_NAME[PARALLEL_OBJECTION_SET][1] == "2"
    assert naive_row[1] == "1"


# ---- Anti-hardcoding, enforced behaviorally by the hidden-seed graph. ----


def test_literal_list_matches_truth_on_the_graph_it_was_copied_from():
    """A hardcoded row list reproduces the answer on the visible graph."""
    assert _fixture_rows("literal_list", VISIBLE_GRAPH) == TRUTH


def test_literal_list_fails_on_the_hidden_graph():
    """The hardcoded row list does not reproduce the hidden graph's answer."""
    assert rows_digest(_fixture_rows("literal_list", HIDDEN_GRAPH)) != HIDDEN_DIGEST


# ---- Generalization to the hidden-seed graph. ----


def test_answer_executes_on_hidden_graph(answer_hidden_raw):
    """The submitted query also runs without error against the hidden-seed graph."""
    _columns, rows, err = answer_hidden_raw
    assert rows is not None, f"query execution failed on the hidden graph: {err}"


def test_hidden_result_returns_exact_column_set(answer_hidden_raw):
    """The submitted query returns exactly the seven columns on the hidden graph."""
    columns, rows, err = answer_hidden_raw
    assert rows is not None, err
    assert set(columns) == set(REQUIRED_COLUMNS)


def test_hidden_result_digest_matches(answer_hidden_normalized):
    """The submitted query generalizes: it reproduces the sealed hidden answer."""
    assert rows_digest(answer_hidden_normalized) == HIDDEN_DIGEST


def test_hidden_result_row_count_matches(answer_hidden_normalized):
    """The submitted query returns one row per candidate set of the hidden graph."""
    assert len(answer_hidden_normalized) == HIDDEN_ROW_COUNT


def test_hidden_result_verdicts_are_boolean_text(answer_hidden_normalized):
    """Every hidden-graph verdict column renders as True or False."""
    for row in answer_hidden_normalized:
        for index in VERDICT_COLUMNS:
            assert row[index] in BOOLEAN_VALUES


def test_hidden_answer_is_not_the_visible_answer(answer_hidden_normalized):
    """The hidden-seed graph is a genuinely different instance."""
    assert answer_hidden_normalized != TRUTH


def test_hidden_graph_is_identity_disjoint_from_the_visible_graph():
    """No candidate set name occurs in both instances, so names cannot transfer."""
    probe = "MATCH (s:CandidateSet) RETURN s.name AS n"
    _c, visible, _e = run_query(probe, VISIBLE_GRAPH)
    _c2, hidden, _e2 = run_query(probe, HIDDEN_GRAPH)
    assert visible and hidden
    assert {r[0] for r in visible} & {r[0] for r in hidden} == set()


def test_hidden_graph_file_is_distinct_from_visible_graph_file():
    """The hidden-seed graph is stored as a separate database directory."""
    assert os.path.abspath(HIDDEN_GRAPH) != os.path.abspath(VISIBLE_GRAPH)
    assert os.path.isdir(HIDDEN_GRAPH)
    assert os.path.isdir(VISIBLE_GRAPH)


# ---- Metamorphic relation: adding a disjoint framework changes nothing else. ----


def test_metamorphic_preserves_every_existing_certificate(
    answer_metamorphic_normalized,
):
    """Adding a disjoint framework leaves every pre-existing certificate untouched."""
    assert answer_metamorphic_normalized >= TRUTH


def test_metamorphic_adds_exactly_the_new_sets(answer_metamorphic_normalized):
    """Adding a disjoint framework adds exactly that framework's own candidate sets."""
    added = answer_metamorphic_normalized - TRUTH
    assert added == {tuple(row) for row in METAMORPHIC_EXTRA_ROWS}


def test_metamorphic_row_count_grows_by_the_added_sets(answer_metamorphic_normalized):
    """The transformed graph reports exactly the added number of extra rows."""
    assert len(answer_metamorphic_normalized) == len(EXPECTED_ROWS) + len(
        METAMORPHIC_EXTRA_ROWS
    )


def test_metamorphic_graph_file_is_distinct():
    """The metamorphic instance is a separate committed database."""
    assert os.path.isdir(METAMORPHIC_GRAPH)
    assert os.path.abspath(METAMORPHIC_GRAPH) != os.path.abspath(VISIBLE_GRAPH)


# ---- Structural sanity: the instance really exhibits what the rules turn on. ----


def _scalar(probe, graph=VISIBLE_GRAPH):
    columns, rows, err = run_query(probe, graph)
    assert rows is not None, err
    (row,) = rows
    return int(row[columns.index("n")])


def test_visible_graph_contains_a_self_objecting_claim():
    """A claim objecting to itself really exists, so that rule is load-bearing."""
    probe = (
        "MATCH (a:Argument)-[:RAISES]->(o:Attack)-[:STRIKES]->(a) RETURN count(o) AS n"
    )
    assert _scalar(probe) > 0


def test_visible_graph_contains_an_empty_candidate_set():
    """A candidate set with no members really exists."""
    probe = (
        "MATCH (s:CandidateSet) "
        "WHERE NOT EXISTS { MATCH (:Argument)-[:MEMBER]->(s) } "
        "RETURN count(s) AS n"
    )
    assert _scalar(probe) > 0


def test_visible_graph_contains_undercuts():
    """Objections against other objections really exist."""
    probe = "MATCH (:Attack)-[:UNDERCUTS]->(:Attack) RETURN count(*) AS n"
    assert _scalar(probe) > 0


def test_visible_graph_contains_a_three_deep_undercut_chain():
    """The undercut relation really reaches the bound the rules disclose."""
    probe = (
        "MATCH (:Attack)-[:UNDERCUTS]->(:Attack)-[:UNDERCUTS]->(:Attack)"
        "-[:UNDERCUTS]->(:Attack) RETURN count(*) AS n"
    )
    assert _scalar(probe) > 0


def test_visible_graph_has_no_four_deep_undercut_chain():
    """No chain runs past the disclosed bound, so unrolling to it is exact."""
    probe = (
        "MATCH (:Attack)-[:UNDERCUTS]->(:Attack)-[:UNDERCUTS]->(:Attack)"
        "-[:UNDERCUTS]->(:Attack)-[:UNDERCUTS]->(:Attack) RETURN count(*) AS n"
    )
    assert _scalar(probe) == 0


def test_hidden_graph_has_no_four_deep_undercut_chain():
    """The hidden instance respects the same disclosed bound."""
    probe = (
        "MATCH (:Attack)-[:UNDERCUTS]->(:Attack)-[:UNDERCUTS]->(:Attack)"
        "-[:UNDERCUTS]->(:Attack)-[:UNDERCUTS]->(:Attack) RETURN count(*) AS n"
    )
    assert _scalar(probe, HIDDEN_GRAPH) == 0


def test_visible_graph_contains_parallel_objections():
    """Two distinct objections between one pair of claims really exist."""
    probe = (
        "MATCH (a:Argument)-[:RAISES]->(o1:Attack)-[:STRIKES]->(b:Argument), "
        "(a)-[:RAISES]->(o2:Attack)-[:STRIKES]->(b) "
        "WHERE o1.id < o2.id RETURN count(*) AS n"
    )
    assert _scalar(probe) > 0


def test_every_objection_has_exactly_one_raiser_and_one_target():
    """Each objection is raised once and aimed at exactly one claim or objection."""
    probe = (
        "MATCH (o:Attack) "
        "WHERE NOT EXISTS { MATCH (:Argument)-[:RAISES]->(o) } "
        "   OR (NOT EXISTS { MATCH (o)-[:STRIKES]->(:Argument) } "
        "       AND NOT EXISTS { MATCH (o)-[:UNDERCUTS]->(:Attack) }) "
        "RETURN count(o) AS n"
    )
    assert _scalar(probe) == 0


# ---- Cross-row structure the frozen answer must itself satisfy. ----


def test_a_stable_certificate_is_always_admissible():
    """The theorem that a stable set is admissible holds across the frozen answer."""
    for row in EXPECTED_ROWS:
        if row[5] == "True":
            assert row[4] == "True", row


def test_admissibility_agrees_with_its_two_counts():
    """The admissible column really is the conjunction of its two zero tests."""
    for row in EXPECTED_ROWS:
        assert row[4] == str(row[1] == "0" and row[2] == "0"), row


def test_stability_agrees_with_its_two_counts():
    """The stable column really is the conjunction of its two zero tests."""
    for row in EXPECTED_ROWS:
        assert row[5] == str(row[1] == "0" and row[3] == "0"), row


def test_maximality_implies_admissibility():
    """No candidate set is maximal admissible without being admissible."""
    for row in EXPECTED_ROWS:
        if row[6] == "True":
            assert row[4] == "True", row


def test_designed_witnesses_carry_their_intended_verdicts():
    """Each designed situation really produces the verdict it was built for."""
    assert BY_NAME[RESCUE_ALL_RAISERS_SET][1] == "1"
    assert BY_NAME[RESCUE_NO_TOP_RAISER_SET][1] == "0"
    assert BY_NAME[RESCUE_NO_CUTTER_SET][1] == "1"
    assert BY_NAME[UNDERCUT_DEFENCE_SET][4] == "True"
    assert BY_NAME[UNDERCUT_UNDEFENDED_SET][4] == "False"
    assert BY_NAME[OWN_STANDING_MAXIMAL_SET][6] == "True"
    assert BY_NAME[OWN_STANDING_RIVAL_SET][4] == "False"
    assert BY_NAME[SELF_OBJECTION_SET][4] == "False"
    assert BY_NAME[EMPTY_FRAMEWORK_SET][5] == "True"


def test_a_set_loses_maximality_to_an_admissible_superset():
    """An admissible set beaten by an admissible strict superset really exists."""
    assert BY_NAME[NON_MAXIMAL_SET][4] == "True"
    assert BY_NAME[NON_MAXIMAL_SET][6] == "False"
    assert BY_NAME[ADMISSIBLE_SUPERSET_SET][4] == "True"


def test_a_set_keeps_maximality_against_an_inadmissible_superset():
    """A maximal set whose only strict superset is inadmissible really exists."""
    assert BY_NAME[INADMISSIBLE_SUPERSET_BASE][6] == "True"
    assert BY_NAME[INADMISSIBLE_SUPERSET_SET][4] == "False"
