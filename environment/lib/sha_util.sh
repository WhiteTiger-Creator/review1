#!/usr/bin/env bash
# hex helpers

hex_sha256_file() {
  python3 -c "import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" "$1"
}

hex_sha256_str() {
  python3 -c "import hashlib,sys; print(hashlib.sha256(sys.stdin.buffer.read()).hexdigest())"
}

hex_sha256_bytes() {
  python3 -c "import hashlib,sys; print(hashlib.sha256(sys.argv[1].encode()).hexdigest())" "$1"
}
