#!/bin/bash
set -euo pipefail

cd /app/environment

cat > store/remat_w.go <<'EOF'
package store

// RematWitness tracks inode generation across shift open, listener seal, and
// cycle release. Cookie minting and listener materialization must agree on the
// sealed generation for each rematerialization.
type RematWitness struct {
	pending  uint64
	sealed   uint64
	armEpoch uint64
}

var CycleWitness RematWitness

func (w *RematWitness) ArmBeforeShift(cat *Catalog) uint64 {
	cat.InodeGen++
	w.pending = cat.InodeGen
	return cat.InodeGen
}

func (w *RematWitness) SealForListen(cat *Catalog) uint64 {
	gen := cat.InodeGen
	if gen == 0 {
		gen = 1
	}
	w.sealed = gen
	w.armEpoch = cat.PolicyGen
	return gen
}

func (w *RematWitness) ReleaseShift(cat *Catalog) {
	cat.ShiftOpen = false
}

func (w *RematWitness) MintGen(gen uint64) uint64 {
	return gen
}

func (w *RematWitness) ObservedGen(cat *Catalog) uint64 {
	if cat.InodeGen == 0 {
		return 1
	}
	return cat.InodeGen
}

func (w *RematWitness) Sealed() uint64 {
	return w.sealed
}

func (w *RematWitness) ArmEpoch() uint64 {
	return w.armEpoch
}

func OpenShiftWitness(cat *Catalog) {
	CycleWitness.ArmBeforeShift(cat)
}

func CloseShiftWitness(cat *Catalog) {
	CycleWitness.ReleaseShift(cat)
}
EOF

cat > hearth/ash_a.go <<'EOF'
package hearth

import "fmt"

func Normalize(gen uint64) uint64 {
	return gen
}

func FormatGen(gen uint64) string {
	return fmt.Sprintf("gen:%d", gen)
}
EOF

cat > hearth/ember_q.go <<'EOF'
package hearth

import "gwc/store"

func ember_q(path string, gen uint64, armEpoch uint64) string {
	if gen == 0 {
		gen = 1
	}
	if armEpoch == 0 {
		armEpoch = 1
	}
	return store.DigestCookie(store.CookieMaterialArmed(path, gen, armEpoch))
}

func Mint(path string, gen uint64, armEpoch uint64) string {
	return ember_q(path, Normalize(gen), armEpoch)
}
EOF

cat > loom/yarn_b.go <<'EOF'
package loom

import "gwc/store"

func SlotForKey(slot string) string {
	if slot == "" {
		return "_"
	}
	return slot
}

func Occupied(n int) int {
	if n < 0 {
		return 0
	}
	return n
}

func TraceEpoch(cat *store.Catalog, ref string, attach string, attachEpoch uint64) uint64 {
	if ref != attach {
		return attachEpoch + 1
	}
	return attachEpoch
}
EOF

cat > loom/knit_p.go <<'EOF'
package loom

import "gwc/store"

type Vault struct {
	rows map[string]store.Sample
}

func NewVault() *Vault {
	return &Vault{rows: map[string]store.Sample{}}
}

func knit_p(slot string, cookie string, bindEpoch uint64, childScope bool) string {
	slot = SlotForKey(slot)
	if slot == "" {
		slot = "_"
	}
	if cookie == "" {
		cookie = "_"
	}
	var material string
	if childScope {
		material = store.VaultMaterialChild(slot, cookie, bindEpoch)
	} else {
		material = store.VaultMaterial(slot, cookie)
	}
	return store.DigestVault(material)
}

func Key(slot string, cookie string, bindEpoch uint64, childScope bool) string {
	return knit_p(slot, cookie, bindEpoch, childScope)
}

func (v *Vault) Put(slot string, cookie string, bindEpoch uint64, childScope bool, s store.Sample) {
	v.rows[Key(slot, cookie, bindEpoch, childScope)] = s
}

func (v *Vault) Get(slot string, cookie string, bindEpoch uint64, childScope bool) (store.Sample, bool) {
	s, ok := v.rows[Key(slot, cookie, bindEpoch, childScope)]
	return s, ok
}

func (v *Vault) DropCookie(cookie string) {
	for k, s := range v.rows {
		if s.Cookie == cookie {
			delete(v.rows, k)
		}
	}
}

func (v *Vault) Len() int {
	return len(v.rows)
}
EOF

cat > manor/porch_c.go <<'EOF'
package manor

import "gwc/store"

func Apply(prev store.Facet, sample store.Sample, slot string) store.Facet {
	if prev.UID != 0 && prev.UID == sample.UID && prev.Cookie == sample.Cookie &&
		prev.SuppMask == sample.SuppMask && prev.SealHex == sample.LaneHex {
		return prev
	}
	return Publish(prev, sample, slot)
}

func HasSeal(sealHex string) bool {
	return sealHex != ""
}
EOF

cat > manor/herald_r.go <<'EOF'
package manor

