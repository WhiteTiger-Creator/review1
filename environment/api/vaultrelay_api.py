from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, request

APP_NOW = datetime(2026, 7, 26, 12, 0, 0, tzinfo=UTC)
REPLAY_WINDOW_SECONDS = 300
CANONICAL_HEADERS = [
    "(request-target)",
    "host",
    "x-vr-merchant",
    "x-vr-key-id",
    "x-vr-timestamp",
    "x-vr-nonce",
    "digest",
]

app = Flask(__name__)
seen_nonces: set[tuple[str, str]] = set()


def _keyring_path() -> Path:
    return Path(os.environ.get("VAULTRELAY_KEYRING", "/app/keyring/hmac_keys.json"))


def _load_key(key_id: str) -> dict[str, Any] | None:
    data = json.loads(_keyring_path().read_text(encoding="utf-8"))
    for item in data["keys"]:
        if item["key_id"] == key_id:
            return item
    return None


def _parse_signature(value: str) -> dict[str, str]:
    parts: dict[str, str] = {}
    for match in re.finditer(r'([A-Za-z]+)="([^"]*)"', value):
        parts[match.group(1)] = match.group(2)
    return parts


def _response_id(raw: bytes, nonce: str, reason: str) -> str:
    return hashlib.sha256(raw + nonce.encode() + reason.encode()).hexdigest()[:16]


def _reject(reason: str, raw: bytes, nonce: str = ""):
    return (
        jsonify(
            {
                "accepted": False,
                "reason": reason,
                "response_id": _response_id(raw, nonce, reason),
            }
        ),
        401,
    )


def _canonical_string(method: str, path: str, headers: dict[str, str]) -> str:
    values = {
        "(request-target)": f"{method.lower()} {path}",
        "host": headers.get("host", ""),
        "x-vr-merchant": headers.get("x-vr-merchant", ""),
        "x-vr-key-id": headers.get("x-vr-key-id", ""),
        "x-vr-timestamp": headers.get("x-vr-timestamp", ""),
        "x-vr-nonce": headers.get("x-vr-nonce", ""),
        "digest": headers.get("digest", ""),
    }
    return "\n".join(f"{name}: {values[name]}" for name in CANONICAL_HEADERS)


def _parse_time(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        return None


@app.post("/webhook/<merchant_id>")
def webhook(merchant_id: str):
    raw = request.get_data()
    lowered = {key.lower(): value for key, value in request.headers.items()}
    nonce = lowered.get("x-vr-nonce", "")
    timestamp = lowered.get("x-vr-timestamp", "")
    key_id = lowered.get("x-vr-key-id", "")

    required = ["host", "x-vr-merchant", "x-vr-key-id", "x-vr-timestamp", "x-vr-nonce", "digest", "signature"]
    if any(not lowered.get(name) for name in required):
        return _reject("missing_header", raw, nonce)
    if lowered["x-vr-merchant"] != merchant_id:
        return _reject("merchant_mismatch", raw, nonce)

    digest = "SHA-256=:" + base64.b64encode(hashlib.sha256(raw).digest()).decode("ascii") + ":"
    if not hmac.compare_digest(digest, lowered["digest"]):
        return _reject("digest_mismatch", raw, nonce)

    key = _load_key(key_id)
    if key is None:
        return _reject("unknown_key", raw, nonce)
    if key["merchant_id"] != merchant_id:
        return _reject("key_merchant_mismatch", raw, nonce)
    if key["purpose"] != "webhook-signing" or key["status"] != "active":
        return _reject("inactive_key", raw, nonce)

    signed_at = _parse_time(timestamp)
    if signed_at is None:
        return _reject("bad_timestamp", raw, nonce)
    if not (_parse_time(key["not_before"]) <= signed_at < _parse_time(key["not_after"])):
        return _reject("key_window", raw, nonce)
    if abs((APP_NOW - signed_at).total_seconds()) > REPLAY_WINDOW_SECONDS:
        return _reject("stale_timestamp", raw, nonce)

    parsed = _parse_signature(lowered["signature"])
    if parsed.get("keyId") != key_id:
        return _reject("signature_key_mismatch", raw, nonce)
    if parsed.get("algorithm") != "hmac-sha256":
        return _reject("bad_algorithm", raw, nonce)
    if parsed.get("headers") != " ".join(CANONICAL_HEADERS):
        return _reject("bad_header_list", raw, nonce)

    canonical = _canonical_string(request.method, request.path, lowered)
    secret = base64.b64decode(key["secret_b64"])
    expected = base64.b64encode(hmac.new(secret, canonical.encode("utf-8"), hashlib.sha256).digest()).decode("ascii")
    if not hmac.compare_digest(expected, parsed.get("signature", "")):
        return _reject("bad_signature", raw, nonce)

    replay_key = (merchant_id, nonce)
    if replay_key in seen_nonces:
        return _reject("replay_nonce", raw, nonce)
    seen_nonces.add(replay_key)

    return jsonify(
        {
            "accepted": True,
            "reason": "accepted",
            "response_id": _response_id(raw, nonce, "accepted"),
        }
    )


@app.get("/healthz")
def healthz():
    return jsonify({"ok": True, "now": "2026-07-26T12:00:00Z"})


if __name__ == "__main__":
    port = int(os.environ.get("VAULTRELAY_PORT", "8089"))
    app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False)
