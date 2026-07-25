"""Independent POSIX ERE reference matcher.

Two-phase algorithm, derived and empirically cross-checked against glibc
regexec(REG_EXTENDED) and Go's regexp.CompilePOSIX across thousands of
generated (pattern, subject) pairs:

Phase 1 (overall leftmost-longest span): for candidate start positions in
increasing order, compute the *set* of all end positions the whole ERE can
reach from that start (an NFA-style reachable-set enumeration, memoized).
The first start with a nonempty reachable set is the leftmost match; its
maximum reachable end is the longest match at that start.

Phase 2 (subexpression capture reconstruction): given the fixed (start, end)
span, perform a constrained backtracking parse that must consume exactly
that span, preferring earlier-listed alternatives and maximal (greedy)
repetition counts, backtracking only as needed to hit the exact target end.
This DFS order reproduces the observed POSIX subexpression disambiguation:
earlier alternatives win when they still permit exact-span completion, and
repeated groups report the span of their last matched iteration.

This module is deliberately independent of the agent-facing Go engine: it
uses a totally different algorithmic strategy (an NFA reachable-set search
plus a continuation-passing backtracking reconstruction) rather than a
direct recursive-descent matcher, so it does not share a bug class with a
typical from-scratch backtracking implementation.
"""

from ere_ast import (
    Alt,
    AnchorEnd,
    AnchorStart,
    AnyChar,
    Bracket,
    Concat,
    Group,
    Lit,
    ParseError,
    Parser,
    Repeat,
)


class NoMatch(Exception):
    pass


def compile_ere(pattern):
    node, ngroups = Parser(pattern).parse()
    return node, ngroups


def _reachable(node, i, s, memo):
    """Return the set of end positions reachable by `node` starting at i."""
    key = (id(node), i)
    if key in memo:
        return memo[key]
    memo[key] = (
        frozenset()
    )  # break cycles defensively (shouldn't hit with well-formed AST)
    result = _reachable_uncached(node, i, s, memo)
    memo[key] = result
    return result


def _reachable_uncached(node, i, s, memo):
    n = len(s)
    if isinstance(node, Lit):
        if i < n and s[i] == node.ch:
            return frozenset((i + 1,))
        return frozenset()
    if isinstance(node, AnyChar):
        if i < n:
            return frozenset((i + 1,))
        return frozenset()
    if isinstance(node, Bracket):
        if i < n and node.matches(s[i]):
            return frozenset((i + 1,))
        return frozenset()
    if isinstance(node, AnchorStart):
        return frozenset((i,)) if i == 0 else frozenset()
    if isinstance(node, AnchorEnd):
        return frozenset((i,)) if i == n else frozenset()
    if isinstance(node, Group):
        return _reachable(node.child, i, s, memo)
    if isinstance(node, Alt):
        out = set()
        for b in node.branches:
            out |= _reachable(b, i, s, memo)
        return frozenset(out)
    if isinstance(node, Concat):
        frontier = {i}
        for part in node.parts:
            nxt = set()
            for j in frontier:
                nxt |= _reachable(part, j, s, memo)
            frontier = nxt
            if not frontier:
                break
        return frozenset(frontier)
    if isinstance(node, Repeat):
        lo, hi = node.lo, node.hi
        # Reachable positions after exactly k repetitions of the child,
        # for k = 0, 1, 2, ... Every k in [lo, hi] (or all k >= lo when hi
        # is unbounded) contributes its reachable set to the result. Once
        # the frontier stops changing we can stop advancing k -- but only
        # once k has already reached lo, since a child that can only match
        # the empty string still needs its (unchanged) frontier counted at
        # k == lo (this matters for constructs like `(b{0,0}){2}`, where
        # the frontier never moves but two repetitions are still required).
        cap = hi if hi is not None else n + 1
        all_ends = set()
        if lo == 0:
            all_ends.add(i)
        frontier = frozenset((i,))
        k = 0
        while k < cap:
            nxt = set()
            for j in frontier:
                nxt |= _reachable(node.child, j, s, memo)
            nxt = frozenset(nxt)
            k += 1
            if not nxt:
                break
            if k >= lo:
                all_ends |= nxt
            if nxt == frontier and k >= lo:
                # fixpoint reached with the minimum already satisfied:
                # further repetitions add nothing new
                break
            frontier = nxt
        return frozenset(all_ends)
    raise TypeError(f"unknown node type {type(node)}")


def find_overall_match(node, s):
    """Return (start, end) of the leftmost-longest match, or None."""
    memo = {}
    for start in range(len(s) + 1):
        ends = _reachable(node, start, s, memo)
        if ends:
            return start, max(ends)
    return None


