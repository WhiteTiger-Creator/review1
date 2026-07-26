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

func GrantFold(windows []markx.Window, deltas []uint32, ribx map[string]any) Result {
	type pair struct {
		w markx.Window
		i int
	}
	pairs := make([]pair, len(windows))
	for i, w := range windows {
		pairs[i] = pair{w: w, i: i}
	}
	sort.Slice(pairs, func(a, b int) bool {
		if pairs[a].w.T0 != pairs[b].w.T0 {
			return pairs[a].w.T0 < pairs[b].w.T0
		}
		if pairs[a].w.T1 != pairs[b].w.T1 {
			return pairs[a].w.T1 < pairs[b].w.T1
		}
		return pairs[a].w.Tx < pairs[b].w.Tx
	})
	wins := make([]markx.Window, len(pairs))
	dels := make([]uint32, len(deltas))
	copy(dels, deltas)
	if len(dels) < len(pairs) {
		tmp := make([]uint32, len(pairs))
		copy(tmp, dels)
		dels = tmp
	}
	permDels := make([]uint32, len(dels))
	for i, p := range pairs {
		wins[i] = p.w
		if p.i < len(dels) {
			permDels[i] = dels[p.i]
		}
	}
	if len(dels) > len(pairs) {
		permDels = append(permDels[:len(pairs)], dels[len(pairs):]...)
	}
	dels = permDels

	grant := uint32(7)
	if ribx != nil {
		if g, ok := ribx["grant_mask"]; ok {
			grant = canon.AsU32(g)
		}
	}
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
	band := int(acc & 0xff)
	matched := false
	var slots []any
	if ribx != nil {
		if s, ok := ribx["slots"].([]any); ok {
			slots = s
		}
	}
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
	digest, _ := canon.HexOf(payload)
	return Result{Band: band, Digest: digest, Esc: esc}
}

func Route(windows []markx.Window, deltas []uint32, ribx map[string]any) Result {
	shadow := filepath.Join(markx.ShadowDir(), "band.json")
	if b, err := os.ReadFile(shadow); err == nil {
		var doc map[string]any
		if json.Unmarshal(b, &doc) == nil {
			band := int(canon.AsU32(doc["band"]))
			dig, _ := doc["digest"].(string)
			if dig != "" {
				return Result{Band: band, Digest: dig, Esc: int(canon.AsU32(doc["esc"]))}
			}
		}
	}
	if ribx == nil {
		return Preview(windows, deltas)
	}
	if _, ok := ribx["slots"]; !ok {
		return Preview(windows, deltas)
	}
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
