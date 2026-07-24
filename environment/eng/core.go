package eng

import (
	"encoding/json"
	"os"
	"path/filepath"

	"k4/ax"
	"k4/bx"
	"k4/cx"
	"k4/src"
)

// RunAll regenerates observation roots and the rights artifact.
func RunAll(root, out string) error {
	_ = src.ScanHex([]float64{0.1, 0.2})
	_ = src.MeterLine("k4", 1)
	_ = src.DumpSummary(out)

	prim, err := buildRoot(root, "primary")
	if err != nil {
		return err
	}
	hold, err := buildRoot(root, "hold")
	if err != nil {
		return err
	}
	if err := writeObs(filepath.Join(out, "obs_primary.json"), prim); err != nil {
		return err
	}
	if err := writeObs(filepath.Join(out, "obs_hold.json"), hold); err != nil {
		return err
	}

	allRows := append([]cx.Row{}, prim.Rows...)
	allRows = append(allRows, hold.Rows...)
	neg := cx.NegOf(allRows)
	if err := cx.Emit(out, allRows, neg); err != nil {
		return err
	}
	return patchSheet(out, prim, hold, neg)
}

type obsRoot struct {
	Root       string   `json:"root"`
	Rows       []cx.Row `json:"rows"`
	BandDigest string   `json:"band_digest"`
	QDigest    string   `json:"q_digest"`
}

func buildRoot(root, name string) (obsRoot, error) {
	files, err := ListPackFiles(root, name)
	if err != nil {
		return obsRoot{}, err
	}
	rows := []cx.Row{}
	bandMap := map[string][]float64{}
	qMap := map[string][]float64{}
	sids := []string{}
	for _, fp := range files {
		p, err := LoadPack(fp)
		if err != nil {
			return obsRoot{}, err
		}
		for _, ch := range p.Ch {
			ax.SetMeta(ch.SL, p.Cuts)
			cache := NewCache()
			wantGen := p.Gen
			if rec, ok := LoadJournal(root, ch.Sid); ok {
				SeedCache(cache, rec, wantGen)
			}
			epoch := len(ch.Tr) - 1
			bands := ax.Fold(ch.Tr, cache, epoch)
			cls := ax.Ladder(ch.Tr, epoch)
			bx.SetLadder(cls)
			prior := p.Prior
			if rec, ok := LoadJournal(root, ch.Sid); ok && p.Mode >= 1 && rec.Gen == wantGen {
				if len(rec.Q) == len(bands) {
					prior = append([]float64(nil), rec.Q...)
				}
			}
			if len(prior) != len(bands) {
				prior = make([]float64, len(bands))
			}
			q := bx.Recompute(bands, prior, p.Mode)
			fld := bx.FldMark(bands)
			row := cx.Row{Sid: ch.Sid, Bands: bands, Cls: cls, Q: q, Fld: fld}
			rows = append(rows, row)
			bandMap[ch.Sid] = bands
			qMap[ch.Sid] = q
			sids = append(sids, ch.Sid)
			_ = SaveJournal(root, ch.Sid, JRec{
				Gen:   wantGen,
				Bands: append([]float64(nil), bands...),
				Cls:   append([]int(nil), cls...),
				Q:     append([]float64(nil), q...),
			})
		}
	}
	return obsRoot{
		Root:       name,
		Rows:       rows,
		BandDigest: HexDigest(JoinBands(sids, bandMap)),
		QDigest:    HexDigest(JoinBands(sids, qMap)),
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

func patchSheet(out string, prim, hold obsRoot, neg []string) error {
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
