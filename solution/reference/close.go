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
		state, token, void := rf.wayOut(house)
		rf.putOut(house, state, token, void)
	}
	for _, house := range keep {
		delete(rf.seat, rf.where[house])
	}
	for _, berth := range rf.cr.berths {
		if _, held := rf.seat[berth]; held {
			continue
		}
		if !rf.bEver[berth] {
			continue
		}
		if _, marked := rf.bVoid[berth]; !marked {
			rf.bVoid[berth] = "void.reseated"
		}
	}
	for index, house := range keep {
		if index >= len(rf.cr.berths) {
			break
		}
		rf.putIn(rf.cr.berths[index], house)
	}
	if len(keep) == 1 && rf.crowned == "" {
		rf.crowned = keep[0]
		if len(gone) > 0 {
			rf.crownToken = "crown.width"
		} else {
			rf.crownToken = "crown.sole"
		}
	}
	rf.rnd++
	rf.lostRound = map[string]bool{}
	rf.gaveRound = map[string]bool{}
	rf.playedRound = map[string]bool{}
}

func (rf *referee) wayOut(house string) (string, string, string) {
	if rf.gaveRound[house] {
		return "FELLED", "felled.given", "void.felled"
	}
	if rf.lostRound[house] {
		return "FELLED", "felled.board", "void.felled"
	}
	if !rf.playedRound[house] {
		return "CUT", "cut.idle", "void.cut"
	}
	return "CUT", "cut.width", "void.cut"
}

func (rf *referee) putOut(house, state, token, void string) {
	if rf.isOut(house) {
		return
	}
	rf.outKey[house] = rf.key(house)
	rf.outState[house] = state
	rf.outToken[house] = token
	berth, standing := rf.where[house]
	if !standing {
		return
	}
	delete(rf.where, house)
	if rf.seat[berth] == house {
		delete(rf.seat, berth)
		rf.bVoid[berth] = void
	}
}
