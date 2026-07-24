"""Authoring-only generator for the signed TUF-style repository fixture.

Not shipped in the agent image. Private key material stays in memory only.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

APP = Path(os.environ.get("TUF_APP_ROOT", "/app"))
REPO = APP / "data" / "repo"
TARGETS = REPO / "targets"


def canonical_json(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_metadata(path: Path, doc: dict) -> bytes:
    text = canonical_json(doc) + "\n"
    path.write_text(text, encoding="utf-8")
    return text.encode("utf-8")


def gen_key() -> tuple[str, Ed25519PrivateKey, bytes]:
    priv = Ed25519PrivateKey.generate()
    pub_bytes = priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    keyid = sha256_hex(pub_bytes)[:16]
    return keyid, priv, pub_bytes


def sign_metadata(signed_body: dict, signers: list[tuple[str, Ed25519PrivateKey]]) -> dict:
    payload = canonical_json(signed_body).encode("utf-8")
    signatures = []
    for keyid, priv in signers:
        sig = priv.sign(payload)
        signatures.append({"keyid": keyid, "sig": sig.hex()})
    return {"signatures": signatures, "signed": signed_body}


def main() -> None:
    REPO.mkdir(parents=True, exist_ok=True)
    TARGETS.mkdir(parents=True, exist_ok=True)

    root_kid, root_priv, root_pub = gen_key()
    ts_kid, ts_priv, ts_pub = gen_key()
    snap_kid_a, snap_priv_a, snap_pub_a = gen_key()
    snap_kid_b, snap_priv_b, snap_pub_b = gen_key()
    tgt_kid, tgt_priv, tgt_pub = gen_key()

    def pub_entry(pub: bytes) -> dict:
        return {
            "keytype": "ed25519",
            "scheme": "ed25519",
            "keyval": {"public": pub.hex()},
            "keyid_hash_algorithm": "sha256",
        }

    root_signed = {
        "_type": "root",
        "spec_version": "1.0.31",
        "version": 1,
        "expires": "2030-01-01T00:00:00Z",
        "consistent_snapshot": True,
        "keys": {
            root_kid: pub_entry(root_pub),
            ts_kid: pub_entry(ts_pub),
            snap_kid_a: pub_entry(snap_pub_a),
            snap_kid_b: pub_entry(snap_pub_b),
            tgt_kid: pub_entry(tgt_pub),
        },
        "roles": {
            "root": {"keyids": [root_kid], "threshold": 1},
            "timestamp": {"keyids": [ts_kid], "threshold": 1},
            "snapshot": {"keyids": [snap_kid_a, snap_kid_b], "threshold": 2},
            "targets": {"keyids": [tgt_kid], "threshold": 1},
        },
    }
    root_doc = sign_metadata(root_signed, [(root_kid, root_priv)])

    target_payloads = {
        "targets/firmware_alpha.bin": b"ALPHA-FIRMWARE-PAYLOAD-v1.0\n",
        "targets/firmware_beta.bin": b"BETA-FIRMWARE-PAYLOAD-v2.3\n",
        "targets/firmware_gamma.bin": b"GAMMA-FIRMWARE-PAYLOAD-v0.9\n",
        "targets/config_delta.json": b'{"channel":"staging","rev":4}\n',
        "targets/config_epsilon.json": b'{"channel":"production","rev":7}\n',
        "targets/patch_zeta.bin": b"ZETA-PATCH-PAYLOAD-v1.1\n",
        "targets/bundle_eta.tar": b"ETA-BUNDLE-PAYLOAD-v3.0\n",
    }
    for rel, blob in target_payloads.items():
        (REPO / rel).write_bytes(blob)

    targets_signed = {
        "_type": "targets",
        "spec_version": "1.0.31",
        "version": 2,
        "expires": "2030-01-01T00:00:00Z",
        "targets": {
            "targets/firmware_alpha.bin": {
                "length": len(target_payloads["targets/firmware_alpha.bin"]),
                "hashes": {"sha256": sha256_hex(target_payloads["targets/firmware_alpha.bin"])},
                "custom": {"rollout": {"min_snapshot_version": 2}},
            },
            "targets/firmware_beta.bin": {
                "length": len(target_payloads["targets/firmware_beta.bin"]),
                "hashes": {"sha256": sha256_hex(target_payloads["targets/firmware_beta.bin"])},
                "custom": {"rollout": {"min_snapshot_version": 5}},
            },
            "targets/firmware_gamma.bin": {
                "length": len(target_payloads["targets/firmware_gamma.bin"]),
                "hashes": {"sha256": sha256_hex(target_payloads["targets/firmware_gamma.bin"])},
                "custom": {"rollout": {"min_snapshot_version": 1}},
            },
            "targets/config_delta.json": {
                "length": len(target_payloads["targets/config_delta.json"]),
                "hashes": {"sha256": sha256_hex(target_payloads["targets/config_delta.json"])},
                "custom": {"rollout": {"min_snapshot_version": 0}},
            },
            "targets/config_epsilon.json": {
                "length": len(target_payloads["targets/config_epsilon.json"]),
                "hashes": {"sha256": sha256_hex(target_payloads["targets/config_epsilon.json"])},
                "custom": {"rollout": {"min_snapshot_version": 3, "max_snapshot_version": 3}},
            },
            "targets/patch_zeta.bin": {
                "length": len(target_payloads["targets/patch_zeta.bin"]),
                "hashes": {"sha256": sha256_hex(target_payloads["targets/patch_zeta.bin"])},
                "custom": {"rollout": {"min_snapshot_version": 3, "max_snapshot_version": 2}},
            },
            "targets/bundle_eta.tar": {
                "length": len(target_payloads["targets/bundle_eta.tar"]),
                "hashes": {"sha256": sha256_hex(target_payloads["targets/bundle_eta.tar"])},
                "custom": {"rollout": {"min_snapshot_version": 0}},
            },
        },
    }
    targets_doc = sign_metadata(targets_signed, [(tgt_kid, tgt_priv)])
    targets_bytes = write_metadata(REPO / "targets.json", targets_doc)
    targets_hash = sha256_hex(targets_bytes)

    snapshot_signed = {
        "_type": "snapshot",
        "spec_version": "1.0.31",
        "version": 3,
        "expires": "2030-01-01T00:00:00Z",
        "meta": {
            "targets.json": {
                "version": 2,
                "length": len(targets_bytes),
                "hashes": {"sha256": targets_hash},
            }
        },
    }
    snapshot_doc = sign_metadata(
        snapshot_signed,
        [(snap_kid_a, snap_priv_a), (snap_kid_b, snap_priv_b)],
    )
    snapshot_bytes = write_metadata(REPO / "snapshot.json", snapshot_doc)
    snapshot_hash = sha256_hex(snapshot_bytes)

    timestamp_signed = {
        "_type": "timestamp",
        "spec_version": "1.0.31",
        "version": 5,
        "expires": "2030-01-01T00:00:00Z",
        "meta": {
            "snapshot.json": {
                "version": 3,
                "length": len(snapshot_bytes),
                "hashes": {"sha256": snapshot_hash},
            }
        },
    }
    timestamp_doc = sign_metadata(timestamp_signed, [(ts_kid, ts_priv)])
    timestamp_doc["signatures"].insert(
        0, {"keyid": ts_kid, "sig": ("ab" * 64)}
    )
    payload = canonical_json(timestamp_signed).encode("utf-8")
    dup_sig = ts_priv.sign(payload)
    timestamp_doc["signatures"].append({"keyid": ts_kid, "sig": dup_sig.hex()})

    write_metadata(REPO / "timestamp.json", timestamp_doc)
    write_metadata(REPO / "root.json", root_doc)

    integrity = {}
    for name in ("root.json", "timestamp.json", "snapshot.json", "targets.json"):
        integrity[name] = sha256_hex((REPO / name).read_bytes())
    (REPO / "integrity.json").write_text(json.dumps(integrity, indent=2) + "\n")

    manifest = {
        "repo_version": "1.0",
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "metadata_files": ["root.json", "timestamp.json", "snapshot.json", "targets.json"],
        "target_paths": sorted(target_payloads.keys()),
    }
    (REPO / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")


if __name__ == "__main__":
    main()
