"""Frozen ground truth for the verifier.

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

COLUMNS = (
    "candidate_set",
    "live_internal_attacks",
    "undefended_members",
    "unattacked_outsiders",
    "admissible",
    "stable",
    "maximal_admissible",
)

# The certificate every candidate set of the visible graph carries.
EXPECTED_ROWS = [
    ("set_bulyn", "0", "0", "1", "True", "False", "True"),
    ("set_bumor", "0", "0", "0", "True", "True", "True"),
    ("set_detiv", "1", "1", "2", "False", "False", "False"),
    ("set_dezad", "0", "0", "3", "True", "False", "True"),
    ("set_falyn", "0", "0", "2", "True", "False", "True"),
    ("set_fanix", "0", "0", "0", "True", "True", "True"),
    ("set_fasen", "0", "0", "1", "True", "False", "True"),
    ("set_fativ", "0", "0", "4", "True", "False", "False"),
    ("set_favok", "0", "0", "0", "True", "True", "True"),
    ("set_fayth", "0", "1", "5", "False", "False", "False"),
    ("set_fazad", "0", "0", "1", "True", "False", "True"),
    ("set_kador", "1", "1", "0", "False", "False", "False"),
    ("set_kafex", "0", "0", "0", "True", "True", "True"),
    ("set_kagil", "1", "1", "0", "False", "False", "False"),
    ("set_kanix", "1", "1", "0", "False", "False", "False"),
    ("set_kativ", "0", "1", "1", "False", "False", "False"),
    ("set_kavok", "0", "1", "1", "False", "False", "False"),
    ("set_loban", "1", "1", "1", "False", "False", "False"),
    ("set_lojav", "1", "0", "0", "False", "False", "False"),
    ("set_lolyn", "2", "1", "0", "False", "False", "False"),
    ("set_lorus", "0", "0", "6", "True", "False", "False"),
    ("set_losen", "1", "1", "2", "False", "False", "False"),
    ("set_lovok", "2", "1", "1", "False", "False", "False"),
    ("set_loyth", "0", "0", "2", "True", "False", "True"),
    ("set_mikor", "0", "0", "2", "True", "False", "True"),
    ("set_milyn", "0", "0", "2", "True", "False", "False"),
    ("set_mipol", "0", "0", "2", "True", "False", "True"),
    ("set_misen", "2", "2", "2", "False", "False", "False"),
    ("set_neban", "0", "2", "1", "False", "False", "False"),
    ("set_nelyn", "0", "0", "3", "True", "False", "True"),
    ("set_nenix", "0", "0", "2", "True", "False", "True"),
    ("set_neyth", "0", "1", "3", "False", "False", "False"),
    ("set_rodor", "0", "0", "2", "True", "False", "True"),
    ("set_rohum", "0", "1", "2", "False", "False", "False"),
    ("set_rolyn", "0", "0", "1", "True", "False", "False"),
    ("set_romor", "1", "1", "0", "False", "False", "False"),
    ("set_ropol", "0", "1", "1", "False", "False", "False"),
    ("set_rotiv", "2", "0", "0", "False", "False", "False"),
    ("set_sudor", "2", "1", "0", "False", "False", "False"),
    ("set_sufex", "0", "1", "1", "False", "False", "False"),
    ("set_sugil", "0", "1", "1", "False", "False", "False"),
    ("set_sujav", "0", "0", "0", "True", "True", "True"),
    ("set_sukor", "0", "1", "1", "False", "False", "False"),
    ("set_sulyn", "2", "0", "0", "False", "False", "False"),
    ("set_supol", "0", "0", "0", "True", "True", "True"),
    ("set_susen", "0", "0", "6", "True", "False", "False"),
    ("set_sutiv", "0", "1", "3", "False", "False", "False"),
    ("set_suzad", "1", "2", "2", "False", "False", "False"),
    ("set_tafex", "0", "0", "2", "True", "False", "True"),
    ("set_tajav", "1", "2", "2", "False", "False", "False"),
    ("set_tayth", "0", "0", "0", "True", "True", "True"),
    ("set_viban", "0", "0", "0", "True", "True", "True"),
    ("set_vigil", "2", "1", "0", "False", "False", "False"),
    ("set_vilyn", "0", "0", "2", "True", "False", "False"),
    ("set_vipol", "0", "0", "2", "True", "False", "False"),
    ("set_vitiv", "0", "1", "3", "False", "False", "False"),
    ("set_vivok", "1", "1", "0", "False", "False", "False"),
    ("set_viyth", "0", "0", "2", "True", "False", "False"),
    ("set_zeban", "0", "1", "2", "False", "False", "False"),
    ("set_zefex", "0", "0", "0", "True", "True", "True"),
    ("set_zehum", "0", "1", "3", "False", "False", "False"),
    ("set_zemor", "0", "1", "3", "False", "False", "False"),
    ("set_zevok", "0", "0", "1", "True", "False", "False"),
]

# The hidden-seed answer, as an uninvertible digest over its sorted rows.
HIDDEN_DIGEST = "e46aaf6216111e402639609f7e63dd7e07e465f6e16d3ec4a04de2a61045f4db"
HIDDEN_ROW_COUNT = 54

# Adding one disjoint framework leaves every existing certificate alone and
# contributes exactly these rows.
METAMORPHIC_EXTRA_ROWS = [
    ("set_extra_alpha", "0", "0", "0", "True", "True", "True"),
    ("set_extra_beta", "0", "1", "1", "False", "False", "False"),
]

# Certificates carried by candidate sets of the designed archetypes.
DESIGNED_ROWS = [
    ("set_bulyn", "0", "0", "1", "True", "False", "True"),
    ("set_bumor", "0", "0", "0", "True", "True", "True"),
    ("set_falyn", "0", "0", "2", "True", "False", "True"),
    ("set_fanix", "0", "0", "0", "True", "True", "True"),
    ("set_fasen", "0", "0", "1", "True", "False", "True"),
    ("set_fazad", "0", "0", "1", "True", "False", "True"),
    ("set_kafex", "0", "0", "0", "True", "True", "True"),
    ("set_kagil", "1", "1", "0", "False", "False", "False"),
    ("set_kanix", "1", "1", "0", "False", "False", "False"),
    ("set_kativ", "0", "1", "1", "False", "False", "False"),
    ("set_kavok", "0", "1", "1", "False", "False", "False"),
    ("set_loban", "1", "1", "1", "False", "False", "False"),
    ("set_lojav", "1", "0", "0", "False", "False", "False"),
    ("set_lolyn", "2", "1", "0", "False", "False", "False"),
    ("set_losen", "1", "1", "2", "False", "False", "False"),
    ("set_loyth", "0", "0", "2", "True", "False", "True"),
    ("set_mikor", "0", "0", "2", "True", "False", "True"),
    ("set_milyn", "0", "0", "2", "True", "False", "False"),
    ("set_mipol", "0", "0", "2", "True", "False", "True"),
    ("set_neban", "0", "2", "1", "False", "False", "False"),
    ("set_nelyn", "0", "0", "3", "True", "False", "True"),
    ("set_nenix", "0", "0", "2", "True", "False", "True"),
    ("set_neyth", "0", "1", "3", "False", "False", "False"),
    ("set_rodor", "0", "0", "2", "True", "False", "True"),
    ("set_rohum", "0", "1", "2", "False", "False", "False"),
    ("set_rolyn", "0", "0", "1", "True", "False", "False"),
    ("set_romor", "1", "1", "0", "False", "False", "False"),
    ("set_ropol", "0", "1", "1", "False", "False", "False"),
    ("set_rotiv", "2", "0", "0", "False", "False", "False"),
    ("set_sudor", "2", "1", "0", "False", "False", "False"),
    ("set_sufex", "0", "1", "1", "False", "False", "False"),
    ("set_sugil", "0", "1", "1", "False", "False", "False"),
    ("set_sujav", "0", "0", "0", "True", "True", "True"),
    ("set_sukor", "0", "1", "1", "False", "False", "False"),
    ("set_sulyn", "2", "0", "0", "False", "False", "False"),
    ("set_supol", "0", "0", "0", "True", "True", "True"),
    ("set_sutiv", "0", "1", "3", "False", "False", "False"),
    ("set_suzad", "1", "2", "2", "False", "False", "False"),
    ("set_tayth", "0", "0", "0", "True", "True", "True"),
    ("set_viban", "0", "0", "0", "True", "True", "True"),
    ("set_vilyn", "0", "0", "2", "True", "False", "False"),
    ("set_vipol", "0", "0", "2", "True", "False", "False"),
    ("set_viyth", "0", "0", "2", "True", "False", "False"),
    ("set_zeban", "0", "1", "2", "False", "False", "False"),
    ("set_zefex", "0", "0", "0", "True", "True", "True"),
    ("set_zemor", "0", "1", "3", "False", "False", "False"),
    ("set_zevok", "0", "0", "1", "True", "False", "False"),
]

# Certificates that some shortcut reading of the rules emits and that the full
# rule set forbids. Each was produced by a committed wrong baseline and checked
# absent from the truth.
FORBIDDEN_ROWS = [
    ("set_bulyn", "0", "1", "1", "False", "False", "False"),
    ("set_detiv", "1", "0", "1", "False", "False", "False"),
    ("set_dezad", "0", "0", "4", "True", "False", "True"),
    ("set_falyn", "0", "0", "2", "True", "False", "False"),
    ("set_fanix", "0", "1", "0", "False", "True", "False"),
    ("set_fasen", "0", "0", "1", "True", "False", "False"),
    ("set_favok", "0", "0", "0", "True", "True", "False"),
    ("set_fazad", "0", "0", "1", "True", "False", "False"),
    ("set_fazad", "1", "1", "1", "False", "False", "False"),
    ("set_kador", "1", "1", "0", "False", "True", "False"),
    ("set_kafex", "1", "1", "0", "False", "False", "False"),
    ("set_kagil", "0", "0", "0", "True", "True", "True"),
    ("set_kagil", "1", "1", "0", "False", "True", "False"),
    ("set_kanix", "1", "1", "0", "False", "True", "False"),
    ("set_kanix", "1", "2", "0", "False", "False", "False"),
    ("set_loban", "0", "0", "1", "True", "False", "False"),
    ("set_lojav", "1", "0", "0", "False", "True", "False"),
    ("set_lolyn", "2", "1", "0", "False", "True", "False"),
    ("set_lolyn", "2", "2", "0", "False", "False", "False"),
    ("set_lolyn", "3", "1", "0", "False", "False", "False"),
    ("set_lovok", "1", "1", "1", "False", "False", "False"),
    ("set_lovok", "2", "1", "0", "False", "False", "False"),
    ("set_loyth", "0", "0", "3", "True", "False", "True"),
    ("set_mikor", "0", "0", "2", "True", "False", "False"),
    ("set_milyn", "0", "1", "2", "False", "False", "False"),
    ("set_mipol", "0", "0", "2", "True", "False", "False"),
    ("set_mipol", "0", "1", "2", "False", "False", "False"),
    ("set_misen", "2", "0", "1", "False", "False", "False"),
    ("set_nelyn", "0", "0", "3", "True", "False", "False"),
    ("set_nenix", "0", "0", "2", "True", "False", "False"),
    ("set_rodor", "0", "0", "2", "True", "False", "False"),
    ("set_romor", "1", "1", "0", "False", "True", "False"),
    ("set_ropol", "0", "0", "1", "True", "False", "True"),
    ("set_rotiv", "2", "0", "0", "False", "True", "False"),
    ("set_rotiv", "2", "1", "0", "False", "False", "False"),
    ("set_sudor", "1", "1", "0", "False", "False", "False"),
    ("set_sudor", "2", "1", "0", "False", "True", "False"),
    ("set_sujav", "0", "0", "0", "True", "True", "False"),
    ("set_sukor", "0", "2", "1", "False", "False", "False"),
    ("set_sulyn", "2", "0", "0", "False", "True", "False"),
    ("set_tafex", "0", "0", "2", "True", "False", "False"),
    ("set_tayth", "0", "0", "0", "True", "True", "False"),
    ("set_viban", "0", "1", "0", "False", "True", "False"),
    ("set_vigil", "1", "1", "0", "False", "False", "False"),
    ("set_vigil", "2", "1", "0", "False", "True", "False"),
    ("set_vigil", "3", "2", "0", "False", "False", "False"),
    ("set_vilyn", "0", "0", "2", "True", "False", "True"),
    ("set_vipol", "0", "0", "2", "True", "False", "True"),
    ("set_vipol", "0", "1", "2", "False", "False", "False"),
    ("set_vivok", "1", "1", "0", "False", "True", "False"),
    ("set_zefex", "0", "0", "0", "True", "True", "False"),
    ("set_zemor", "0", "0", "3", "True", "False", "False"),
]

# The columns each named wrong baseline actually moves on the visible graph.
NAIVE_COLUMNS = {
    "naive_all_objections_stand": [
        "admissible",
        "live_internal_attacks",
        "maximal_admissible",
        "stable",
        "unattacked_outsiders",
        "undefended_members",
    ],
    "naive_count_objection_pairs": ["live_internal_attacks"],
    "naive_self_defence": ["admissible", "maximal_admissible", "undefended_members"],
    "naive_shared_standing": ["maximal_admissible"],
    "naive_single_undercut": [
        "admissible",
        "live_internal_attacks",
        "maximal_admissible",
        "stable",
        "undefended_members",
    ],
    "naive_stable_without_conflict_free": ["stable"],
    "naive_superset_only_maximality": ["maximal_admissible"],
    "naive_undercut_depth_two": [
        "admissible",
        "live_internal_attacks",
        "maximal_admissible",
        "stable",
        "undefended_members",
    ],
    "naive_undercut_ignores_raiser": [
        "admissible",
        "live_internal_attacks",
        "maximal_admissible",
        "unattacked_outsiders",
        "undefended_members",
    ],
}

# Digests of what each wrong baseline returns, on each graph.
NAIVE_VISIBLE_DIGEST = {
    "naive_all_objections_stand": "e42274a3e87b63c77f07aba31f488d488735ece1a7c0ebf02392519ae64c9252",
    "naive_count_objection_pairs": "6b3ccb06d203b96906f810357056bc62958327ae6077ac4df6cf8c599a175b2c",
    "naive_self_defence": "c48164d7fcd6a48a65aeaa1bd8f18f38e76491b05cd347ce6363d668736d31ca",
    "naive_shared_standing": "30174af5a1f0f976b8b133cda55e1c5a729c6ff77c0c1adda1719c37d58ecffc",
    "naive_single_undercut": "70cc19578ed02768f09ec5f0ede6fb9501cd04334aeb14d504ae55392fdf8c10",
    "naive_stable_without_conflict_free": "e4da6c95bd4a517cfb2ab8567ef7d0a907eef2342c379d347cee4e1c77301a8c",
    "naive_superset_only_maximality": "6ec499dfdc5357a54d93db7e6b4fd6b7427673db2573ba306df67c5f9bc47e4f",
    "naive_undercut_depth_two": "8870a4e4783d758ddaed391965f4b1ae512685671bef4aabad8a4fafb3836419",
    "naive_undercut_ignores_raiser": "db798194d824a5dd71c74639b78257543c97e46f0f89f53b204cda5fa0dc5357",
}
NAIVE_HIDDEN_DIGEST = {
    "naive_all_objections_stand": "e303f210433499aafe55d54ff91072786cfd939cb6d2b2c80e5abbbce07286ef",
    "naive_count_objection_pairs": "14b78f9a9681d1f50b1d4a92b6a367da35c126dbd397286ccabba427417fb514",
    "naive_self_defence": "2c374d5bcace50c57041d046ffdb3acbd8067993f0e93c727e23e53652721f21",
    "naive_shared_standing": "4d3f1bded69d2809d1e466befd3e43265b3f588277420726127ed88a26a619dc",
    "naive_single_undercut": "c62e9543aee9ef5d76685d89789af0a01fea469f746df8ac65416142488eb161",
    "naive_stable_without_conflict_free": "49d0423818ffe856938d5429c90ab9e80a4f6eb746a0c4fc280f984f250c2536",
    "naive_superset_only_maximality": "adf712dac2f982837d8b0e201f3b22aa69df23da43b303d0e4c8b1e85a7bd56e",
    "naive_undercut_depth_two": "45491853f5cf85ec24159fbce6e0d08dc1914be7ac59c364d22c889e97e57f4e",
    "naive_undercut_ignores_raiser": "6a73cecae9839ea4b3f7d18508dbbeeadf9c8dce632d1f6b58141659565ac657",
}

# The designed situation that proves each wrong baseline load-bearing, as
# (candidate set, the row the baseline emits, the row the rules require).
BASELINE_WITNESS_ROWS = {
    "naive_all_objections_stand": (
        "set_milyn",
        ("set_milyn", "0", "1", "2", "False", "False", "False"),
        ("set_milyn", "0", "0", "2", "True", "False", "False"),
    ),
    "naive_count_objection_pairs": (
        "set_sudor",
        ("set_sudor", "1", "1", "0", "False", "False", "False"),
        ("set_sudor", "2", "1", "0", "False", "False", "False"),
    ),
    "naive_self_defence": (
        "set_fanix",
        ("set_fanix", "0", "1", "0", "False", "True", "False"),
        ("set_fanix", "0", "0", "0", "True", "True", "True"),
    ),
    "naive_shared_standing": (
        "set_mipol",
        ("set_mipol", "0", "0", "2", "True", "False", "False"),
        ("set_mipol", "0", "0", "2", "True", "False", "True"),
    ),
    "naive_single_undercut": (
        "set_kagil",
        ("set_kagil", "0", "0", "0", "True", "True", "True"),
        ("set_kagil", "1", "1", "0", "False", "False", "False"),
    ),
    "naive_stable_without_conflict_free": (
        "set_romor",
        ("set_romor", "1", "1", "0", "False", "True", "False"),
        ("set_romor", "1", "1", "0", "False", "False", "False"),
    ),
    "naive_superset_only_maximality": (
        "set_falyn",
        ("set_falyn", "0", "0", "2", "True", "False", "False"),
        ("set_falyn", "0", "0", "2", "True", "False", "True"),
    ),
    "naive_undercut_depth_two": (
        "set_kafex",
        ("set_kafex", "1", "1", "0", "False", "False", "False"),
        ("set_kafex", "0", "0", "0", "True", "True", "True"),
    ),
    "naive_undercut_ignores_raiser": (
        "set_fazad",
        ("set_fazad", "1", "1", "1", "False", "False", "False"),
        ("set_fazad", "0", "0", "1", "True", "False", "True"),
    ),
}

# The digest of the visible answer, for comparing against the baselines above.
VISIBLE_DIGEST = "f39d0ad8a8f03118e360ec372ca807414b01e0f20ae389a2a384ff088be8fc30"

RESCUE_ALL_RAISERS_SET = "set_kagil"
RESCUE_NO_TOP_RAISER_SET = "set_fazad"
RESCUE_NO_CUTTER_SET = "set_losen"
DEPTH_THREE_SET = "set_kafex"
UNDERCUT_DEFENCE_SET = "set_milyn"
UNDERCUT_UNDEFENDED_SET = "set_zemor"
OWN_STANDING_MAXIMAL_SET = "set_mipol"
OWN_STANDING_RIVAL_SET = "set_ropol"
PARALLEL_OBJECTION_SET = "set_sudor"
INTERNAL_OBJECTION_SET = "set_romor"
DEFENDED_BY_OTHER_SET = "set_fanix"
INADMISSIBLE_SUPERSET_BASE = "set_falyn"
INADMISSIBLE_SUPERSET_SET = "set_kavok"
NON_MAXIMAL_SET = "set_vilyn"
ADMISSIBLE_SUPERSET_SET = "set_viban"
EMPTY_FRAMEWORK_SET = "set_bumor"
SELF_OBJECTION_SET = "set_lojav"
