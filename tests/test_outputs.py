"""Behavioral tests for rotctl's rotation-log repair logic."""
import random
import subprocess
import time

AGENT_BIN = "/app/target/release/rotctl"
CHECKER_BIN = "/tmp/reference_check"


def _format_batch(windows):
    """Render a list of (n, m, tags) windows into rotctl's batch format."""
    lines = [str(len(windows))]
    for n, m, tags in windows:
        lines.append(f"{n} {m}")
        lines.append(" ".join(str(t) for t in tags))
    return "\n".join(lines) + "\n"


def _run_agent(windows, timeout=60):
    """Run `rotctl repair` on a batch and parse (count, corrected) per window."""
    proc = subprocess.run(
        [AGENT_BIN, "repair"],
        input=_format_batch(windows),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    assert proc.returncode == 0, (
        f"rotctl repair exited {proc.returncode}, stderr: {proc.stderr}"
    )
    out_lines = proc.stdout.split("\n")
    results = []
    idx = 0
    for _ in windows:
        count = int(out_lines[idx])
        corrected = [int(x) for x in out_lines[idx + 1].split()]
        results.append((count, corrected))
        idx += 2
    return results


def _run_checker(windows, timeout=60):
    """Run the independent ground-truth checker and return one count per window."""
    proc = subprocess.run(
        [CHECKER_BIN],
        input=_format_batch(windows),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    assert proc.returncode == 0, f"reference checker crashed: {proc.stderr}"
    lines = [line for line in proc.stdout.split("\n") if line.strip() != ""]
    return [int(x) for x in lines]


def _true_count(n, m, tags):
    """Ground-truth minimum correction count for a single window."""
    return _run_checker([(n, m, tags)])[0]


def _is_producible(n, m, tags):
    """Whether a tag array is itself reachable by some legitimate rotate history."""
    return _true_count(n, m, tags) == 0


def _assert_valid_repair(n, m, tags, count, corrected):
    """Shared checks: range, diff count, and producibility of one repaired window."""
    assert len(corrected) == n, f"expected {n} tags back, got {len(corrected)}"
    assert all(1 <= v <= m for v in corrected), f"tag out of [1,{m}]: {corrected}"
    diff = sum(1 for x, y in zip(tags, corrected) if x != y)
    assert diff == count, f"claimed {count} corrections but arrays differ in {diff}"
    assert _is_producible(n, m, corrected), (
        f"corrected window is not itself producible: n={n} m={m} corrected={corrected}"
    )


def test_repair_matches_known_answers():
    """Fixed (n, m, tags) -> minimum-correction-count pairs with independently
    known answers are reproduced exactly, and the returned array is producible."""
    cases = [
        (5, 3, [1, 2, 3, 2, 3], 0),
        (4, 3, [1, 2, 2, 3], 1),
        (5, 3, [2, 1, 2, 3, 2], 2),
        (5, 3, [2, 2, 2, 2, 2], 3),
        (5, 4, [1, 1, 3, 4, 1], 2),
        (6, 3, [1, 1, 1, 2, 1, 1], 2),
        (8, 5, [1, 2, 1, 2, 3, 4, 5, 1], 1),
        (5, 3, [2, 3, 1, 1, 2], 4),
        (8, 4, [1, 2, 3, 2, 3, 2, 3, 4], 2),
        (4, 4, [4, 3, 2, 1], 4),
        (5, 1, [1, 1, 1, 1, 1], 0),
        (7, 3, [3, 3, 3, 2, 1, 1, 1], 4),
        (10, 3, [1, 2, 3, 1, 2, 2, 3, 1, 2, 3], 1),
        (7, 3, [1, 3, 2, 3, 2, 1, 2], 3),
        (10, 4, [1, 4, 3, 3, 2, 3, 4, 4, 2, 2], 4),
    ]
    windows = [(n, m, tags) for n, m, tags, _ in cases]
    results = _run_agent(windows)
    for (n, m, tags, expected), (count, corrected) in zip(cases, results):
        assert count == expected, f"n={n} m={m} tags={tags}: got {count}, expected {expected}"
        _assert_valid_repair(n, m, tags, count, corrected)


def test_repair_already_producible_window_is_untouched():
    """A window that's already producible reports zero corrections and hands
    back the same array, not merely an equally-valid rewrite."""
    n, m, tags = 5, 3, [1, 2, 3, 2, 3]
    (count, corrected) = _run_agent([(n, m, tags)])[0]
    assert count == 0
    assert corrected == tags
    _assert_valid_repair(n, m, tags, count, corrected)


def test_repair_batch_size_one_is_always_producible():
    """With a batch size of 1, a rotate command can only ever write the tag
    1, and the input contract already guarantees every recorded tag is in
    [1, m] — so an m=1 window is necessarily already all ones and needs no
    correction. This is the degenerate boundary of the batch-size range."""
    n, m = 20, 1
    tags = [1] * n
    (count, corrected) = _run_agent([(n, m, tags)])[0]
    assert count == 0
    assert corrected == tags
    _assert_valid_repair(n, m, tags, count, corrected)


def test_repair_boundary_window_matches_batch_size():
    """When the window is exactly one batch (n == m), only a single rotate
    placement exists, so the array must already be the identity pattern."""
    n = m = 12
    scrambled = list(range(2, n + 1)) + [1]  # a cyclic shift of 1..n
    (count, corrected) = _run_agent([(n, m, scrambled)])[0]
    _assert_valid_repair(n, m, scrambled, count, corrected)
    assert count == _true_count(n, m, scrambled)


def test_repair_adversarial_patterns():
    """Hand-built patterns designed to break naive greedy or off-by-one
    approaches: strictly descending tags, a repeating cyclic pattern, and a
    window with several equally cheap ways to reach the minimum."""
    windows = [
        (12, 4, [4, 3, 2, 1, 4, 3, 2, 1, 4, 3, 2, 1]),
        (15, 5, [3, 4, 5, 1, 2, 3, 4, 5, 1, 2, 3, 4, 5, 1, 2]),
        (9, 3, [1, 2, 2, 1, 2, 3, 3, 2, 1]),
        (11, 4, [2, 3, 4, 1, 2, 3, 4, 4, 3, 2, 1]),
        (6, 6, [6, 5, 4, 3, 2, 2]),
    ]
    results = _run_agent(windows)
    for (n, m, tags), (count, corrected) in zip(windows, results):
        expected = _true_count(n, m, tags)
        assert count == expected, f"n={n} m={m} tags={tags}: got {count}, expected {expected}"
        _assert_valid_repair(n, m, tags, count, corrected)


def test_repair_random_fuzz_against_reference():
    """A batch of 250 varied small-to-medium random windows, cross-checked
    against the independent reference for both the correction count and the
    producibility of the returned array."""
    rng = random.Random(2024)
    windows = []
    for _ in range(250):
        n = rng.randint(1, 60)
        m = rng.randint(1, n)
        tags = [rng.randint(1, m) for _ in range(n)]
        windows.append((n, m, tags))

    agent_results = _run_agent(windows)
    checker_counts = _run_checker(windows)

    for (n, m, tags), (count, corrected), expected in zip(
        windows, agent_results, checker_counts
    ):
        assert count == expected, f"n={n} m={m} tags={tags}: got {count}, expected {expected}"
        _assert_valid_repair(n, m, tags, count, corrected)


def test_repair_large_single_window_within_time_budget():
    """A single 500000-slot window (the maximum a report can contain) is
    repaired well inside the reward timeout, ruling out anything quadratic
    in n or scaling with the batch size m."""
    n = 500_000
    rng = random.Random(7)
    for m in (1, n // 2, n):
        tags = [rng.randint(1, m) for _ in range(n)]
        start = time.monotonic()
        (count, corrected) = _run_agent([(n, m, tags)], timeout=45)[0]
        elapsed = time.monotonic() - start
        assert elapsed < 30, f"n={n} m={m} took {elapsed:.1f}s, too slow"
        _assert_valid_repair(n, m, tags, count, corrected)


def test_repair_many_small_windows_within_time_budget():
    """A report bundling 10000 small windows (the maximum window count) is
    handled without per-window overhead blowing the time budget."""
    rng = random.Random(13)
    windows = []
    total = 0
    while len(windows) < 9_950 and total < 500_000:
        n = rng.randint(1, 60)
        if total + n > 500_000:
            break
        m = rng.randint(1, n)
        tags = [rng.randint(1, m) for _ in range(n)]
        windows.append((n, m, tags))
        total += n

    start = time.monotonic()
    agent_results = _run_agent(windows, timeout=60)
    elapsed = time.monotonic() - start
    assert elapsed < 45, f"{len(windows)} windows totaling {total} slots took {elapsed:.1f}s"

    checker_counts = _run_checker(windows, timeout=60)
    for (n, m, tags), (count, corrected), expected in zip(
        windows, agent_results, checker_counts
    ):
        assert count == expected, f"n={n} m={m}: got {count}, expected {expected}"
        _assert_valid_repair(n, m, tags, count, corrected)


def test_repair_single_slot_windows():
    """n = m = 1 windows: the only possible tag is 1, so a recorded 1 needs no
    correction and anything else needs exactly one."""
    (count_a, corrected_a) = _run_agent([(1, 1, [1])])[0]
    assert (count_a, corrected_a) == (0, [1])
