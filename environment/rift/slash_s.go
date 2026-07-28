package rift

import "gwc/store"

func slash_s(prev store.Sample, nextUID int, nextMark string, dropMask uint32, path string, cookie string, lane string) store.Sample {
	if lane == "" {
		lane = prev.LaneKey
	}
	if cookie == "" {
		cookie = prev.Cookie
	}
	raw := prev.SuppMask
	material := store.LaneMaterial(lane, path, cookie, nextUID, raw, nextMark)
	kept := Cleared(prev.SuppMask, dropMask)
	return store.Sample{
		UID:      nextUID,
		SuppMask: kept,
		Cookie:   cookie,
		LaneKey:  lane,
		Mark:     nextMark,
		LaneHex:  store.DigestLane(material),
	}
}

func Advance(prev store.Sample, nextUID int, nextMark string, dropMask uint32, path string, cookie string, lane string) store.Sample {
	return slash_s(prev, nextUID, nextMark, dropMask, path, cookie, lane)
}

func Stamp(lane string, path string, cookie string, uid int, supp uint32, mark string) store.Sample {
	if lane == "" {
		lane = "_"
	}
	material := store.LaneMaterial(lane, path, cookie, uid, supp, mark)
	return store.Sample{
		UID:      uid,
		SuppMask: supp,
		Cookie:   cookie,
		LaneKey:  lane,
		Mark:     mark,
		LaneHex:  store.DigestLane(material),
	}
}
