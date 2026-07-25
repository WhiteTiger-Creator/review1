#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def sign_doc(doc: dict, priv: Ed25519PrivateKey) -> dict:
    import json as _json

    subset = {
        "manifest_id": doc.get("manifest_id"),
        "tenant": doc.get("tenant"),
        "module_digest": doc.get("module", {}).get("digest"),
        "abi": doc.get("abi"),
    }
    payload = _json.dumps(subset, sort_keys=True, separators=(",", ":")).encode("utf-8")
    out = dict(doc)
    sig = priv.sign(payload)
    out["signature"] = sig.hex()
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ap.add_argument("--app", required=True)
    ap.add_argument("--seed", default="")
    args = ap.parse_args()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    if args.seed:
        priv = Ed25519PrivateKey.from_private_bytes(Path(args.seed).read_bytes())
    else:
        seed_path = Path("/tests/fixtures/signing-key.seed")
        if seed_path.exists() and seed_path.stat().st_size == 32:
            priv = Ed25519PrivateKey.from_private_bytes(seed_path.read_bytes())
        else:
            priv = Ed25519PrivateKey.generate()
    (out / "trust").mkdir(parents=True, exist_ok=True)
    (out / "trust" / "doc-signers.pub").write_text(
        priv.public_key().public_bytes_raw().hex() + "\n", encoding="utf-8"
    )
    for tenant, canary in (("tenant-a", "CANARY-A"), ("tenant-b", "CANARY-B")):
        tdir = out / "tenants" / tenant
        tdir.mkdir(parents=True, exist_ok=True)
        (tdir / "notes.txt").write_text(f"{canary}\n", encoding="utf-8")
        (tdir / ".env.json").write_text(
            json.dumps({"TENANT_TAG": canary}) + "\n", encoding="utf-8"
        )
    mod = {
        "ops": [
            {"import": "fs.read", "resource": "notes.txt"},
            {"import": "kv.write", "resource": "seen", "value": "1"},
        ]
    }
    mod_path = Path(args.app) / "modules" / "sample.json"
    mod_path.parent.mkdir(parents=True, exist_ok=True)
    mod_path.write_text(json.dumps(mod, indent=2) + "\n", encoding="utf-8")
    digest = hashlib.sha256(mod_path.read_bytes()).hexdigest()
    for tenant in ("tenant-a", "tenant-b"):
        manifest = sign_doc(
            {
                "manifest_id": f"{tenant}-sample",
                "tenant": tenant,
                "abi": 2,
                "module": {"digest": digest, "size": mod_path.stat().st_size},
                "capabilities": ["fs.read", "fs.write", "kv.write", "kv.read"],
                "limits": {"fuel": 1000000, "host_calls": 64, "output_bytes": 4096},
                "signer_key_id": "default",
            },
            priv,
        )
        mpath = Path(args.app) / "config" / f"manifest-{tenant}.json"
        mpath.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    v1 = sign_doc(
        {
            "manifest_id": "legacy-v1",
            "tenant": "tenant-a",
            "abi": 1,
            "module": {"digest": digest, "size": mod_path.stat().st_size},
            "capabilities": ["fs.read"],
            "limits": {"fuel": 500000, "host_calls": 32, "output_bytes": 2048},
            "signer_key_id": "default",
        },
        priv,
    )
    (Path(args.app) / "config" / "manifest-v1.json").write_text(
        json.dumps(v1, indent=2) + "\n", encoding="utf-8"
    )
    (out / "legacy-v1").mkdir(parents=True, exist_ok=True)
    (out / "legacy-v1" / "behavior.json").write_text(
        json.dumps({"expected_caps": ["env.read", "clock.read", "fs.read"]}) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
