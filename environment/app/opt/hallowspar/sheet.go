package main

import (
	"fmt"
	"sort"
	"strings"
)

var berthStates = []string{"CROWNED", "UPSET", "RESTED", "VACATED", "DARK"}
var houseStates = []string{"CROWNED", "BARRED", "CUT", "FELLED", "SEATED"}

const berthHeader = "-- berths --"
const houseHeader = "-- houses --"

func (rf *referee) placeOrder() []string {
	rest := []string{}
	for _, house := range rf.cr.roll {
		if house != rf.crowned {
			rest = append(rest, house)
		}
	}
	keys := map[string][4]int{}
	rounds := map[string]int{}
	for _, house := range rf.cr.roll {
		keys[house] = rf.key(house)
		if gone, ok := rf.outRound[house]; ok {
			rounds[house] = gone
		} else {
			rounds[house] = len(rf.cr.widths) + 1
		}
	}
	sort.SliceStable(rest, func(i, j int) bool {
		if rounds[rest[i]] != rounds[rest[j]] {
			return rounds[rest[i]] > rounds[rest[j]]
		}
		return keyBelow(keys[rest[i]], keys[rest[j]])
	})
	if rf.crowned != "" {
		return append([]string{rf.crowned}, rest...)
	}
	return rest
}

func (rf *referee) berthRuling(berth string) (string, string) {
	house, held := rf.seat[berth]
	if rf.crowned != "" && held && house == rf.crowned {
		return "CROWNED", "held.long"
	}
	if token, marked := rf.bUpset[berth]; marked {
		return "UPSET", token
	}
	if token, marked := rf.bRest[berth]; marked {
		return "RESTED", token
	}
	if rf.bEver[berth] {
		return "VACATED", "void.reseated"
	}
	if rf.bNamed[berth] {
		return "DARK", "dark.named"
	}
	return "DARK", "dark.silent"
}

func (rf *referee) houseRuling(house string) (string, string) {
	if rf.isOut(house) {
		return rf.outState[house], rf.outToken[house]
	}
	if house == rf.crowned {
		return "CROWNED", "crown.width"
	}
	if _, standing := rf.where[house]; standing {
		return "SEATED", "stand.seated"
	}
	return "SEATED", "stand.unseated"
}

func (rf *referee) sheetLines() []string {
	order := rf.placeOrder()
	place := map[string]int{}
	for index, house := range order {
		place[house] = index + 1
	}
	lines := []string{
		fmt.Sprintf("bracket %s berths %d houses %d rounds %d boards %d byes %d concedes %d",
			rf.cr.name, len(rf.cr.berths), len(rf.cr.roll), rf.closes,
			rf.nBoards, rf.nByes, rf.nConcedes),
		berthHeader,
	}
	berthTally := map[string]int{}
	houseTally := map[string]int{}
	for _, berth := range rf.cr.berths {
		state, token := rf.berthRuling(berth)
		berthTally[state]++
		sitting := "-"
		if house, held := rf.seat[berth]; held {
			sitting = house
		}
		lines = append(lines, strings.TrimRight(fmt.Sprintf(
			"%-9s house %-9s boards %2d hands %3d %-8s %-15s",
			berth, sitting, rf.bBoards[berth], rf.bHands[berth], state, token), " "))
	}
	lines = append(lines, houseHeader)
	for _, house := range rf.cr.roll {
		state, token := rf.houseRuling(house)
		houseTally[state]++
		berth := "-"
		if held, standing := rf.where[house]; standing {
			berth = held
		}
		lines = append(lines, strings.TrimRight(fmt.Sprintf(
			"%-9s seed %2d won %2d lost %2d met %2d strength %2d for %3d against %3d "+
				"berth %-9s place %2d %-14s %-8s %-15s",
			house, rf.cr.seed[house], rf.wins[house], rf.losses[house], rf.meetings[house],
			rf.strength(house), rf.taken[house], rf.given[house], berth, place[house],
			"place.seed", state, token), " "))
	}
	lines = append(lines, tallyLine("berths", berthStates, berthTally))
	lines = append(lines, tallyLine("houses", houseStates, houseTally))
	return lines
}

func tallyLine(label string, states []string, counts map[string]int) string {
	parts := []string{label}
	for _, state := range states {
		parts = append(parts, fmt.Sprintf("%s %d", state, counts[state]))
	}
	return strings.Join(parts, " ")
}
