package record

// ManifestFieldOrder documents the required JSON member sequence for audits.
var ManifestFieldOrder = []string{
	"format",
	"network_sha256",
	"ramp_sha256",
	"status",
	"critical_lambda",
	"point_count",
	"event_count",
	"limiting_buses",
	"voltage_violation_count",
	"max_power_mismatch",
	"max_arc_residual",
	"total_active_loss",
	"total_reactive_loss",
}

// EntryOrder is the ZIP entry sequence.
var EntryOrder = []string{
	"manifest.json",
	"curve.csv",
	"events.csv",
	"critical_bus.csv",
	"critical_branch.csv",
}
