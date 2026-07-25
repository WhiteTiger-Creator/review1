import os
import sys

SEED = 20260724
M32 = 0xFFFFFFFF
HERE = os.path.dirname(os.path.abspath(sys.argv[0]))
TASK = os.path.dirname(os.path.dirname(HERE))
VISIBLE_DIR = os.path.join(TASK, "environment", "inputs")
HIDDEN_DIR = os.path.join(TASK, "tests", "inputs_hidden")


class Rng:
    def __init__(self, seed):
        self.s = seed & M32

    def next(self):
        self.s = (self.s * 1103515245 + 12345) & M32
        return (self.s >> 8) & 0xFFFFFF

    def below(self, n):
        return self.next() % n

    def between(self, lo, hi):
        return lo + self.below(hi - lo + 1)

    def pick(self, seq):
        return seq[self.below(len(seq))]


def trace(start, ops):
    return f"S {start & M32}\n" + "".join(ops)


def arm(ident, deadline):
    return f"A {ident & 0xFFFF} {deadline & M32}\n"


def cancel(ident):
    return f"C {ident & 0xFFFF}\n"


def adv(n):
    return f"T {n}\n"


def advance(rng, total):
    out = []
    while total > 0:
        if total > 200000:
            step = rng.between(20000, 65535)
        elif total > 4000:
            step = rng.between(200, 2000)
        else:
            step = rng.between(1, 200)
        step = min(step, total)
        out.append(adv(step))
        total -= step
    return out


