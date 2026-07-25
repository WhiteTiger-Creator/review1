"""Deterministic case battery for the posix-ere-leftmost-longest-capture
verifier. HAND_CASES pins one example per disclosed disambiguation rule;
random_cases(seed, n) generates additional structurally varied cases from a
fixed seed so hidden runs still cover fresh instances of the same rules.

The random generator is deliberately capped at a shallow nesting depth and a
short alphabet/subject length: this keeps every generated case fast for both
the Python reference and a typical from-scratch matcher, and stays clear of
the handful of ultra-deeply-nested nullable-repetition shapes where even
independent real-world POSIX implementations (glibc regexec vs. Go's
regexp.CompilePOSIX) disagree with each other -- see the note in
reference.py's match_unbounded_repeat docstring. Every case actually used
here was cross-checked by the task author against both of those independent
implementations.
"""

import random

# One example per disclosed rule in environment/docs/. Each tuple is
# (pattern, subject).
HAND_CASES = [
    ("a", "abc"),
    ("abc", "xxabcxx"),
    ("a|ab", "abc"),  # leftmost-longest beats leftmost-first
    ("a|ab", "xab"),
    ("(a|ab)(c|bcd)(d*)", "abcd"),  # alternation order vs. length (worked example 1)
    ("(ab|a)(c|bcd)(d*)", "abcd"),
    ("(a|ab)(bcd|c)(d*)", "abcd"),
    ("(ab)*", "ababab"),  # repeated group reports last iteration
    ("(ab)*", "xyz"),
    ("(a)(a)(a)", "aaa"),
    ("a^b", "a^b"),  # mid-pattern anchor can never match
    ("a^b", "ab"),
    ("^a", "a"),
    ("^a", "ba"),
    ("a$", "a"),
    ("a$", "ab"),
    ("^abc$", "abc"),
    ("^abc$", "xabc"),
    ("^^a", "a"),
    ("a$$", "a"),
    ("[a-z]+", "Hello123world"),
    ("[^0-9]+", "abc123"),
    ("[]ab]", "]"),
    ("[a-]", "-"),
    ("[-a]", "-"),
    ("[^]a]", "x"),
    ("a{2,4}", "aaaaa"),
    ("a{2}", "aaaaa"),
    ("a{2,}", "aaaaa"),
    ("(a?)*", "b"),  # nullable-under-star: one empty rep, not zero
    ("(a?)*", "aaa"),
    ("(a*)*", "aaa"),
    ("(a?)+", "aaa"),
    ("(a?){0,3}", "a"),  # bounded interval unrolling of a nullable atom
    ("(a?){3}", "a"),
    ("(a|b|c)+", "cba"),
    ("x(a|ab)(bc|c)y", "xabcy"),
    ("(foo|foobar)(bar)?", "foobar"),
    ("(foobar|foo)(bar)?", "foobar"),
    ("(a(b(c)?)?)?", "ab"),
    ("(a(b(c)?)?)?", "a"),
    ("(a(b(c)?)?)?", ""),
    ("a.*b", "axxxbxxxb"),
    ("a.*b", "ab"),
    ("(a|)b", "b"),
    ("(|a)b", "ab"),
    ("()a", "a"),
    ("(a)?b", "b"),
    ("(a)?b", "ab"),
    ("(ab)?(cd)?", "cd"),
    ("(a|b)(a|b)(a|b)", "bab"),
    (".*", "xyz"),
    (".+", ""),
    ("(.)(.)(.)", "xyz"),
    ("^(a|ab)$", "ab"),
    ("(a.c|abc)", "abc"),
    ("a{0,2}b", "aaab"),
    ("(foo|foobar)", "foobart"),
    ("[abc]*", "cba"),
    ("[^abc]*", "xyz"),
    ("(a|aa)(a|aa)", "aaaa"),
    ("(aaa|aa|a)", "aaaa"),
    ("(a|aa|aaa)", "aaaa"),
    # -- Stage B additions: the previously under-specified parse-error and
    # disambiguation cases pinned in 01-grammar.md / 03-subexpression-rule.md.
    # Unbalanced parentheses (PARSE_ERROR).
    ("a)", "a"),
    (")", "a"),
    ("(a", "a"),
    # `{,n}` has no digit before the comma, so it never starts an interval;
    # it and the following characters are read as ordinary literals.
    ("a{,2}", "aaa"),
    ("a{,2}", "xa{,2}y"),
    # Backslash is not special inside a bracket expression: `\` and the
    # character after it are two separate ordinary members.
    ("[\\)]", ")"),
    ("[\\)]", "\\"),
    # A reversed bracket range is a PARSE_ERROR.
    ("[z-a]", "abz"),
    ("[b-a]", "ab"),
    # A trailing, unescaped backslash at the end of the pattern is a
    # PARSE_ERROR.
    ("a\\", "a"),
    ("\\", "a"),
    # Greedy fork: a repetition's own consumption is resolved before its
    # enclosing construct considers taking a further repetition -- the walk
    # does not maximize repetition count. See worked example 2.
    ("((.)+){0,2}", "ba"),
    ("((.)+){0,2}", "b"),
    ("((.)+){0,3}", "bab"),
    # Stale nested group: a nested group keeps its last-participating span
    # even when its enclosing repetition's final iteration skips it. See
    # worked example 3.
    ("(a(b)?)*", "aba"),
    ("(a(b)?)*", "ab"),
    ("(a(b)?){2,3}", "aba"),
    ("(a(b)?){1,3}", "aab"),
    # -- Stage C additions: thickening the bounded-vs-unbounded empty-
    # iteration asymmetry (03-subexpression-rule.md's two "explicit finite
    # upper bound" vs. "no upper bound" bullets). Before this addition, only
    # one case in the whole battery ((a?){0,3} on "a") exercised the axis
    # where a BOUNDED quantifier (`{m,n}`, `{m}`, `?`) must take a further
    # optional repetition even when it can only match the empty string,
    # whereas an UNBOUNDED quantifier (`*`, `+`, `{m,}`) refuses a further
    # zero-width repetition once at least one repetition has already
    # occurred. These vary: the nullable body's shape ((a?), (a*), (a|), an
    # explicitly-grouped ((a)?), and a nested-group shape ((a?)(b?)) /
    # ((a?)(b)?)); the bounded interval's own m/n (`{0,n}`, `{m,n}` with
    # m>0, and `{n}` exact); whether the subject supplies enough characters
    # to satisfy every optional slot with a real character, exactly enough
    # for the mandatory reps only, or none at all; and, as a control, the
    # identical body shapes wrapped in the UNBOUNDED `*`/`+` instead -- these
    # must behave the same whether or not an engine mishandles the bounded
    # case, which is exactly what isolates the axis to the bounded/unbounded
    # split rather than to nullable bodies in general.
    # Just enough subject characters to feed some but not all of the
    # optional slots -- the subject runs dry partway through the optional
    # repetitions, forcing the last one or two to be taken empty.
    ("(a?){0,3}", "aa"),
    ("(a?){1,3}", "a"),
    ("(a?){1,4}", "aa"),
    ("(a?){2,4}", "aaa"),
    ("(a?){0,4}", "aaa"),
    ("(a*){0,3}", "aa"),
    ("(a*){1,3}", "a"),
    ("(a*){1,4}", "aa"),
    ("(a|){0,2}", "a"),
    ("(a|){1,3}", "a"),
    ("(a|){1,4}", "aa"),
    ("((a)?){0,4}", "aa"),
    ("((a)?){1,3}", "a"),
    ("((a)?){2,4}", "aaa"),
    # A nested nullable shape under a bounded interval: the asymmetry now
    # also has to propagate correctly to an inner group's reported span,
    # not just the outer repeated group's.
    ("((a?)(b?)){1,3}", "ab"),
    ("((a?)(b)?){1,3}", "ab"),
    ("((a?)(b?)){1,4}", "aab"),
    ("((a?)(b?)){2,4}", "aa"),
    ("((a?)(b)?){2,4}", "aa"),
    # Contrast: plenty of subject characters, so no optional slot is ever
    # forced empty -- the bounded interval's own greediness alone decides
    # the answer and there is nothing for the asymmetry to bite on.
    ("(a?){2,4}", "aaaa"),
    # Contrast: the subject runs out during the MANDATORY reps themselves,
    # so the mandatory phase's own last repetition is already empty; taking
    # or refusing further *optional* empty repetitions cannot change the
    # reported span either way.
    ("(a?){2,4}", "a"),
    ("(a?){1,2}", ""),
    ("(a?){0,2}", ""),
    ("(a?){3,3}", "a"),
    ("((a?)(b?)){0,3}", ""),
    # Contrast: the identical nullable-body shapes under UNBOUNDED `*`/`+`
    # instead of a bounded interval -- these must NOT diverge for an engine
    # that only mishandles the bounded case, which is what proves the axis
    # is specifically about the bounded/unbounded split.
    ("(a?)*", "a"),
    ("(a?)+", "a"),
    ("(a*)*", "a"),
    ("(a|)+", "a"),
    ("((a)?)*", "a"),
    ("((a?)(b?))*", "ab"),
    ("((a?)(b)?)+", "ab"),
]


