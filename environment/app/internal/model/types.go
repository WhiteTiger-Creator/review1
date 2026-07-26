package model

type Unit struct {
	SchemaVersion  string   `json:"schema_version"`
	UnitID         string   `json:"unit_id"`
	Timezone       string   `json:"timezone"`
	Hour           int      `json:"hour"`
	Minute         int      `json:"minute"`
	Weekdays       []int    `json:"weekdays"`
	Persistent     bool     `json:"persistent"`
	RandomDelaySec int      `json:"random_delay_sec"`
	AccuracySec    int      `json:"accuracy_sec"`
	DependsOn      []string `json:"depends_on"`
	Priority       int      `json:"priority"`
	Enabled        bool     `json:"enabled"`
	CatchUpCap     int      `json:"catch_up_cap"`
	Salt           string   `json:"salt"`
}

type TraceEvent struct {
	Seq    int    `json:"seq"`
	Kind   string `json:"kind"`
	UTC    string `json:"utc"`
	BootID string `json:"boot_id,omitempty"`
}

type State struct {
	SchemaVersion  string            `json:"schema_version"`
	TraceSeq       int               `json:"trace_seq"`
	ClockUTC       string            `json:"clock_utc"`
	HighWaterUTC   string            `json:"high_water_utc"`
	BootID         string            `json:"boot_id"`
	Pending        []Occurrence      `json:"pending"`
	CommittedIDs   []string          `json:"committed_ids"`
	LastActivation map[string]string `json:"last_activation"`
	Cursors        map[string]string `json:"cursors"`
}

type Occurrence struct {
	UnitID         string   `json:"unit_id"`
	OccurrenceID   string   `json:"occurrence_id"`
	ScheduledLocal string   `json:"scheduled_local"`
	ScheduledUTC   string   `json:"scheduled_utc"`
	OffsetSec      int      `json:"offset_sec"`
	DelayedUTC     string   `json:"delayed_utc"`
	AccuracySec    int      `json:"accuracy_sec"`
	Priority       int      `json:"priority"`
	DependsOn      []string `json:"depends_on"`
}

type JournalRecord struct {
	ActivationID  string   `json:"activation_id"`
	Phase         string   `json:"phase"`
	GroupID       string   `json:"group_id"`
	OccurrenceIDs []string `json:"occurrence_ids"`
}
