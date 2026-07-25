#!/bin/bash
set -euo pipefail

cd /app

# ---------------------------------------------------------------------------
# Scalar profile: SI depth conversion, full elastic storage, transient mode,
# no packing adjustment, identified properties in force, contract closure band.
# ---------------------------------------------------------------------------
cat > /app/config/basin-profile.toml <<'TOML'
# GW-Basin-12 scalar profile — conservation-admissible vector.
# The integrity stamp embedded in the runtime covers every scalar in the
# [depth], [stress_envelope] and [mode] sections of this file.

[depth]
mm_to_m_divisor = 1000.0

[stress_envelope]
wilt_head_m = 10.0
field_head_m = 25.0

[mode]
use_steady_state = false
storage_scale = 1.0
apply_packing = false
prefer_certificate = false
campaign_tolerance_m3 = 0.000001

# Property certificate issued with the 2024 seasonal campaign package.
[certificate]
recharge_efficiency = 0.28
crop_factor = 0.75

[certificate.conductivity]
C01 = 4.0
C02 = 2.8
C03 = 5.76

[certificate.specific_yield]
C01 = 0.176
C02 = 0.144
C03 = 0.200
TOML

# ---------------------------------------------------------------------------
# Derive the integrity stamp of the scalar vector just written, using the same
# FNV-1a formatting the runtime applies, then embed it in the resolver.
# ---------------------------------------------------------------------------
mkdir -p /tmp/stampgen
cat > /tmp/stampgen/main.go <<'GO'
package main

import (
	"bufio"
	"fmt"
	"hash/fnv"
	"os"
	"strconv"
	"strings"
)

func main() {
	f, err := os.Open(os.Args[1])
	if err != nil {
		panic(err)
	}
	defer f.Close()

	div, wilt, field, scale, tol := 0.0, 0.0, 0.0, 0.0, 0.0
	steady, packing, prefer := false, false, false
	section := ""
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		if strings.HasPrefix(line, "[") && strings.HasSuffix(line, "]") {
			section = strings.Trim(line, "[]")
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			continue
		}
		key := strings.TrimSpace(parts[0])
		val := strings.Trim(strings.TrimSpace(parts[1]), `"`)
		num, _ := strconv.ParseFloat(val, 64)
		truthy := val == "true" || val == "1" || val == "yes"
		switch section + "." + key {
		case "depth.mm_to_m_divisor":
			div = num
		case "stress_envelope.wilt_head_m":
			wilt = num
		case "stress_envelope.field_head_m":
			field = num
		case "mode.storage_scale":
			scale = num
		case "mode.campaign_tolerance_m3":
			tol = num
		case "mode.use_steady_state":
			steady = truthy
		case "mode.apply_packing":
			packing = truthy
		case "mode.prefer_certificate":
			prefer = truthy
		}
	}
	if err := sc.Err(); err != nil {
		panic(err)
	}

	h := fnv.New64a()
	fmt.Fprintf(h, "%.6f|%.6f|%.6f|%.6f|%t|%t|%t|%.6f",
		div, wilt, field, scale, steady, packing, prefer, tol)
	fmt.Print(h.Sum64())
}
GO
cd /tmp/stampgen
go mod init stampgen >/dev/null 2>&1 || true
STAMP="$(go run . /app/config/basin-profile.toml)"
cd /app
if [ -z "$STAMP" ]; then
  echo "stamp derivation produced no value" >&2
  exit 1
fi
echo "derived scalar stamp: ${STAMP}"

# ---------------------------------------------------------------------------
# Apply the staged corrections across the editable sources.
# ---------------------------------------------------------------------------
python3 - "$STAMP" <<'PY'
import pathlib
import sys

stamp = sys.argv[1]


def edit(path, pairs):
    p = pathlib.Path(path)
    text = p.read_text()
    for old, new in pairs:
        assert old in text, f"{path}: anchor not found:\n{old}"
        assert text.count(old) == 1, f"{path}: anchor is not unique:\n{old}"
        text = text.replace(old, new)
    p.write_text(text)


# Stage B: the straight-line abscissa is the decimal logarithm of elapsed time.
edit("/app/internal/f7t/estimators.go", [
    (
        "// The abscissa is the logarithm of elapsed time in minutes. Field kits record\n"
        "// elapsed time on a natural-logarithm ruling, so the slope is taken directly\n"
        "// against math.Log of the elapsed minutes.",
        "// The abscissa is the decimal logarithm of elapsed time in minutes, so the\n"
        "// slope is a drawdown increment per decimal log cycle of time.",
    ),
    ("\t\tx := math.Log(elapsedMin[i])", "\t\tx := math.Log10(elapsedMin[i])"),
    # Stage C: the storage response is strictly proportional, with no offset term.
    (
        "// Storage-response trials are referenced to the pre-trial static head, so the\n"
        "// regression carries an additive offset term to absorb the datum shift.",
        "// The storage response is strictly proportional: a zero injected volume gives a\n"
        "// zero head rise, so the slope is taken through the origin with no offset term.",
    ),
    (
        "\tn := float64(len(x))\n"
        "\tvar sx, sy, sxy, sxx float64\n"
        "\tfor i := range x {\n"
        "\t\tsx += x[i]\n"
        "\t\tsy += y[i]\n"
        "\t\tsxy += x[i] * y[i]\n"
        "\t\tsxx += x[i] * x[i]\n"
        "\t}\n"
        "\tden := n*sxx - sx*sx\n"
        "\tif math.Abs(den) < 1e-15 {\n"
        "\t\treturn 0, ErrDegenerate\n"
        "\t}\n"
        "\treturn (n*sxy - sx*sy) / den, nil",
        "\tvar sxy, sxx float64\n"
        "\tfor i := range x {\n"
        "\t\tsxy += x[i] * y[i]\n"
        "\t\tsxx += x[i] * x[i]\n"
        "\t}\n"
        "\tif math.Abs(sxx) < 1e-15 {\n"
        "\t\treturn 0, ErrDegenerate\n"
        "\t}\n"
        "\treturn sxy / sxx, nil",
    ),
])

