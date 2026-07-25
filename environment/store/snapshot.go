package store

type RunCtx struct {
	Cycle    int
	OutDir   string
	Append   bool
	Seal     int
	Rank     int
	LegBOpen bool
}

type SegmentRow struct {
	LegID      string `json:"leg_id"`
	HoldMS     int    `json:"hold_ms"`
	ByteOffset int    `json:"byte_offset"`
	Epoch      int    `json:"epoch"`
	IODone     bool   `json:"-"`
}

type StageEvt struct {
	Path          string
	PresentMark   bool
	HoleClearMark bool
	ContentMark   bool
	ByteSpan      int
}

type StagePipe struct {
	Closed        bool
	Staged        int
	HoleSpan      int
	HolesCleared  bool
	ContentCaught bool
	Logical       string
}

type Snap struct {
	LogicalRef string
	AMetric    int
	BMetric    int
	AEpoch     int
	BEpoch     int
	FlagBits   int
}

type ViewRow struct {
	Source   string `json:"source"`
	Tally    int    `json:"tally"`
	Epoch    int    `json:"epoch"`
	TallyHex string `json:"tally_hex"`
}

type RollingExport struct {
	Views []ViewRow `json:"views"`
}

type PushTrace struct {
	Segments []SegmentRow `json:"segments"`
}

type TraceLine struct {
	Epoch int    `json:"epoch"`
	Op    string `json:"op"`
	Path  string `json:"path"`
}

type CycleWin struct {
	Cycle         int `json:"cycle"`
	SyncedBytes   int `json:"synced_bytes"`
	VerifiedBytes int `json:"verified_bytes"`
}

type ConvReport struct {
	Cycles []CycleWin `json:"cycles"`
}

type CatFixture struct {
	LogicalPath string `json:"logical_path"`
	StateFlags  int    `json:"state_flags"`
	Finished    bool   `json:"finished"`
	Tally       int    `json:"tally"`
	Epoch       int    `json:"epoch"`
	PresentGen  int    `json:"present_gen"`
}

type PrbFixture struct {
	LogicalPath   string `json:"logical_path"`
	Tally         int    `json:"tally"`
	Epoch         int    `json:"epoch"`
	HoleDebt      int    `json:"hole_debt"`
	HolesCleared  bool   `json:"holes_cleared"`
	ContentCaught bool   `json:"content_caught"`
	PresentMark   bool   `json:"present_mark"`
	HoleClearMark bool   `json:"hole_clear_mark"`
	ContentMark   bool   `json:"content_mark"`
	LegAIODone    bool   `json:"leg_a_io_done"`
	LegBIODone    bool   `json:"leg_b_io_done"`
	DelayedOffset int    `json:"delayed_offset"`
	DelayedSpan   int    `json:"delayed_span"`
	LegASum       int    `json:"leg_a_sum"`
	LegBSum       int    `json:"leg_b_sum"`
}

type HaltFixture struct {
	Cycle         int `json:"cycle"`
	DelayedOffset int `json:"delayed_offset"`
	DelayedSpan   int `json:"delayed_span"`
}

type PayloadCfg struct {
	LogicalPath string `toml:"logical_path"`
	LegA        string `toml:"leg_a"`
	LegB        string `toml:"leg_b"`
}

type PushCfg struct {
	HoldUS     int `toml:"hold_us"`
	ByteSpan   int `toml:"byte_span"`
	DelayAfter int `toml:"delay_after_ms"`
}

type LaneCfg struct {
	CatalogLane int `toml:"catalog_lane"`
	ProbeLane   int `toml:"probe_lane"`
}
