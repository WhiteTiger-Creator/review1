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
	if rf.bLast[berth] != house {
		rf.bSeen[berth]++
	}
	rf.bLast[berth] = house
	delete(rf.bVoid, berth)
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
	case rf.cr.seed[left] > rf.cr.seed[right]:
		won, lost, wonBerth = left, right, first
	default:
		won, lost, wonBerth = right, left, second
	}
	order := rf.standing()
	gap := placeAt(order, won) - placeAt(order, lost)
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
	rf.bBoards[first]++
	rf.bBoards[second]++
	rf.bHands[first] += handsFirst
	rf.bHands[second] += handsSecond
	rf.met[won] = append(rf.met[won], lost)
	rf.met[lost] = append(rf.met[lost], won)
	if gap > 0 {
		if _, marked := rf.bUpset[wonBerth]; !marked {
			if gap > 1 {
				rf.bUpset[wonBerth] = "upset.wide"
			} else {
				rf.bUpset[wonBerth] = "upset.close"
			}
		}
	}
	rf.playedRound[left] = true
	rf.playedRound[right] = true
	rf.lostRound[lost] = true
}

func (rf *referee) stepBye() {
	order := rf.standing()
	if len(order) == 0 {
		return
	}
	rf.nByes++
	house := order[len(order)-1]
	token := "rest.clear"
	if len(order) > 1 {
		above := rf.key(order[len(order)-2])
		lowest := rf.key(house)
		if above[0] == lowest[0] && above[1] == lowest[1] && above[2] == lowest[2] {
			token = "rest.tie"
		}
	}
	rf.wins[house]++
	rf.playedRound[house] = true
	berth := rf.where[house]
	if _, marked := rf.bRest[berth]; !marked {
		rf.bRest[berth] = token
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
	rf.met[giver] = append(rf.met[giver], other)
	rf.bBoards[giverBerth]++
	rf.bBoards[otherBerth]++
	rf.playedRound[giver] = true
	rf.playedRound[other] = true
	rf.lostRound[giver] = true
	rf.gaveRound[giver] = true
}

func (rf *referee) stepStrike(house string) {
	if !rf.onRoll(house) || rf.isOut(house) {
		return
	}
	token := "barred.aside"
	if _, standing := rf.where[house]; standing {
		token = "barred.seated"
	}
	rf.putOut(house, "BARRED", token, "void.barred")
}