# Stage A: only straight-line-window samples enter the conductivity fit.
# Stage D/F: the scalar stamp tracks the vector actually in force.
edit("/app/internal/q4c/resolve.go", [
    (
        "\t\tfor _, s := range test.Samples {\n"
        "\t\t\txs = append(xs, s.ElapsedMin)\n"
        "\t\t\tys = append(ys, s.DrawdownM)\n"
        "\t\t}",
        "\t\tfor _, s := range test.Samples {\n"
        "\t\t\tif !s.InStraightLineWindow {\n"
        "\t\t\t\tcontinue\n"
        "\t\t\t}\n"
        "\t\t\txs = append(xs, s.ElapsedMin)\n"
        "\t\t\tys = append(ys, s.DrawdownM)\n"
        "\t\t}",
    ),
    (
        "const profileStamp uint64 = 4579007983133597389",
        f"const profileStamp uint64 = {stamp}",
    ),
])

# Stage D: the stress reference head is the mid-period average.
# Stage A/E: only qualified campaign records enter the inversion.
edit("/app/internal/b3t/budget.go", [
    (
        "// The SCADA snapshot is taken at period close, so the end-of-period head is the\n"
        "// reference head for the stress envelope.",
        "// The reference head is the mid-period average of the start and end heads.",
    ),
    (
        "\treturn clamp01((headEndM - wiltM) / den)",
        "\treturn clamp01((0.5*(headStartM+headEndM) - wiltM) / den)",
    ),
    (
        "\tfor _, rec := range ev.Calibration {\n"
        "\t\tcell, ok := ev.Cells[rec.CellID]\n"
        "\t\tif !ok {\n"
        "\t\t\tcontinue\n"
        "\t\t}",
        "\tfor _, rec := range ev.Calibration {\n"
        "\t\tif !rec.Qualified {\n"
        "\t\t\tcontinue\n"
        "\t\t}\n"
        "\t\tcell, ok := ev.Cells[rec.CellID]\n"
        "\t\tif !ok {\n"
        "\t\t\tcontinue\n"
        "\t\t}",
    ),
])

# Stage F: ascending period_id ordering, contract closure band, and summary
# totals that stay the arithmetic sums of the emitted period rows.
edit("/app/internal/r9p/emit.go", [
    (
        "\t// Rows are grouped per mesh cell so that per-cell budgets read contiguously.\n"
        "\tsort.SliceStable(rows, func(i, j int) bool {\n"
        "\t\tif rows[i].CellID != rows[j].CellID {\n"
        "\t\t\treturn rows[i].CellID < rows[j].CellID\n"
        "\t\t}\n"
        "\t\treturn rows[i].PeriodID < rows[j].PeriodID\n"
        "\t})",
        "\t// Rows are emitted as a flat array in ascending period_id order.\n"
        "\tsort.SliceStable(rows, func(i, j int) bool {\n"
        "\t\treturn rows[i].PeriodID < rows[j].PeriodID\n"
        "\t})",
    ),
    (
        "\ttolerance := cal.CampaignToleranceM3\n"
        "\tif tolerance <= 0 {\n"
        "\t\ttolerance = ClosureToleranceM3\n"
        "\t}",
        "\t// Closure is evaluated against the contract tolerance, which is not tunable.\n"
        "\ttolerance := ClosureToleranceM3",
    ),
    (
        "\t// Historian reconciliation of the summed recharge against the archive\n"
        "\t// divisor. Operations records this as a validation-only pass.\n"
        "\tif cal.DepthDivisor > 0 {\n"
        "\t\ttotalRecharge = totalRecharge * (cal.DepthDivisor / archivalDivisor)\n"
        "\t}\n\n",
        "",
    ),
])

# archivalDivisor is no longer referenced once the summary rescale is gone.
p = pathlib.Path("/app/internal/r9p/emit.go")
text = p.read_text()
anchor = (
    "// archivalDivisor is the depth divisor of the historian archive that summary\n"
    "// recharge totals are reconciled against.\n"
    "const archivalDivisor = 100.0\n\n"
)
assert anchor in text, "r9p: archival divisor declaration not found"
p.write_text(text.replace(anchor, ""))
print("staged corrections applied")
PY

gofmt -l /app/internal /app/cmd
make clean
make

mkdir -p /app/output
/app/bin/basin-flux

python3 -c "
import json
with open('/app/output/water_budget_report.json') as f:
    doc = json.load(f)
s = doc['summary']
print('periods', [p['period_id'] for p in doc['periods']])
print('eta/crop %.9f %.9f' % (s['recharge_efficiency'], s['crop_factor']))
print('max residual', s['max_balance_residual_m3'], 'compliant', s['periods_compliant'], '/', s['period_count'])
"
