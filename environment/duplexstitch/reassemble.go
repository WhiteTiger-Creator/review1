package duplexstitch

import (
	"cdnqual/framestream"
)

const (
	FlagFIN = 0x01
	FlagSYN = 0x02
	FlagACK = 0x10
)

// UniStats captures unidirectional reassembly metrics.
type UniStats struct {
	Payload          []byte
	RetransmitCount  int
	OutOfOrderCount  int
	OverlapByteCount int
	UniqueSeqSpan    int
	PacketCount      int
}

// Bout is a duplex reassembled session.
type Bout struct {
	ID              string
	ClientPayload   []byte
	ServerPayload   []byte
	PacketCount     int
	RetransmitCount int
	OutOfOrderCount int
	OverlapBytes    int
	UniqueSeqSpan   int
	DurationUS      int64
	SynAckRTTUS     int64
	FinSeen         int
	FirstTS         int64
	LastTS          int64
}

// ReassembleBout rebuilds one duplex bout from arrival-ordered packets.
func ReassembleBout(boutID string, pkts []framestream.Packet) Bout {
	b := Bout{ID: boutID, PacketCount: len(pkts)}
	if len(pkts) == 0 {
		return b
	}
	b.FirstTS = pkts[0].TsTotal()
	b.LastTS = pkts[len(pkts)-1].TsTotal()
	b.DurationUS = b.LastTS - b.FirstTS
	var client, server []byte
	for _, p := range pkts {
		if p.Flags&FlagFIN != 0 {
			b.FinSeen = 1
		}
		if len(p.Payload) == 0 {
			continue
		}
		if p.Index%2 == 0 {
			client = append(client, p.Payload...)
		} else {
			server = append(server, p.Payload...)
		}
	}
	b.ClientPayload = client
	b.ServerPayload = server
	b.UniqueSeqSpan = len(client) + len(server)
	return b
}
