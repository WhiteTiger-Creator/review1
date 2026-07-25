# Operations

Rebuild with `bash /app/environment/tools/mk_all.sh`. Binary: `/app/bin/gm_infer`. The image provides the Go toolchain on `PATH` (`go version`).

## settle

```
/app/bin/gm_infer settle \
  --g1 /app/environment/seed/tile_g1.json \
  --g2 /app/environment/seed/tile_g2.json \
  --scraps /app/environment/seed/scrap_old.txt,/app/environment/seed/scrap_new.txt \
  --sum /app/environment/seed/sum_partial.txt \
  --arms a7,b2 \
  --nest /app/environment/nest \
  --var /app/environment/var \
  --out /app/output/graph_probe.json
```

`--arms` is a comma-separated subset of `a7,b2`. Soft settle: identical `--g1`/`--g2` bytes, or fewer than two scrap files. Soft exits 0 and still writes `--out`.

Seed inputs under `/app/environment/seed/`:

- `/app/environment/seed/tile_g1.json`, `/app/environment/seed/tile_g2.json`
- `/app/environment/seed/tile_g1_x2.json`, `/app/environment/seed/tile_g2_x2.json`
- `/app/environment/seed/tile_e1.json`, `/app/environment/seed/tile_e2.json` with `/app/environment/seed/sum_equal.txt`
- `/app/environment/seed/sum_partial.txt`
- `/app/environment/seed/scrap_old.txt`, `/app/environment/seed/scrap_mid.txt`, `/app/environment/seed/scrap_new.txt`, `/app/environment/seed/scrap_drop.txt`
- `/app/environment/seed/stub_trace.json`
- temporary whitespace-equivalent scrap files such as `scrap_ws.txt` are identity-preserving when only blank lines and comments differ

Triad scrap order examples:

```
--scraps /app/environment/seed/scrap_old.txt,/app/environment/seed/scrap_mid.txt,/app/environment/seed/scrap_new.txt
--scraps /app/environment/seed/scrap_mid.txt,/app/environment/seed/scrap_old.txt,/app/environment/seed/scrap_new.txt
```

## recover / status / compact

```
/app/bin/gm_infer recover --nest /app/environment/nest --var /app/environment/var --out /app/output/graph_probe.json
/app/bin/gm_infer status --nest /app/environment/nest --var /app/environment/var --out /app/output/graph_probe.json
/app/bin/gm_infer compact --var /app/environment/var
```

`status` prints JSON with `state` of `settled` or `pending`. Coherence rules for those states, plus recover/compact quarantine and journal repair behavior, are in `/app/environment/docs/state_contract.md`.

## Offline builds

```
cd /app/environment/nest && GOPROXY=off GOSUMDB=off go build -o /tmp/a7.bin ./a7
cd /app/environment/nest && GOPROXY=off GOSUMDB=off go build -o /tmp/b2.bin ./b2
```

## Digest helper

```
python3 /app/environment/tools/view_sum.py
```
