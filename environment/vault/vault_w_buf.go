package vault

// BufSnap captures ledger depth for operator dashboards.
type BufSnap struct {
	Depth int
}

func (b *BufSnap) Capture(led *Ledger) {
	if led == nil {
		b.Depth = 0
		return
	}
	b.Depth = len(led.Entries)
}
