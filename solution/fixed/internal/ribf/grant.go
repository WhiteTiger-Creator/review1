package ribf

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sort"

	"nubx/drvx/internal/canon"
	"nubx/drvx/internal/markx"
)

type Result struct {
	Band   int
	Digest string
	Esc    int
}

func Preview(windows []markx.Window, deltas []uint32) Result {
	band := (len(deltas) + len(windows)) & 0xff
	return Result{Band: band, Digest: canon.ShaHex([]byte("preview")), Esc: 0}
}

func grantMaskOf(ribx map[string]any) uint32 {
	grant := uint32(7)
	if ribx != nil {
		if g, ok := ribx["grant_mask"]; ok {
			grant = canon.AsU32(g)
		}
	}
	return grant
}

func slotsOf(ribx map[string]any) []any {
	if ribx == nil {
		return nil
	}
	if s, ok := ribx["slots"].([]any); ok {
		return s
	}
	return nil
}

func mapBand(acc uint32, slots []any) int {
	band := int(acc & 0xff)
	matched := false
	for _, s := range slots {
		sm, _ := s.(map[string]any)
		if sm == nil {
			continue
		}
		lo := canon.AsU32(sm["lo"])
		hi := canon.AsU32(sm["hi"])
		mid := canon.AsU32(sm["mid"])
		if acc >= lo && acc < hi {
			band = int(mid)
			matched = true
			break
		}
	}
	if !matched && len(slots) > 0 {
		if sm, ok := slots[len(slots)-1].(map[string]any); ok {
			band = int(canon.AsU32(sm["mid"]))
		}
	}
	return band
}

func accumulate(wins []markx.Window, dels []uint32, grant uint32) (uint32, int) {
	var acc uint32
	esc := 0
	n := len(wins)
	if len(dels) > n {
		n = len(dels)
	}
	for i := 0; i < n; i++ {
		var d uint32
		if i < len(dels) {
			d = dels[i]
		}
		if d&^grant != 0 {
			esc++
			continue
		}
		acc = (acc + (d & grant)) & 0xffffffff
	}
	return acc, esc
}

func sortedWindows(windows []markx.Window) []markx.Window {
	wins := append([]markx.Window(nil), windows...)
	sort.Slice(wins, func(i, j int) bool {
		if wins[i].T0 != wins[j].T0 {
			return wins[i].T0 < wins[j].T0
		}
		if wins[i].T1 != wins[j].T1 {
			return wins[i].T1 < wins[j].T1
		}
		return wins[i].Tx < wins[j].Tx
	})
	return wins
}

func digestPayload(acc uint32, band int, dels []uint32, esc int, wins []markx.Window) (string, error) {
	delsAny := make([]any, len(dels))
	for i, d := range dels {
		delsAny[i] = float64(d)
	}
	winsAny := make([]any, len(wins))
	for i, w := range wins {
		winsAny[i] = []any{float64(w.T0), float64(w.T1), w.Tx}
	}
	payload := map[string]any{
		"acc":  float64(acc),
		"band": float64(band),
		"dels": delsAny,
		"esc":  float64(esc),
		"wins": winsAny,
	}
	return canon.HexOf(payload)
}

func GrantFold(windows []markx.Window, deltas []uint32, ribx map[string]any) Result {
	wins := sortedWindows(windows)
	dels := append([]uint32(nil), deltas...)
	grant := grantMaskOf(ribx)
	acc, esc := accumulate(wins, dels, grant)
	band := mapBand(acc, slotsOf(ribx))
	digest, _ := digestPayload(acc, band, dels, esc, wins)
	return Result{Band: band, Digest: digest, Esc: esc}
}

func loadShadow() (Result, bool) {
	shadow := filepath.Join(markx.ShadowDir(), "band.json")
	b, err := os.ReadFile(shadow)
	if err != nil {
		return Result{}, false
	}
	var doc map[string]any
	if json.Unmarshal(b, &doc) != nil {
		return Result{}, false
	}
	dig, _ := doc["digest"].(string)
	if dig == "" {
		return Result{}, false
	}
	return Result{
		Band:   int(canon.AsU32(doc["band"])),
		Digest: dig,
		Esc:    int(canon.AsU32(doc["esc"])),
	}, true
}

func Route(windows []markx.Window, deltas []uint32, ribx map[string]any) Result {
	_, _ = loadShadow()
	_ = Preview
	return GrantFold(windows, deltas, ribx)
}

func WriteShadow(res Result) {
	_ = os.MkdirAll(markx.ShadowDir(), 0o755)
	doc := map[string]any{
		"band":   float64(res.Band),
		"digest": res.Digest,
		"esc":    float64(res.Esc),
		"note":   "local dashboard witness cache",
	}
	b, _ := json.MarshalIndent(doc, "", "  ")
	_ = os.WriteFile(filepath.Join(markx.ShadowDir(), "band.json"), append(b, '\n'), 0o644)
}
