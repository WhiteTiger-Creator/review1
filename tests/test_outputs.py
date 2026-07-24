from __future__ import annotations

import json
import os
import pwd
import re
import subprocess
import tempfile
import uuid
from pathlib import Path

import pytest

ENV = Path("/app/environment")
BIN = "/tmp/scepd-bin"

DEFAULT_MAX_VALIDITY = 90
DEFAULT_CHALLENGE = "s3cr3t-default"
CA_SUBJECT = "Example SCEP Intermediate CA"

GO_CRASH_SIGNATURES = (
    "panic:",
    "goroutine ",
    "runtime error",
    "fatal error",
    "signal sigsegv",
    "stack overflow",
    "out of memory",
)


def _candidate_sandbox():
    """Extra subprocess kwargs that drop the candidate binary to an unprivileged
    user when the verifier runs as root, so a submitted binary cannot read the
    verifier trees (/tests, /solution, /logs/verifier). A no-op for non-root local
    runs, where those trees are not present."""
    try:
        if os.geteuid() != 0:
            return {}
    except AttributeError:  # non-POSIX
        return {}
    try:
        pw = pwd.getpwnam("nobody")
    except KeyError:
        return {}
    return {"user": pw.pw_uid, "group": pw.pw_gid, "extra_groups": []}


_SANDBOX = _candidate_sandbox()


def run_candidate(cmd, **kwargs):
    """Run the built scepd binary under the unprivileged sandbox (when root)."""
    kwargs.setdefault("text", True)
    return subprocess.run(cmd, **_SANDBOX, **kwargs)


@pytest.fixture(scope="session")
def binary():
    """Build the scepd binary from the agent's on-disk source.

    The build itself runs with the verifier's privileges (it needs the Go cache);
    every invocation of the resulting binary goes through run_candidate, which
    drops it to an unprivileged user.
    """
    build = subprocess.run(
        ["go", "build", "-o", BIN, "./cmd/scepd"],
        cwd=str(ENV),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=300,
    )
    assert build.returncode == 0, f"go build failed:\n{build.stdout}"
    assert os.path.exists(BIN), "scepd binary not produced"
    # World-readable+executable so the unprivileged sandbox user can run it.
    os.chmod(BIN, 0o755)
    return BIN


def run_enroll(binary, relpath, timeout=60):
    """Run scepd enroll against a fixture path relative to the environment root."""
    return run_candidate(
        [binary, "enroll", str(ENV / relpath)],
        cwd=str(ENV),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )


