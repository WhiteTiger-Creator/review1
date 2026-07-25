import os
import re
import shutil
import subprocess
import sys
import tempfile

import pytest

APP = "/app"
SRC = os.path.join(APP, "src")
REF_DIR = os.path.join(os.path.dirname(__file__), "reference")
sys.path.insert(0, REF_DIR)

import battery as B
import reference as R


def _all_src_text():
    chunks = []
    for root, _dirs, files in os.walk(SRC):
        for fname in sorted(files):
            if fname.endswith(".go"):
                path = os.path.join(root, fname)
                with open(path, encoding="utf-8", errors="replace") as handle:
                    chunks.append(handle.read())
    return "\n".join(chunks)


@pytest.fixture(scope="session")
def binary():
    """Build the agent's Go source fresh into a temp directory and return the
    resulting binary path. Building fresh (rather than trusting whatever
    /app/posixmatch already contains) guarantees the test exercises whatever
    is currently in /app/src."""
    assert os.path.isdir(SRC), "/app/src is missing"
    workdir = tempfile.mkdtemp(prefix="posixmatch_build_")
    binpath = os.path.join(workdir, "posixmatch")
    env = dict(os.environ)
    env["GOFLAGS"] = "-mod=mod"
    env["GOTOOLCHAIN"] = "local"
    env["CGO_ENABLED"] = "0"
    proc = subprocess.run(
        ["go", "build", "-o", binpath, "./src"],
        cwd=APP,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, "go build failed:\n" + proc.stdout + proc.stderr
    assert os.path.isfile(binpath), "binary not produced"
    yield binpath
    shutil.rmtree(workdir, ignore_errors=True)


def run_binary(binary, pattern, subject, timeout=5):
    proc = subprocess.run(
        [binary, pattern, subject],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return proc.stdout.strip(), proc.returncode


def test_no_forbidden_regex_library():
    """The engine must be written from scratch: no regexp package, and no
    cgo call into a C regex implementation (regcomp/regexec)."""
    combined = _all_src_text()
    assert not re.search(r'"regexp"', combined), (
        "forbidden import of the standard library regexp package"
    )
    assert "regexp." not in combined, "forbidden use of the regexp package"
    assert 'import "C"' not in combined, "forbidden cgo usage"
    assert "regcomp" not in combined, (
        "forbidden call into a C regular-expression library"
    )
    assert "regexec" not in combined, (
        "forbidden call into a C regular-expression library"
    )


def test_build_smoke(binary):
    """The build must produce a binary that runs and prints the documented
    format for a simple case."""
    out, rc = run_binary(binary, "a", "abc")
    assert rc == 0
    assert out == "MATCH 0 1"


@pytest.mark.parametrize(
    "case", B.HAND_CASES, ids=[f"hand{i}" for i in range(len(B.HAND_CASES))]
)
def test_hand_case(binary, case):
    pattern, subject = case
    expected = R.format_cli(pattern, subject)
    out, rc = run_binary(binary, pattern, subject)
    assert out == expected, f"pattern={pattern!r} subject={subject!r}"
    if expected == "PARSE_ERROR":
        assert rc == 1
    else:
        assert rc == 0


@pytest.mark.parametrize(
    "case", B.RANDOM_CASES, ids=[f"rand{i}" for i in range(len(B.RANDOM_CASES))]
)
def test_random_case(binary, case):
    pattern, subject = case
    expected = R.format_cli(pattern, subject)
    out, rc = run_binary(binary, pattern, subject)
    assert out == expected, f"pattern={pattern!r} subject={subject!r}"
    if expected == "PARSE_ERROR":
        assert rc == 1
    else:
        assert rc == 0


@pytest.mark.parametrize(
    "pattern",
    ["a**", "a*{2,3}", "a+?", "b?*", "(a", "a)", "[abc"],
)
def test_reject_undefined_or_malformed_patterns(binary, pattern):
    """Stacked duplication symbols (undefined by POSIX ERE) and structurally
    malformed patterns must both be reported as PARSE_ERROR, matching the
    reference parser."""
    expected = R.format_cli(pattern, "aaa")
    assert expected == "PARSE_ERROR", (
        f"reference did not reject {pattern!r} as expected"
    )
    out, rc = run_binary(binary, pattern, "aaa")
    assert out == "PARSE_ERROR", f"pattern={pattern!r} got {out!r}"
    assert rc == 1
