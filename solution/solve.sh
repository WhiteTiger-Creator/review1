#!/usr/bin/env bash
set -euo pipefail
ROOT=/app/environment
export MIRROR_ROOT="$ROOT"

echo "=== Inspect divergent replay exports ==="
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

cord = Path("/app/environment/store/cord_m.go")
cord.write_text(
    """package store

// CordLedger reconciles phased wave completion with stage-pipe materialization
// before rank sealing, digest export, and destination-leg gating consult it.
type CordLedger struct {
	Pipe  *StagePipe
	Waves WaveFlags
	Prb   PrbFixture
}

func NewCord(pipe *StagePipe, waves WaveFlags, prb PrbFixture) *CordLedger {
	return &CordLedger{Pipe: pipe, Waves: waves, Prb: prb}
}

// SealGrade feeds digest authority and maintenance rank sealing.
func (c *CordLedger) SealGrade() int {
	if c.Pipe == nil {
		return 0
	}
	if c.Waves.Settled() && c.Pipe.Closed && c.Prb.HoleDebt == 0 &&
		c.Prb.HolesCleared && c.Prb.ContentCaught {
		return c.Prb.Epoch
	}
	return 0
}

// LegBEligible gates whether destination-leg rows may advance hold or epoch.
func (c *CordLedger) LegBEligible() bool {
	return c.Waves.Settled() && c.Prb.LegBIODone
}

// VerifiedReady gates whether verified byte counts may catch synced bytes.
func (c *CordLedger) VerifiedReady() bool {
	if c.Pipe == nil {
		return false
	}
	return c.Waves.Settled() && c.Pipe.Closed && c.Prb.HoleDebt == 0 &&
		c.Prb.HolesCleared && c.Prb.ContentCaught
}

func CordSealGrade(pipe *StagePipe, waves WaveFlags, prb PrbFixture) int {
	return NewCord(pipe, waves, prb).SealGrade()
}
"""
)

shift = Path("/app/environment/gate/shift_s.go")
shift.write_text(
    shift.read_text().replace(
        """func finalize_pipe(pipe *store.StagePipe) *store.StagePipe {
	out := *pipe
	if out.Staged > 0 {
		out.Closed = true
	}
	if out.HolesCleared && out.ContentCaught {
		out.Closed = true
	}
	return &out
}""",
        """func finalize_pipe(pipe *store.StagePipe) *store.StagePipe {
	out := *pipe
	if out.HolesCleared && out.ContentCaught {
		out.Closed = true
	}
	return &out
}""",
        1,
    )
)

settle = Path("/app/environment/engine/settle_h.go")
settle.write_text(
    """package engine

import "blkmir/store"

type settleView struct {
	debtOpen bool
	axisOpen bool
}

func viewFrom(prb store.PrbFixture) settleView {
	return settleView{
		debtOpen: prb.HoleDebt > 0,
		axisOpen: !prb.HolesCleared || !prb.ContentCaught,
	}
}

func fold_w(pipe *store.StagePipe, prb store.PrbFixture, waves store.WaveFlags, cord *store.CordLedger) (int, int) {
	return SettlePhased(pipe, prb, waves, cord)
}

func settle_z(pipe *store.StagePipe, prb store.PrbFixture, waves store.WaveFlags, cord *store.CordLedger) (int, int) {
	_ = viewFrom(prb)
	return fold_w(pipe, prb, waves, cord)
}
"""
)

account = Path("/app/environment/engine/account.go")
account.write_text(
    """package engine

import "blkmir/store"

func CreditVerified(pipe *store.StagePipe, waves store.WaveFlags, cord *store.CordLedger) int {
	if cord != nil && cord.VerifiedReady() {
		return pipe.Staged
	}
	_ = waves
	return 0
}

func SettlePhased(pipe *store.StagePipe, prb store.PrbFixture, waves store.WaveFlags, cord *store.CordLedger) (int, int) {
	synced := pipe.Staged
	verified := CreditVerified(pipe, waves, cord)
	_ = prb
	return synced, verified
}
"""
)

run_go = Path("/app/environment/engine/run.go")
run_go.write_text(
    run_go.read_text().replace(
        "cordRaw := buildCord(pipeRaw, waves, prbEarly)\n\tcordFinal := buildCord(pipeFinal, waves, prbEarly)\n\tcord := cordRaw\n\t_ = cordFinal",
        "cord := buildCord(pipeFinal, waves, prbEarly)",
        1,
    )
)