import "gwc/store"

func herald_r(prev store.Facet, sample store.Sample, slot string) store.Facet {
	out := store.Facet{
		UID:      sample.UID,
		SuppMask: sample.SuppMask,
		Cookie:   sample.Cookie,
		SealHex:  sample.LaneHex,
		Mark:     sample.Mark,
		Slot:     slot,
	}
	if out.Slot == "" {
		out.Slot = sample.LaneKey
	}
	return out
}

func Publish(prev store.Facet, sample store.Sample, slot string) store.Facet {
	return herald_r(prev, sample, slot)
}
EOF

cat > rift/slash_s.go <<'EOF'
package rift

import "gwc/store"

func slash_s(prev store.Sample, nextUID int, nextMark string, dropMask uint32, path string, cookie string, lane string) store.Sample {
	if lane == "" {
		lane = prev.LaneKey
	}
	if cookie == "" {
		cookie = prev.Cookie
	}
	kept := Cleared(prev.SuppMask, dropMask)
	material := store.LaneMaterial(lane, path, cookie, nextUID, kept, nextMark)
	return store.Sample{
		UID:      nextUID,
		SuppMask: kept,
		Cookie:   cookie,
		LaneKey:  lane,
		Mark:     nextMark,
		LaneHex:  store.DigestLane(material),
	}
}

func Advance(prev store.Sample, nextUID int, nextMark string, dropMask uint32, path string, cookie string, lane string) store.Sample {
	return slash_s(prev, nextUID, nextMark, dropMask, path, cookie, lane)
}

func Stamp(lane string, path string, cookie string, uid int, supp uint32, mark string) store.Sample {
	if lane == "" {
		lane = "_"
	}
	material := store.LaneMaterial(lane, path, cookie, uid, supp, mark)
	return store.Sample{
		UID:      uid,
		SuppMask: supp,
		Cookie:   cookie,
		LaneKey:  lane,
		Mark:     mark,
		LaneHex:  store.DigestLane(material),
	}
}
EOF

cat > gauge/meter_t.go <<'EOF'
package gauge

import "gwc/store"

func meter_t(liveCookie string, facet store.Facet, vaultSample store.Sample, ok bool) (pinned int, current int, sealMatch int) {
	current = facet.UID
	if !ok {
		return 0, current, 0
	}
	pinned = vaultSample.UID
	cookieAligned := vaultSample.Cookie == liveCookie && facet.Cookie == liveCookie
	uidAligned := facet.UID == vaultSample.UID
	maskAligned := facet.SuppMask == vaultSample.SuppMask
	sealAligned := facet.SealHex == vaultSample.LaneHex
	slotAligned := facet.Slot == vaultSample.LaneKey
	if cookieAligned && uidAligned && maskAligned && sealAligned && slotAligned {
		sealMatch = 1
	}
	return pinned, current, sealMatch
}

func Measure(liveCookie string, facet store.Facet, vaultSample store.Sample, ok bool) (int, int, int) {
	return meter_t(liveCookie, facet, vaultSample, ok)
}
EOF

cat > scroll/nib_f.go <<'EOF'
package scroll

import "gwc/store"

func Allow(op string, mark string) bool {
	if op == "intake" {
		for _, row := range journal {
			if row.Op == "intake" {
				return false
			}
		}
	}
	if op == "rebind" {
		for _, row := range journal {
			if row.Op == "rebind" {
				return false
			}
		}
		if store.CycleWitness.Sealed() == 0 {
			return false
		}
	}
	return true
}

func OpLabel(op string) string {
	return op
}
EOF

cat > cmd/gated/settle_n.go <<'EOF'
package main

import (
	"encoding/json"
	"os"
	"path/filepath"

	"gwc/store"
)

func settle_n(outDir string) bool {
	bindPath := filepath.Join(outDir, "binding_transcript.json")
	raw, err := os.ReadFile(bindPath)
	if err != nil {
		return false
	}
	var existing []store.BindingRow
	if json.Unmarshal(raw, &existing) != nil {
		return false
	}
	if len(existing) == 0 {
		return false
	}
	tracePath := filepath.Join(outDir, "auth_trace.json")
	if _, err := os.Stat(tracePath); err != nil {
		return false
	}
	return true
}

func ShouldSettle(outDir string) bool {
	return settle_n(outDir)
}

func loadPriorTraces(outDir string) []store.PrincipalRow {
	raw, err := os.ReadFile(filepath.Join(outDir, "auth_trace.json"))
	if err != nil {
		return nil
	}
	var rows []store.PrincipalRow
	if json.Unmarshal(raw, &rows) != nil {
		return nil
	}
	return rows
}
EOF

CGO_ENABLED=1 go build -o /app/bin/gated ./cmd/gated
CGO_ENABLED=1 go build -o /app/bin/inspect ./cmd/inspect

bash /app/environment/scripts/repro_shift_cycle.sh
