# Toolchain

From `/app/environment`:

```bash
cargo build --release --manifest-path k7/Cargo.toml
cargo build --release --manifest-path m3/Cargo.toml
install -m 0755 k7/target/release/k7 /app/bin/k7
install -m 0755 m3/target/release/m3 /app/bin/m3
go build -o /app/bin/chironymctl ./cmd/chironymctl
```

Verifier rebuilds under `/tmp/chironym_vbin` using the same manifests with `CARGO_TARGET_DIR` overrides as needed.