def reconstruct_groups(node, ngroups, s, start, end):
    """Constrained backtracking parse of s[start:end] against node, exactly
    spanning [start, end). Returns a dict {group_idx: (a, b) or None}."""
    groups = dict.fromkeys(range(1, ngroups + 1))

    def m(nd, i, cont):
        if isinstance(nd, Lit):
            if i < end and s[i] == nd.ch:
                return cont(i + 1)
            return False
        if isinstance(nd, AnyChar):
            if i < end:
                return cont(i + 1)
            return False
        if isinstance(nd, Bracket):
            if i < end and nd.matches(s[i]):
                return cont(i + 1)
            return False
        if isinstance(nd, AnchorStart):
            return cont(i) if i == 0 else False
        if isinstance(nd, AnchorEnd):
            return cont(i) if i == len(s) else False
        if isinstance(nd, Group):
            saved = groups[nd.idx]

            def wrapped(j):
                groups[nd.idx] = (i, j)
                if cont(j):
                    return True
                groups[nd.idx] = saved
                return False

            ok = m(nd.child, i, wrapped)
            if not ok:
                groups[nd.idx] = saved
            return ok
        if isinstance(nd, Alt):
            return any(m(b, i, cont) for b in nd.branches)
        if isinstance(nd, Concat):

            def build(idx):
                if idx == len(nd.parts):
                    return cont

                def k(j, idx=idx):
                    return m(nd.parts[idx], j, build(idx + 1))

                return k

            return build(0)(i)
        if isinstance(nd, Repeat):
            if nd.hi is not None:
                return match_bounded_repeat(nd.child, i, nd.lo, nd.hi, cont)
            return match_unbounded_repeat(nd, i, 0, cont)
        raise TypeError(type(nd))

    def match_bounded_repeat(child, i, lo, hi, cont):
        """{m,n} (hi finite): unrolled as `lo` mandatory copies followed by
        `hi - lo` discretely-optional nested copies. Each optional copy is
        tried greedily (taken even if it only matches the empty string,
        since it is a discrete concatenation element, not a loop with an
        infinite-empty-iteration hazard) and falls back to being skipped.
        Empirically matches glibc regexec and Go regexp.CompilePOSIX for
        every bounded-interval case probed."""

        def mandatory(i, remaining, cont):
            if remaining == 0:
                return optional(i, hi - lo, cont)
            return m(child, i, lambda j: mandatory(j, remaining - 1, cont))

        def optional(i, remaining, cont):
            if remaining == 0:
                return cont(i)

            def take(j):
                return optional(j, remaining - 1, cont)

            if m(child, i, take):
                return True
            return cont(i)

        return mandatory(i, lo, cont)

    def match_unbounded_repeat(nd, i, count, cont):
        """`*`, `+`, and `{m,}` (hi is None): `lo` mandatory copies (always
        taken regardless of width) followed by a genuine loop for any
        further repetitions. The loop may take one more repetition greedily,
        but a repetition that turns out to consume nothing is accepted only
        when it is the very first repetition attempted for the whole
        construct (count == 0, only reachable when lo == 0); any later
        zero-width repetition is rejected so the loop stops rather than
        spinning forever on an empty match. This split (mandatory-then-loop)
        is the standard NFA construction for `{m,}` and matches both glibc
        regexec and Go regexp.CompilePOSIX on every case except one
        documented corner (a nullable body with lo >= 1, e.g. `(a?){2,}`),
        where the two reference implementations themselves disagree."""
        lo = nd.lo
        if count < lo:
            return m(
                nd.child, i, lambda j: match_unbounded_repeat(nd, j, count + 1, cont)
            )

        def after(j):
            if j == i:
                if count == 0:
                    return cont(i)
                return False
            return match_unbounded_repeat(nd, j, count + 1, cont)

        if m(nd.child, i, after):
            return True
        return cont(i)

    ok = m(node, start, lambda j: j == end)
    if not ok:
        raise NoMatch("phase-2 reconstruction failed: reference bug")
    return groups


def match(pattern, subject):
    """Return (mstart, mend, {group_idx: (a,b) or None}) or None if no match."""
    node, ngroups = compile_ere(pattern)
    span = find_overall_match(node, subject)
    if span is None:
        return None
    start, end = span
    groups = reconstruct_groups(node, ngroups, subject, start, end)
    return start, end, groups


def format_cli(pattern, subject):
    """Return the expected stdout text in the posixmatch CLI's own format
    (see environment/docs/04-io-contract.md), for direct comparison against
    the built binary's output."""
    try:
        res = match(pattern, subject)
    except ParseError:
        return "PARSE_ERROR"
    if res is None:
        return "NOMATCH"
    start, end, groups = res
    lines = [f"MATCH {start} {end}"]
    for idx in sorted(groups):
        span = groups[idx]
        if span is None:
            lines.append(f"GROUP {idx} NOMATCH")
        else:
            lines.append(f"GROUP {idx} {span[0]} {span[1]}")
    return "\n".join(lines)
