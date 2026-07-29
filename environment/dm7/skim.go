package dm7

// SkimSeg lists lane labels for documentation samples without mutating tables.
func SkimSeg(labels []string) []string {
	out := make([]string, 0, len(labels))
	for _, s := range labels {
		if s != "" {
			out = append(out, s)
		}
	}
	return out
}
