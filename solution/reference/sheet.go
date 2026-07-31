package main

import (
	"fmt"
	"sort"
	"strings"
)

var berthStates = []string{"CROWNED", "UPSET", "RESTED", "VACATED", "DARK"}
var houseStates = []string{"CROWNED", "BARRED", "CUT", "FELLED", "SEATED"}
var placeRungs = []string{"place.wins", "place.losses", "place.strength", "place.seed"}

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
	for _, house := range rf.cr.roll {
		keys[house] = rf.exitKey(house)
	}
	sort.SliceStable(rest, func(i, j int) bool {
		return keyBelow(keys[rest[i]], keys[rest[j]])
	})
	if rf.crowned != "" {
		return append([]string{rf.crowned}, rest...)
	}
	return rest
}

func (rf *referee) placeTokens(order []string) map[string]string {
	tokens := map[string]string{}
	for index, house := range order {
		if index == 0 {
			if house == rf.crowned || len(order) == 1 {
				tokens[house] = "place.crown"
			} else {
				tokens[house] = rungBetween(rf.exitKey(house), rf.exitKey(order[1]))
			}
			continue
		}
		tokens[house] = rungBetween(rf.exitKey(order[index-1]), rf.exitKey(house))
	}
	return tokens
}

func (rf *referee) berthRuling(berth string) (string, string) {
	house, held := rf.seat[berth]
	if rf.crowned != "" && held && house == rf.crowned {
		if rf.bSeen[berth] > 1 {
			return "CROWNED", "held.long"
		}
		return "CROWNED", "held.own"
	}
	if token, marked := rf.bUpset[berth]; marked {
		return "UPSET", token
	}
	if token, marked := rf.bRest[berth]; marked {
		return "RESTED", token
	}
	if token, marked := rf.bVoid[berth]; marked {
		return "VACATED", token
	}
	if rf.bEver[berth] {
		return "VACATED", "void.standing"
	}
	if rf.bNamed[berth] {
		return "DARK", "dark.named"
	}
	return "DARK", "dark.silent"
}

func (rf *referee) houseRuling(house string) (string, string) {
	if rf.crowned != "" && house == rf.crowned {
		return "CROWNED", rf.crownToken
	}
	if rf.isOut(house) {
		return rf.outState[house], rf.outToken[house]
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
	tokens := rf.placeTokens(order)
	lines := []string{
		fmt.Sprintf("bracket %s berths %d houses %d rounds %d boards %d byes %d concedes %d",
			rf.cr.name, len(rf.cr.berths), len(rf.cr.roll), rf.rnd,
			rf.nBoards, rf.nByes, rf.nConcedes),
		berthHeader,
	}
	berthTally := map[string]int{}
	houseTally := map[string]int{}
	sorted := append([]string{}, rf.cr.berths...)
	sort.Strings(sorted)
	for _, berth := range sorted {
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
			house, rf.cr.seed[house], rf.wins[house], rf.losses[house], len(rf.met[house]),
			rf.strength(house), rf.taken[house], rf.given[house], berth, place[house],
			tokens[house], state, token), " "))
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
