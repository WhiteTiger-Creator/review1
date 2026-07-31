package main

import "strconv"

func (rf *referee) take(step []string) {
	if len(step) == 0 {
		return
	}
	switch step[0] {
	case "seat":
		if len(step) >= 3 {
			rf.stepSeat(step[1], step[2])
		}
	case "board":
		if len(step) >= 5 {
			first, _ := strconv.Atoi(step[3])
			second, _ := strconv.Atoi(step[4])
			rf.stepBoard(step[1], step[2], first, second)
		}
	case "bye":
		rf.stepBye()
	case "concede":
		if len(step) >= 3 {
			rf.stepConcede(step[1], step[2])
		}
	case "strike":
		if len(step) >= 2 {
			rf.stepStrike(step[1])
		}
	case "close":
		rf.stepClose()
	}
}

func (rf *referee) nameBerth(berth string) {
	if rf.inBracket[berth] {
		rf.bNamed[berth] = true
	}
}

func (rf *referee) live(berth string) string {
	rf.nameBerth(berth)
	house, seated := rf.seat[berth]
	if !seated || rf.isOut(house) {
		return ""
	}
	return house
}

func (rf *referee) putIn(berth, house string) {
	rf.seat[berth] = house
	rf.where[house] = berth
	rf.bEver[berth] = true
}

func (rf *referee) stepSeat(house, berth string) {
	rf.nameBerth(berth)
	if !rf.onRoll(house) || !rf.inBracket[berth] {
		return
	}
	if rf.isOut(house) {
		return
	}
	if _, standing := rf.where[house]; standing {
		return
	}
	if _, held := rf.seat[berth]; held {
		return
	}
	rf.putIn(berth, house)
}

func (rf *referee) stepBoard(first, second string, handsFirst, handsSecond int) {
	left := rf.live(first)
	right := rf.live(second)
	if left == "" || right == "" || first == second {
		return
	}
	rf.nBoards++
	var won, lost, wonBerth string
	switch {
	case handsFirst > handsSecond:
		won, lost, wonBerth = left, right, first
	case handsSecond > handsFirst:
		won, lost, wonBerth = right, left, second
	case rf.cr.seed[left] < rf.cr.seed[right]:
		won, lost, wonBerth = left, right, first
	default:
		won, lost, wonBerth = right, left, second
	}
	handsWon, handsLost := handsFirst, handsSecond
	if won == right {
		handsWon, handsLost = handsSecond, handsFirst
	}
	rf.wins[won]++
	rf.losses[lost]++
	rf.taken[won] += handsWon
	rf.given[won] += handsLost
	rf.taken[lost] += handsLost
	rf.given[lost] += handsWon
	rf.meetings[won]++
	rf.meetings[lost]++
	rf.bBoards[first]++
	rf.bBoards[second]++
	rf.bHands[first] += handsFirst
	rf.bHands[second] += handsSecond
	if rf.cr.seed[won] > rf.cr.seed[lost] {
		if _, marked := rf.bUpset[wonBerth]; !marked {
			if rf.cr.seed[won]-rf.cr.seed[lost] > 1 {
				rf.bUpset[wonBerth] = "upset.wide"
			} else {
				rf.bUpset[wonBerth] = "upset.close"
			}
		}
	}
}

func (rf *referee) stepBye() {
	house := ""
	berth := ""
	for _, name := range rf.cr.berths {
		if sitting := rf.live(name); sitting != "" {
			house = sitting
			berth = name
		}
	}
	if house == "" {
		return
	}
	rf.nByes++
	rf.wins[house]++
	rf.bBoards[berth]++
	if _, marked := rf.bRest[berth]; !marked {
		rf.bRest[berth] = "rest.clear"
	}
}

func (rf *referee) stepConcede(giverBerth, otherBerth string) {
	giver := rf.live(giverBerth)
	other := rf.live(otherBerth)
	if giver == "" || other == "" || giverBerth == otherBerth {
		return
	}
	rf.nConcedes++
	rf.losses[giver]++
	rf.wins[other]++
	rf.meetings[giver]++
	rf.meetings[other]++
	rf.bBoards[giverBerth]++
	rf.bBoards[otherBerth]++
}

func (rf *referee) stepStrike(house string) {
	if !rf.onRoll(house) || rf.isOut(house) {
		return
	}
	token := "barred.aside"
	if _, standing := rf.where[house]; standing {
		token = "barred.seated"
	}
	rf.putOut(house, "BARRED", token)
}
