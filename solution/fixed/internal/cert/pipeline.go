package cert

import (
	"os"
	"path/filepath"

	"nubx/drvx/internal/ribf"
	"nubx/drvx/internal/canon"
	"nubx/drvx/internal/markx"
)

func envRoot() string {
	if v := os.Getenv("DRVX_ENV"); v != "" {
		return v
	}
	return "/app/environment"
}

func Run(transcriptPath, reportPath string) error {
	raw, err := canon.LoadJSON(transcriptPath)
	if err != nil {
		return err
	}
	doc := raw.(map[string]any)
	ribxRaw, err := canon.LoadJSON(filepath.Join(envRoot(), "corpus", "ribx.json"))
	if err != nil {
		return err
	}
	ribx := ribxRaw.(map[string]any)
	rows := doc["rows"].([]any)
	obs := make([]any, 0, len(rows))
	var allW []markx.Window
	var allD []uint32
	for _, r := range rows {
		rm := r.(map[string]any)
		wins := windowsOf(rm)
		dels := deltasOf(rm)
		a := ribf.Route(wins, dels, ribx)
		b := ribf.Route(wins, dels, ribx)
		obs = append(obs, map[string]any{
			"lane":         rm["lane"],
			"band":         float64(a.Band),
			"digest":       a.Digest,
			"replay_match": a.Digest == b.Digest,
			"esc":          float64(a.Esc),
		})
		allW = append(allW, wins...)
		allD = append(allD, dels...)
	}
	g1 := ribf.Route(allW, allD, ribx)
	g2 := ribf.Route(allW, allD, ribx)
	inBand := false
	if slots, ok := ribx["slots"].([]any); ok {
		for _, s := range slots {
			sm := s.(map[string]any)
			lo := int(canon.AsU32(sm["lo"]))
			hi := int(canon.AsU32(sm["hi"]))
			if g1.Band >= lo && g1.Band < hi {
				inBand = true
				break
			}
		}
	}
	out := map[string]any{
		"schema":        "nubx-replay-v1",
		"band":          float64(g1.Band),
		"digest":        g1.Digest,
		"replay_digest": g2.Digest,
		"observations":  obs,
		"in_band":       inBand,
	}
	return canon.WritePretty(reportPath, out)
}

func windowsOf(rm map[string]any) []markx.Window {
	raw, _ := rm["windows"].([]any)
	out := make([]markx.Window, 0, len(raw))
	for _, w := range raw {
		wm := w.(map[string]any)
		tx, _ := wm["tx"].(string)
		out = append(out, markx.Window{T0: canon.AsU32(wm["t0"]), T1: canon.AsU32(wm["t1"]), Tx: tx})
	}
	return out
}

func deltasOf(rm map[string]any) []uint32 {
	raw, _ := rm["deltas"].([]any)
	out := make([]uint32, 0, len(raw))
	for _, d := range raw {
		out = append(out, canon.AsU32(d))
	}
	return out
}
