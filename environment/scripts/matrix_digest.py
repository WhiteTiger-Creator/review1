"""Compute matrix_digest per docs/digest_canon.md."""
import hashlib
import sys

if len(sys.argv) != 3:
    print("usage: matrix_digest.py <scenario_id> <outcome>", file=sys.stderr)
    sys.exit(2)
payload = f"{sys.argv[1]}|{sys.argv[2]}"
print(hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16])
