package main

func (rf *referee) stepClose() {
	order := rf.standing()
	width := rf.width(rf.rnd + 1)
	if width > len(order) {
		width = len(order)
	}
	if width < 0 {
		width = 0
	}
	keep := order[:width]
	gone := order[width:]
	for _, house := range gone {
		rf.putOut(house, "FELLED", "felled.board")
	}
	if len(keep) == 1 && rf.crowned == "" {
		rf.crowned = keep[0]
	}
	rf.rnd++
	rf.closes++
}

func (rf *referee) putOut(house, state, token string) {
	if rf.isOut(house) {
		return
	}
	rf.outState[house] = state
	rf.outToken[house] = token
	rf.outRound[house] = rf.rnd
	berth, standing := rf.where[house]
	if !standing {
		return
	}
	delete(rf.where, house)
	if rf.seat[berth] == house {
		delete(rf.seat, berth)
	}
}
