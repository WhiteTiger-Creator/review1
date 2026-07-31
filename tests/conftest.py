import json
from pathlib import Path

_REPORTS = []


def pytest_addoption(parser):
    parser.addoption("--ctrf", action="store", default=None)


def pytest_runtest_logreport(report):
    if report.when != "call":
        return
    status = "passed"
    if report.failed:
        status = "failed"
    elif report.skipped:
        status = "skipped"
    _REPORTS.append(
        {
            "name": report.nodeid,
            "status": status,
            "duration": round(report.duration * 1000, 3),
            "message": "" if report.passed else str(report.longrepr),
        }
    )


def pytest_sessionfinish(session, exitstatus):
    path = session.config.getoption("--ctrf")
    if not path:
        return
    tests = len(_REPORTS)
    failed = sum(1 for report in _REPORTS if report["status"] == "failed")
    skipped = sum(1 for report in _REPORTS if report["status"] == "skipped")
    passed = tests - failed - skipped
    payload = {
        "results": {
            "tool": {"name": "pytest"},
            "summary": {
                "tests": tests,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
            },
            "tests": _REPORTS,
        }
    }
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
