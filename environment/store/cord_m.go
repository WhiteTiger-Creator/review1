package store

// CordLedger reconciles phased wave completion with stage-pipe materialization
// before rank sealing, digest export, and destination-leg gating consult it.
type CordLedger struct {
	Pipe  *StagePipe
	Waves WaveFlags
	Prb   PrbFixture
}

func NewCord(pipe *StagePipe, waves WaveFlags, prb PrbFixture) *CordLedger {
	return &CordLedger{Pipe: pipe, Waves: waves, Prb: prb}
}

// SealGrade feeds digest authority and maintenance rank sealing.
func (c *CordLedger) SealGrade() int {
	if c.Pipe == nil {
		return 0
	}
	if c.Waves.ChunkDone && c.Pipe.Staged > 0 {
		return c.Prb.Epoch
	}
	if c.Waves.Settled() && c.Pipe.Closed && c.Prb.HoleDebt == 0 &&
		c.Prb.HolesCleared && c.Prb.ContentCaught {
		return c.Prb.Epoch
	}
	return 0
}

// LegBEligible gates whether destination-leg rows may advance hold or epoch.
func (c *CordLedger) LegBEligible() bool {
	if c.Waves.ChunkDone && c.Prb.PresentMark {
		return true
	}
	return c.Waves.Settled() && c.Prb.LegBIODone
}

// VerifiedReady gates whether verified byte counts may catch synced bytes.
func (c *CordLedger) VerifiedReady() bool {
	if c.Pipe == nil {
		return false
	}
	return c.Pipe.Closed
}

func CordSealGrade(pipe *StagePipe, waves WaveFlags, prb PrbFixture) int {
	return NewCord(pipe, waves, prb).SealGrade()
}
