#!/usr/bin/env bash
set -euo pipefail
ROOT=/app/environment
export MIRROR_ROOT="$ROOT"

echo "=== Inspect broken replay exports ==="
rm -rf /app/output
OUTPUT_DIR=/app/output CYCLE_COUNT=1 bash "$ROOT/scripts/repro_mirror.sh" || true
if [ -f /app/output/convergence_report.json ]; then
  python3 - <<'PY'
import json
from pathlib import Path

conv = json.loads(Path("/app/output/convergence_report.json").read_text())
row = conv["cycles"][0]
print(
    f"cycle {row['cycle']}: synced_bytes={row['synced_bytes']} "
    f"verified_bytes={row['verified_bytes']}"
)
PY
fi

echo "=== Apply coordinated source repairs ==="
python3 <<'PY'
from pathlib import Path

shift = Path("/app/environment/gate/shift_s.go")
shift.write_text(
    shift.read_text().replace(
        """func applyPresent(out *store.StagePipe, span int) {
	out.Staged = span
	out.Closed = true
}""",
        """func applyPresent(out *store.StagePipe, span int) {
	out.Staged = span
}""",
        1,
    )
)

settle = Path("/app/environment/engine/settle_h.go")
settle.write_text(
    settle.read_text().replace(
        """func fold_w(pipe *store.StagePipe, prb store.PrbFixture) (int, int) {
	synced := pipe.Staged
	verified := 0
	if pipe.Closed {
		verified = synced
	}
	_ = viewFrom(prb)
	return synced, verified
}""",
        """func fold_w(pipe *store.StagePipe, prb store.PrbFixture) (int, int) {
	synced := pipe.Staged
	verified := 0
	if pipe.Closed && pipe.HolesCleared && pipe.ContentCaught && prb.HoleDebt == 0 && prb.HolesCleared && prb.ContentCaught {
		verified = synced
	}
	return synced, verified
}""",
        1,
    )
)

pack = Path("/app/environment/store/pack_r.go")
pack.write_text(
    pack.read_text().replace(
        """func pack_r(root string, cat CatFixture, prb PrbFixture, seal int) (int, int) {
	_ = root
	return lane_s(cat, prb, LaneCfg{CatalogLane: 0, ProbeLane: 0}, seal)
}""",
        """func pack_r(root string, cat CatFixture, prb PrbFixture, seal int) (int, int) {
	return lane_s(cat, prb, readLaneCfg(root), seal)
}""",
        1,
    )
)

latch = Path("/app/environment/stride/latch_k.go")
latch.write_text(
    latch.read_text().replace(
        """func latch_k(pipe *store.StagePipe, prb store.PrbFixture, rank int) bool {
	_ = rank
	if prb.PresentMark && pipe.Staged > 0 {
		return true
	}
	return false
}""",
        """func latch_k(pipe *store.StagePipe, prb store.PrbFixture, rank int) bool {
	_ = rank
	if prb.LegBIODone && pipe.HolesCleared && pipe.ContentCaught {
		return true
	}
	return false
}""",
        1,
    )
)

snap = Path("/app/environment/engine/snap_q.go")
snap.write_text(
    snap.read_text().replace(
        "	_ = seal\n\treturn store.FuseViews(cat, prb, 0), nil",
        "\treturn store.FuseViews(cat, prb, seal), nil",
        1,
    )
)

slot = Path("/app/environment/store/slot_k.go")
slot.write_text(
    slot.read_text().replace(
        "if c.SyncedBytes > 0 && c.Cycle > rank {",
        "if c.VerifiedBytes > 0 && c.VerifiedBytes == c.SyncedBytes && c.Cycle > rank {",
        1,
    )
)

drain = Path("/app/environment/store/drain_m.go")
drain.write_text(
    drain.read_text().replace(
        """	if pipe.Staged > 0 && cycle > sealed {
		return cycle
	}
	return sealed""",
        """	_ = pipe
	_ = cycle
	return sealed""",
        1,
    )
)

fuse = Path("/app/environment/store/fuse_j.go")
fuse.write_text(
    fuse.read_text().replace(
        """	aEpoch, bEpoch := bundle_t(cat, prb, seal)
	if cat.Finished && seal < prb.Epoch {
		aEpoch = prb.Epoch
	}
	return Snap{""",
        """	aEpoch, bEpoch := bundle_t(cat, prb, seal)
	return Snap{""",
        1,
    )
)

lane = Path("/app/environment/store/lane_s.go")
lane.write_text(
    lane.read_text().replace(
        """	if cat.Finished && seal < prbEpoch {
		return prbEpoch, prbEpoch
	}
	if lanes.CatalogLane == lanes.ProbeLane {""",
        """	_ = seal
	if lanes.CatalogLane == lanes.ProbeLane {""",
        1,
    )
)

