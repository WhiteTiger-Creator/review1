package synth

import (
	"fmt"
	"os"
	"path/filepath"
	"sort"

	"nubx/drvx/internal/ribf"
	"nubx/drvx/internal/canon"
	"nubx/drvx/internal/markx"
	"nubx/drvx/internal/bagx"
)

func envRoot() string {
	if v := os.Getenv("DRVX_ENV"); v != "" {
		return v
	}
	return "/app/environment"
}

func Run(annexPath, outPath string) error {
	env := envRoot()
	metaRaw, err := canon.LoadJSON(filepath.Join(env, "data", "suite_meta.json"))
	if err != nil {
		return err
	}
	meta := metaRaw.(map[string]any)
	lanesAny := meta["lanes"].([]any)
	annex, err := os.ReadFile(annexPath)
	if err != nil {
		return err
	}
	slabsDir := filepath.Join(env, "corpus", "slabs")
	entries, _ := os.ReadDir(slabsDir)
	type slab struct {
		Name string
		Doc  map[string]any
	}
	var slabs []slab
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		raw, err := canon.LoadJSON(filepath.Join(slabsDir, e.Name()))
		if err != nil {
			return err
		}
		slabs = append(slabs, slab{Name: e.Name(), Doc: raw.(map[string]any)})
	}
	sort.Slice(slabs, func(i, j int) bool { return slabs[i].Name < slabs[j].Name })

	rows := make([]any, 0, len(lanesAny))
	escTotal := 0
	scratch := markx.ScratchDir()
	for _, laneV := range lanesAny {
		lane := laneV.(string)
		var sl slab
		for _, s := range slabs {
			if s.Doc["lane"] == lane {
				sl = s
				break
			}
		}
		actorsAny, _ := sl.Doc["actors"].([]any)
		actors := make([]int, 0, len(actorsAny))
		for _, a := range actorsAny {
			actors = append(actors, int(canon.AsU32(a)))
		}
		wins := markx.PullWindows(annex, lane, scratch)
		markx.WriteResiduals(lane, wins)
		folded := bagx.Fold(sl.Doc["root"], sl.Doc["patch"], actors)
		pair := bagx.Fold(sl.Doc["root"], bagx.ReverseKeys(sl.Doc["patch"]), actors)
		knitHex, _ := canon.HexOf(folded)
		pairHex, _ := canon.HexOf(pair)
		esc := bagx.CountEsc(folded, actors)
		escTotal += esc
		deltasAny, _ := sl.Doc["deltas"].([]any)
		deltas := make([]any, 0, len(deltasAny))
		for _, d := range deltasAny {
			deltas = append(deltas, float64(canon.AsU32(d)))
		}
		for len(deltas) < len(wins) {
			deltas = append(deltas, float64(0))
		}
		winRows := make([]any, 0, len(wins))
		for _, w := range wins {
			winRows = append(winRows, map[string]any{
				"t0": float64(w.T0), "t1": float64(w.T1), "tx": w.Tx,
			})
		}
		rows = append(rows, map[string]any{
			"lane":      lane,
			"slab":      sl.Name,
			"knit_hex":  knitHex,
			"pair_hex":  pairHex,
			"esc_hits":  float64(esc),
			"win_count": float64(len(wins)),
			"windows":   winRows,
			"deltas":    deltas,
		})
	}
	parts := ""
	for i, r := range rows {
		rm := r.(map[string]any)
		if i > 0 {
			parts += "|"
		}
		parts += fmt.Sprintf("%s:%s:%s:%d", rm["lane"], rm["knit_hex"], rm["pair_hex"], int(canon.AsU32(rm["esc_hits"])))
	}
	suite := canon.ShaHex([]byte(parts))
	doc := map[string]any{
		"schema":           "nubx-transcript-v1",
		"rows":             rows,
		"escalation_total": float64(escTotal),
		"suite_digest":     suite,
	}
	if err := canon.WritePretty(outPath, doc); err != nil {
		return err
	}
	var allW []markx.Window
	var allD []uint32
	for _, r := range rows {
		rm := r.(map[string]any)
		for _, w := range rm["windows"].([]any) {
			wm := w.(map[string]any)
			allW = append(allW, markx.Window{T0: canon.AsU32(wm["t0"]), T1: canon.AsU32(wm["t1"]), Tx: wm["tx"].(string)})
		}
		for _, d := range rm["deltas"].([]any) {
			allD = append(allD, canon.AsU32(d))
		}
	}
	ribf.WriteShadow(ribf.Preview(allW, allD))
	return nil
}