def run_enroll_obj(binary, obj, timeout=60):
    """Run scepd enroll against a request object written to a fresh temp file."""
    fd, path = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w") as fh:
            json.dump(obj, fh)
        # Readable by the unprivileged sandbox user that runs the candidate binary.
        os.chmod(path, 0o644)
        return run_candidate(
            [binary, "enroll", path],
            cwd=str(ENV),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
    finally:
        os.unlink(path)


def _not_after_days(stdout: str) -> int | None:
    m = re.search(r"not_after_days=(\d+)", stdout)
    return int(m.group(1)) if m else None


def assert_clean_rejection(r, name, subsystem_keywords, reason_words):
    """Assert a request was refused by a clean error, not a crash, with a reason."""
    err = (r.stdout + "\n" + r.stderr).lower()
    assert "issued" not in r.stdout.lower(), (
        f"{name}: a certificate was ISSUED but the request must be refused.\n"
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    assert r.returncode != 0, (
        f"{name}: expected a non-zero exit for the refused request.\n"
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    for sig in GO_CRASH_SIGNATURES:
        assert sig not in err, (
            f"{name}: the request was refused via a crash ({sig!r}), not the clean "
            f"returned-error path.\nstderr:\n{r.stderr}"
        )
    assert any(k in err for k in subsystem_keywords), (
        f"{name}: the refusal must name its subsystem "
        f"{subsystem_keywords}.\nstderr:\n{r.stderr}"
    )
    assert any(w in err for w in reason_words), (
        f"{name}: the refusal must name what was wrong "
        f"{reason_words}.\nstderr:\n{r.stderr}"
    )


def test_binary_builds_and_prints_usage(binary):
    """The tree builds a scepd that prints usage and exits 2 with no args."""
    r = run_candidate([binary], capture_output=True, timeout=10)
    assert r.returncode == 2, (
        f"bare scepd should print usage and exit 2; got rc={r.returncode}\n{r.stderr}"
    )
    assert "usage" in r.stderr.lower(), r.stderr


def test_ca_info_reports_provisioner_config(binary):
    """ca-info reports the CA subject and each provisioner's policy."""
    r = run_candidate(
        [binary, "ca-info"], cwd=str(ENV), capture_output=True, timeout=30
    )
    assert r.returncode == 0, f"ca-info failed:\n{r.stderr}"
    out = r.stdout.lower()
    assert "ca.subject" in out and "provisioner.default.max_validity_days" in out, (
        r.stdout
    )


def test_valid_corpus_all_issue(binary):
    """Every well-formed enrollment and renewal fixture is issued a certificate."""
    for i in range(1, 8):
        f = f"testdata/valid/valid_{i:03d}.json"
        r = run_enroll(binary, f)
        assert r.returncode == 0, (
            f"{f} was refused:\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
        )
        assert "ISSUED" in r.stdout, f"{f} produced no certificate:\n{r.stdout}"


def test_valid_sub_max_validity_is_unchanged(binary):
    """A request below the maximum keeps its requested validity."""
    r = run_enroll(binary, "testdata/valid/valid_001.json")
    assert r.returncode == 0, r.stderr
    assert _not_after_days(r.stdout) == 60, (
        f"a 60-day request under the 90-day maximum must be issued "
        f"for 60 days, not re-clamped.\n{r.stdout}"
    )


def test_boundary_at_max_validity_issues(binary):
    """A request exactly at the provisioner maximum is issued at the maximum."""
    r = run_enroll(binary, "testdata/valid/valid_004.json")
    assert r.returncode == 0, r.stderr
    assert _not_after_days(r.stdout) == DEFAULT_MAX_VALIDITY, (
        f"an at-maximum (90-day) request must still be issued at 90 days.\n{r.stdout}"
    )


def test_valid_zero_validity_issues_at_max(binary):
    """An enrollment with unset (zero) validity is issued at the provisioner maximum."""
    r = run_enroll(binary, "testdata/valid/valid_006.json")
    assert r.returncode == 0, (
        f"a zero-validity request must be issued at the maximum, not refused.\n{r.stderr}"
    )
    assert _not_after_days(r.stdout) == DEFAULT_MAX_VALIDITY, (
        f"an unset (zero-day) request must be issued at the provisioner maximum "
        f"({DEFAULT_MAX_VALIDITY}).\n{r.stdout}"
    )


def test_boundary_near_expiry_signer_renewal_issues(binary):
    """A renewal with a CA-issued, barely-valid signer still issues."""
    r = run_enroll(binary, "testdata/valid/valid_005.json")
    assert r.returncode == 0, (
        f"a renewal with a CA-issued, one-day-remaining signer must still be issued.\n"
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    assert "ISSUED" in r.stdout, r.stdout


def test_updatereq_is_not_authorized(binary):
    """An UpdateReq (type 18) enrollment is refused, not issued unauthenticated."""
    r = run_enroll(binary, "testdata/exploits/exploit_01.json")
    assert_clean_rejection(
        r,
        "updatereq",
        subsystem_keywords=(
            "scep/api",
            "api",
            "scep/authority",
            "authority",
            "scep/challenge",
            "challenge",
        ),
        reason_words=(
            "message type",
            "messagetype",
            "authoriz",
            "unauthorized",
            "enroll",
            "not allowed",
            "not permitted",
            "not supported",
            "reject",
            "operation",
            "implement",
        ),
    )


def test_fresh_updatereq_is_not_authorized(binary):
    """A fresh UpdateReq with a random subject is refused (no fixture hardcoding)."""
    nonce = uuid.uuid4().hex[:10]
    obj = {
        "transaction_id": f"txn-{nonce}",
        "message_type": "18",
        "provisioner": "default",
        "challenge": "",
        "subject_common_name": f"device-{nonce}",
        "sans": [f"device-{nonce}.corp.example"],
        "requested_validity_days": 365,
    }
    r = run_enroll_obj(binary, obj)
    assert_clean_rejection(
        r,
        "fresh-updatereq",
        subsystem_keywords=(
            "scep/api",
            "api",
            "scep/authority",
            "authority",
            "scep/challenge",
            "challenge",
        ),
        reason_words=(
            "message type",
            "messagetype",
            "authoriz",
            "unauthorized",
            "enroll",
            "not allowed",
            "not permitted",
            "not supported",
            "reject",
            "operation",
            "implement",
        ),
    )


def test_unknown_message_type_refused_without_crash(binary):
    """A reserved or unknown message type is refused, never a panic."""
    r = run_enroll(binary, "testdata/exploits/exploit_02.json")
    assert_clean_rejection(
        r,
        "unknown-type",
        subsystem_keywords=("scep/authority", "authority"),
        reason_words=("unknown", "message type", "not accepted"),
    )


def test_fresh_unknown_message_type_refused_without_crash(binary):
    """A freshly chosen reserved message type is refused without a panic."""
    nonce = uuid.uuid4().hex[:8]
    reserved = str(40 + (int(nonce, 16) % 50))
    obj = {
        "transaction_id": f"txn-{nonce}",
        "message_type": reserved,
        "provisioner": "default",
        "challenge": "",
        "subject_common_name": f"device-{nonce}",
        "sans": [f"device-{nonce}.corp.example"],
        "requested_validity_days": 60,
    }
    r = run_enroll_obj(binary, obj)
    assert_clean_rejection(
        r,
        "fresh-unknown-type",
        subsystem_keywords=("scep/authority", "authority"),
        reason_words=("unknown", "message type", "not accepted"),
    )


def test_unconfigured_challenge_provisioner_refused(binary):
    """Enrollment against a provisioner with no challenge configured fails closed."""
    r = run_enroll(binary, "testdata/exploits/exploit_03.json")
    assert_clean_rejection(
        r,
        "no-challenge-provisioner",
        subsystem_keywords=("scep/challenge", "challenge"),
        reason_words=("challenge", "refused", "configured"),
    )


def test_renewal_foreign_signer_refused(binary):
    """A renewal signed by a certificate this authority did not issue is refused."""
    r = run_enroll(binary, "testdata/exploits/exploit_04.json")
    assert_clean_rejection(
        r,
        "foreign-signer",
        subsystem_keywords=("scep/renewal", "renewal"),
        reason_words=(
            "signer",
            "issuer",
            "issued",
            "authority",
            "expired",
            "match",
            "genuine",
            "this ca",
        ),
    )


def test_fresh_foreign_signer_refused(binary):
    """A fresh renewal with a random foreign issuer and correct challenge is refused."""
    nonce = uuid.uuid4().hex[:10]
    obj = {
        "transaction_id": f"txn-{nonce}",
        "message_type": "17",
        "provisioner": "default",
        "challenge": DEFAULT_CHALLENGE,
        "subject_common_name": f"device-{nonce}",
        "sans": [f"device-{nonce}.corp.example"],
        "requested_validity_days": 30,
        "signer": {
            "subject_common_name": f"device-{nonce}",
            "issuer_common_name": f"Rogue Root CA {nonce}",
            "not_after_days": 400,
        },
    }
    r = run_enroll_obj(binary, obj)
    assert_clean_rejection(
        r,
        "fresh-foreign-signer",
        subsystem_keywords=("scep/renewal", "renewal"),
        reason_words=(
            "signer",
            "issuer",
            "issued",
            "authority",
            "expired",
            "match",
            "genuine",
            "this ca",
        ),
    )


def test_renewal_expired_ca_signer_refused(binary):
    """A renewal signed by a CA-issued but expired certificate is refused."""
    r = run_enroll(binary, "testdata/exploits/exploit_06.json")
    assert_clean_rejection(
        r,
        "expired-ca-signer",
        subsystem_keywords=("scep/renewal", "renewal"),
        reason_words=("expir", "valid", "not after", "not_after", "past", "signer"),
    )


def test_fresh_expired_ca_signer_refused(binary):
    """A fresh renewal with a CA-issued but expired signer is refused."""
    nonce = uuid.uuid4().hex[:10]
    obj = {
        "transaction_id": f"txn-{nonce}",
        "message_type": "17",
        "provisioner": "default",
        "challenge": DEFAULT_CHALLENGE,
        "subject_common_name": f"device-{nonce}",
        "sans": [f"device-{nonce}.corp.example"],
        "requested_validity_days": 30,
        "signer": {
            "subject_common_name": f"device-{nonce}",
            "issuer_common_name": CA_SUBJECT,
            "not_after_days": -1,
        },
    }
    r = run_enroll_obj(binary, obj)
    assert_clean_rejection(
        r,
        "fresh-expired-ca-signer",
        subsystem_keywords=("scep/renewal", "renewal"),
        reason_words=("expir", "valid", "not after", "not_after", "past", "signer"),
    )


def test_excessive_validity_is_clamped(binary):
    """An excessive-validity enrollment is issued but capped to the maximum."""
    r = run_enroll(binary, "testdata/exploits/exploit_05.json")
    assert r.returncode == 0, (
        f"the request should still be issued (capped), not refused:\n{r.stderr}"
    )
    days = _not_after_days(r.stdout)
    assert days is not None, f"no issued certificate found:\n{r.stdout}"
    assert 0 < days <= DEFAULT_MAX_VALIDITY, (
        f"a 3650-day request must be capped to the maximum "
        f"({DEFAULT_MAX_VALIDITY}); "
        f"got not_after_days={days}."
    )


def test_fresh_excessive_validity_is_clamped(binary):
    """A fresh excessive-validity request is capped to the maximum."""
    nonce = uuid.uuid4().hex[:10]
    obj = {
        "transaction_id": f"txn-{nonce}",
        "message_type": "19",
        "provisioner": "default",
        "challenge": DEFAULT_CHALLENGE,
        "subject_common_name": f"device-{nonce}",
        "sans": [f"device-{nonce}.corp.example"],
        "requested_validity_days": 9999,
    }
    r = run_enroll_obj(binary, obj)
    assert r.returncode == 0, (
        f"the request should still be issued (capped), not refused:\n{r.stderr}"
    )
    days = _not_after_days(r.stdout)
    assert days is not None and 0 < days <= DEFAULT_MAX_VALIDITY, (
        f"excessive validity must be capped to {DEFAULT_MAX_VALIDITY}; got {days}."
    )


def test_security_notes_covers_all_themes():
    """security_notes.md exists and records the audit the brief asks for.

    The brief keeps the write-up deliberately light, so this verifies only the
    parts it names explicitly -- a non-trivial summary, the CWE classes, and the
    step-ca / Apache attribution -- rather than a fixed vocabulary of weakness
    names the concise instruction no longer dictates.
    """
    notes = ENV / "security_notes.md"
    assert notes.exists(), (
        "security_notes.md was not written to /app/environment (required)."
    )
    body = notes.read_text().lower()
    assert len(body.split()) >= 20, (
        "security_notes.md should be a short write-up of the audit, not a stub."
    )
    for kw in ("cwe-287", "cwe-295", "apache", "step-ca"):
        assert kw in body, f"security_notes.md missing required keyword '{kw}'"


def test_certrep_response_type_refused(binary):
    """CertRep (type 3) is a response type; submitted as a request it is refused, not a crash."""
    r = run_enroll(binary, "testdata/exploits/exploit_09.json")
    assert_clean_rejection(
        r,
        "certrep-response-type",
        subsystem_keywords=("scep/api", "api", "scep/authority", "authority"),
        reason_words=(
            "response",
            "message type",
            "request",
            "enroll",
            "not accepted",
            "operation",
            "implement",
        ),
    )


def test_fresh_certrep_response_type_refused(binary):
    """A fresh CertRep (type 3) request is refused cleanly, never a panic."""
    nonce = uuid.uuid4().hex[:10]
    obj = {
        "transaction_id": f"txn-{nonce}",
        "message_type": "3",
        "provisioner": "default",
        "challenge": DEFAULT_CHALLENGE,
        "subject_common_name": f"device-{nonce}",
        "sans": [f"device-{nonce}.corp.example"],
        "requested_validity_days": 60,
    }
    r = run_enroll_obj(binary, obj)
    assert_clean_rejection(
        r,
        "fresh-certrep-response-type",
        subsystem_keywords=("scep/api", "api", "scep/authority", "authority"),
        reason_words=(
            "response",
            "message type",
            "request",
            "enroll",
            "not accepted",
            "operation",
            "implement",
        ),
    )


def test_reserved_operation_types_refused(binary):
    """Every known non-enrollment operation type is refused cleanly, never issued."""
    for mt in ("20", "21", "22"):
        nonce = uuid.uuid4().hex[:8]
        obj = {
            "transaction_id": f"txn-{nonce}",
            "message_type": mt,
            "provisioner": "default",
            "challenge": DEFAULT_CHALLENGE,
            "subject_common_name": f"device-{nonce}",
            "sans": [f"device-{nonce}.corp.example"],
            "requested_validity_days": 60,
        }
        r = run_enroll_obj(binary, obj)
        assert_clean_rejection(
            r,
            f"reserved-operation-{mt}",
            subsystem_keywords=("scep/authority", "authority"),
            reason_words=(
                "operation",
                "implement",
                "message type",
                "not accepted",
                "unknown",
            ),
        )


def test_forged_ca_name_signer_refused(binary):
    """A signer bearing the CA's own name but no valid authority signature is refused."""
    r = run_enroll(binary, "testdata/exploits/exploit_07.json")
    assert_clean_rejection(
        r,
        "forged-ca-name-signer",
        subsystem_keywords=("scep/renewal", "renewal"),
        reason_words=(
            "signer",
            "signature",
            "issued",
            "authority",
            "genuine",
            "valid",
            "match",
        ),
    )


def test_fresh_forged_ca_name_signer_refused(binary):
    """A fresh signer with the CA's name and a live expiry but an invalid signature is refused."""
    nonce = uuid.uuid4().hex[:10]
    cn = f"device-{nonce}"
    obj = {
        "transaction_id": f"txn-{nonce}",
        "message_type": "17",
        "provisioner": "default",
        "challenge": DEFAULT_CHALLENGE,
        "subject_common_name": cn,
        "sans": [f"{cn}.corp.example"],
        "requested_validity_days": 30,
        "signer": {
            "subject_common_name": cn,
            "issuer_common_name": CA_SUBJECT,
            "not_after_days": 200,
            "signature": "0" * 64,
        },
    }
    r = run_enroll_obj(binary, obj)
    assert_clean_rejection(
        r,
        "fresh-forged-ca-name-signer",
        subsystem_keywords=("scep/renewal", "renewal"),
        reason_words=(
            "signer",
            "signature",
            "issued",
            "authority",
            "genuine",
            "valid",
            "match",
        ),
    )


def test_renewal_signer_subject_not_bound_refused(binary):
    """A genuine CA-issued signer replayed to renew a different subject is refused."""
    r = run_enroll(binary, "testdata/exploits/exploit_08.json")
    assert_clean_rejection(
        r,
        "signer-subject-mismatch",
        subsystem_keywords=("scep/renewal", "renewal"),
        reason_words=("subject", "match", "signer", "bound", "belong", "different"),
    )


def test_fresh_signer_subject_not_bound_refused(binary):
    """A valid fixture signer reused to renew a different subject is refused."""
    src = json.loads((ENV / "testdata/valid/valid_003.json").read_text())
    nonce = uuid.uuid4().hex[:10]
    other = f"device-{nonce}"
    obj = {
        "transaction_id": f"txn-{nonce}",
        "message_type": "17",
        "provisioner": "default",
        "challenge": DEFAULT_CHALLENGE,
        "subject_common_name": other,
        "sans": [f"{other}.corp.example"],
        "requested_validity_days": 30,
        "signer": src["signer"],
    }
    r = run_enroll_obj(binary, obj)
    assert_clean_rejection(
        r,
        "fresh-signer-subject-mismatch",
        subsystem_keywords=("scep/renewal", "renewal"),
        reason_words=("subject", "match", "signer", "bound", "belong", "different"),
    )


def test_fresh_unconfigured_challenge_provisioner_refused(binary):
    """Any provisioner with no challenge configured fails closed, not only the bundled one."""
    nonce = uuid.uuid4().hex[:10]
    cn = f"device-{nonce}"
    obj = {
        "transaction_id": f"txn-{nonce}",
        "message_type": "19",
        "provisioner": "legacy",
        "challenge": "",
        "subject_common_name": cn,
        "sans": [f"{cn}.corp.example"],
        "requested_validity_days": 30,
    }
    r = run_enroll_obj(binary, obj)
    assert_clean_rejection(
        r,
        "fresh-unconfigured-challenge",
        subsystem_keywords=("scep/challenge", "challenge"),
        reason_words=("challenge", "refused", "configured"),
    )


def test_fresh_unconfigured_challenge_uncovered_provisioner_refused(binary):
    """Fail-closed applies to every challenge-less provisioner, not only the ones the
    exploit corpus happens to exercise: a provisioner whose ca-info reports
    challenge_configured=false must refuse enrollment even when no sample covers it."""
    nonce = uuid.uuid4().hex[:10]
    cn = f"device-{nonce}"
    obj = {
        "transaction_id": f"txn-{nonce}",
        "message_type": "19",
        "provisioner": "sensor",
        "challenge": "",
        "subject_common_name": cn,
        "sans": [f"{cn}.example"],
        "requested_validity_days": 20,
    }
    r = run_enroll_obj(binary, obj)
    assert_clean_rejection(
        r,
        "uncovered-unconfigured-challenge",
        subsystem_keywords=("scep/challenge", "challenge"),
        reason_words=("challenge", "refused", "configured"),
    )


def test_unconfigured_challenge_ignores_presented_secret_refused(binary):
    """A provisioner with no challenge configured cannot be satisfied by presenting
    any password: enrollment fails closed regardless of the presented value, so a
    non-empty presented challenge against such a provisioner is still refused."""
    nonce = uuid.uuid4().hex[:10]
    cn = f"device-{nonce}"
    obj = {
        "transaction_id": f"txn-{nonce}",
        "message_type": "19",
        "provisioner": "gateway",
        "challenge": f"guessed-secret-{nonce}",
        "subject_common_name": cn,
        "sans": [f"{cn}.example"],
        "requested_validity_days": 20,
    }
    r = run_enroll_obj(binary, obj)
    assert_clean_rejection(
        r,
        "nonempty-presented-unconfigured-challenge",
        subsystem_keywords=("scep/challenge", "challenge"),
        reason_words=("challenge", "refused", "configured"),
    )


def test_unconfigured_challenge_on_renewal_refused(binary):
    """The challenge gate applies to renewals too: a renewal against a challenge-less
    provisioner fails closed even when it carries a genuine CA-issued signer, so the
    refusal comes from the challenge check rather than the renewal-signer check."""
    src = json.loads((ENV / "testdata/valid/valid_003.json").read_text())
    nonce = uuid.uuid4().hex[:10]
    obj = {
        "transaction_id": f"txn-{nonce}",
        "message_type": "17",
        "provisioner": "sensor",
        "challenge": "",
        "subject_common_name": src["subject_common_name"],
        "sans": [f"{src['subject_common_name']}.example"],
        "requested_validity_days": 20,
        "signer": src["signer"],
    }
    r = run_enroll_obj(binary, obj)
    assert_clean_rejection(
        r,
        "unconfigured-challenge-renewal",
        subsystem_keywords=("scep/challenge", "challenge"),
        reason_words=("challenge", "refused", "configured"),
    )


NAME_CONSTRAINT_REASONS = (
    "name",
    "excluded",
    "permitted",
    "constraint",
    "wildcard",
    "space",
)


def test_valid_wildcard_san_issues(binary):
    """A wildcard SAN that stays inside the permitted space and clear of every
    excluded subtree is still issued."""
    r = run_enroll(binary, "testdata/valid/valid_007.json")
    assert r.returncode == 0, (
        f"an in-bounds wildcard SAN must still be issued, not refused.\n"
        f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    assert "ISSUED" in r.stdout, r.stdout


def test_wildcard_san_into_excluded_refused(binary):
    """A wildcard SAN whose certified hosts reach an excluded subtree is refused,
    even though its parent domain is permitted."""
    r = run_enroll(binary, "testdata/exploits/exploit_10.json")
    assert_clean_rejection(
        r,
        "wildcard-into-excluded",
        subsystem_keywords=("scep/authority", "authority"),
        reason_words=NAME_CONSTRAINT_REASONS,
    )


def test_fresh_wildcard_san_into_excluded_refused(binary):
    """A freshly built wildcard SAN that expands into the excluded subtree is
    refused (no fixture-name hardcoding)."""
    nonce = uuid.uuid4().hex[:10]
    obj = {
        "transaction_id": f"txn-{nonce}",
        "message_type": "19",
        "provisioner": "default",
        "challenge": DEFAULT_CHALLENGE,
        "subject_common_name": f"device-{nonce}",
        "sans": ["*.corp.example"],
        "requested_validity_days": 30,
    }
    r = run_enroll_obj(binary, obj)
    assert_clean_rejection(
        r,
        "fresh-wildcard-into-excluded",
        subsystem_keywords=("scep/authority", "authority"),
        reason_words=NAME_CONSTRAINT_REASONS,
    )


def test_concrete_excluded_san_refused(binary):
    """A concrete SAN inside an excluded subtree is refused."""
    r = run_enroll(binary, "testdata/exploits/exploit_11.json")
    assert_clean_rejection(
        r,
        "concrete-excluded",
        subsystem_keywords=("scep/authority", "authority"),
        reason_words=NAME_CONSTRAINT_REASONS,
    )


def test_fresh_concrete_excluded_san_refused(binary):
    """A freshly built concrete SAN inside the excluded subtree is refused."""
    nonce = uuid.uuid4().hex[:10]
    obj = {
        "transaction_id": f"txn-{nonce}",
        "message_type": "19",
        "provisioner": "default",
        "challenge": DEFAULT_CHALLENGE,
        "subject_common_name": f"device-{nonce}",
        "sans": [f"host-{nonce}.internal.corp.example"],
        "requested_validity_days": 30,
    }
    r = run_enroll_obj(binary, obj)
    assert_clean_rejection(
        r,
        "fresh-concrete-excluded",
        subsystem_keywords=("scep/authority", "authority"),
        reason_words=NAME_CONSTRAINT_REASONS,
    )


def test_plain_san_outside_permitted_refused(binary):
    """A plain (non-wildcard) SAN outside the permitted subtree is refused: the
    permitted name space is an upper bound, not only the excluded set."""
    nonce = uuid.uuid4().hex[:10]
    obj = {
        "transaction_id": f"txn-{nonce}",
        "message_type": "19",
        "provisioner": "default",
        "challenge": DEFAULT_CHALLENGE,
        "subject_common_name": f"device-{nonce}",
        "sans": [f"printer-{nonce}.vendor.example"],
        "requested_validity_days": 30,
    }
    r = run_enroll_obj(binary, obj)
    assert_clean_rejection(
        r,
        "plain-outside-permitted",
        subsystem_keywords=("scep/authority", "authority"),
        reason_words=NAME_CONSTRAINT_REASONS,
    )


def test_label_boundary_sibling_issues(binary):
    """A concrete SAN under a sibling subtree that merely shares a suffix with an
    excluded subtree (notinternal.corp.example vs the excluded internal.corp.example)
    stays in bounds and must still be issued: matching is on whole DNS labels, not a
    bare suffix, so the sibling is not mistaken for the excluded subtree."""
    nonce = uuid.uuid4().hex[:10]
    obj = {
        "transaction_id": f"txn-{nonce}",
        "message_type": "19",
        "provisioner": "default",
        "challenge": DEFAULT_CHALLENGE,
        "subject_common_name": f"device-{nonce}",
        "sans": [f"host-{nonce}.notinternal.corp.example"],
        "requested_validity_days": 30,
    }
    r = run_enroll_obj(binary, obj)
    assert r.returncode == 0, (
        f"a whole-label sibling of the excluded subtree must still be issued, not "
        f"refused by a bare-suffix match.\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}"
    )
    assert "ISSUED" in r.stdout, r.stdout
