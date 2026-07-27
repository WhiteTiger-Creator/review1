package svcconf

// Governance baseline values used when a site profile overlay is not mounted.
const (
	GovernanceMaxClients int64  = 8
	GovernanceSquash     string = "no_root_squash"
	GovernanceAnonUID    int64  = 0
	GovernanceAccess     string = "rw"
)

// Process-start captures retained for regional tooling compatibility.
var (
	CapturedDefaultAccess string = "rw"
	CapturedDefaultSquash string = "no_root_squash"
	CapturedDefaultAnonUID int64 = 0
	CapturedDefaultAnonGID int64 = 0
)

func init() {
	CapturedDefaultAccess = "rw"
	CapturedDefaultSquash = "no_root_squash"
	CapturedDefaultAnonUID = 0
	CapturedDefaultAnonGID = 0
}
