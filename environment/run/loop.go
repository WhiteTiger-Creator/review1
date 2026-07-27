package run

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"cqrun/internal/util"
	"cqrun/knot"
	"cqrun/sieve"
	"cqrun/vault"
)

type Policy struct {
	Epochs             int
	Alpha              float64
	FenceLag           int
	BandCuts           []float64
	InterruptAfter     int
	WeightDecimals     int
}

func LoadPolicy(path string) (Policy, error) {
	b, err := os.ReadFile(path)
	if err != nil {
		return Policy{}, err
	}
	p := Policy{
		Epochs:         2,
		Alpha:          0.35,
		FenceLag:       1,
		BandCuts:       []float64{0.25, 0.5, 0.75},
		InterruptAfter: 1,
		WeightDecimals: 6,
	}
	for _, line := range strings.Split(string(b), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") || !strings.Contains(line, "=") {
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		k := strings.TrimSpace(parts[0])
		v := strings.TrimSpace(parts[1])
		switch k {
		case "epochs":
			p.Epochs, _ = strconv.Atoi(v)
		case "alpha":
			p.Alpha, _ = strconv.ParseFloat(v, 64)
		case "fence_lag":
			p.FenceLag, _ = strconv.Atoi(v)
		case "interrupt_after_epoch":
			p.InterruptAfter, _ = strconv.Atoi(v)
		case "weight_decimals":
			p.WeightDecimals, _ = strconv.Atoi(v)
		case "band_cuts":
			inner := strings.Trim(v, "[]")
			p.BandCuts = nil
			for _, piece := range strings.Split(inner, ",") {
				piece = strings.TrimSpace(piece)
				if piece == "" {
					continue
				}
				f, err := strconv.ParseFloat(piece, 64)
				if err == nil {
					p.BandCuts = append(p.BandCuts, f)
				}
			}
		}
	}
	return p, nil
}

func Loop(packsDir, outPath, stateDir, polPath string) error {
	pol, err := LoadPolicy(polPath)
	if err != nil {
		return err
	}
	seeds, err := util.LoadSeeds(packsDir)
	if err != nil {
		return err
	}
	book := knot.NewBook(pol.Alpha, pol.BandCuts)
	for _, s := range seeds {
		for _, it := range s.Items {
			book.Seed(s.ID, it.ItemID, it.Prior, it.Signal)
		}
	}
	led := vault.NewLedger(stateDir)
	_ = os.RemoveAll(stateDir)
	_ = os.MkdirAll(stateDir, 0o755)

	rows := make([]sieve.Row, 0, 64)
	startEpoch := 1
	for epoch := startEpoch; epoch <= pol.Epochs; epoch++ {
		if err := runEpoch(book, led, seeds, pol, epoch, &rows); err != nil {
			return err
		}
		if err := vault.ApplyVault(led, book, epoch); err != nil {
			return err
		}
		var snap vault.BufSnap
		snap.Capture(led)
		_ = snap

		if epoch == pol.InterruptAfter && epoch < pol.Epochs {
			if err := vault.ResumeInto(led, book); err != nil {
				return err
			}
		}
	}

	trace := sieve.Trace{
		Rows:    rows,
		Summary: sieve.FoldRows(rows, pol.Epochs, len(led.Entries), pol.WeightDecimals, book),
	}
	if err := os.MkdirAll(filepath.Dir(outPath), 0o755); err != nil {
		return err
	}
	b, err := json.MarshalIndent(trace, "", "  ")
	if err != nil {
		return err
	}
	b = append(b, '\n')
	return os.WriteFile(outPath, b, 0o644)
}

func runEpoch(book *knot.Book, led *vault.Ledger, seeds []util.Seed, pol Policy, epoch int, rows *[]sieve.Row) error {
	forbidden := vault.TrainForbidden(led, epoch, pol.FenceLag)
	for _, seed := range seeds {
		items := make([]sieve.ItemRef, 0, len(seed.Items))
		for _, it := range seed.Items {
			items = append(items, sieve.ItemRef{
				SID: seed.ID,
				IID: it.ItemID,
				W:   book.Weight(seed.ID, it.ItemID),
			})
		}
		trainN := len(items) / 2
		train, eval, err := sieve.ApplySieve(items, forbidden, trainN)
		if err != nil {
			return err
		}
		for _, ref := range train {
			w, band, err := knot.ApplyKnot(book, ref.SID, ref.IID, true)
			if err != nil {
				return err
			}
			row := sieve.StampRow(ref.SID, ref.IID, epoch, "train", band, w, forbidden, pol.WeightDecimals)
			*rows = append(*rows, row)
			_ = sieve.DebugFmt(row)
			if err := vault.AppendAdmit(led, vault.Entry{
				Epoch: epoch,
				SID:   ref.SID,
				IID:   ref.IID,
				Role:  "train",
				Band:  band,
				WPre:  w,
			}); err != nil {
				return err
			}
		}
		for _, ref := range eval {
			w, band, err := knot.ApplyKnot(book, ref.SID, ref.IID, false)
			if err != nil {
				return err
			}
			row := sieve.StampRow(ref.SID, ref.IID, epoch, "eval", band, w, forbidden, pol.WeightDecimals)
			*rows = append(*rows, row)
			if err := vault.AppendAdmit(led, vault.Entry{
				Epoch: epoch,
				SID:   ref.SID,
				IID:   ref.IID,
				Role:  "eval",
				Band:  band,
				WPre:  w,
			}); err != nil {
				return err
			}
		}
	}
	return nil
}
