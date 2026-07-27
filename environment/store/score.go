package store

func ScoreCycle(liveUID, wantUID int, siblingHex, parentHex string, journalOps map[string]int, cookieAligned bool, facetAligned bool) int {
	agree := 0
	if liveUID == wantUID {
		agree++
	}
	if siblingHex != "" && siblingHex != parentHex {
		agree++
	}
	if journalOps["intake"] == 1 && journalOps["rebind"] == 1 {
		agree++
	}
	if cookieAligned {
		agree++
	}
	if facetAligned {
		agree++
	}
	return agree
}