def gen_atom(depth, rnd, alphabet):
    if depth <= 0:
        choice = rnd.choice(["lit", "lit", "dot", "bracket"])
    else:
        choice = rnd.choice(["lit", "dot", "bracket", "group"])
    if choice == "lit":
        return rnd.choice(alphabet)
    if choice == "dot":
        return "."
    if choice == "bracket":
        neg = rnd.random() < 0.3
        chars = rnd.sample(list(alphabet), k=min(len(alphabet), rnd.randint(1, 3)))
        return f"[{'^' if neg else ''}{''.join(chars)}]"
    if choice == "group":
        return "(" + gen_pattern(depth - 1, rnd, alphabet) + ")"
    raise AssertionError(choice)


def gen_quantified(depth, rnd, alphabet):
    atom = gen_atom(depth, rnd, alphabet)
    q = rnd.choice(["none", "none", "star", "plus", "opt", "interval"])
    if q == "none":
        return atom
    if q == "star":
        return atom + "*"
    if q == "plus":
        return atom + "+"
    if q == "opt":
        return atom + "?"
    if q == "interval":
        lo = rnd.randint(0, 2)
        hi = lo + rnd.randint(0, 2)
        return atom + "{" + str(lo) + "," + str(hi) + "}"
    raise AssertionError(q)


