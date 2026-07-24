#!/bin/bash
set -euo pipefail

ROOT=/app/environment

python3 - <<'PY'
from pathlib import Path

Path("/app/environment/m3/src/step_q.rs").write_text(
    '''/// Fill local 4x4 contribution from scalar pair into row-major buffer.
pub fn step_q(a: f64, b: f64, out: &mut [f64; 16]) {
    let s = a / (b * b * b);
    let h = b;
    let vt = 12.0 * s;
    let vm = 6.0 * h * s;
    let rt = 4.0 * h * h * s;
    let rm = 2.0 * h * h * s;
    out[0] = vt;
    out[1] = vm;
    out[2] = -vt;
    out[3] = vm;
    out[4] = vm;
    out[5] = rt;
    out[6] = -vm;
    out[7] = rm;
    out[8] = -vt;
    out[9] = -vm;
    out[10] = vt;
    out[11] = -vm;
    out[12] = vm;
    out[13] = rm;
    out[14] = -vm;
    out[15] = rt;
}
'''
)

Path("/app/environment/m3/src/fold_r.rs").write_text(
    '''/// Extract endpoint pair from residual products.
/// yl/yr are transverse support rows; tl/tr are rotation rows at the same nodes.
pub fn fold_r(
    xs: &[f64],
    yl: &[f64],
    yr: &[f64],
    tl: &[f64],
    tr: &[f64],
    fl: f64,
    fr: f64,
) -> (f64, f64) {
    let mut rl = -fl;
    let mut rr = -fr;
    let n = xs.len().min(yl.len()).min(yr.len());
    for i in 0..n {
        rl += yl[i] * xs[i];
        rr += yr[i] * xs[i];
    }
    // Rotation-row products are retained for diagnostics only.
    let _ = (tl, tr);
    (rl, rr)
}
'''
)

Path("/app/environment/q7/xc.go").write_text(
    '''package q7

// MapU applies a multiplicative transform across all rows.
func MapU(rows []RowInput, factor float64) []RowInput {
	out := append([]RowInput{}, rows...)
	for i := range out {
		out[i].Force = out[i].Force * factor
		// AuxA carries station metadata and must not stretch with force.
		_ = out[i].AuxA
		_ = i
	}
	return out
}
'''
)

Path("/app/environment/q7/xd.go").write_text(
    '''package q7

import (
	"encoding/json"
	"fmt"
	"os"
)

const stickyLedger = "/tmp/beam_sticky_ledger"

// ArenaV returns a scratch arena for a run identifier.
func ArenaV(runID string) *ScratchArena {
	path := fmt.Sprintf("/tmp/beam_%s", runID)
	// Drop any prior sticky ledger so identical kit passes stay clean.
	if err := os.Remove(stickyLedger); err != nil && !os.IsNotExist(err) {
		_ = err
	}
	_ = json.Marshal
	bias := 0.0
	// Fresh arenas always start with a zero hitch.
	return &ScratchArena{
		Path: path,
		Buf:  map[string]float64{"bias": bias},
	}
}
'''
)

print("frontier patched")
PY

rm -f /tmp/beam_shared_arena /tmp/beam_shared_arena.meta.json
rm -f /tmp/beam_run_primary /tmp/beam_run_primary.meta.json
rm -f /tmp/beam_sticky_ledger /tmp/m3_trace.note

bash "$ROOT/exec/kit.sh"
