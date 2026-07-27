package eng

import (
	"encoding/json"
	"os"
	"path/filepath"

	"k4/infer"
	"k4/loss"
	"k4/gate"
	"k4/src"
)

// RunAll regenerates observation roots and the rights artifact.
func RunAll(root, out string) error {
	_ = src.ScanHex([]float64{0.1, 0.2})
	_ = src.MeterLine("k4", 1)
	_ = src.DumpSummary(out)

	seal, err := OpenSeal(root)
	if err != nil {
		return err
	}
	if err := TruncateLedger(); err != nil {
		return err
	}

	prim, err := buildRoot(root, "primary", seal)
	if err != nil {
		return err
	}
	hold, err := buildRoot(root, "hold", seal)
	if err != nil {
		return err
	}
	if err := writeObs(filepath.Join(out, "obs_primary.json"), prim); err != nil {
		return err
	}
	if err := writeObs(filepath.Join(out, "obs_hold.json"), hold); err != nil {
		return err
	}

	allRows := append([]gate.Row{}, prim.Rows...)
	allRows = append(allRows, hold.Rows...)
	neg := gate.NegOf(allRows)
	if err := gate.Emit(out, allRows, neg); err != nil {
		return err
	}
	if err := patchSheet(out, prim, hold, neg, seal); err != nil {
		return err
	}
	return CommitSeal(seal, prim.BandDigest, hold.BandDigest, prim.QDigest, hold.QDigest)
}

type obsRoot struct {
	Root       string   `json:"root"`
	Rows       []gate.Row `json:"rows"`
	BandDigest string   `json:"band_digest"`
	QDigest    string   `json:"q_digest"`
	Gen        int      `json:"gen"`
	EvalFP     string   `json:"eval_fp"`
}

func buildRoot(root, name string, seal Seal) (obsRoot, error) {
	files, err := ListPackFiles(root, name)
	if err != nil {
		return obsRoot{}, err
	}
	rows := []gate.Row{}
	bandMap := map[string][]float64{}
	qMap := map[string][]float64{}
	sids := []string{}
	for _, fp := range files {
		p, err := LoadPack(fp)
		if err != nil {
			return obsRoot{}, err
		}
		for _, ch := range p.Ch {
			infer.SetMeta(ch.SL, p.Cuts)
			cache := NewCache()
			wantGen := p.Gen
			if rec, ok := LoadJournal(root, ch.Sid); ok {
				SeedCache(cache, rec, wantGen)
			}
			epoch := len(ch.Tr) - 1
			bands := infer.Fold(ch.Tr, cache, epoch)
			cls := infer.Ladder(ch.Tr, epoch)
			loss.SetLadder(cls)
			prior := p.Prior
			if rec, ok := LoadJournal(root, ch.Sid); ok && p.Mode >= 1 && rec.Gen == wantGen {
				if len(rec.Q) == len(bands) {
					prior = append([]float64(nil), rec.Q...)
				}
			}
			if len(prior) != len(bands) {
				prior = make([]float64, len(bands))
			}
			q := loss.Recompute(bands, prior, p.Mode)
			fld := loss.FldMark(bands)
			row := gate.Row{Sid: ch.Sid, Bands: bands, Cls: cls, Q: q, Fld: fld}
			rows = append(rows, row)
			bandMap[ch.Sid] = bands
			qMap[ch.Sid] = q
			sids = append(sids, ch.Sid)
			_ = SaveJournal(root, ch.Sid, JRec{
				Gen:    wantGen,
				Bands:  append([]float64(nil), bands...),
				Cls:    append([]int(nil), cls...),
				Q:      append([]float64(nil), q...),
				EvalFP: seal.EvalFP,
			})
			_ = AppendLedger(LedgerLine{
				Sid:    ch.Sid,
				Root:   name,
				Bands:  append([]float64(nil), bands...),
				Cls:    append([]int(nil), cls...),
				Q:      append([]float64(nil), q...),
				Fld:    fld,
				Gen:    seal.Gen,
				EvalFP: seal.EvalFP,
			})
		}
	}
	return obsRoot{
		Root:       name,
		Rows:       rows,
		BandDigest: HexDigest(JoinBands(sids, bandMap)),
		QDigest:    HexDigest(JoinBands(sids, qMap)),
		Gen:        seal.Gen,
		EvalFP:     seal.EvalFP,
	}, nil
}

func writeObs(path string, o obsRoot) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	enc := json.NewEncoder(f)
	enc.SetEscapeHTML(false)
	return enc.Encode(o)
}

func patchSheet(out string, prim, hold obsRoot, neg []string, seal Seal) error {
	path := filepath.Join(out, "rights_map.json")
	b, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	var doc map[string]any
	if err := json.Unmarshal(b, &doc); err != nil {
		return err
	}
	doc["digests"] = map[string]string{"primary": prim.BandDigest, "hold": hold.BandDigest}
	doc["qdig"] = map[string]string{"primary": prim.QDigest, "hold": hold.QDigest}
	doc["gen"] = seal.Gen
	doc["eval_fp"] = seal.EvalFP
	fldAny := 0
	for _, r := range append(prim.Rows, hold.Rows...) {
		if r.Fld == 1 {
			fldAny = 1
			break
		}
	}
	doc["fld_any"] = fldAny
	_ = neg
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	enc := json.NewEncoder(f)
	enc.SetEscapeHTML(false)
	return enc.Encode(doc)
}
