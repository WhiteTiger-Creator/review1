# Hall certification controller

`certctl` replays every hall listed in `programme/site_index.toml` through the
certification stages and writes one JSON document.

```
make all
./bin/certctl --all --out /app/output/certification_report.json
```

Layout:

- `estate/` published hall bundles and the site index
- `cmd/certctl/` controller entry point
- `internal/run/` stage wiring and report writing
- `ingest/` bundle loading and normalisation
- `q4/` shared record types
- `docs/` published contract, bundle layout, attestation rules
- `*-desk/` desk reference material carried over from the pre-merge tools
