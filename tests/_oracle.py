import json
import random

POINTS = list(range(8))
ROTSTEP = 2


class TsuroError(Exception):
    pass


def rotate_point(p, rot):
    return (p + ROTSTEP * rot) % 8


def gpoint(c, r, p):
    if p == 0:
        return ("H", c, r, 0)
    if p == 1:
        return ("H", c, r, 1)
    if p == 2:
        return ("V", c, r, 1)
    if p == 3:
        return ("V", c, r, 0)
    if p == 4:
        return ("H", c, r - 1, 1)
    if p == 5:
        return ("H", c, r - 1, 0)
    if p == 6:
        return ("V", c - 1, r, 0)
    return ("V", c - 1, r, 1)


def cross(c, r, q):
    if q == 0:
        return (c, r + 1, 5)
    if q == 1:
        return (c, r + 1, 4)
    if q == 2:
        return (c + 1, r, 7)
    if q == 3:
        return (c + 1, r, 6)
    if q == 4:
        return (c, r - 1, 1)
    if q == 5:
        return (c, r - 1, 0)
    if q == 6:
        return (c - 1, r, 3)
    return (c - 1, r, 2)


def pairing_from_paths(paths):
    mate = {}
    seen = set()
    for pair in paths:
        if len(pair) != 2:
            raise TsuroError("bad pair")
        a, b = pair
        if a not in POINTS or b not in POINTS or a == b:
            raise TsuroError("bad point")
        if a in seen or b in seen:
            raise TsuroError("repeat point")
        seen.add(a)
        seen.add(b)
        mate[a] = b
        mate[b] = a
    if len(seen) != 8:
        raise TsuroError("incomplete tile")
    return mate


def paths_of(mate):
    out = []
    done = set()
    for a in POINTS:
        b = mate[a]
        if a in done or b in done:
            continue
        done.add(a)
        done.add(b)
        out.append([a, b])
    return out


def in_board(n, c, r):
    return 0 <= c < n and 0 <= r < n


def board_of(tiles):
    return [{"sq": [c, r], "paths": paths_of(tiles[(c, r)])}
            for (c, r) in sorted(tiles)]


def make_inst(n, tiles, tokens, active, tile_paths):
    return {
        "n": n,
        "board": board_of(tiles),
        "tokens": [{"cell": [c, r], "p": p} for (c, r, p) in tokens],
        "active": active,
        "tile": tile_paths,
    }


def load(inst):
    n = inst["n"]
    if not isinstance(n, int) or n < 1:
        raise TsuroError("bad n")
    tiles = {}
    for t in inst["board"]:
        c, r = t["sq"]
        if not in_board(n, c, r):
            raise TsuroError("tile off board")
        if (c, r) in tiles:
            raise TsuroError("tile stacked")
        tiles[(c, r)] = pairing_from_paths(t["paths"])
    tokens = []
    occupied = set()
    for tk in inst["tokens"]:
        c, r = tk["cell"]
        p = tk["p"]
        if not in_board(n, c, r):
            raise TsuroError("token cell off board")
        if (c, r) in tiles:
            raise TsuroError("token on tiled cell")
        if p not in POINTS:
            raise TsuroError("bad token point")
        g = gpoint(c, r, p)
        if g in occupied:
            raise TsuroError("token overlap")
        occupied.add(g)
        tokens.append((c, r, p))
    active = inst["active"]
    if not isinstance(active, int) or active < 0 or active >= len(tokens):
        raise TsuroError("bad active")
    place_mate = pairing_from_paths(inst["tile"])
    pc, pr, _ = tokens[active]
    return n, tiles, tokens, active, place_mate, (pc, pr)


def walk_pointer(n, tiles, c0, r0, p0):
    trace = [gpoint(c0, r0, p0)]
    seen = {gpoint(c0, r0, p0)}
    c, r, p = c0, r0, p0
    limit = 8 * n * n + 16
    steps = 0
    while True:
        steps += 1
        if steps > limit:
            raise TsuroError("cycle")
        if not in_board(n, c, r):
            return trace, "out", None
        mate = tiles.get((c, r))
        if mate is None:
            return trace, "stop", (c, r, p)
        q = mate[p]
        c, r, p = cross(c, r, q)
        g = gpoint(c, r, p)
        if g in seen and in_board(n, c, r) and (c, r) in tiles:
            raise TsuroError("cycle")
        seen.add(g)
        trace.append(g)


