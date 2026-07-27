"""Derive each wrong-reading baseline from the reference by one substitution.

Every baseline in this directory exists to show that a single specific
misreading of the artifact moves a specific family of traces. Deriving them
mechanically keeps each one different from the reference in exactly one place,
so a divergence test cannot pass for a reason other than the one it names.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(sys.argv[0]))
BASE = os.path.join(HERE, "original.c")

REVERSE_GROUP = """    if ((g_casc & 1u) != 0u) {
        int32_t prev = -1;
        while (node >= 0) {
            int32_t nxt = g_next[node];
            g_next[node] = prev;
            prev = node;
            node = nxt;
        }
        node = prev;
    }
"""

REHOME_LOOP = """    while (node >= 0) {
        int32_t nxt = g_next[node];
        place(node);
        node = nxt;
    }"""

PREPEND = """    g_next[node] = g_head[lvl][idx];
    g_head[lvl][idx] = node;"""

TICK_HEAD = "    uint32_t index = g_now & 255u;\n    int32_t node;\n"

APPEND = """    {
        int32_t *cur = &g_head[lvl][idx];
        while (*cur >= 0) {
            cur = &g_next[*cur];
        }
        *cur = node;
    }
    g_next[node] = -1;"""

# name -> (note, from, to)
VARIANTS = {
    "wrong_unsigned": (
        "The due test compares the deadline and the clock as unsigned.",
        "    if ((int32_t)delta <= 0) {",
        "    if (expires <= g_now) {",
    ),
    "wrong_boundary": (
        "The exact boundary delta is admitted into the nearer tier.",
        "    if (delta < 256u) {",
        "    if (delta <= 256u) {",
    ),
    "wrong_boundary2": (
        None,
        "    } else if (delta < 65536u) {",
        "    } else if (delta <= 65536u) {",
    ),
    "wrong_boundary3": (
        None,
        "    } else if (delta < 16777216u) {",
        "    } else if (delta <= 16777216u) {",
    ),
    "wrong_append": (
        "Every pending group is kept in arrival order.",
        PREPEND,
        APPEND,
    ),
    "wrong_cascade": (
        "A due group is re-homed in list order instead of reversed.",
        REHOME_LOOP,
        """    {
        int32_t prev = -1;
        while (node >= 0) {
            int32_t nxt = g_next[node];
            g_next[node] = prev;
            prev = node;
            node = nxt;
        }
        node = prev;
    }
"""
        + REHOME_LOOP,
    ),
    "wrong_rearm": (
        "A cancelled id is armable again straight away.",
        "            if (g_lookup[ident] != 0 || g_held[ident] || g_waiting[ident]) {",
        "            if (g_lookup[ident] != 0 || g_waiting[ident]) {",
    ),
    "wrong_settled": (
        "An id is free again the moment it comes due, not once it is named.",
        "            if (g_lookup[ident] != 0 || g_held[ident] || g_waiting[ident]) {",
        "            if (g_lookup[ident] != 0 || g_held[ident]) {",
    ),
    "wrong_uncapped": (
        "Every id that came due is named by the advance that retired it.",
        "            take = ready < (uint32_t)REPORT ? ready : (uint32_t)REPORT;",
        "            take = ready;",
    ),
    "wrong_freshfirst": (
        "A fresh retirement is named ahead of one that was already owed.",
        """            for (t = 0; t < fired; t++) {
                g_queue[g_qtail++] = g_fired[t];
            }""",
        """            {
                uint32_t owed = g_qtail - g_qhead;
                for (t = 0; t < owed; t++) {
                    g_queue[g_qtail + fired - 1u - t] = g_queue[g_qtail - 1u - t];
                }
                for (t = 0; t < fired; t++) {
                    g_queue[g_qhead + t] = g_fired[t];
                }
                g_qtail += fired;
            }""",
    ),
    "wrong_settledcount": (
        "The count carries only the timers still armed.",
        "            outstanding = g_live + (g_qtail - g_qhead);",
        "            outstanding = g_live;",
    ),
    "wrong_foldearly": (
        "The digest folds an id when it comes due rather than when it is named.",
        "        g_fired[count++] = ident;\n        g_lookup[ident] = 0;",
        (
            "        g_fired[count++] = ident;\n"
            "        g_digest = rotl32(g_digest ^ ident, 7) + 0x7feb352du;\n"
            "        g_lookup[ident] = 0;"
        ),
    ),
    "wrong_foldearly2": (
        None,
        (
            "                g_waiting[ident] = 0u;\n"
            "                g_digest = rotl32(g_digest ^ ident, 7) + 0x7feb352du;\n"
        ),
        "                g_waiting[ident] = 0u;\n",
    ),
    "wrong_drain": (
        "Every group is drained head first, whatever has happened before it.",
        REVERSE_GROUP,
        "",
    ),
    "wrong_prefetch": (
        "The drain direction is read before the re-homing passes, not after.",
        TICK_HEAD,
        TICK_HEAD + "    uint32_t seen = g_casc;\n",
    ),
    "wrong_shallow": (
        "Only the outermost re-homing pass is counted.",
        "    g_casc++;",
        "    if (lvl == 1) {\n        g_casc++;\n    }",
    ),
}

# wrong_boundary carries all three tier comparisons; wrong_prefetch needs the
# guard rewritten to read its own snapshot.
CHAINED = {
    "wrong_boundary": ["wrong_boundary2", "wrong_boundary3"],
    "wrong_foldearly": ["wrong_foldearly2"],
}
EXTRA = {
    "wrong_prefetch": [
        ("    if ((g_casc & 1u) != 0u) {", "    if ((seen & 1u) != 0u) {")
    ]
}


def build(name):
    note, old, new = VARIANTS[name]
    with open(BASE, encoding="ascii") as handle:
        text = handle.read()
    steps = [(old, new)]
    for follow in CHAINED.get(name, []):
        steps.append(VARIANTS[follow][1:])
    steps.extend(EXTRA.get(name, []))
    for old_step, new_step in steps:
        if text.count(old_step) != 1:
            sys.exit(f"{name}: anchor is not unique: {old_step[:60]!r}")
        text = text.replace(old_step, new_step)
    header = f"/* {note} */\n"
    with open(os.path.join(HERE, name + ".c"), "w", encoding="ascii") as handle:
        handle.write(header + text)
    return name


def main():
    written = [build(name) for name, spec in VARIANTS.items() if spec[0] is not None]
    sys.stdout.write("variants=" + " ".join(sorted(written)) + "\n")


if __name__ == "__main__":
    main()
