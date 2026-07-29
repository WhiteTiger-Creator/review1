package model

import (
	"crypto/sha256"
	"encoding/hex"
	"strings"
)

const TopologyBlock = `name=bootmirror level=raid1 uuid=11111111-2222-3333-4444-555555555555 members=3 active_needed=1 spare_group=boot bitmap=internal boot_degraded=allow
name=data5 level=raid5 uuid=aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee members=3 active_needed=3 spare_group=data bitmap=none boot_degraded=refuse
name=fast10 level=raid10 uuid=ffffffff-0000-1111-2222-333333333333 members=4 active_needed=2 spare_group=fast bitmap=internal boot_degraded=refuse
`

const ForeignUUID = "99999999-aaaa-bbbb-cccc-ddddeeeeffff"

type ArraySpec struct {
	Name         string
	Level        string
	UUID         string
	Members      int
	ActiveNeeded int
	SpareGroup   string
	Bitmap       string
	BootDegraded string
	ScrubDOM     int
	DOMMin       int
	DOMMax       int
	FloorKib     int
}

func Specs() []ArraySpec {
	return []ArraySpec{
		{Name: "bootmirror", Level: "raid1", UUID: "11111111-2222-3333-4444-555555555555", Members: 3, ActiveNeeded: 1, SpareGroup: "boot", Bitmap: "internal", BootDegraded: "allow", ScrubDOM: 1, DOMMin: 1, DOMMax: 7, FloorKib: 20000},
		{Name: "data5", Level: "raid5", UUID: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", Members: 3, ActiveNeeded: 3, SpareGroup: "data", Bitmap: "none", BootDegraded: "refuse", ScrubDOM: 8, DOMMin: 8, DOMMax: 14, FloorKib: 80000},
		{Name: "fast10", Level: "raid10", UUID: "ffffffff-0000-1111-2222-333333333333", Members: 4, ActiveNeeded: 2, SpareGroup: "fast", Bitmap: "internal", BootDegraded: "refuse", ScrubDOM: 15, DOMMin: 15, DOMMax: 28, FloorKib: 60000},
	}
}

func Digest() string {
	payload := "\n" + TopologyBlock
	sum := sha256.Sum256([]byte(payload))
	return hex.EncodeToString(sum[:])
}

func NormUUID(u string) string {
	return strings.ToLower(strings.TrimSpace(u))
}
