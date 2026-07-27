hostctl-export systemd oneshot for this host.

Operators apply locale Environment= from metricd.service before ExecStart
(see /app/scripts/run_ship.sh --from-unit). Bind-mount inventory lives in
bind-mounts.conf; RequiresMountsFor lists snap trees, exclbook ledgers, and
language packs. After mount migration, exported host digests, ship journal
recovery, and pack_label freshness must still match /app/docs/ship-contract.rst.
