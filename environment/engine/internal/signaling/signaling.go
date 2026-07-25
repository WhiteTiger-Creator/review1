package signaling

import (
	"fmt"
	"sort"
	"strings"
)

var DefaultTypes = []string{
	"WARN_LANE", "COVER", "NEED_POWER", "ACK", "SYNC_CAPTURE", "STATUS", "CANCEL_SCAN",
}

type Message struct {
	ID      string         `json:"id"`
	From    string         `json:"from"`
	To      string         `json:"to"`
	Type    string         `json:"type"`
	Sector  string         `json:"sector,omitempty"`
	Contact string         `json:"contact,omitempty"`
	Payload map[string]any `json:"payload,omitempty"`
	Round   int            `json:"round"`
	Bytes   int            `json:"bytes"`
}

type Bus struct {
	Budget       int
	Used         int
	Types        map[string]bool
	MaxBytes     int
	Pending      []Message // deliver next round
	Inbox        []Message
	Jammed       bool
	History      []Message
	nextID       int
	AckRequired  map[string]bool
}

func NewBus(budget int, types []string, maxBytes int) *Bus {
	m := map[string]bool{}
	if len(types) == 0 {
		types = DefaultTypes
	}
	for _, t := range types {
		m[t] = true
	}
	if maxBytes <= 0 {
		maxBytes = 128
	}
	return &Bus{
		Budget:      budget,
		Types:       m,
		MaxBytes:    maxBytes,
		AckRequired: map[string]bool{},
	}
}

func (b *Bus) AdvanceRound() {
	b.Inbox = append([]Message(nil), b.Pending...)
	b.Pending = nil
	b.Jammed = false
}

func (b *Bus) SetJammed(v bool) {
	b.Jammed = v
}

func (b *Bus) CanSend(msgType string, approxBytes int) error {
	if !b.Types[msgType] {
		return fmt.Errorf("malformed signal type %s", msgType)
	}
	if b.Used >= b.Budget {
		return fmt.Errorf("signal budget exhausted")
	}
	if approxBytes > b.MaxBytes {
		return fmt.Errorf("message too large")
	}
	// Illegal: cannot transmit hidden threat plans or partner private observations
	if strings.HasPrefix(msgType, "HIDDEN_") || msgType == "WAVE_PLAN" || msgType == "PARTNER_PRIVATE" {
		return fmt.Errorf("illegal signal content")
	}
	return nil
}

func (b *Bus) Enqueue(from, to, msgType, sector, contact string, payload map[string]any, round int) (Message, error) {
	bytes := 16 + len(msgType) + len(sector) + len(contact)
	if err := b.CanSend(msgType, bytes); err != nil {
		return Message{}, err
	}
	if b.Jammed && msgType == "ACK" {
		return Message{}, fmt.Errorf("ack jammed")
	}
	b.nextID++
	id := fmt.Sprintf("sig-%03d", b.nextID)
	msg := Message{
		ID: id, From: from, To: to, Type: msgType,
		Sector: sector, Contact: contact, Payload: payload,
		Round: round, Bytes: bytes,
	}
	if b.Jammed {
		// jammed: message is dropped but still consumes token for non-status? consume budget still
		b.Used++
		b.History = append(b.History, msg)
		return msg, fmt.Errorf("message jammed")
	}
	b.Used++
	b.Pending = append(b.Pending, msg)
	b.History = append(b.History, msg)
	if msgType == "WARN_LANE" || msgType == "SYNC_CAPTURE" {
		b.AckRequired[id] = true
	}
	return msg, nil
}

func (b *Bus) DeliveredSorted() []Message {
	out := append([]Message(nil), b.Inbox...)
	sort.Slice(out, func(i, j int) bool {
		if out[i].Round != out[j].Round {
			return out[i].Round < out[j].Round
		}
		return out[i].ID < out[j].ID
	})
	return out
}

func (b *Bus) HistorySorted() []Message {
	out := append([]Message(nil), b.History...)
	sort.Slice(out, func(i, j int) bool {
		if out[i].Round != out[j].Round {
			return out[i].Round < out[j].Round
		}
		return out[i].ID < out[j].ID
	})
	return out
}
