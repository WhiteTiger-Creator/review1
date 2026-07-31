package duplexstitch

import (
	"sort"

	"cdnqual/framestream"
)

const (
	FlagFIN = 0x01
	FlagSYN = 0x02
	FlagRST = 0x04
	FlagPSH = 0x08
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
	if len(pkts) == 0 {
		return Bout{ID: boutID}
	}
	firstTS := pkts[0].TsTotal()
	lastTS := pkts[0].TsTotal()
	for _, p := range pkts {
		t := p.TsTotal()
		if t < firstTS {
			firstTS = t
		}
		if t > lastTS {
			lastTS = t
		}
	}

	var syn *framestream.Packet
	for i := range pkts {
		p := &pkts[i]
		if p.Flags&FlagSYN != 0 && p.Flags&FlagACK == 0 {
			syn = p
			break
		}
	}
	clientKey := ""
	serverKey := ""
	var synTS int64
	if syn != nil {
		clientKey = framestream.FlowKey(*syn)
		serverKey = framestream.SwapKey(*syn)
		synTS = syn.TsTotal()
	} else {
		// fallback: first packet defines client
		clientKey = framestream.FlowKey(pkts[0])
		serverKey = framestream.SwapKey(pkts[0])
		synTS = pkts[0].TsTotal()
	}

	var clientPkts, serverPkts []framestream.Packet
	finSeen := 0
	for _, p := range pkts {
		k := framestream.FlowKey(p)
		if k == clientKey {
			clientPkts = append(clientPkts, p)
		} else if k == serverKey {
			serverPkts = append(serverPkts, p)
		}
		if p.Flags&FlagFIN != 0 {
			finSeen = 1
		}
	}

	cOrigin, cHas := dataOrigin(clientPkts, true)
	sOrigin, sHas := dataOrigin(serverPkts, false)
	cStats := reassembleUni(clientPkts, cOrigin, cHas)
	sStats := reassembleUni(serverPkts, sOrigin, sHas)

	var synAckRTT int64
	for _, p := range serverPkts {
		if p.Flags&FlagSYN != 0 && p.Flags&FlagACK != 0 {
			synAckRTT = p.TsTotal() - synTS
			if synAckRTT < 0 {
				synAckRTT = 0
			}
			break
		}
	}

	return Bout{
		ID:              boutID,
		ClientPayload:   cStats.Payload,
		ServerPayload:   sStats.Payload,
		PacketCount:     cStats.PacketCount + sStats.PacketCount,
		RetransmitCount: cStats.RetransmitCount + sStats.RetransmitCount,
		OutOfOrderCount: cStats.OutOfOrderCount + sStats.OutOfOrderCount,
		OverlapBytes:    cStats.OverlapByteCount + sStats.OverlapByteCount,
		UniqueSeqSpan:   cStats.UniqueSeqSpan + sStats.UniqueSeqSpan,
		DurationUS:      lastTS - firstTS,
		SynAckRTTUS:     synAckRTT,
		FinSeen:         finSeen,
		FirstTS:         firstTS,
		LastTS:          lastTS,
	}
}

func dataOrigin(pkts []framestream.Packet, client bool) (uint32, bool) {
	for _, p := range pkts {
		if client {
			if p.Flags&FlagSYN != 0 && p.Flags&FlagACK == 0 {
				return p.Seq + 1, true
			}
		} else {
			if p.Flags&FlagSYN != 0 && p.Flags&FlagACK != 0 {
				return p.Seq + 1, true
			}
		}
	}
	// no SYN: use first data packet seq as origin
	for _, p := range pkts {
		if len(p.Payload) > 0 {
			return p.Seq, true
		}
	}
	return 0, false
}

func reassembleUni(pkts []framestream.Packet, origin uint32, hasOrigin bool) UniStats {
	st := UniStats{PacketCount: len(pkts)}
	if !hasOrigin {
		return st
	}
	buf := map[int64]byte{}
	coveredMax := int64(-1) // highest contiguous covered from 0

	// process in arrival order (slice order)
	for _, p := range pkts {
		if len(p.Payload) == 0 {
			continue
		}
		off := seqOffset(p.Seq, origin)
		end := off + int64(len(p.Payload)) - 1

		// OOO detection against contiguous coverage before apply
		if off > coveredMax+1 {
			st.OutOfOrderCount++
		}

		identical := true
		anyExists := false
		for i := 0; i < len(p.Payload); i++ {
			o := off + int64(i)
			if b, ok := buf[o]; ok {
				anyExists = true
				if b != p.Payload[i] {
					identical = false
					st.OverlapByteCount++
				}
			} else {
				identical = false
			}
			_ = o
		}
		if anyExists && identical {
			st.RetransmitCount++
			continue
		}

		for i := 0; i < len(p.Payload); i++ {
			buf[off+int64(i)] = p.Payload[i]
		}

		// recompute contiguous coverage from 0
		coveredMax = -1
		for {
			if _, ok := buf[coveredMax+1]; ok {
				coveredMax++
				continue
			}
			break
		}
		_ = end
	}

	if len(buf) == 0 {
		return st
	}
	keys := make([]int64, 0, len(buf))
	for k := range buf {
		keys = append(keys, k)
	}
	sort.Slice(keys, func(i, j int) bool { return keys[i] < keys[j] })
	st.UniqueSeqSpan = int(keys[len(keys)-1] - keys[0] + 1)
	// Actually spec: (max_written_offset+1) for offsets that received writes — from 0 perspective
	maxOff := keys[0]
	for _, k := range keys {
		if k > maxOff {
			maxOff = k
		}
	}
	minNonNeg := int64(0)
	hasNonNeg := false
	for _, k := range keys {
		if k >= 0 {
			if !hasNonNeg || k < minNonNeg {
				minNonNeg = k
			}
			hasNonNeg = true
		}
	}
	if hasNonNeg {
		st.UniqueSeqSpan = int(maxOff + 1)
	}

	// emit contiguous from 0 until first gap
	var payload []byte
	for o := int64(0); ; o++ {
		b, ok := buf[o]
		if !ok {
			break
		}
		payload = append(payload, b)
	}
	st.Payload = payload
	return st
}

func seqOffset(seq, origin uint32) int64 {
	return int64(int32(seq - origin))
}
