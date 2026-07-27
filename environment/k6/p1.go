package k6

const (
	SchemaVersion   = 1
	TempThresholdC  = 8.0
	EnvRoot         = "/app/environment"
	OutputRoot      = "/app/output"
	CheckpointPath  = "/app/environment/state/checkpoint.json"
	InventoryPath   = "/app/output/inventory.json"
	ShipmentsPath   = "/app/output/shipments.csv"
	CompliancePath  = "/app/output/compliance.log"
	AnalyticsPath   = "/app/output/analytics.json"
)
