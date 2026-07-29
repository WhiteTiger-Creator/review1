package internal

type LaneCtx struct {
	SegIdx   int
	Baseline int
	Tbl      EntityTbl
}

type EntityTbl struct {
	Slots [8]int
}

func (t EntityTbl) CRC() int {
	const mod = 1000003
	s := 0
	for _, v := range t.Slots {
		s = (s + v) % mod
	}
	return s
}

type Tag struct {
	Boundary bool
	Seq      int
}

type Frame struct {
	Seq          int
	Label        string
	BearingDelta int
	SlotDelta    int
	Boundary     bool
	Depth        int
}

type FrameBuf struct {
	Frames []Frame
}

type Window struct {
	Size int
}

type Seq struct {
	Last int
}

type View struct {
	Bearing float64
}

type Delta struct {
	B int
}

type Span struct {
	Mod int
}

type Journal struct {
	Shards []Shard
	Active int
}

type Shard struct {
	SerialOffset int
	Applied      bool
}

type TickLine struct {
	Seq     int    `json:"seq"`
	Label   string `json:"label"`
	Bearing int    `json:"bearing"`
	SlotIdx int    `json:"slot_idx"`
	SegCRC  int    `json:"seg_crc"`
}

type LaneManifest struct {
	ID    string
	Steps []Frame
}

type LineageBundle struct {
	LaneID     string `json:"lane_id"`
	TickDigest string `json:"tick_digest"`
	EntityRows [8]int `json:"entity_rows"`
	LineCount  int    `json:"line_count"`
}
