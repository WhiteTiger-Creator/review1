package knot

func NewBook(alpha float64, cuts []float64) *Book {
	return &Book{
		W:      map[string]float64{},
		Sig:    map[string]float64{},
		Prior:  map[string]float64{},
		Alpha:  alpha,
		Cuts:   append([]float64(nil), cuts...),
		Shadow: map[string]float64{},
	}
}

func (b *Book) Seed(sid, iid string, prior, signal float64) {
	k := Key(sid, iid)
	b.Prior[k] = prior
	b.Sig[k] = signal
	b.W[k] = prior
	b.Shadow[k] = prior
}

func (b *Book) Weight(sid, iid string) float64 {
	return b.W[Key(sid, iid)]
}

func (b *Book) ResetFromPriors() {
	for k, p := range b.Prior {
		b.W[k] = p
		b.Shadow[k] = p
	}
	b.Frozen = false
}
