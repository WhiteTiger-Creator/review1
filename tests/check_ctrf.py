#!/usr/bin/env python3
"""Gate the reward on a genuine, complete CTRF pass report.

test.sh writes reward 1 only when this script exits 0. That requires the CTRF
report produced by the real pytest run to show every collected test passed, with
none failed, skipped, pending, or other, and every security-critical test present
and passed. A stub that merely fakes pytest's exit code -- for example a planted
pytest.py that returns success without running the suite -- cannot satisfy this,
so faking the run can no longer earn the reward.
"""

from __future__ import annotations

import json
import sys

# Floor on the number of collected tests. The suite has 37 tests; requiring at
# least this many rejects a truncated or empty run while tolerating future
# additions.
REQUIRED_MIN_TESTS = 37

# A representative slice of the security-critical behaviors. Every one of these
# must appear in the report with status "passed"; a fabricated minimal report
# would have to reproduce all of them truthfully.
REQUIRED_TESTS = {
    "test_valid_corpus_all_issue",
    "test_updatereq_is_not_authorized",
    "test_unknown_message_type_refused_without_crash",
    "test_unconfigured_challenge_provisioner_refused",
    "test_fresh_unconfigured_challenge_uncovered_provisioner_refused",
    "test_unconfigured_challenge_ignores_presented_secret_refused",
    "test_unconfigured_challenge_on_renewal_refused",
    "test_renewal_foreign_signer_refused",
    "test_forged_ca_name_signer_refused",
    "test_renewal_signer_subject_not_bound_refused",
    "test_excessive_validity_is_clamped",
    "test_wildcard_san_into_excluded_refused",
    "test_concrete_excluded_san_refused",
    "test_plain_san_outside_permitted_refused",
    "test_security_notes_covers_all_themes",
}


def fail(msg: str) -> None:
    print(f"check_ctrf: {msg}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    if len(sys.argv) != 2:
        fail("usage: check_ctrf.py <ctrf.json>")
    path = sys.argv[1]
    try:
        with open(path) as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as exc:
        fail(f"could not read a valid CTRF report at {path}: {exc}")

    results = doc.get("results") if isinstance(doc, dict) else None
    if not isinstance(results, dict):
        fail("CTRF report has no results object")
    tool = results.get("tool") or {}
    if tool.get("name") != "pytest":
        fail(f"CTRF report was not produced by pytest (tool={tool!r})")

    summary = results.get("summary") or {}
    tests = results.get("tests")
    if not isinstance(tests, list):
        fail("CTRF report has no tests array")

    for key in ("failed", "skipped", "pending", "other"):
        if summary.get(key, 0) != 0:
            fail(f"CTRF summary reports {summary.get(key)} {key}; expected 0")

    total = summary.get("tests")
    passed = summary.get("passed")
    if not isinstance(total, int) or total < REQUIRED_MIN_TESTS:
        fail(f"CTRF ran {total} tests; expected at least {REQUIRED_MIN_TESTS}")
    if passed != total:
        fail(f"CTRF passed {passed} of {total} tests; all must pass")
    if len(tests) != total:
        fail(f"CTRF tests array has {len(tests)} entries; summary says {total}")

    passed_names = set()
    for t in tests:
        if not isinstance(t, dict):
            fail("CTRF tests array contains a non-object entry")
        if t.get("status") != "passed":
            fail(
                f"CTRF test {t.get('name')!r} status is {t.get('status')!r}; must be passed"
            )
        passed_names.add((t.get("name") or "").rsplit("::", 1)[-1])

    missing = sorted(n for n in REQUIRED_TESTS if n not in passed_names)
    if missing:
        fail(f"CTRF report is missing required passed tests: {missing}")

    print(f"check_ctrf: genuine pass report verified ({passed}/{total} tests)")


if __name__ == "__main__":
    main()
