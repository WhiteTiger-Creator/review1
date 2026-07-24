// Package journal is the durable, monotonic record of every security
// transition. It is the source of truth used by recovery and reconciliation.
package journal

// Event kinds recorded in the journal.
const (
	KindPrepared       = "prepared"
	KindEffectApplied  = "effect_applied"
	KindCommitted      = "committed"
	KindDenied         = "denied"
	KindConflict       = "conflict"
	KindRecoveryDenied = "recovery_denied"
)

// Event is a single append-only journal record. Fields marked omitempty are
// only present when applicable to the event kind.
type Event struct {
	EventSeq           int    `json:"event_seq"`
	Event              string `json:"event"`
	RequestID          string `json:"request_id"`
	RequestDigest      string `json:"request_digest"`
	Principal          string `json:"principal"`
	Action             string `json:"action"`
	Unit               string `json:"unit"`
	ManifestGeneration int    `json:"manifest_generation"`
	ManifestDigest     string `json:"manifest_digest"`
	HelperName         string `json:"helper_name,omitempty"`
	HelperDigest       string `json:"helper_digest,omitempty"`
	Decision           string `json:"decision,omitempty"`
	Outcome            string `json:"outcome,omitempty"`
	Reason             string `json:"reason,omitempty"`
}