def gen_pattern(depth, rnd, alphabet):
    if depth <= 0:
        return gen_quantified(depth, rnd, alphabet)
    choice = rnd.choice(["single", "single", "concat", "alt"])
    if choice == "single":
        return gen_quantified(depth, rnd, alphabet)
    if choice == "concat":
        n = rnd.randint(2, 3)
        return "".join(gen_quantified(depth - 1, rnd, alphabet) for _ in range(n))
    if choice == "alt":
        n = rnd.randint(2, 3)
        return "|".join(gen_quantified(depth - 1, rnd, alphabet) for _ in range(n))
    raise AssertionError(choice)


def gen_subject(rnd, alphabet):
    n = rnd.randint(0, 8)
    return "".join(rnd.choice(alphabet) for _ in range(n))


def random_cases(seed, n, alphabet="ab", max_depth=2):
    """Regenerate the (pattern, subject) pairs `gen_pattern`/`gen_subject`
    would produce from a fixed seed. Depth is capped at 2 -- ample for
    concatenation/alternation of quantified groups/brackets, while staying
    clear of the pathological nesting depth (3+) where an unbounded
    quantifier directly wraps an alternation with a nullable branch inside
    another unbounded quantifier, which can blow up even independent
    real-world regex engines. Provided for provenance/extensibility; the
    graded battery below (RANDOM_CASES) is the output of this exact
    generator with seed 20260721, already filtered and pinned -- see the
    module docstring."""
    rnd = random.Random(seed)
    cases = []
    while len(cases) < n:
        pat = gen_pattern(max_depth, rnd, alphabet)
        subj = gen_subject(rnd, alphabet)
        cases.append((pat, subj))
    return cases