rebase = Path("/app/environment/engine/rebase_v.go")
rebase.write_text(
    """package engine

import (
	"encoding/json"
	"os"
	"path/filepath"

	"blkmir/store"
)

func rebase_v(outDir string, cycle int, cat store.CatFixture, prb store.PrbFixture) (int, int) {
	aPacked, bPacked := store.BundleEpochs(cat, prb)
	aBase := aPacked - 1
	bBase := bPacked - 1
	if cycle <= 1 || outDir == "" {
		return aBase, bBase
	}
	convPath := filepath.Join(outDir, "convergence_report.json")
	raw, err := os.ReadFile(convPath)
	if err != nil {
		return aBase, bBase
	}
	var conv store.ConvReport
	if json.Unmarshal(raw, &conv) != nil {
		return aBase, bBase
	}
	for _, row := range conv.Cycles {
		if row.Cycle >= cycle {
			continue
		}
		if row.VerifiedBytes > 0 && row.VerifiedBytes < row.SyncedBytes {
			return aBase, bBase
		}
	}
	return aBase, bBase
}

func RebaseFloors(outDir string, cycle int, cat store.CatFixture, prb store.PrbFixture) (int, int) {
	return rebase_v(outDir, cycle, cat, prb)
}
"""
)

nudge = Path("/app/environment/stride/nudge_p.go")
nudge.write_text(
    nudge.read_text().replace(
        """	if next.LegID == "leg-b" && !ctx.LegBOpen && !next.IODone {
		return out, nil
	}
	holdReady := next.HoldMS > 0 || (ctx.Cycle > ctx.Rank && next.LegID == "leg-b")
	if holdReady {
		out.HoldMS = next.HoldMS
		if out.HoldMS == 0 && ctx.Cycle > 0 {
			out.HoldMS = 1
		}
		out.Epoch = prior.Epoch + 1
	}""",
        """	if next.LegID == "leg-b" && !ctx.LegBOpen {
		return out, nil
	}
	if next.HoldMS > 0 {
		out.HoldMS = next.HoldMS
		out.Epoch = prior.Epoch + 1
	} else if ctx.Cycle > 0 && next.LegID == "leg-b" {
		out.HoldMS = 1
		out.Epoch = prior.Epoch + 1
	}""",
        1,
    )
)

haul = Path("/app/environment/store/haul_u.go")
haul.write_text(
    haul.read_text().replace(
        """	var anchor int
	for _, row := range prev.Segments {
		if row.LegID == "leg-a" {
			anchor = row.ByteOffset
		}
	}
	for _, row := range prev.Segments {
		r := row
		if r.LegID == "leg-b" {
			r.ByteOffset = anchor
		}
		ledger.Append(r)
	}""",
        """	for _, row := range prev.Segments {
		ledger.Append(row)
	}""",
        1,
    ).replace(
        "return c.VerifiedBytes > 0 && c.VerifiedBytes < c.SyncedBytes",
        "return c.VerifiedBytes > 0 && c.VerifiedBytes == c.SyncedBytes",
        1,
    )
)

stamp = Path("/app/environment/phase/stamp_r.go")
stamp.write_text(
    stamp.read_text().replace(
        """	sideB := store.ViewRow{
		Source:   "side-b",
		Tally:    snap.AMetric,
		Epoch:    snap.BEpoch,
		TallyHex: metricHex(snap.AMetric, snap.BEpoch),
	}""",
        "	sideB := clip_x(snap)",
        1,
    )
)

merge = Path("/app/environment/engine/merge.go")
merge.write_text(
    merge.read_text().replace("if holdUS > 0 {", "if ioDone && holdUS > 0 {", 1).replace(
        """	_, _ = store.BundleEpochs(cat, prb)
	return cat.Epoch - 1, cat.Epoch - 1""",
        """	aPacked, bPacked := store.BundleEpochs(cat, prb)
	return aPacked, bPacked - 1""",
        1,
    )
)

queue = Path("/app/environment/engine/queue_w.go")
queue.write_text(
    queue.read_text().replace(
        """	rows := []store.TraceLine{
		{Epoch: cycle, Op: "latch", Path: path},
		{Epoch: cycle, Op: "roll", Path: path},
		{Epoch: cycle, Op: "chunk", Path: path},
	}
	return append(rows, prior...)""",
        """	rows := []store.TraceLine{
		{Epoch: cycle, Op: "chunk", Path: path},
		{Epoch: cycle, Op: "roll", Path: path},
		{Epoch: cycle, Op: "latch", Path: path},
	}
	return append(prior, rows...)""",
        1,
    )
)

checks = [
    ("/app/environment/gate/shift_s.go", "out.Staged = span\n}"),
    ("/app/environment/engine/settle_h.go", "prb.HoleDebt == 0"),
    ("/app/environment/store/pack_r.go", "readLaneCfg(root)"),
    ("/app/environment/stride/latch_k.go", "pipe.HolesCleared && pipe.ContentCaught"),
    ("/app/environment/engine/snap_q.go", "FuseViews(cat, prb, seal)"),
    ("/app/environment/store/slot_k.go", "c.VerifiedBytes == c.SyncedBytes"),
    ("/app/environment/phase/stamp_r.go", "sideB := clip_x(snap)"),
]
for path, needle in checks:
    text = Path(path).read_text()
    if needle not in text:
        raise SystemExit(f"patch verification failed: {path} missing {needle!r}")
PY

echo "=== Rebuild maintenance CLIs ==="
cd "$ROOT"
export PATH="/usr/local/go/bin:${PATH:-/usr/bin:/bin}"
if ! command -v go >/dev/null 2>&1; then
  echo "go toolchain missing from PATH; expected /usr/local/go/bin/go" >&2
  exit 1
fi
go build -o /app/bin/mirctl ./cmd/mirctl
go build -o /app/bin/viewctl ./cmd/viewctl

echo "=== Rerun full two-cycle replay ==="
bash "$ROOT/scripts/repro_mirror.sh"
