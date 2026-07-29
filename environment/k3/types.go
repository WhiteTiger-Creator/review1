package k3

// Buf holds live pid residency and a running high-water for one lane.
type Buf struct {
	Live map[int]int
	Peak int
	Lane string
}

// Tick is one residency sample for a pid at a stream position.
type Tick struct {
	Pid   int
	Pages int
}

// Members maps pid -> lane id.
type Members map[int]string
