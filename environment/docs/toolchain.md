# Toolchain

Go module root: `/app/environment` (`go.mod`).

Build gated and inspect:

```bash
cd /app/environment
CGO_ENABLED=1 go build -o /app/bin/gated ./cmd/gated
CGO_ENABLED=1 go build -o /app/bin/inspect ./cmd/inspect
```

Runtime requires `gcc` and libc headers for the `sense` cgo wrapper.

Replay entrypoint: `bash /app/environment/scripts/repro_shift_cycle.sh`

Bind-cookie vault and facet rules live in `/app/environment/docs/peer_model.md`.
Marks and `drop_mask` live in `/app/environment/config/principals.toml`.
