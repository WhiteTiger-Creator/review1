package engine

import "blkmir/store"

// CreditVerified maps wave progression and coordinator readiness into verified byte credit.
func CreditVerified(pipe *store.StagePipe, waves store.WaveFlags, cord *store.CordLedger) int {
	if waves.ChunkDone && waves.RollDone && !waves.LatchDone && pipe.Staged > 0 {
		return pipe.Staged
	}
	if cord != nil && cord.VerifiedReady() {
		return pipe.Staged
	}
	return 0
}

// SettlePhased derives synced and verified byte counts from finalized pipe and coordinator state.
func SettlePhased(pipe *store.StagePipe, prb store.PrbFixture, waves store.WaveFlags, cord *store.CordLedger) (int, int) {
	synced := pipe.Staged
	verified := CreditVerified(pipe, waves, cord)
	_ = prb
	return synced, verified
}
