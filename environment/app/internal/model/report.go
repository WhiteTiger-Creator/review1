package model

type Report struct {
	SchemaVersion       string               `json:"schema_version"`
	TraceSeq            int                  `json:"trace_seq"`
	Recovered           []RecoveryDecision   `json:"recovered"`
	Activations         []Activation         `json:"activations"`
	Skipped             []Skipped            `json:"skipped"`
	CoalescingGroups    []CoalescingGroup    `json:"coalescing_groups"`
	DependencyDecisions []DependencyDecision `json:"dependency_decisions"`
	FinalCursors        map[string]string    `json:"final_cursors"`
	StateDigest         string               `json:"state_digest"`
}

type RecoveryDecision struct {
	ActivationID string `json:"activation_id"`
	Decision     string `json:"decision"`
}

type Activation struct {
	ActivationID  string   `json:"activation_id"`
	GroupID       string   `json:"group_id"`
	EffectiveUTC  string   `json:"effective_utc"`
	UnitIDs       []string `json:"unit_ids"`
	OccurrenceIDs []string `json:"occurrence_ids"`
}

type Skipped struct {
	OccurrenceID string `json:"occurrence_id"`
	UnitID       string `json:"unit_id"`
	Reason       string `json:"reason"`
}

type CoalescingGroup struct {
	GroupID       string   `json:"group_id"`
	EffectiveUTC  string   `json:"effective_utc"`
	OccurrenceIDs []string `json:"occurrence_ids"`
}

type DependencyDecision struct {
	UnitID       string `json:"unit_id"`
	OccurrenceID string `json:"occurrence_id"`
	Decision     string `json:"decision"`
}