def evaluate_route_a(inst):
    n, tiles, tokens, _active, place_mate, placed = load(inst)
    tiles = dict(tiles)
    tiles[placed] = place_mate
    movers = [i for i, (c, r, p) in enumerate(tokens) if (c, r) == placed]
    outcome = {}
    occ = {}
    for i in movers:
        c, r, p = tokens[i]
        trace, kind, final = walk_pointer(n, tiles, c, r, p)
        occ[i] = set(trace)
        outcome[i] = (kind, final)
    for i, (c, r, p) in enumerate(tokens):
        if i in movers:
            continue
        occ[i] = {gpoint(c, r, p)}
        outcome[i] = ("stay", (c, r, p))
    counts = {}
    for held in occ.values():
        for g in held:
            counts[g] = counts.get(g, 0) + 1
    contested = {g for g, k in counts.items() if k >= 2}
    result = {}
    for i in range(len(tokens)):
        kind, final = outcome[i]
        hit = any(g in contested for g in occ[i])
        if kind == "out" or hit:
            result[i] = None
        else:
            result[i] = final
    return result


def build_graph(tiles):
    adj = {}
    for (c, r), mate in tiles.items():
        for a, b in paths_of(mate):
            ga = gpoint(c, r, a)
            gb = gpoint(c, r, b)
            adj.setdefault(ga, []).append(gb)
            adj.setdefault(gb, []).append(ga)
    return adj


def refs_of(n):
    table = {}
    for c in range(-1, n + 1):
        for r in range(-1, n + 1):
            for p in POINTS:
                table.setdefault(gpoint(c, r, p), []).append((c, r, p))
    return table


def walk_graph(adj, refs, n, tiles, c0, r0, p0):
    start = gpoint(c0, r0, p0)
    inside = gpoint(c0, r0, tiles[(c0, r0)][p0])
    visited = [start]
    seen = {start}
    prev, cur = start, inside
    limit = 8 * n * n + 16
    steps = 0
    while True:
        steps += 1
        if steps > limit:
            raise TsuroError("cycle")
        visited.append(cur)
        nxts = [g for g in adj.get(cur, []) if g != prev]
        if not nxts:
            break
        if cur in seen:
            raise TsuroError("cycle")
        seen.add(cur)
        prev, cur = cur, nxts[0]
    terminal = cur
    chosen = None
    for (cc, rr, pp) in refs[terminal]:
        if (cc, rr) in tiles and gpoint(cc, rr, tiles[(cc, rr)][pp]) == prev:
            chosen = (cc, rr, pp)
            break
    if chosen is None:
        raise TsuroError("no terminal tile")
    cc, rr, pp = chosen
    nc, nr, npp = cross(cc, rr, pp)
    if not in_board(n, nc, nr):
        return visited, "out", None
    return visited, "stop", (nc, nr, npp)


def evaluate_route_b(inst):
    n, tiles, tokens, _active, place_mate, placed = load(inst)
    tiles = dict(tiles)
    tiles[placed] = place_mate
    adj = build_graph(tiles)
    refs = refs_of(n)
    movers = [i for i, (c, r, p) in enumerate(tokens) if (c, r) == placed]
    outcome = {}
    occ = {}
    for i in movers:
        c, r, p = tokens[i]
        visited, kind, final = walk_graph(adj, refs, n, tiles, c, r, p)
        occ[i] = set(visited)
        outcome[i] = (kind, final)
    for i, (c, r, p) in enumerate(tokens):
        if i in movers:
            continue
        occ[i] = {gpoint(c, r, p)}
        outcome[i] = ("stay", (c, r, p))
    coverage = {}
    for i, held in occ.items():
        for g in held:
            coverage.setdefault(g, set()).add(i)
    contested = {g for g, s in coverage.items() if len(s) >= 2}
    result = {}
    for i in range(len(tokens)):
        kind, final = outcome[i]
        hit = any(g in contested for g in occ[i])
        if kind == "out" or hit:
            result[i] = None
        else:
            result[i] = final
    return result


def format_result(inst, result):
    parts = []
    for i in range(len(inst["tokens"])):
        st = result[i]
        if st is None:
            parts.append(str(i) + ":out")
        else:
            c, r, p = st
            parts.append(str(i) + ":" + str(c) + "." + str(r) + "." + str(p))
    body = "".join(" " + x for x in parts)
    return "TOKENS " + str(len(parts)) + body


def evaluate(inst):
    try:
        ra = evaluate_route_a(inst)
    except TsuroError:
        return "ILLEGAL"
    rb = evaluate_route_b(inst)
    if ra != rb:
        raise TsuroError("routes disagree")
    return format_result(inst, ra)


CATALOG = None


def noncrossing_matchings():
    results = []

    def rec(seq, avail):
        if not avail:
            results.append(list(seq))
            return
        first = avail[0]
        for j in range(1, len(avail), 2):
            partner = avail[j]
            inner = avail[1:j]
            outer = avail[j + 1:]
            rec([*seq, (first, partner)], inner + outer)

    rec([], list(range(8)))
    uniq = []
    seen = set()
    for m in results:
        key = frozenset(frozenset(pr) for pr in m)
        if key in seen:
            continue
        seen.add(key)
        uniq.append([list(pr) for pr in m])
    uniq.sort(key=lambda m: tuple(sorted(tuple(sorted(pr)) for pr in m)))
    return uniq


