package k6

import "fmt"

func ExpectedPolicy() Policy {
	return Policy{
		ParentLinkMode:   "enforce_parent",
		ChildIDMode:      "increment_generation",
		TempOnRecovery:   "preserve_transit",
		QuarantineMode:   "honor_violation",
		InTransitRelease: "release",
		TempThresholdC:   TempThresholdC,
	}
}

func ValidatePolicy(policy Policy) []string {
	expected := ExpectedPolicy()
	issues := []string{}
	if policy.ParentLinkMode != expected.ParentLinkMode {
		issues = append(issues, fmt.Sprintf("lineage.parent_link_mode must be %s, found %s", expected.ParentLinkMode, policy.ParentLinkMode))
	}
	if policy.ChildIDMode != expected.ChildIDMode {
		issues = append(issues, fmt.Sprintf("lineage.child_id_mode must be %s, found %s", expected.ChildIDMode, policy.ChildIDMode))
	}
	if policy.TempOnRecovery != expected.TempOnRecovery {
		issues = append(issues, fmt.Sprintf("recovery.temp_on_recovery must be %s, found %s", expected.TempOnRecovery, policy.TempOnRecovery))
	}
	if policy.QuarantineMode != expected.QuarantineMode {
		issues = append(issues, fmt.Sprintf("merge.quarantine_mode must be %s, found %s", expected.QuarantineMode, policy.QuarantineMode))
	}
	if policy.InTransitRelease != expected.InTransitRelease {
		issues = append(issues, fmt.Sprintf("merge.in_transit_release must be %s, found %s", expected.InTransitRelease, policy.InTransitRelease))
	}
	return issues
}
