package main

import "sort"

type referee struct {
	cr        *crown
	seat      map[string]string
	where     map[string]string
	wins      map[string]int
	losses    map[string]int
	taken     map[string]int
	given     map[string]int
	meetings  map[string]int
	outState  map[string]string
	outToken  map[string]string
	outRound  map[string]int
	crowned   string
	rnd       int
	closes    int
	bBoards   map[string]int
	bHands    map[string]int
	bUpset    map[string]string
	bRest     map[string]string
	bEver     map[string]bool
	bNamed    map[string]bool
	inBracket map[string]bool
	nBoards   int
	nByes     int
	nConcedes int
}

func newReferee(cr *crown) *referee {
	rf := &referee{
		cr:        cr,
		seat:      map[string]string{},
		where:     map[string]string{},
		wins:      map[string]int{},
		losses:    map[string]int{},
		taken:     map[string]int{},
		given:     map[string]int{},
		meetings:  map[string]int{},
		outState:  map[string]string{},
		outToken:  map[string]string{},
		outRound:  map[string]int{},
		rnd:       1,
		bBoards:   map[string]int{},
		bHands:    map[string]int{},
		bUpset:    map[string]string{},
		bRest:     map[string]string{},
		bEver:     map[string]bool{},
		bNamed:    map[string]bool{},
		inBracket: map[string]bool{},
	}
	for _, berth := range cr.berths {
		rf.bBoards[berth] = 0
		rf.bHands[berth] = 0
		rf.inBracket[berth] = true
	}
	for _, house := range cr.roll {
		rf.wins[house] = 0
		rf.losses[house] = 0
		rf.taken[house] = 0
		rf.given[house] = 0
		rf.meetings[house] = 0
	}
	return rf
}

func (rf *referee) onRoll(house string) bool {
	_, ok := rf.wins[house]
	return ok
}

func (rf *referee) isOut(house string) bool {
	_, ok := rf.outState[house]
	return ok
}

func (rf *referee) width(round int) int {
	widths := rf.cr.widths
	if len(widths) == 0 {
		return 0
	}
	if round-1 < len(widths) {
		return widths[round-1]
	}
	return widths[len(widths)-1]
}

func (rf *referee) strength(house string) int {
	return rf.taken[house] - rf.given[house]
}

func (rf *referee) key(house string) [4]int {
	return [4]int{-rf.wins[house], rf.losses[house], -rf.strength(house), rf.cr.seed[house]}
}

func keyBelow(a, b [4]int) bool {
	for i := 0; i < 4; i++ {
		if a[i] != b[i] {
			return a[i] < b[i]
		}
	}
	return false
}

func (rf *referee) standing() []string {
	order := []string{}
	for _, house := range rf.cr.roll {
		if _, seated := rf.where[house]; seated && !rf.isOut(house) {
			order = append(order, house)
		}
	}
	keys := map[string][4]int{}
	for _, house := range order {
		keys[house] = rf.key(house)
	}
	sort.SliceStable(order, func(i, j int) bool {
		return keyBelow(keys[order[i]], keys[order[j]])
	})
	return order
}
