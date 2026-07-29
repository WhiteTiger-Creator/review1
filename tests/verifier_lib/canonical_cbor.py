"""Deterministic CBOR subset used by evidence verification."""
from __future__ import annotations

from typing import Any


def encode_unsigned(value: int) -> bytes:
    if value <= 23:
        return bytes([value])
    if value <= 0xFF:
        return bytes([0x18, value])
    if value <= 0xFFFF:
        return bytes([0x19, (value >> 8) & 0xFF, value & 0xFF])
    if value <= 0xFFFFFFFF:
        return bytes([0x1A, (value >> 24) & 0xFF, (value >> 16) & 0xFF, (value >> 8) & 0xFF, value & 0xFF])
    raise ValueError("integer too large")

def encode_text(text: str) -> bytes:
    raw = text.encode()
    prefix = encode_unsigned(len(raw))
    if len(raw) <= 23:
        return bytes([0x60 + len(raw)]) + raw
    head = {0x18: 0x78, 0x19: 0x79, 0x1A: 0x7A}[prefix[0]]
    return bytes([head]) + prefix[1:] + raw

def encode_bytes(data: bytes) -> bytes:
    if len(data) <= 23:
        return bytes([0x40 + len(data)]) + data
    prefix = encode_unsigned(len(data))
    head = {0x18: 0x58, 0x19: 0x59, 0x1A: 0x5A}[prefix[0]]
    return bytes([head]) + prefix[1:] + data

def encode_bool(value: bool) -> bytes:
    return bytes([0xF5 if value else 0xF4])

def encode_null() -> bytes:
    return bytes([0xF6])

def encode_value(value: Any) -> bytes:
    if value is None:
        return encode_null()
    if isinstance(value, bool):
        return encode_bool(value)
    if isinstance(value, int):
        return encode_unsigned(value)
    if isinstance(value, str):
        return encode_text(value)
    if isinstance(value, bytes):
        return encode_bytes(value)
    if isinstance(value, list):
        items = b"".join(encode_value(item) for item in value)
        length = len(value)
        if length <= 23:
            return bytes([0x80 + length]) + items
        prefix = encode_unsigned(length)
        head = {0x18: 0x98, 0x19: 0x99, 0x1A: 0x9A}[prefix[0]]
        return bytes([head]) + prefix[1:] + items
    if isinstance(value, dict):
        pairs = sorted(value.items(), key=lambda item: item[0])
        chunks = b"".join(encode_text(k) + encode_value(v) for k, v in pairs)
        length = len(pairs)
        if length <= 23:
            return bytes([0xA0 + length]) + chunks
        prefix = encode_unsigned(length)
        head = {0x18: 0xB8, 0x19: 0xB9, 0x1A: 0xBA}[prefix[0]]
        return bytes([head]) + prefix[1:] + chunks
    raise TypeError(type(value))

def validate_cbor(data: bytes) -> None:
    if not data:
        raise ValueError("empty cbor")
