package grid

import "loadcrest/internal/deck"

// Bus is a mutable operating bus (type may switch PV→PQ).
type Bus struct {
	ID           string
	DeclaredType deck.BusType
	Type         deck.BusType
	V            float64
	AngleRad     float64
	PGen         float64
	QGen         float64
	QMin         float64
	QMax         float64
	PLoad0       float64
	QLoad0       float64
	GShunt       float64
	BShunt       float64
	Switched     bool
}

// FromDeck builds operating buses from a network deck.
func BusesFromDeck(n *deck.Network) []Bus {
	out := make([]Bus, len(n.Buses))
	for i, b := range n.Buses {
		out[i] = Bus{
			ID: b.ID, DeclaredType: b.Type, Type: b.Type,
			V: b.VSet, AngleRad: b.Angle * deg2rad,
			PGen: b.PGen, QGen: b.QGen, QMin: b.QMin, QMax: b.QMax,
			PLoad0: b.PLoad, QLoad0: b.QLoad, GShunt: b.GShunt, BShunt: b.BShunt,
		}
	}
	return out
}

const deg2rad = 0.017453292519943295