pack = Path("/app/environment/store/pack_r.go")
pack.write_text(
    pack.read_text().replace(
        """func pack_r(root string, cat CatFixture, prb PrbFixture, seal int) (int, int) {
	lanes := readLaneCfg(root)
	lanes.ProbeLane = lanes.CatalogLane
	return lane_s(cat, prb, lanes, seal)
}""",
        """func pack_r(root string, cat CatFixture, prb PrbFixture, seal int) (int, int) {
	return lane_s(cat, prb, readLaneCfg(root), seal)
}""",
        1,
    )
)

lane = Path("/app/environment/store/lane_s.go")
lane.write_text(
    """package store

func lane_s(cat CatFixture, prb PrbFixture, lanes LaneCfg, seal int) (int, int) {
	catEpoch := cat.Epoch
	prbEpoch := prb.Epoch
	_ = seal
	if lanes.CatalogLane == lanes.ProbeLane {
		return prbEpoch, catEpoch
	}
	return catEpoch, prbEpoch
}

func LaneEpochs(cat CatFixture, prb PrbFixture, lanes LaneCfg, seal int) (int, int) {
	return lane_s(cat, prb, lanes, seal)
}
"""
)

latch = Path("/app/environment/stride/latch_k.go")
latch.write_text(
    latch.read_text().replace(
        """func latch_k(pipe *store.StagePipe, prb store.PrbFixture, rank int, waves store.WaveFlags) bool {
	_ = rank
	_ = waves
	if prb.PresentMark && pipe.Staged > 0 {
		return true
	}
	return false
}""",
        """func latch_k(pipe *store.StagePipe, prb store.PrbFixture, rank int, waves store.WaveFlags) bool {
	_ = rank
	if waves.Settled() && prb.LegBIODone && pipe.HolesCleared && pipe.ContentCaught {
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
	if !store.TraceLatchSealed(outDir, cycle-1) {
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
	}
	_ = ctx.Waves""",
        """	if next.LegID == "leg-b" && !ctx.LegBOpen {
		return out, nil
	}
	if next.HoldMS > 0 {
		out.HoldMS = next.HoldMS
		out.Epoch = prior.Epoch + 1
	} else if ctx.Cycle > 0 && next.LegID == "leg-b" && ctx.Waves.Settled() {
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
    ).replace(
        """	aBase, bBase := packedBaseline(ctx, cat, prb)
	rows := []store.SegmentRow{
		{LegID: "leg-a", ByteOffset: 0, Epoch: aBase},
		{
			LegID:      "leg-b",
			ByteOffset: prb.DelayedOffset,
			HoldMS:     0,
			Epoch:      bBase,
			IODone:     prb.LegBIODone,
		},
	}""",
        """	aBase, bBase := packedBaseline(ctx, cat, prb)
	bEpoch := bBase
	if !prb.LegBIODone && bEpoch > aBase {
		bEpoch = aBase
	}
	rows := []store.SegmentRow{
		{LegID: "leg-a", ByteOffset: 0, Epoch: aBase},
		{
			LegID:      "leg-b",
			ByteOffset: prb.DelayedOffset,
			HoldMS:     0,
			Epoch:      bEpoch,
			IODone:     prb.LegBIODone,
		},
	}""",
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
    ("/app/environment/store/cord_m.go", "c.Waves.Settled() && c.Pipe.Closed"),
    ("/app/environment/gate/shift_s.go", "out.HolesCleared && out.ContentCaught"),
    ("/app/environment/engine/account.go", "cord.VerifiedReady()"),
    ("/app/environment/engine/settle_h.go", "SettlePhased"),
    ("/app/environment/engine/run.go", "buildCord(pipeFinal, waves, prbEarly)"),
    ("/app/environment/store/pack_r.go", "readLaneCfg(root)"),
    ("/app/environment/stride/latch_k.go", "waves.Settled()"),
    ("/app/environment/engine/snap_q.go", "FuseViews(cat, prb, seal)"),
    ("/app/environment/store/slot_k.go", "c.VerifiedBytes == c.SyncedBytes"),
    ("/app/environment/phase/stamp_r.go", "sideB := clip_x(snap)"),
    ("/app/environment/engine/rebase_v.go", "TraceLatchSealed"),
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
