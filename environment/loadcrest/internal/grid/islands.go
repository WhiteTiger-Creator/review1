package grid

import (
	"fmt"

	"loadcrest/internal/deck"
)

// ValidateEnergizedIsland requires one connected IN-component covering all buses and the slack.
func ValidateEnergizedIsland(buses []Bus, branches []Branch, slack string) error {
	adj := map[string][]string{}
	for _, b := range buses {
		adj[b.ID] = nil
	}
	for _, br := range branches {
		if br.Status != deck.BranchIN {
			continue
		}
		adj[br.From] = append(adj[br.From], br.To)
		adj[br.To] = append(adj[br.To], br.From)
	}
	seen := map[string]bool{}
	stack := []string{slack}
	seen[slack] = true
	for len(stack) > 0 {
		u := stack[len(stack)-1]
		stack = stack[:len(stack)-1]
		for _, v := range adj[u] {
			if !seen[v] {
				seen[v] = true
				stack = append(stack, v)
			}
		}
	}
	if len(seen) != len(buses) {
		return fmt.Errorf("energized island does not cover all buses")
	}
	return nil
}