_CATALOG_SLOT = [None]


def get_catalog():
    if _CATALOG_SLOT[0] is None:
        _CATALOG_SLOT[0] = noncrossing_matchings()
    return _CATALOG_SLOT[0]


def rot_paths(paths, rot):
    return [[rotate_point(a, rot), rotate_point(b, rot)] for a, b in paths]


def random_tile(rng):
    base = rng.choice(get_catalog())
    rot = rng.randint(0, 3)
    return rot_paths(base, rot)


def rim_starts(n, rng):
    starts = []
    for c in range(n):
        starts.append((c, 0, 5))
        starts.append((c, 0, 4))
        starts.append((c, n - 1, 0))
        starts.append((c, n - 1, 1))
    for r in range(n):
        starts.append((0, r, 6))
        starts.append((0, r, 7))
        starts.append((n - 1, r, 2))
        starts.append((n - 1, r, 3))
    rng.shuffle(starts)
    return starts


def fresh_tokens(n, rng, k):
    used = set()
    chosen = []
    for (c, r, p) in rim_starts(n, rng):
        g = gpoint(c, r, p)
        if g in used:
            continue
        used.add(g)
        chosen.append((c, r, p))
        if len(chosen) >= k:
            break
    return chosen


def apply_move(n, tiles, tokens, active, tile_paths):
    inst = make_inst(n, tiles, tokens, active, tile_paths)
    res = evaluate_route_a(inst)
    placed = tokens[active][:2]
    ntiles = dict(tiles)
    ntiles[placed] = pairing_from_paths(tile_paths)
    ntokens = [res[i] for i in range(len(tokens)) if res[i] is not None]
    return ntiles, ntokens


def self_play(rng, n, plies):
    tokens = fresh_tokens(n, rng, rng.randint(3, 6))
    tiles = {}
    snapshots = []
    for _ in range(plies):
        if not tokens:
            break
        active = rng.randrange(len(tokens))
        pc, pr, _ = tokens[active]
        if (pc, pr) in tiles:
            break
        tile_paths = random_tile(rng)
        inst = make_inst(n, tiles, tokens, active, tile_paths)
        try:
            line = evaluate(inst)
        except TsuroError:
            break
        if line == "ILLEGAL":
            break
        snapshots.append(inst)
        tiles, tokens = apply_move(n, tiles, tokens, active, tile_paths)
    return snapshots


STRAIGHT_H = [[7, 2], [6, 3], [0, 5], [1, 4]]


def matching_with_pair(a, b, rng):
    rest = [x for x in POINTS if x not in (a, b)]
    rng.shuffle(rest)
    pairs = [[a, b]]
    for i in range(0, 6, 2):
        pairs.append([rest[i], rest[i + 1]])
    return pairs


def scatter_tiles(rng, n, avoid, k):
    tiles = {}
    cells = [(c, r) for c in range(n) for r in range(n) if (c, r) not in avoid]
    rng.shuffle(cells)
    for (c, r) in cells[:k]:
        tiles[(c, r)] = pairing_from_paths(random_tile(rng))
    return tiles


def collision_maker(rng, n):
    r0 = rng.randrange(n)
    tc = rng.randrange(1, n - 1) if n >= 3 else 0
    target = (tc, r0)
    a, b = rng.sample(POINTS, 2)
    tokens = [(tc, r0, a), (tc, r0, b)]
    used = {gpoint(tc, r0, a), gpoint(tc, r0, b)}
    extra = rng.randint(0, 2)
    for (c, r, p) in fresh_tokens(n, rng, extra + 4):
        if (c, r) == target:
            continue
        g = gpoint(c, r, p)
        if g in used:
            continue
        used.add(g)
        tokens.append((c, r, p))
        if len(tokens) >= 2 + extra:
            break
    tiles = {}
    if rng.random() < 0.55:
        for step in (1, -1):
            cc = tc + step
            rr = r0
            reach = 0
            while in_board(n, cc, rr) and reach < rng.randint(1, 2):
                if (cc, rr) != target and (cc, rr) not in tiles:
                    tiles[(cc, rr)] = pairing_from_paths(STRAIGHT_H)
                cc += step
                reach += 1
    tokens = [t for t in tokens if (t[0], t[1]) not in tiles]
    if len(tokens) < 2:
        return None
    active = 0
    tile_paths = matching_with_pair(tokens[0][2], tokens[1][2], rng)
    if (target[0], target[1]) != (tokens[0][0], tokens[0][1]):
        return None
    return make_inst(n, tiles, tokens, active, tile_paths)


