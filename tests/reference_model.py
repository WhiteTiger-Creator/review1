#!/usr/bin/env python3
"""Independent PKCS8 encrypted-key reference used only by verifier tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

PBES2_OID = bytes.fromhex("06092a864886f70d01050d")  # 1.2.840.113549.1.5.13
PBKDF2_OID = bytes.fromhex("06092a864886f70d01050c")  # 1.2.840.113549.1.5.12
AES256_CBC_OID = bytes.fromhex("060960864801650304012a")  # 2.16.840.1.101.3.4.1.42
STAMP_LABEL = b"lock-vault\n"


def parse_hex(text: object) -> bytes | None:
    if not isinstance(text, str):
        return None
    if any(c not in "0123456789abcdef" for c in text):
        return None
    if len(text) % 2 != 0:
        return None
    try:
        return bytes.fromhex(text)
    except ValueError:
        return None


def _read_len(data: bytes, i: int) -> tuple[int, int]:
    first = data[i]
    i += 1
    if first < 0x80:
        return first, i
    n = first & 0x7F
    if n == 0 or n > 3 or i + n > len(data):
        raise ValueError("len")
    value = int.from_bytes(data[i : i + n], "big")
    return value, i + n


def _read_tlv(data: bytes, i: int) -> tuple[int, bytes, int]:
    tag = data[i]
    length, j = _read_len(data, i + 1)
    end = j + length
    if end > len(data):
        raise ValueError("tlv")
    return tag, data[j:end], end


def is_pbes2(der: bytes) -> bool:
    return PBES2_OID in der


def is_aes256_cbc(der: bytes) -> bool:
    return AES256_CBC_OID in der


def bag_id(der: bytes) -> str:
    return hashlib.sha256(der).hexdigest()


def pbkdf2_iterations(der: bytes) -> int | None:
    """Read PBKDF2-params iterationCount: after PBKDF2 OID, SEQUENCE then salt then INTEGER."""
    idx = der.find(PBKDF2_OID)
    if idx < 0:
        return None
    i = idx + len(PBKDF2_OID)
    limit = min(len(der), i + 64)
    while i < limit and der[i] != 0x30:
        i += 1
    if i >= limit:
        return None
    try:
        _tag, body, _end = _read_tlv(der, i)
        j = 0
        if j >= len(body) or body[j] != 0x04:
            return None
        _t, _salt, j = _read_tlv(body, j)
        if j >= len(body) or body[j] != 0x02:
            return None
        _t, ibody, _j2 = _read_tlv(body, j)
        if not ibody:
            return None
        return int.from_bytes(ibody, "big")
    except (ValueError, IndexError):
        return None


def load_phrases(path: Path) -> dict[str, str]:
    table: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        slot = row.get("slot")
        phrase = row.get("phrase")
        if isinstance(slot, str) and slot and isinstance(phrase, str):
            table[slot] = phrase
    return table


def load_policy(path: Path) -> int:
    row = json.loads(path.read_text(encoding="utf-8"))
    return int(row["min_iters"])


def spki_fingerprint(private_key) -> str:
    pub = private_key.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(pub).hexdigest()


def unwrap(der: bytes, phrase: str) -> str | None:
    try:
        key = serialization.load_der_private_key(der, password=phrase.encode("utf-8"))
    except (ValueError, TypeError):
        return None
    return spki_fingerprint(key)


def expected_outputs(vault_root: Path) -> tuple[str, str]:
    phrases = load_phrases(vault_root / "phrases" / "main" / "phrases.ndjson")
    min_iters = load_policy(vault_root / "policy" / "iters.json")
    bag_burn: set[str] = set()
    key_seen: set[str] = set()
    holds: dict[str, int] = {}
    rows: list[str] = []
    unwrapped = 0
    denied = 0

    for raw in (vault_root / "bags" / "main" / "bags.ndjson").read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            rows.append(json.dumps({"seq": 0, "verdict": "format", "slot": "-"}, separators=(",", ":")))
            denied += 1
            continue

        seq = row.get("seq")
        slot = row.get("slot")
        der = parse_hex(row.get("der", ""))
        if not isinstance(seq, int) or seq < 1 or not isinstance(slot, str) or not slot or der is None or len(der) < 16:
            rows.append(
                json.dumps(
                    {"seq": seq if isinstance(seq, int) else 0, "verdict": "format", "slot": "-"},
                    separators=(",", ":"),
                )
            )
            denied += 1
            continue

        if slot not in phrases:
            rows.append(json.dumps({"seq": seq, "verdict": "slot", "slot": slot}, separators=(",", ":")))
            denied += 1
            continue

        if seq <= holds.get(slot, 0):
            rows.append(json.dumps({"seq": seq, "verdict": "hold", "slot": slot}, separators=(",", ":")))
            denied += 1
            continue

        phrase = phrases[slot]
        if not phrase:
            rows.append(json.dumps({"seq": seq, "verdict": "phrase", "slot": slot}, separators=(",", ":")))
            denied += 1
            continue

        if not is_pbes2(der):
            rows.append(json.dumps({"seq": seq, "verdict": "pbes2", "slot": slot}, separators=(",", ":")))
            denied += 1
            continue

        if not is_aes256_cbc(der):
            rows.append(json.dumps({"seq": seq, "verdict": "cipher", "slot": slot}, separators=(",", ":")))
            denied += 1
            continue

        iters = pbkdf2_iterations(der)
        if iters is None or iters < min_iters:
            rows.append(json.dumps({"seq": seq, "verdict": "iters", "slot": slot}, separators=(",", ":")))
            denied += 1
            continue

        bid = bag_id(der)
        if bid in bag_burn:
            rows.append(json.dumps({"seq": seq, "verdict": "replay", "slot": slot}, separators=(",", ":")))
            denied += 1
            continue

        fp = unwrap(der, phrase)
        bag_burn.add(bid)
        if fp is None:
            rows.append(json.dumps({"seq": seq, "verdict": "unwrap", "slot": slot}, separators=(",", ":")))
            denied += 1
            continue

        if fp in key_seen:
            rows.append(json.dumps({"seq": seq, "verdict": "replay", "slot": slot}, separators=(",", ":")))
            denied += 1
            continue
        key_seen.add(fp)

        rows.append(
            json.dumps({"seq": seq, "verdict": "ok", "slot": slot, "fp": fp}, separators=(",", ":"))
        )
        unwrapped += 1
        hold_until = row.get("hold_until")
        if isinstance(hold_until, int) and hold_until > seq:
            holds[slot] = hold_until

    log = ("\n".join(rows) + ("\n" if rows else "")).encode("utf-8")
    stamp_hex = hashlib.sha256(STAMP_LABEL + log).hexdigest()[:16]
    stamp = f"unwrapped={unwrapped}\ndenied={denied}\nstamp={stamp_hex}\n"
    return log.decode("utf-8"), stamp


def write_vault(
    root: Path,
    phrases: list[dict],
    min_iters: int,
    bags: list[dict],
) -> None:
    (root / "phrases" / "main").mkdir(parents=True, exist_ok=True)
    (root / "policy").mkdir(parents=True, exist_ok=True)
    (root / "bags" / "main").mkdir(parents=True, exist_ok=True)
    (root / "phrases" / "main" / "phrases.ndjson").write_text(
        "".join(json.dumps(p, separators=(",", ":")) + "\n" for p in phrases),
        encoding="utf-8",
    )
    (root / "policy" / "iters.json").write_text(
        json.dumps({"min_iters": min_iters}, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    (root / "bags" / "main" / "bags.ndjson").write_text(
        "".join(json.dumps(b, separators=(",", ":")) + "\n" for b in bags),
        encoding="utf-8",
    )


def encrypt_rsa(phrase: str, iterations: int, cipher: str = "aes-256-cbc") -> bytes:
    """Create PBES2 encrypted PKCS#8 DER using openssl (available in the task image)."""
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        key = root / "key.pem"
        enc = root / "enc.der"
        subprocess.run(
            ["openssl", "genrsa", "-out", str(key), "2048"],
            check=True,
            capture_output=True,
            timeout=30,
        )
        subprocess.run(
            [
                "openssl",
                "pkcs8",
                "-topk8",
                "-in",
                str(key),
                "-outform",
                "DER",
                "-out",
                str(enc),
                "-v2",
                cipher,
                "-iter",
                str(iterations),
                "-passout",
                f"pass:{phrase}",
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        return enc.read_bytes()


def encrypt_pbes1_legacy(phrase: str) -> bytes:
    """Create a legacy PBES1 encrypted PKCS#8 DER (for pbes2 rejection fixtures)."""
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        key = root / "key.pem"
        enc = root / "enc.der"
        subprocess.run(
            ["openssl", "genrsa", "-out", str(key), "2048"],
            check=True,
            capture_output=True,
            timeout=30,
        )
        subprocess.run(
            [
                "openssl",
                "pkcs8",
                "-topk8",
                "-in",
                str(key),
                "-outform",
                "DER",
                "-out",
                str(enc),
                "-v1",
                "PBE-SHA1-3DES",
                "-passout",
                f"pass:{phrase}",
            ],
            check=True,
            capture_output=True,
            timeout=30,
        )
        return enc.read_bytes()


def encrypt_same_key_pair(phrase: str, iterations: int) -> tuple[bytes, bytes]:
    """Two different PBES2 bags for the same RSA key (key-replay fixtures)."""
    import subprocess
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        key = root / "key.pem"
        a = root / "a.der"
        b = root / "b.der"
        subprocess.run(
            ["openssl", "genrsa", "-out", str(key), "2048"],
            check=True,
            capture_output=True,
            timeout=30,
        )
        for out in (a, b):
            subprocess.run(
                [
                    "openssl",
                    "pkcs8",
                    "-topk8",
                    "-in",
                    str(key),
                    "-outform",
                    "DER",
                    "-out",
                    str(out),
                    "-v2",
                    "aes-256-cbc",
                    "-iter",
                    str(iterations),
                    "-passout",
                    f"pass:{phrase}",
                ],
                check=True,
                capture_output=True,
                timeout=30,
            )
        return a.read_bytes(), b.read_bytes()
