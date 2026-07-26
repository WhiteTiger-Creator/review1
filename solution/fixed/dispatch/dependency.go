package dispatch

import (
	"sort"

	"wakeclock/internal/model"
)

func Order(group []model.Occurrence, state model.State) ([]model.Occurrence, []model.DependencyDecision, []model.Skipped) {
	items := append([]model.Occurrence{}, group...)
	byUnit := map[string][]int{}
	for index, item := range items {
		byUnit[item.UnitID] = append(byUnit[item.UnitID], index)
	}
	skipped := map[int]bool{}
	for index, item := range items {
		for _, dependency := range item.DependsOn {
			if len(byUnit[dependency]) == 0 && state.LastActivation[dependency] == "" {
				skipped[index] = true
				break
			}
		}
	}
	changed := true
	for changed {
		changed = false
		for index, item := range items {
			if skipped[index] {
				continue
			}
			for _, dependency := range item.DependsOn {
				for _, dependencyIndex := range byUnit[dependency] {
					if skipped[dependencyIndex] {
						skipped[index] = true
						changed = true
						break
					}
				}
				if skipped[index] {
					break
				}
			}
		}
	}

	indegree := make([]int, len(items))
	outgoing := map[int][]int{}
	for index, item := range items {
		if skipped[index] {
			continue
		}
		for _, dependency := range item.DependsOn {
			for _, dependencyIndex := range byUnit[dependency] {
				if skipped[dependencyIndex] || dependencyIndex == index {
					continue
				}
				indegree[index]++
				outgoing[dependencyIndex] = append(outgoing[dependencyIndex], index)
			}
		}
	}

	ordered := []model.Occurrence{}
	used := map[int]bool{}
	for {
		eligible := []int{}
		for index := range items {
			if !skipped[index] && !used[index] && indegree[index] == 0 {
				eligible = append(eligible, index)
			}
		}
		if len(eligible) == 0 {
			break
		}
		sort.Slice(eligible, func(i, j int) bool {
			left, right := items[eligible[i]], items[eligible[j]]
			if left.Priority != right.Priority {
				return left.Priority > right.Priority
			}
			if left.UnitID != right.UnitID {
				return left.UnitID < right.UnitID
			}
			return left.OccurrenceID < right.OccurrenceID
		})
		index := eligible[0]
		used[index] = true
		ordered = append(ordered, items[index])
		for _, dependent := range outgoing[index] {
			indegree[dependent]--
		}
	}

	decisions := make([]model.DependencyDecision, 0, len(items))
	skips := []model.Skipped{}
	for index, item := range items {
		if skipped[index] {
			decisions = append(decisions, model.DependencyDecision{UnitID: item.UnitID, OccurrenceID: item.OccurrenceID, Decision: "skipped_missing_prerequisite"})
			skips = append(skips, model.Skipped{OccurrenceID: item.OccurrenceID, UnitID: item.UnitID, Reason: "missing_prerequisite"})
			continue
		}
		hasGroupDependency := false
		hasHistoricalDependency := false
		for _, dependency := range item.DependsOn {
			if len(byUnit[dependency]) > 0 {
				hasGroupDependency = true
			} else {
				hasHistoricalDependency = true
			}
		}
		decision := "ready"
		if hasGroupDependency {
			decision = "ordered_after_group_dependency"
		} else if hasHistoricalDependency {
			decision = "satisfied_by_history"
		}
		decisions = append(decisions, model.DependencyDecision{UnitID: item.UnitID, OccurrenceID: item.OccurrenceID, Decision: decision})
	}
	sort.Slice(decisions, func(i, j int) bool {
		if decisions[i].OccurrenceID != decisions[j].OccurrenceID {
			return decisions[i].OccurrenceID < decisions[j].OccurrenceID
		}
		return decisions[i].UnitID < decisions[j].UnitID
	})
	sort.Slice(skips, func(i, j int) bool {
		if skips[i].OccurrenceID != skips[j].OccurrenceID {
			return skips[i].OccurrenceID < skips[j].OccurrenceID
		}
		return skips[i].UnitID < skips[j].UnitID
	})
	return ordered, decisions, skips
}
