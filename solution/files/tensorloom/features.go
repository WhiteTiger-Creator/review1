package tensorloom

import (
	"cdnqual/duplexstitch"
	"cdnqual/entropymilli"
)

// Knit builds the fixed 12-D integer feature tensor for a bout.
func Knit(b duplexstitch.Bout) []int {
	payloadN := len(b.ClientPayload) + len(b.ServerPayload)
	pkt := b.PacketCount
	if pkt < 1 {
		pkt = 1
	}
	avgMilli := 1000 * payloadN / pkt
	concat := append(append([]byte{}, b.ClientPayload...), b.ServerPayload...)
	entropy := entropymilli.Of(concat)
	asym := 0
	if payloadN > 0 {
		asym = 1000 * len(b.ClientPayload) / payloadN
	}
	return []int{
		payloadN,
		b.PacketCount,
		b.RetransmitCount,
		b.OutOfOrderCount,
		b.OverlapBytes,
		int(b.DurationUS),
		avgMilli,
		int(b.SynAckRTTUS),
		b.FinSeen,
		entropy,
		b.UniqueSeqSpan,
		asym,
	}
}
