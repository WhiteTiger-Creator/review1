#!/usr/bin/env bash
set -euo pipefail

cat > /app/environment/g6_hst/floors.go <<'GO'
package g6_hst

import "wavellite_dc/q4"

func MatchFloors(in []q4.Unit, req q4.HostReq) ([]q4.Unit, int) {
	permitted := make(map[string]struct{}, len(req.Firmware))
	for _, tag := range req.Firmware {
		permitted[tag] = struct{}{}
	}
	held := 0
	out := make([]q4.Unit, 0, len(in))
	for _, u := range in {
		if u.ReadyNodes < req.MinNodes {
			held++
			continue
		}
		if len(permitted) > 0 {
			if _, ok := permitted[u.Firmware]; !ok {
				held++
				continue
			}
		}
		out = append(out, u)
	}
	return out, held
}
GO

cat > /app/environment/t3_vol/usable.go <<'GO'
package t3_vol

import "wavellite_dc/q4"

func UsableAfterLoss(in []q4.Unit, req q4.VolReq) ([]q4.Unit, int) {
	held := 0
	out := make([]q4.Unit, 0, len(in))
	for _, u := range in {
		available := u.RawTB - u.DegradedTB
		if available < req.MinUsable {
			held++
			continue
		}
		if u.Replicas < req.MinCopies {
			held++
			continue
		}
		out = append(out, u)
	}
	return out, held
}
GO

cat > /app/environment/w9_lnk/pairing.go <<'GO'
package w9_lnk

import "wavellite_dc/q4"

func RequirePair(in []q4.Unit, req q4.LinkReq) ([]q4.Unit, int) {
	held := 0
	out := make([]q4.Unit, 0, len(in))
	for _, u := range in {
		live := 0
		for _, path := range u.Uplinks {
			if !path.Healthy {
				continue
			}
			if path.Gbps < req.MinRate {
				continue
			}
			live++
		}
		if live < req.MinPaths {
			held++
			continue
		}
		out = append(out, u)
	}
	return out, held
}
GO

cat > /app/environment/y5_qrm/roles.go <<'GO'
package y5_qrm

import "wavellite_dc/q4"

func DistinctRoles(in []q4.Unit, ledger []q4.Approval, req q4.SignReq) ([]q4.Unit, int) {
	held := 0
	out := make([]q4.Unit, 0, len(in))
	for _, u := range in {
		seen := map[string]struct{}{}
		for _, entry := range ledger {
			if entry.Unit != u.ID {
				continue
			}
			if entry.ExpiresEpoch <= req.Epoch {
				continue
			}
			seen[entry.Role] = struct{}{}
		}
		if len(seen) < req.MinRoles {
			held++
			continue
		}
		missing := false
		for _, tag := range req.Roles {
			if _, ok := seen[tag]; !ok {
				missing = true
				break
			}
		}
		if missing {
			held++
			continue
		}
		out = append(out, u)
	}
	return out, held
}
GO

cat > /app/environment/b7_win/recency.go <<'GO'
package b7_win

import "wavellite_dc/q4"

func RecentUnresolved(in []q4.Unit, ledger []q4.MaintRec, req q4.WinReq) ([]q4.Unit, int) {
	pick := map[string]q4.MaintRec{}
	for _, entry := range ledger {
		current, ok := pick[entry.Unit]
		if !ok || entry.Epoch > current.Epoch {
			pick[entry.Unit] = entry
		}
	}
	held := 0
	out := make([]q4.Unit, 0, len(in))
	for _, u := range in {
		entry, ok := pick[u.ID]
		if ok {
			if !entry.Resolved {
				held++
				continue
			}
			if req.Epoch-entry.Epoch < req.Cool {
				held++
				continue
			}
		}
		out = append(out, u)
	}
	return out, held
}
GO

cat > /app/environment/f2_wgt/classes.go <<'GO'
package f2_wgt

import "wavellite_dc/q4"

func AdmitClass(in []q4.Unit, req q4.ZoneReq) ([]q4.Unit, int) {
	if len(req.Classes) == 0 {
		out := make([]q4.Unit, 0, len(in))
		out = append(out, in...)
		return out, 0
	}
	permitted := make(map[string]struct{}, len(req.Classes))
	for _, tag := range req.Classes {
		permitted[tag] = struct{}{}
	}
	held := 0
	out := make([]q4.Unit, 0, len(in))
	for _, u := range in {
		if _, ok := permitted[u.Class]; !ok {
			held++
			continue
		}
		out = append(out, u)
	}
	return out, held
}

func WeighTier(in []q4.Unit, req q4.ZoneReq) int {
	total := 0
	for _, u := range in {
		factor, ok := req.Weights[u.Region]
		if !ok {
			factor = 1
		}
		total += u.Tier * factor
	}
	return total
}
GO

cat > /app/environment/d8_bgt/draw.go <<'GO'
package d8_bgt

import (
	"sort"

	"wavellite_dc/q4"
)

func FitDraw(in []q4.Unit, ceiling int) ([]q4.Unit, int) {
	ordered := append([]q4.Unit(nil), in...)
	sort.SliceStable(ordered, func(i, j int) bool {
		if ordered[i].Tier != ordered[j].Tier {
			return ordered[i].Tier > ordered[j].Tier
		}
		return ordered[i].ID < ordered[j].ID
	})
	consumed := 0
	held := 0
	out := make([]q4.Unit, 0, len(ordered))
	for _, u := range ordered {
		if consumed+u.DrawKW > ceiling {
			held++
			continue
		}
		consumed += u.DrawKW
		out = append(out, u)
	}
	return out, held
}
GO

cat > /app/environment/x6_sig/mark.go <<'GO'
package x6_sig

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"

	"wavellite_dc/q4"
)

func BindMark(row q4.SiteRow) string {
	text := fmt.Sprintf(
		"{\"name\":\"%s\",\"stats\":{\"approval_blocks\":%d,\"capacity_trims\":%d,"+
			"\"certified_count\":%d,\"compute_blocks\":%d,\"maintenance_blocks\":%d,"+
			"\"network_blocks\":%d,\"rack_count\":%d,\"readiness_index\":%d,"+
			"\"region_rejections\":%d,\"storage_blocks\":%d}}",
		row.Name,
		row.ApprovalBlocks,
		row.CapacityTrims,
		row.CertifiedCount,
		row.ComputeBlocks,
		row.MaintenanceBlocks,
		row.NetworkBlocks,
		row.RackCount,
		row.ReadinessIndex,
		row.RegionRejections,
		row.StorageBlocks,
	)
	sum := sha256.Sum256([]byte(text))
	return hex.EncodeToString(sum[:])
}
GO

make -C /app/environment all
make -C /app/environment report
