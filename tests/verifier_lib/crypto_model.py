"""Ed25519 and envelope signing helpers."""
from __future__ import annotations

import base64
import hashlib
import struct
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from verifier_lib.canonical_json import canonical_bytes, digest_bytes, parse_strict


def private_key_from_seed(label: str) -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(hashlib.sha256(label.encode()).digest())

def public_key_b64(private_key: Ed25519PrivateKey) -> str:
    return base64.b64encode(private_key.public_key().public_bytes_raw()).decode()

def dac1_message(payload_type: str, payload_bytes: bytes) -> bytes:
    out = bytearray(b"DAC1\0envelope\0")
    out.extend(struct.pack(">I", len(payload_type)))
    out.extend(payload_type.encode())
    out.extend(struct.pack(">Q", len(payload_bytes)))
    out.extend(payload_bytes)
    return bytes(out)

def sign_envelope(payload_type: str, payload: dict[str, Any], key_id: str, private_key: Ed25519PrivateKey) -> dict[str, Any]:
    payload_bytes = canonical_bytes(payload)
    signature = private_key.sign(dac1_message(payload_type, payload_bytes))
    return {
        "schema_version": 1,
        "payload_type": payload_type,
        "payload": base64.b64encode(payload_bytes).decode(),
        "signatures": [{"key_id": key_id, "signature": base64.b64encode(signature).decode()}],
    }

def verify_envelope(envelope: dict[str, Any], keyring: dict[str, bytes]) -> None:
    payload_bytes = base64.b64decode(envelope["payload"])
    message = dac1_message(envelope["payload_type"], payload_bytes)
    for entry in envelope["signatures"]:
        public = keyring[entry["key_id"]]
        signature = base64.b64decode(entry["signature"])
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        Ed25519PublicKey.from_public_bytes(public).verify(signature, message)

def envelope_digest(envelope_text: str) -> str:
    return digest_bytes(envelope_text.rstrip("\n").encode())

def load_keyring(path: Path) -> dict[str, bytes]:
    return {
        item["key_id"]: base64.b64decode(item["public_key"])
        for item in parse_strict(path.read_text())
    }
