import os
from fractions import Fraction

VARIANTS = ("pinned", "edgetie", "classtie")


def read_tables(data_dir):
    out = {}
    for name in sorted(os.listdir(data_dir)):
        if not name.endswith(".csv"):
            continue
        with open(os.path.join(data_dir, name), encoding="utf-8") as fh:
            lines = [ln.strip() for ln in fh if ln.strip() != ""]
        rows = []
        for line in lines[1:]:
            cells = [int(c) for c in line.split(",")]
            rows.append((tuple(cells[:-1]), cells[-1]))
        out[name[:-4]] = rows
    return out


def pair_score(rows, a, b, card, classes):
    total = Fraction(0)
    for c in range(classes):
        block = [r for r in rows if r[1] == c]
        n = len(block)
        if n == 0:
            continue
        joint = {}
        left = {}
        right = {}
        for feats, _label in block:
            u, v = feats[a], feats[b]
            joint[(u, v)] = joint.get((u, v), 0) + 1
            left[u] = left.get(u, 0) + 1
            right[v] = right.get(v, 0) + 1
        for u in range(card):
            for v in range(card):
                observed = joint.get((u, v), 0)
                expected = Fraction(left.get(u, 0) * right.get(v, 0), n)
                if expected == 0:
                    continue
                delta = observed - expected
                total += delta * delta / expected
    return total


def spanning(features, scores, variant):
    chosen = []
    edges = []
    for a in range(features):
        for b in range(a + 1, features):
            edges.append((scores[(a, b)], a, b))
    parent = list(range(features))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    if variant == "edgetie":
        ordered = sorted(edges, key=lambda e: (-e[0], -e[1], -e[2]))
    elif variant == "kruskal":
        ordered = sorted(edges, key=lambda e: (-e[0], e[2], e[1]))
    else:
        ordered = sorted(edges, key=lambda e: (-e[0], e[1], e[2]))
    for score, a, b in ordered:
        ra, rb = find(a), find(b)
        if ra == rb:
            continue
        parent[ra] = rb
        chosen.append((a, b, score))
    return chosen


def orient(features, chosen, variant):
    root = 0
    adjacency = {j: [] for j in range(features)}
    for a, b, _s in chosen:
        adjacency[a].append(b)
        adjacency[b].append(a)
    parent = {root: -1}
    stack = [root]
    seen = {root}
    while stack:
        node = stack.pop()
        for nxt in sorted(adjacency[node]):
            if nxt not in seen:
                seen.add(nxt)
                parent[nxt] = node
                stack.append(nxt)
    for j in range(features):
        parent.setdefault(j, -1)
    return parent


def conditional(rows, j, p, card, classes, variant):
    table = {}
    for feats, label in rows:
        key = (label, feats[j]) if p < 0 else (label, feats[p], feats[j])
        table[key] = table.get(key, 0) + 1
    return table


def predict(rows, parent, card, classes, feats, variant):
    best = 0
    best_score = None
    n = len(rows)
    for c in range(classes):
        prior = Fraction(sum(1 for r in rows if r[1] == c) + 1, n + classes)
        score = prior
        for j in range(len(feats)):
            p = parent[j]
            if p < 0:
                numer = sum(1 for f, l in rows if l == c and f[j] == feats[j])
                denom = sum(1 for f, l in rows if l == c)
            else:
                numer = sum(
                    1
                    for f, l in rows
                    if l == c and f[p] == feats[p] and f[j] == feats[j]
                )
                denom = sum(1 for f, l in rows if l == c and f[p] == feats[p])
            score *= Fraction(numer + 1, denom + card)
        better = best_score is None or score > best_score
        if variant == "classtie" and best_score is not None and score == best_score:
            better = True
        if better:
            best_score = score
            best = c
    return best, best_score


def parse_int(token):
    if not token.lstrip("+").isdigit():
        return None
    return int(token)


def _frac(v):
    return f"{v.numerator}/{v.denominator}"


def _handle(tables, parts, variant):
    if len(parts) != 3:
        return None
    if parts[1] not in tables or parts[2] not in tables:
        return None
    rows = tables[parts[1]]
    probes = tables[parts[2]]
    if len(rows) < 2 or not probes:
        return None
    features = len(rows[0][0])
    if features < 2:
        return None
    if any(len(r[0]) != features for r in rows) or any(
        len(p[0]) != features for p in probes
    ):
        return None
    labels = {label for _f, label in rows}
    if len(labels) < 2:
        return None
    classes = max(labels) + 1
    card = max(max(f) for f, _l in rows) + 1
    scores = {}
    for a in range(features):
        for b in range(a + 1, features):
            scores[(a, b)] = pair_score(rows, a, b, card, classes)
    chosen = spanning(features, scores, variant)
    parent = orient(features, chosen, variant)
    qid = parts[0]
    lines = []
    for a, b, score in sorted(chosen, key=lambda e: (e[0], e[1])):
        lines.append(f"{qid} E {a} {b} S {_frac(score)}")
    tree = " ".join(str(parent[j]) for j in range(features))
    lines.append(f"{qid} T {tree}")
    for i, (feats, _label) in enumerate(probes):
        c, score = predict(rows, parent, card, classes, feats, variant)
        lines.append(f"{qid} P {i} C {c} W {_frac(score)}")
    return lines


def process(tables, lines, variant="pinned"):
    out = []
    for raw in lines:
        parts = raw.split()
        if not parts:
            continue
        result = _handle(tables, parts, variant)
        if result is None:
            out.append(f"{parts[0]} REJECT")
        else:
            out.extend(result)
    return out