def probe(rng, focus, window):
    out = []
    coarse = max(0, focus - window)
    out.extend(advance(rng, coarse))
    for _ in range(window + window // 2):
        out.append(adv(1))
    return out


def short_family(rng, count):
    out = []
    for i in range(count):
        start = rng.between(0, 0x00FF0000)
        ops = []
        live = []
        for _ in range(rng.between(2, 12)):
            ident = rng.between(1, 4000)
            if ident in live:
                continue
            live.append(ident)
            ops.append(arm(ident, (start + rng.between(0, 250)) & M32))
        for _ in range(rng.between(1, 4)):
            ops.append(adv(rng.between(1, 120)))
        ops.extend(advance(rng, 400))
        out.append((f"short_{i:02d}", trace(start, ops)))
    return out


def wrap_family(rng, count):
    out = []
    for i in range(count):
        mode = i % 4
        if mode == 0:
            start = (0x100000000 - rng.between(200, 4000)) & M32
            deadlines = [rng.between(0, 3000) for _ in range(6)]
        elif mode == 1:
            start = (0x100000000 - rng.between(50, 900)) & M32
            deadlines = [(start + rng.between(300, 60000)) & M32 for _ in range(6)]
        elif mode == 2:
            start = rng.between(1000, 500000)
            deadlines = [
                (start + 0x80000000 + rng.between(0, 100000)) & M32 for _ in range(6)
            ]
        else:
            start = (0x100000000 - rng.between(100, 100000)) & M32
            deadlines = [rng.between(0, 200) for _ in range(3)]
            deadlines += [(start + 0x90000000) & M32 for _ in range(3)]
        ops = []
        for k, deadline in enumerate(deadlines):
            ops.append(arm(100 + k, deadline))
        ops.extend(advance(rng, rng.between(70000, 200000)))
        out.append((f"wrap_{i:02d}", trace(start, ops)))
    return out


def bound_family(rng, count):
    out = []
    for i in range(count):
        mode = i % 4
        start = (rng.between(0, 0x00F00000) & ~0xFF) + rng.pick([0, 1, 15, 128, 255])
        if mode == 3:
            block = ((start >> 16) + 2) << 16
            expires = block + 256
            ops = [arm(500, expires & M32), arm(501, (expires + 1) & M32)]
            ops.extend(probe(rng, (block - start) + 300, 320))
        else:
            delta = [256, 256, rng.pick([255, 257])][mode]
            ops = [arm(500, (start + delta) & M32)]
            for k in range(rng.between(1, 4)):
                ops.append(arm(510 + k, (start + delta + rng.between(0, 3)) & M32))
            ops.extend(probe(rng, delta + 40, 360))
        out.append((f"bound_{i:02d}", trace(start, ops)))
    return out


def order_direct_family(rng, count):
    out = []
    for i in range(count):
        start = rng.between(0, 0x00F00000)
        group = rng.between(2, 9)
        deadline = (start + rng.between(3, 200)) & M32
        ops = [arm(700 + k, deadline) for k in range(group)]
        for k in range(rng.between(0, 3)):
            ops.append(arm(800 + k, (start + rng.between(3, 200)) & M32))
        ops.extend(advance(rng, 400))
        out.append((f"orderdirect_{i:02d}", trace(start, ops)))
    return out


def order_cascade_family(rng, count):
    out = []
    for i in range(count):
        start = rng.between(0, 0x00F00000)
        group = rng.between(2, 9)
        deadline = (start + rng.between(300, 3000)) & M32
        ops = [arm(700 + k, deadline) for k in range(group)]
        ops.extend(advance(rng, 6000))
        out.append((f"ordercascade_{i:02d}", trace(start, ops)))
    return out


def order_mixed_family(rng, count):
    out = []
    for i in range(count):
        start = rng.between(0, 0x00F00000) & ~0xFFF
        deadline = (start + 512 + rng.between(0, 200)) & M32
        early = rng.between(2, 5)
        late = rng.between(2, 5)
        ops = [arm(700 + k, deadline) for k in range(early)]
        ops.append(adv(512 - rng.between(1, 100)))
        ops.extend(arm(900 + k, deadline) for k in range(late))
        ops.extend(advance(rng, 2000))
        out.append((f"ordermixed_{i:02d}", trace(start, ops)))
    return out


def degen_family(rng, count):
    cases = []
    cases.append("S 4096\n")
    cases.append(trace(4096, [adv(1)]))
    cases.append(trace(4096, [adv(65535), adv(65535)]))
    cases.append(trace(4096, [arm(9, 4100), arm(9, 9000), adv(200), adv(6000)]))
    cases.append(trace(4096, [cancel(9), arm(9, 4200), cancel(9), adv(300)]))
    cases.append(trace(4096, [arm(9, 4100), adv(200), cancel(9), adv(200)]))
    cases.append(trace(4096, [arm(0, 4096), arm(65535, 0), adv(300)]))
    cases.append(trace(0, [arm(3, 4294967295), adv(400)]))
    cases.append(
        trace(
            4096,
            [arm(k, 4200) for k in range(1, 40)]
            + [cancel(k) for k in range(1, 40, 2)]
            + advance(rng, 600),
        )
    )
    cap = [arm(k, 20000 + (k % 300)) for k in range(8192)]
    cases.append(trace(4096, cap + advance(rng, 20000)))
    cases.append(trace(4096, cap + [arm(60000, 4200)]))
    cases.append(trace(1, [arm(5, 0), arm(6, 1), arm(7, 2), adv(3), adv(3)]))
    out = []
    for i in range(count):
        out.append((f"degen_{i:02d}", cases[i % len(cases)]))
    return out


def err_family(count):
    cases = [
        "A 1 2\n",
        "S 4096\nS 4097\n",
        "S 4096\nX 1\n",
        "S 4096\nA 1\n",
        "S 4096\nA 1 2 3\n",
        "S 4096\nT 1a\n",
        "S 4096\nT 0\n",
        "S 4096\nA 65536 4100\n",
        "S 4294967296\n",
        "S 4096\nT 65536\n",
        "S 4096\nA 1 4294967296\n",
        "S 4096\nT 5",
        "S 4096\n" + "C 1\n" * 20001,
        "S 4096\n" + "".join(arm(k, 20000) for k in range(8193)),
        "S 4096\n" + "T 65535\n" * 513,
        "S 4096\n" + "A 1 " + "9" * 11 + "\n",
    ]
    out = []
    for i in range(count):
        out.append((f"err_{i:02d}", cases[i % len(cases)]))
    return out


def shift_family(rng, count):
    pairs = count // 2
    out = []
    for i in range(pairs):
        wrapping = i % 2 == 0
        if wrapping:
            base_start = 0
            shift = 0xFF000000
            span = 0x1001000 + rng.between(0, 4000)
        else:
            base_start = 0x00010000
            shift = 0x03000000
            span = rng.between(70000, 130000)
        deadlines = []
        for _ in range(8):
            deadlines.append((base_start + rng.between(1, span - 1)) & M32)
        steps = advance(rng, span)
        base_ops = [arm(200 + k, d) for k, d in enumerate(deadlines)] + steps
        shift_ops = [
            arm(200 + k, (d + shift) & M32) for k, d in enumerate(deadlines)
        ] + steps
        out.append((f"shift_{i:02d}a", trace(base_start, base_ops)))
        out.append((f"shift_{i:02d}b", trace((base_start + shift) & M32, shift_ops)))
    return out


def mixed_family(rng, count):
    out = []
    for i in range(count):
        start = rng.pick(
            [0, 4096, 0x00FFFF00, 0xFFFFFF00, 0x7FFFFF00, rng.between(0, M32) & ~0xFF]
        )
        ops = []
        live = set()
        total = 0
        for _ in range(rng.between(20, 90)):
            choice = rng.below(10)
            if choice < 5:
                ident = rng.between(1, 900)
                deadline = (
                    start
                    + rng.pick(
                        [
                            rng.between(0, 255),
                            rng.between(256, 65535),
                            rng.between(65536, 16777215),
                            16777216 + rng.between(0, 1000),
                            0x80000000 + rng.between(0, 1000),
                        ]
                    )
                ) & M32
                ops.append(arm(ident, deadline))
                live.add(ident)
            elif choice < 7 and live:
                ident = sorted(live)[rng.below(len(live))]
                ops.append(cancel(ident))
                live.discard(ident)
            else:
                n = rng.pick([1, 2, 255, 256, 257, 4096, 65535])
                if total + n > 500000:
                    continue
                total += n
                ops.append(adv(n))
        ops.extend(advance(rng, min(65535 * 4, 500000 - total)))
        out.append((f"mixed_{i:02d}", trace(start, ops)))
    return out


def rearm_family(rng, count):
    """Cancels and arms of the same id interleaved with advances."""
    out = []
    for i in range(count):
        mode = i % 4
        start = rng.between(0, 0x00FF0000)
        ident = rng.between(1, 4000)
        other = (ident + rng.between(1, 400)) & 0xFFFF
        near = (start + rng.between(20, 240)) & M32
        far = (start + rng.between(300, 900)) & M32
        ops = []
        if mode == 0:
            ops += [arm(ident, near), cancel(ident), arm(ident, far)]
        elif mode == 1:
            ops += [arm(ident, near), cancel(ident), adv(rng.between(1, 30))]
            ops += [arm(ident, far)]
        elif mode == 2:
            ops += [cancel(ident), arm(ident, near)]
            ops += [arm(other, far), cancel(other), arm(other, near)]
        else:
            ops += [arm(ident, near), arm(other, near), cancel(ident)]
            ops += [cancel(other), arm(ident, near), arm(other, far)]
        ops.extend(advance(rng, 1200))
        out.append((f"rearm_{i:02d}", trace(start, ops)))
    return out


def visible_set():
    out = []
    out.append(
        ("visible_00", trace(4096, [arm(7, 4106), arm(8, 4106), adv(20), adv(300)]))
    )
    out.append(
        (
            "visible_01",
            trace(
                0, [arm(1, 50), arm(2, 120), arm(3, 200), adv(60), adv(60), adv(120)]
            ),
        )
    )
    out.append(
        ("visible_02", trace(1024, [arm(5, 1100), cancel(5), arm(6, 1150), adv(200)]))
    )
    out.append(
        ("visible_03", trace(2048, [arm(9, 2048), arm(10, 2000), adv(1), adv(10)]))
    )
    out.append(
        (
            "visible_04",
            trace(65280, [arm(11, 65400), arm(12, 66000), adv(200), adv(1000)]),
        )
    )
    out.append(("visible_05", trace(500, [adv(10), adv(10)])))
    out.append(("visible_06", "S 500\nQ 3\n"))
    out.append(
        ("visible_07", trace(300, [arm(k, 400 + k) for k in range(4)] + [adv(200)]))
    )
    return out


def write(directory, prefix, items):
    os.makedirs(directory, exist_ok=True)
    for name, text in items:
        path = os.path.join(directory, f"{prefix}{name}.bin")
        with open(path, "wb") as handle:
            handle.write(text.encode("ascii"))


def main():
    rng = Rng(SEED)
    write(VISIBLE_DIR, "", visible_set())
    hidden = []
    hidden += short_family(rng, 10)
    hidden += wrap_family(rng, 16)
    hidden += bound_family(rng, 16)
    hidden += order_direct_family(rng, 8)
    hidden += order_cascade_family(rng, 8)
    hidden += order_mixed_family(rng, 8)
    hidden += degen_family(rng, 12)
    hidden += err_family(16)
    hidden += shift_family(rng, 16)
    hidden += mixed_family(rng, 16)
    hidden += rearm_family(rng, 16)
    write(HIDDEN_DIR, "hidden_", hidden)
    sys.stdout.write(f"hidden={len(hidden)} visible={len(visible_set())}\n")


if __name__ == "__main__":
    main()