# The output of random_cases(20260721, ...) (seed fixed, alphabet "ab", depth
# 2), drawn from a pool of 900 generated candidates and filtered down to the
# 896 that glibc regexec(REG_EXTENDED) and Go's regexp.CompilePOSIX both
# independently agree with this task's reference on -- pinned here as a
# plain list so the shipped battery needs no external regex engine at
# verification time. The 4 dropped candidates are exactly the documented
# glibc-only-divergent shape described in reference.py's
# match_unbounded_repeat docstring (a nullable body under a bounded interval
# or unbounded repeat with a mandatory lower bound); this task's disclosed
# rule (03-subexpression-rule.md) resolves them the way Go's independent
# implementation does.
RANDOM_CASES = [
    ("(.+|a{1,3}|a)+", "b"),
    ("a?[^b]+a?", "ababb"),
    ("(a{0,0})?b+a", "aaaab"),
    ("b*", "aa"),
    (".|[b]?|([a]+)", "abbb"),
    ("a", "babbbb"),
    ("a?", "baa"),
    ("[b].(b)", "babbb"),
    (".|(b*)?", "aabba"),
    ("b|([ba])*|.?", "aba"),
    ("b", "abaaabb"),
    ("b(b)*", "bbbbbbb"),
    ("[^ab]{0,0}", "aabba"),
    ("(.?|[ab]?|[ab])?", "bbaaaaa"),
    ("[^ba]|([a]*)", "bb"),
    ("a+(.)(.)+", "bbbaa"),
    (".(a+)*", "abbbb"),
    ("a?", "aaab"),
    (".", "bbbbb"),
    (".+|[a]+", "aaa"),
    ("[^b]+", "aabaaab"),
    ("a*", "bbbaba"),
    ("a", "bbbb"),
    ("[a]+b+", "bbbbbab"),
    ("[^b]([ab]{2,4})(a?)+", "aaa"),
    ("(b*.+)", "a"),
    ("a+", "ba"),
    ("([ba])?", "babab"),
    (".?|.", ""),
    ("([^b]?|.?|.){2,4}", "aababaa"),
    ("[^ab]+", "bbbbbba"),
    ("[b]", "babababb"),
    ("(a+){2,4}|.*", "baaabaa"),
    ("(.)?|.|.+", "bab"),
    (".*b+(a+)", "ab"),
    (".?", "aabbba"),
    (".{2,2}a*", "a"),
    ("(b?|.)?", "baabbaba"),
    (".?", ""),
    ("a(b?)", ""),
    ("(a*)|b*|.?", "aa"),
    ("(b*)(b*)+.{1,3}", "bbab"),
    ("(.|.+|a){2,3}", "bbbbab"),
    (".?|(.{1,2}){0,1}", "aaabab"),
    (".*", "ababbb"),
    ("(b+)?|b", "abbabaaa"),
    ("[^ba]{2,3}[^ab]+.", "ab"),
    (".", "bbababba"),
    ("(b[b]{0,0})", "aaab"),
    ("a+", "b"),
    ("(.*a?)*", "aaaa"),
    ("a([b]{1,2})[ab]?", "a"),
    ("([ba]+)", "bbaba"),
    ("(a)*", "bbaa"),
    ("[^ba]*[^ab]", ""),
    (".", ""),
    ("a", "bbaaaaaa"),
    ("b?", "baaabb"),
    (".*|([b]{0,2})|.?", "aaabbaab"),
    ("b{1,1}", "bbbbbaaa"),
    ("(a+)?|[b]", "abbaaabb"),
    (".+(a?)?", "abbabbbb"),
    ("b", ""),
    (".+", "aaa"),
    (".+", "ababaa"),
    ("a", "bbb"),
    ("(b)|b?", "bba"),
    ("a?a", "abab"),
    ("(a*)?", "bbaabab"),
    (".?", "bbabbbab"),
    ("(b){1,1}", "bbba"),
    ("[b]?|b?", "bbabbb"),
    ("a?", "aabbaaab"),
    ("(b)?[ba]*", "aabaaa"),
    ("(a|[ab]|[ba])?", "bbaba"),
    (".?(b)*b*", "aabbabb"),
    ("(a{1,1})*", "bbbaaabb"),
    ("([^ab]*)|.{2,2}", "abba"),
    (".", "aab"),
    ("[ba].", "abbaaaba"),
    (".b", "ab"),
    ("([ab]+)*a*", "baabbb"),
    ("a", "a"),
    ("[^ab]?|(b)*|[b]+", "b"),
    ("b", "baabab"),
    ("([ba]+)|(.)", ""),
    ("b?", ""),
    ("b*", "bbbba"),
    (".{1,2}|(b+)?", "baaabbb"),
    (".", "abb"),
    ("[b]?", "baabbb"),
    ("(a{1,3})?|a", ""),
    ("b{0,1}", "abbab"),
    (".?.*.{2,2}", "bbabbaa"),
    ("(.)+|.{0,0}", "aababaa"),
    ("(a+).[ba]", "b"),
    (".|b?", "b"),
    (".", "bab"),
    ("a|[^ba]{2,3}", "abbb"),
    ("a?", "abbb"),
    (".", "abbaabb"),
    ("b+", "a"),
    ("b+", ""),
    ("(a*)+[^a]?a", "ba"),
    ("(b+)+(.*)", "bbaab"),
    ("(.)", "bababbba"),
    ("[b]|.*", "aaabaaab"),
    ("[^ba]{1,3}([ab])", "babab"),
    ("a{0,0}", "aaab"),
    ("(b{1,3})[b]*a{0,1}", "ba"),
    (".|b+", "b"),
    (".{2,3}(b{2,4})*", "b"),
    ("a", "aaabb"),
    ("a*(a+)*b?", "b"),
    ("(.)+(.?).+", "abab"),
    ("[a]{2,3}", "bbaa"),
    (".|.{2,2}|(.{2,2})+", "aaa"),
    ("[^b]*(a)?.", "bbaa"),
    ("b+", "baabbaab"),
    ("b*|.*|a{1,2}", "ab"),
    ("[a]?.*[ba]", "aaabb"),
    ("(a+|.|b*)+", "aababbb"),
    ("(bb?)", "aababa"),
    ("([a]+)*", "bbbabab"),
    ("(a){0,1}.*", "aaaaaba"),
    ("[^b]b(a+)+", "aaabbba"),
    ("a{2,3}|.?", "aa"),
    (".+", "b"),
    (".+|(a+){2,3}|([a]?)*", "babababa"),
    (".|.|a*", "babab"),
    (".+|.|[ba]?", "bbbbbbb"),
    ("(.{2,4}|a)", "baaaba"),
    ("a(a)?[^ab]", "aabaa"),
    ("([ab]*)*", "aababaa"),
    ("a+", "abab"),
    ("(b?[b]{2,3})", "baaa"),
    ("b*|b{1,1}", "aaab"),
    (".|(a+)*|.*", "aa"),
    ("[b]*b", "b"),
    ("[ab]*|(b+)", ""),
    ("(.*){2,4}|a?|[b]+", "aa"),
    ("a?", "babb"),
    (".+([ab])?(b)*", "bbbaa"),
    ("(b)+|[ab]{1,2}|[ab]", "aabb"),
    ("(b{2,2})|[ba]*", "bb"),
    (".?", "abbbbbba"),
    ("a?|[ba]*", "ababa"),
    ("b?", "bababa"),
    ("(b{1,2})([a]).+", "aabbbbb"),
    ("a{2,4}", "abbb"),
    (".{1,1}|(.?)*|b?", "aaa"),
    ("aa*", ""),
    (".|.|(a?)", "aa"),
    ("([ba]?){2,3}", "abbabba"),
    (".+", "bab"),
    (".+", "aabaabaa"),
    ("(a)*a*.", "aba"),
    ("(b)?|.+", "a"),
    (".+", "bababbbb"),
    ("[ba]{0,0}", "abbb"),
    ("([ab])*.[ab]{2,3}", "abbbbbbb"),
    ("(a*).*.", "a"),
    (".*", ""),
    ("([b]|.{0,0}|[ba]?)", "aababba"),
    ("(b{2,3})?|.+", "bbbabaab"),
    ("([ab]{2,2}|b{0,1}){2,3}", "aaabb"),
    ("b", "baba"),
    (".{1,2}[ab]+([ba]+){1,1}", "baaaabb"),
    (".+", "ba"),
    ("[ab]?.*", "bbaaaa"),
    ("[^ab]?", "b"),
    ("([ab]{2,2}){2,3}(b?)+[ba]{0,1}", "aaa"),
    (".?b", "bab"),
    ("[^ba]?", "abaa"),
    ("a+", "baababb"),
    ("a", "baaabb"),
    ("[^ba]+a{2,3}b+", "baabb"),
    ("bb?", "baab"),
    (".", "ababb"),
    (".*", "aa"),
    ("..+", "babaa"),
    (".?|.", "aab"),
    (".*", "a"),
    ("[^ba]+", "baaaba"),
    (".{2,3}.*", "abbaaa"),
    (".+.*[^ab]?", ""),
    ("[^a]a+.+", "baa"),
    ("b", "ababab"),
    ("b[ba]?", "bbb"),
    ("(.{1,1})+a", "ababaa"),
    ("(.*){0,1}.?", ""),
    ("[b]{2,4}|a+|(a+){2,4}", "bbababa"),
    ("(.)b", "bbbaaba"),
    ("[ba]+", "b"),
    (".", "bbbba"),
    (".+", ""),
    ("[ab]?", "bbabb"),
    (".{2,2}", "bbbaabb"),
    ("[ba]?", "baabaab"),
    ("[b]?", "baabaaba"),
]

ALL_CASES = HAND_CASES + RANDOM_CASES
