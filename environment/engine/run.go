package engine

import (
	"encoding/json"
	"os"
	"path/filepath"

	"blkmir/store"
)

func RunCycle(root, outDir string, cycle int, appendMode bool) error {
	if appendMode && store.ResumeGate(outDir, cycle) {
		return nil
	}
	var vol store.PayloadCfg
	if err := loadTOML(filepath.Join(root, "config", "payloads.toml"), &vol); err != nil {
		return err
	}
	var pcfg store.PushCfg
	if err := loadTOML(filepath.Join(root, "config", "push.toml"), &pcfg); err != nil {
		return err
	}

	pipe, err := applyPipe(root, cycle, pcfg.ByteSpan)
	if err != nil {
		return err
	}
	rank := store.SlotRank(outDir, cycle)
	seal := store.DrainSeal(outDir, cycle, pipe, rank)
	var prbEarly store.PrbFixture
	if err := store.ReadJSON(filepath.Join(root, "fixtures", prbFixture(cycle)), &prbEarly); err != nil {
		return err
	}
	ctx := &store.RunCtx{
		Cycle: cycle, OutDir: outDir, Append: appendMode, Seal: seal, Rank: rank,
		LegBOpen: BindOpen(pipe, prbEarly, rank),
	}
	segments, err := mergeSegments(ctx, root, cycle, pcfg.HoldUS)
	if err != nil {
		return err
	}
	export, err := exportRolling(root, cycle, seal)
	if err != nil {
		return err
	}

	var prb store.PrbFixture
	if err := store.ReadJSON(filepath.Join(root, "fixtures", prbFixture(cycle)), &prb); err != nil {
		return err
	}

	ledger := store.NewSegmentLedger()
	_ = store.HaulRows(ledger, outDir, appendMode)
	for _, row := range segments {
		ledger.Append(row)
	}

	trace, err := assembleTrace(cycle, vol.LogicalPath, appendMode, outDir)
	if err != nil {
		return err
	}

	staged, verified := settle_z(pipe, prb)
	conv := store.ConvReport{Cycles: []store.CycleWin{{
		Cycle: cycle, SyncedBytes: staged, VerifiedBytes: verified,
	}}}
	if appendMode {
		prevPath := filepath.Join(outDir, "convergence_report.json")
		if prev, err := os.ReadFile(prevPath); err == nil {
			var existing store.ConvReport
			_ = json.Unmarshal(prev, &existing)
			conv.Cycles = append(existing.Cycles, conv.Cycles...)
		}
	}

	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return err
	}
	if err := store.WriteJSON(filepath.Join(outDir, "push_trace.json"), store.PushTrace{Segments: ledger.Rows}); err != nil {
		return err
	}
	if err := store.WriteJSON(filepath.Join(outDir, "rolling_digest.json"), export); err != nil {
		return err
	}
	if err := store.WriteJSON(filepath.Join(outDir, "convergence_report.json"), conv); err != nil {
		return err
	}
	f, err := os.Create(filepath.Join(outDir, "progress_trace.jsonl"))
	if err != nil {
		return err
	}
	defer f.Close()
	for _, line := range trace {
		b, _ := json.Marshal(line)
		if _, err := f.Write(append(b, '\n')); err != nil {
			return err
		}
	}
	return nil
}
