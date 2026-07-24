#!/usr/bin/env python3
# Oracle ground-truth generator: regenerates the enrollment/exploit fixtures under
# environment/testdata. It duplicates the CA signer key and mirrors the fixed
# behavior, so it is kept under solution/ (out of the agent's environment), not in
# the task environment. It is a development-time tool and is not run by the oracle
# or the verifier.
from __future__ import annotations

import hashlib
import hmac
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "environment" / "testdata"
VALID = OUT / "valid"
ADVERSARIAL = OUT / "exploits"

CA_SUBJECT = "Example SCEP Intermediate CA"
# Must match CA.signerKey in internal/scep/caidentity.go.
CA_SIGNER_KEY = b"enrollward-ca-signer-key-2026"


def signer_fingerprint(subject: str, issuer: str, not_after: int) -> str:
    """Mirror of CA.SignerFingerprint in caidentity.go."""
    canonical = f"{subject}\n{issuer}\n{not_after}".encode()
    return hmac.new(CA_SIGNER_KEY, canonical, hashlib.sha256).hexdigest()


def write(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n")
    print(f"wrote {path.relative_to(OUT.parent.parent)}")


def pkcs_req(txn, provisioner, challenge, cn, validity, sans=None):
    return {
        "transaction_id": txn,
        "message_type": "19",
        "provisioner": provisioner,
        "challenge": challenge,
        "subject_common_name": cn,
        "sans": sans or [f"{cn}.corp.example"],
        "requested_validity_days": validity,
    }


def renewal_req(
    txn,
    provisioner,
    challenge,
    cn,
    validity,
    signer_issuer,
    signer_not_after,
    signer_subject=None,
    signature=None,
):
    signer_subject = cn if signer_subject is None else signer_subject
    if signature is None:
        signature = signer_fingerprint(signer_subject, signer_issuer, signer_not_after)
    return {
        "transaction_id": txn,
        "message_type": "17",
        "provisioner": provisioner,
        "challenge": challenge,
        "subject_common_name": cn,
        "sans": [f"{cn}.corp.example"],
        "requested_validity_days": validity,
        "signer": {
            "subject_common_name": signer_subject,
            "issuer_common_name": signer_issuer,
            "not_after_days": signer_not_after,
            "signature": signature,
        },
    }


def main() -> None:
    write(
        VALID / "valid_001.json",
        pkcs_req("txn-1001", "default", "s3cr3t-default", "device-0001", 60),
    )
    write(
        VALID / "valid_002.json",
        pkcs_req("txn-1002", "iot", "iot-enroll-2026", "sensor-22", 30),
    )
    write(
        VALID / "valid_003.json",
        renewal_req(
            "txn-1003", "default", "s3cr3t-default", "device-0002", 45, CA_SUBJECT, 20
        ),
    )
    write(
        VALID / "valid_004.json",
        pkcs_req("txn-1004", "default", "s3cr3t-default", "device-0003", 90),
    )
    write(
        VALID / "valid_005.json",
        renewal_req(
            "txn-1005", "iot", "iot-enroll-2026", "sensor-9", 30, CA_SUBJECT, 1
        ),
    )
    write(
        VALID / "valid_006.json",
        pkcs_req("txn-1006", "default", "s3cr3t-default", "device-0004", 0),
    )
    # Wildcard SAN that stays inside the permitted space and clear of the
    # excluded subtree: every host it certifies (*.devices.corp.example) is
    # permitted, so it must still be issued.
    write(
        VALID / "valid_007.json",
        pkcs_req(
            "txn-1007",
            "default",
            "s3cr3t-default",
            "device-0005",
            60,
            sans=["*.devices.corp.example"],
        ),
    )

    # UpdateReq (18): carries a CSR but is not an authorized enrollment type.
    write(
        ADVERSARIAL / "exploit_01.json",
        {
            "transaction_id": "txn-9001",
            "message_type": "18",
            "provisioner": "default",
            "challenge": "",
            "subject_common_name": "device-9001",
            "sans": ["device-9001.corp.example"],
            "requested_validity_days": 3650,
        },
    )
    # Unknown/reserved numeric message type.
    write(
        ADVERSARIAL / "exploit_02.json",
        {
            "transaction_id": "txn-9002",
            "message_type": "99",
            "provisioner": "default",
            "challenge": "",
            "subject_common_name": "device-9002",
            "sans": ["device-9002.corp.example"],
            "requested_validity_days": 60,
        },
    )
    # Provisioner with no challenge configured must fail closed.
    write(
        ADVERSARIAL / "exploit_03.json",
        pkcs_req("txn-9003", "open", "", "device-9003", 30),
    )
    # Renewal signer issued by a foreign CA name.
    write(
        ADVERSARIAL / "exploit_04.json",
        renewal_req(
            "txn-9004",
            "default",
            "s3cr3t-default",
            "device-9004",
            30,
            "Acme Internal Root CA",
            400,
        ),
    )
    # Excessive validity: must be clamped to the provisioner max and issued.
    write(
        ADVERSARIAL / "exploit_05.json",
        pkcs_req("txn-9005", "default", "s3cr3t-default", "device-9005", 3650),
    )
    # Renewal signer carrying the CA's name but already expired.
    write(
        ADVERSARIAL / "exploit_06.json",
        renewal_req(
            "txn-9006",
            "default",
            "s3cr3t-default",
            "device-9006",
            30,
            CA_SUBJECT,
            0,
        ),
    )
    # Forged signer: carries the CA's name and a live expiry but no valid
    # authority signature (the caller cannot reproduce the fingerprint).
    write(
        ADVERSARIAL / "exploit_07.json",
        renewal_req(
            "txn-9007",
            "default",
            "s3cr3t-default",
            "device-9007",
            30,
            CA_SUBJECT,
            200,
            signature="0" * 64,
        ),
    )
    # Genuinely CA-issued signer for device-0002 replayed to renew a different
    # subject (device-9008): the signature is valid but the subject is not bound.
    write(
        ADVERSARIAL / "exploit_08.json",
        renewal_req(
            "txn-9008",
            "default",
            "s3cr3t-default",
            "device-9008",
            30,
            CA_SUBJECT,
            200,
            signer_subject="device-0002",
        ),
    )
    # CertRep (3): a response message type submitted as a request.
    write(
        ADVERSARIAL / "exploit_09.json",
        {
            "transaction_id": "txn-9009",
            "message_type": "3",
            "provisioner": "default",
            "challenge": "s3cr3t-default",
            "subject_common_name": "device-9009",
            "sans": ["device-9009.corp.example"],
            "requested_validity_days": 60,
        },
    )
    # Wildcard SAN whose certified hosts include an excluded name. "*.corp.example"
    # would certify "internal.corp.example", which is excluded, so it must be
    # refused even though "corp.example" itself is permitted.
    write(
        ADVERSARIAL / "exploit_10.json",
        pkcs_req(
            "txn-9010",
            "default",
            "s3cr3t-default",
            "device-9010",
            60,
            sans=["*.corp.example"],
        ),
    )
    # Concrete SAN inside an excluded subtree.
    write(
        ADVERSARIAL / "exploit_11.json",
        pkcs_req(
            "txn-9011",
            "default",
            "s3cr3t-default",
            "device-9011",
            60,
            sans=["host.internal.corp.example"],
        ),
    )


if __name__ == "__main__":
    main()