def corridor_maker(rng, n):
    r0 = rng.randrange(n)
    tiles = {}
    length = rng.randint(2, n - 1)
    start = rng.randint(0, n - length - 1) if n - length - 1 >= 0 else 0
    for c in range(start + 1, start + length):
        tiles[(c, r0)] = pairing_from_paths(STRAIGHT_H)
    target = (start, r0)
    tokens = [(start, r0, 7)]
    used = {gpoint(start, r0, 7)}
    for (c, r, p) in fresh_tokens(n, rng, 4):
        if (c, r) == target or (c, r) in tiles:
            continue
        g = gpoint(c, r, p)
        if g in used:
            continue
        used.add(g)
        tokens.append((c, r, p))
        if len(tokens) >= rng.randint(1, 3):
            break
    tile_paths = STRAIGHT_H
    return make_inst(n, tiles, tokens, 0, tile_paths)


def classify(inst):
    n, tiles, tokens, _active, place_mate, placed = load(inst)
    tiles2 = dict(tiles)
    tiles2[placed] = place_mate
    movers = [i for i, (c, r, p) in enumerate(tokens) if (c, r) == placed]
    res = evaluate_route_a(inst)
    elim = sum(1 for i in range(len(tokens)) if res[i] is None)
    maxlen = 0
    for i in movers:
        c, r, p = tokens[i]
        trace, _kind, _final = walk_pointer(n, tiles2, c, r, p)
        maxlen = max(maxlen, len(trace))
    return {"movers": len(movers), "elim": elim, "maxlen": maxlen}


def one_instance(rng, novel):
    n = rng.choice([4, 5, 6])
    roll = rng.random()
    if not novel:
        snaps = self_play(rng, n, rng.randint(1, 4))
        return snaps[0] if snaps else None
    if roll < 0.34:
        snaps = self_play(rng, n, rng.randint(2, 16))
        return snaps[-1] if snaps else None
    if roll < 0.72:
        return collision_maker(rng, n)
    return corridor_maker(rng, n)


def generate(seed, count, novel=True):
    rng = random.Random(seed)
    out = []
    guard = 0
    while len(out) < count and guard < count * 200:
        guard += 1
        inst = one_instance(rng, novel)
        if inst is None:
            continue
        try:
            line = evaluate(inst)
        except TsuroError:
            continue
        if line == "ILLEGAL":
            continue
        out.append(inst)
    return out


def rot180_point(p):
    return (p + 4) % 8


def rot180_paths(paths):
    return [[rot180_point(a), rot180_point(b)] for a, b in paths]


def rotate180_instance(inst):
    n = inst["n"]
    board = []
    for t in inst["board"]:
        c, r = t["sq"]
        board.append({"sq": [n - 1 - c, n - 1 - r],
                      "paths": rot180_paths(t["paths"])})
    tokens = []
    for tk in inst["tokens"]:
        c, r = tk["cell"]
        tokens.append({"cell": [n - 1 - c, n - 1 - r],
                       "p": rot180_point(tk["p"])})
    return {"n": n, "board": board, "tokens": tokens,
            "active": inst["active"], "tile": rot180_paths(inst["tile"])}


def rotate180_output(line, n):
    toks = line.split()
    parts = toks[2:]
    out = []
    for part in parts:
        idx, st = part.split(":")
        if st == "out":
            out.append(idx + ":out")
        else:
            c, r, p = (int(x) for x in st.split("."))
            out.append(idx + ":" + str(n - 1 - c) + "." + str(n - 1 - r)
                       + "." + str(rot180_point(p)))
    body = "".join(" " + x for x in out)
    return "TOKENS " + toks[1] + body


def to_line(inst):
    return json.dumps(inst, separators=(",", ":"), sort_keys=True)


if __name__ == "__main__":
    import sys
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 20260727
    cnt = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    data = generate(seed, cnt, novel=True)
    agree = 0
    fams = {"flow": 0, "multi_elim": 0, "collide": 0, "onestop": 0, "plain": 0}
    for it in data:
        a = evaluate_route_a(it)
        b = evaluate_route_b(it)
        if a == b:
            agree += 1
        else:
            print("DISAGREE", to_line(it))
            print("A", a)
            print("B", b)
        info = classify(it)
        if info["elim"] >= 2:
            fams["multi_elim"] += 1
        elif info["maxlen"] >= 4:
            fams["flow"] += 1
        elif info["movers"] >= 2:
            fams["collide"] += 1
        elif info["maxlen"] == 2:
            fams["onestop"] += 1
        else:
            fams["plain"] += 1
    print("agree", agree, "of", len(data))
    print("families", fams)
