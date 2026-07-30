package q4

type Uplink struct {
	Gbps    int  `json:"gbps"`
	Healthy bool `json:"healthy"`
}

type Unit struct {
	ID         string   `json:"id"`
	Region     string   `json:"region"`
	Class      string   `json:"class"`
	Tier       int      `json:"tier"`
	ReadyNodes int      `json:"ready_nodes"`
	Firmware   string   `json:"firmware"`
	RawTB      int      `json:"raw_tb"`
	DegradedTB int      `json:"degraded_tb"`
	Replicas   int      `json:"replicas"`
	Uplinks    []Uplink `json:"uplinks"`
	DrawKW     int      `json:"draw_kw"`
}

type Approval struct {
	Unit         string `json:"unit"`
	Role         string `json:"role"`
	ExpiresEpoch int    `json:"expires_epoch"`
}

type MaintRec struct {
	Unit     string `json:"unit"`
	Epoch    int    `json:"epoch"`
	Resolved bool   `json:"resolved"`
}

type HostReq struct {
	MinNodes int
	Firmware []string
}

type VolReq struct {
	MinUsable int
	MinCopies int
}

type LinkReq struct {
	MinRate  int
	MinPaths int
}

type SignReq struct {
	Epoch    int
	MinRoles int
	Roles    []string
}

type WinReq struct {
	Epoch int
	Cool  int
}

type ZoneReq struct {
	Classes []string
	Weights map[string]int
}

type Policy struct {
	EvalEpoch       int
	MinNodes        int
	AllowedFirmware []string
	MinUsableTB     int
	MinReplicas     int
	MinGbps         int
	MinHealthyLinks int
	MinRoles        int
	RequiredRoles   []string
	CoolEpochs      int
	BudgetKW        int
	AllowedClasses  []string
	RegionWeights   map[string]int
}

type Bundle struct {
	Name        string
	Policy      Policy
	Units       []Unit
	Approvals   []Approval
	Maintenance []MaintRec
}

type SiteRow struct {
	Name              string `json:"name"`
	RackCount         int    `json:"rack_count"`
	CertifiedCount    int    `json:"certified_count"`
	ComputeBlocks     int    `json:"compute_blocks"`
	StorageBlocks     int    `json:"storage_blocks"`
	NetworkBlocks     int    `json:"network_blocks"`
	ApprovalBlocks    int    `json:"approval_blocks"`
	MaintenanceBlocks int    `json:"maintenance_blocks"`
	RegionRejections  int    `json:"region_rejections"`
	CapacityTrims     int    `json:"capacity_trims"`
	ReadinessIndex    int    `json:"readiness_index"`
	Attestation       string `json:"attestation"`
}

type Report struct {
	SchemaVersion      int       `json:"schema_version"`
	Sites              []SiteRow `json:"sites"`
	ProgramAttestation string    `json:"program_attestation"`
}
