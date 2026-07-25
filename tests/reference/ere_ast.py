"""ERE parser producing an AST. Supported grammar (POSIX 1003.1 ERE subset,
disclosed in full in environment/docs/01-grammar.md):

literal, '.', concatenation, '|', '(...)' capturing group,
postfix '*', '+', '?', '{m}', '{m,}', '{m,n}' on a single preceding atom,
bracket expressions '[...]'/'[^...]' with ranges and literal ']'/'-' handling,
anchors '^' and '$' (special in every position, matching only true
start-of-subject / end-of-subject respectively -- zero width).
No backreferences (ERE never has them). Two duplication symbols may never be
stacked directly on the same atom (undefined by POSIX ERE).
"""


class Node:
    pass


class Lit(Node):
    def __init__(self, ch):
        self.ch = ch

    def __repr__(self):
        return f"Lit({self.ch!r})"


class AnyChar(Node):
    def __repr__(self):
        return "AnyChar()"


class Bracket(Node):
    def __init__(self, negate, items):
        # items: list of (lo, hi) inclusive char ranges (lo==hi for singles)
        self.negate = negate
        self.items = items

    def matches(self, c):
        inside = any(lo <= c <= hi for lo, hi in self.items)
        return (not inside) if self.negate else inside

    def __repr__(self):
        return f"Bracket(neg={self.negate}, items={self.items})"


class Concat(Node):
    def __init__(self, parts):
        self.parts = parts

    def __repr__(self):
        return f"Concat({self.parts})"


class Alt(Node):
    def __init__(self, branches):
        self.branches = branches  # listed order matters for disambiguation

    def __repr__(self):
        return f"Alt({self.branches})"


class Group(Node):
    def __init__(self, idx, child):
        self.idx = idx
        self.child = child

    def __repr__(self):
        return f"Group({self.idx}, {self.child})"


class Repeat(Node):
    def __init__(self, child, lo, hi):
        # hi is None for unbounded
        self.child = child
        self.lo = lo
        self.hi = hi

    def __repr__(self):
        return f"Repeat({self.child}, {self.lo}, {self.hi})"


class AnchorStart(Node):
    def __repr__(self):
        return "AnchorStart()"


class AnchorEnd(Node):
    def __repr__(self):
        return "AnchorEnd()"


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, pattern):
        self.p = pattern
        self.i = 0
        self.n = len(pattern)
        self.group_count = 0

    def peek(self):
        return self.p[self.i] if self.i < self.n else None

    def parse(self):
        node = self.parse_alt()
        if self.i != self.n:
            raise ParseError(f"unexpected char at {self.i}: {self.p[self.i]!r}")
        return node, self.group_count

    def parse_alt(self):
        branches = [self.parse_concat()]
        while self.peek() == "|":
            self.i += 1
            branches.append(self.parse_concat())
        if len(branches) == 1:
            return branches[0]
        return Alt(branches)

    def parse_concat(self):
        parts = []
        while self.i < self.n and self.peek() not in ("|", ")"):
            parts.append(self.parse_repeat())
        if len(parts) == 1:
            return parts[0]
        return Concat(parts)

    def parse_repeat(self):
        atom = self.parse_atom()
        c = self.peek()
        if c == "*":
            self.i += 1
            atom = Repeat(atom, 0, None)
        elif c == "+":
            self.i += 1
            atom = Repeat(atom, 1, None)
        elif c == "?":
            self.i += 1
            atom = Repeat(atom, 0, 1)
        elif c == "{" and self._looks_like_interval():
            atom = Repeat(atom, *self._parse_interval())
        else:
            return atom
        if self.peek() in ("*", "+", "?") or (
            self.peek() == "{" and self._looks_like_interval()
        ):
            raise ParseError(
                f"stacked duplication symbol at {self.i} is undefined by POSIX ERE"
            )
        return atom

    def _looks_like_interval(self):
        j = self.i + 1
        saw_digit = False
        while j < self.n and self.p[j].isdigit():
            saw_digit = True
            j += 1
        if j < self.n and self.p[j] == ",":
            j += 1
            while j < self.n and self.p[j].isdigit():
                j += 1
        return saw_digit and j < self.n and self.p[j] == "}"

    def _parse_interval(self):
        assert self.p[self.i] == "{"
        self.i += 1
        start = self.i
        while self.p[self.i].isdigit():
            self.i += 1
        lo = int(self.p[start : self.i])
        if self.peek() == ",":
            self.i += 1
            start2 = self.i
            while self.i < self.n and self.p[self.i].isdigit():
                self.i += 1
            hi = int(self.p[start2 : self.i]) if self.i > start2 else None
        else:
            hi = lo
        assert self.peek() == "}"
        self.i += 1
        return lo, hi

    def parse_atom(self):
        c = self.peek()
        if c is None:
            raise ParseError("unexpected end of pattern")
        if c == "(":
            self.i += 1
            self.group_count += 1
            idx = self.group_count
            child = self.parse_alt()
            if self.peek() != ")":
                raise ParseError("missing )")
            self.i += 1
            return Group(idx, child)
        if c == "^":
            self.i += 1
            return AnchorStart()
        if c == "$":
            self.i += 1
            return AnchorEnd()
        if c == ".":
            self.i += 1
            return AnyChar()
        if c == "[":
            return self.parse_bracket()
        if c == "\\":
            self.i += 1
            nc = self.peek()
            if nc is None:
                raise ParseError("dangling backslash")
            self.i += 1
            return Lit(nc)
        if c in ("*", "+", "?"):
            raise ParseError(f"nothing to repeat at {self.i}")
        self.i += 1
        return Lit(c)

    def parse_bracket(self):
        assert self.p[self.i] == "["
        self.i += 1
        negate = False
        if self.peek() == "^":
            negate = True
            self.i += 1
        items = []
        first = True
        while True:
            c = self.peek()
            if c is None:
                raise ParseError("unterminated bracket expression")
            if c == "]" and not first:
                self.i += 1
                break
            first = False
            if c == "]":
                self.i += 1
                lo = "]"
            else:
                self.i += 1
                lo = c
            if self.peek() == "-" and self.i + 1 < self.n and self.p[self.i + 1] != "]":
                self.i += 1
                hi = self.peek()
                self.i += 1
                if lo > hi:
                    raise ParseError(
                        f"reversed bracket range {lo!r}-{hi!r}: "
                        "start collates after end"
                    )
                items.append((lo, hi))
            else:
                items.append((lo, lo))
        return Bracket(negate, items)
