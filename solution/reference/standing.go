package main

import "sort"

type referee struct {
	cr          *crown
	seat        map[string]string
	where       map[string]string
	wins        map[string]int
	losses      map[string]int
	taken       map[string]int
	given       map[string]int
	met         map[string][]string
	outState    map[string]string
	outToken    map[string]string
	outKey      map[string][4]int
	crowned     string
	crownToken  string
	rnd         int
	lostRound   map[string]bool
	gaveRound   map[string]bool
	playedRound map[string]bool
	bBoards     map[string]int
	bHands      map[string]int
	bUpset      map[string]string
	bRest       map[string]string
	bVoid       map[string]string
	bEver       map[string]bool
	bNamed      map[string]bool
	bSeen       map[string]int
	bLast       map[string]string
	inBracket   map[string]bool
	nBoards     int
	nByes       int
	nConcedes   int
}

func newReferee(cr *crown) *referee {
	rf := &referee{
		cr:          cr,
		seat:        map[string]string{},
		where:       map[string]string{},
		wins:        map[string]int{},
		losses:      map[string]int{},
		taken:       map[string]int{},
		given:       map[string]int{},
		met:         map[string][]string{},
		outState:    map[string]string{},
		outToken:    map[string]string{},
		outKey:      map[string][4]int{},
		rnd:         1,
		lostRound:   map[string]bool{},
		gaveRound:   map[string]bool{},
		playedRound: map[string]bool{},
		bBoards:     map[string]int{},
		bHands:      map[string]int{},
		bUpset:      map[string]string{},
		bRest:       map[string]string{},
		bVoid:       map[string]string{},
		bEver:       map[string]bool{},
		bNamed:      map[string]bool{},
		bSeen:       map[string]int{},
		bLast:       map[string]string{},
		inBracket:   map[string]bool{},
	}
	for _, berth := range cr.berths {
		rf.bBoards[berth] = 0
		rf.bHands[berth] = 0
		rf.bSeen[berth] = 0
		rf.inBracket[berth] = true
	}
	for _, house := range cr.roll {
		rf.wins[house] = 0
		rf.losses[house] = 0
		rf.taken[house] = 0
		rf.given[house] = 0
		rf.met[house] = []string{}
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
	total := 0
	for _, other := range rf.met[house] {
		total += rf.wins[other]
	}
	return total
}

func (rf *referee) key(house string) [4]int {
	return [4]int{-rf.wins[house], rf.losses[house], -rf.strength(house), -rf.cr.seed[house]}
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

func placeAt(order []string, house string) int {
	for index, name := range order {
		if name == house {
			return index
		}
	}
	return -1
}

func (rf *referee) exitKey(house string) [4]int {
	if frozen, ok := rf.outKey[house]; ok {
		return frozen
	}
	return rf.key(house)
}

func rungBetween(above, below [4]int) string {
	for i := 0; i < 4; i++ {
		if above[i] != below[i] {
			return placeRungs[i]
		}
	}
	return placeRungs[3]
}
