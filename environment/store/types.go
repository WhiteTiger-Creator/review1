package store

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
)

type SlotRef string

type Conn struct {
	UID      int
	SuppMask uint32
	PID      int
}

type Sample struct {
	UID      int
	SuppMask uint32
	Cookie   string
	LaneKey  string
	Mark     string
	LaneHex  string
}

type Facet struct {
	UID      int
	SuppMask uint32
	Cookie   string
	SealHex  string
	Mark     string
	Slot     string
}

type Ctx struct {
	StateDir string
	OutDir   string
}

type Catalog struct {
	ActiveMark string
	DropMask   uint32
	InodeGen   uint64
	PolicyGen  uint64
	ShiftOpen  bool
	UIDByMark  map[string]int
	SuppByMark map[string]uint32
	PathByRef  map[string]string
	MarkByRef  map[string]string
}

type Listener struct {
	Path   string
	Gen    uint64
	Cookie string
}

type BindingRow struct {
	Ref       SlotRef `json:"slot_ref"`
	PolicyGen uint64  `json:"policy_epoch"`
	PathHex   string  `json:"path_digest_hex"`
}

type PrincipalRow struct {
	Ref       SlotRef `json:"slot_ref"`
	MarkHex   string  `json:"mark_digest_hex"`
	SealHex   string  `json:"seal_hex"`
	SuppMask  uint32  `json:"supp_mask"`
	PolicyGen uint64  `json:"policy_epoch"`
	Cookie    string  `json:"bind_cookie"`
}

type ProbeRow struct {
	Ref       SlotRef `json:"slot_ref"`
	CredSkew  int     `json:"cred_gap"`
	Pinned    int     `json:"pinned_uid"`
	Current   int     `json:"current_uid"`
	SealMatch int     `json:"seal_match"`
	Cookie    string  `json:"bind_cookie"`
}

type JournalRow struct {
	Op        string  `json:"op"`
	Ref       SlotRef `json:"slot_ref"`
	Mark      string  `json:"mark"`
	SealHex   string  `json:"seal_hex"`
	SuppMask  uint32  `json:"supp_mask"`
	PolicyGen uint64  `json:"policy_epoch"`
	Cookie    string  `json:"bind_cookie"`
}

type ScopeRow struct {
	Cycle           int `json:"cycle"`
	ScopeAgreeCount int `json:"scope_agreement_count"`
	TranscriptRows  int `json:"transcript_rows"`
	TraceRows       int `json:"trace_rows"`
	JournalRows     int `json:"journal_rows"`
}

type ConvergeReport struct {
	Cycles []ScopeRow `json:"cycles"`
}

func MarkHex(uid int, tag string) string {
	h := sha256.Sum256([]byte(fmt.Sprintf("%s:%d", tag, uid)))
	return hex.EncodeToString(h[:8])
}

func PathHex(path string) string {
	h := sha256.Sum256([]byte(path))
	return hex.EncodeToString(h[:16])
}

func CookieMaterial(path string, gen uint64) string {
	return fmt.Sprintf("%s|%d", path, gen)
}

func CookieMaterialArmed(path string, gen uint64, armEpoch uint64) string {
	return fmt.Sprintf("%s|%d|%d", path, gen, armEpoch)
}

func DigestCookie(material string) string {
	h := sha256.Sum256([]byte(material))
	return hex.EncodeToString(h[:8])
}

func VaultMaterial(slot string, cookie string) string {
	return fmt.Sprintf("%s|%s", slot, cookie)
}

func VaultMaterialChild(slot string, cookie string, attachEpoch uint64) string {
	return fmt.Sprintf("%s|%s|%d", slot, cookie, attachEpoch)
}

func DigestVault(material string) string {
	h := sha256.Sum256([]byte(material))
	return hex.EncodeToString(h[:8])
}

func LaneMaterial(lane string, path string, cookie string, uid int, supp uint32, mark string) string {
	return fmt.Sprintf("%s|%s|%s|%d|%d|%s", lane, path, cookie, uid, supp, mark)
}

func DigestLane(material string) string {
	h := sha256.Sum256([]byte(material))
	return hex.EncodeToString(h[:8])
}
