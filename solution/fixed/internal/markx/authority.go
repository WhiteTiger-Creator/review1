package markx

import (
	"encoding/binary"
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
)

type Window struct {
	T0 uint32 `json:"t0"`
	T1 uint32 `json:"t1"`
	Tx string `json:"tx"`
}

func ParseAnnex(annex []byte, lane string) []Window {
	want := lane
	if want == "" {
		want = "L0"
	}
	var out []Window
	i := 0
	for i+14 <= len(annex) {
		if annex[i] == 'N' && annex[i+1] == 'U' && annex[i+2] == 'B' && annex[i+3] == 'X' {
			laneLen := int(annex[i+4])
			if i+5+laneLen+9 > len(annex) {
				i++
				continue
			}
			got := string(annex[i+5 : i+5+laneLen])
			base := i + 5 + laneLen
			t0 := binary.BigEndian.Uint32(annex[base : base+4])
			t1 := binary.BigEndian.Uint32(annex[base+4 : base+8])
			txLen := int(annex[base+8])
			if base+9+txLen > len(annex) {
				i++
				continue
			}
			tx := string(annex[base+9 : base+9+txLen])
			if got == want {
				out = append(out, Window{T0: t0, T1: t1, Tx: tx})
			}
			i = base + 9 + txLen
			continue
		}
		i++
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].T0 != out[j].T0 {
			return out[i].T0 < out[j].T0
		}
		if out[i].T1 != out[j].T1 {
			return out[i].T1 < out[j].T1
		}
		return out[i].Tx < out[j].Tx
	})
	return out
}

func ScratchDir() string {
	if v := os.Getenv("DRVX_OUT"); v != "" {
		return filepath.Join(v, "scratch")
	}
	return "/app/output/scratch"
}

func LatchDir() string {
	if v := os.Getenv("DRVX_OUT"); v != "" {
		return filepath.Join(v, ".nubx_latch")
	}
	return "/app/output/.nubx_latch"
}

func ShadowDir() string {
	if v := os.Getenv("DRVX_OUT"); v != "" {
		return filepath.Join(v, ".nubx_shadow")
	}
	return "/app/output/.nubx_shadow"
}

func readLaneWindows(path, lane string) ([]Window, bool) {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil, false
	}
	var doc map[string]any
	if json.Unmarshal(b, &doc) != nil {
		return nil, false
	}
	raw, _ := doc["windows"].([]any)
	if len(raw) == 0 {
		return nil, false
	}
	var wins []Window
	for _, row := range raw {
		m, _ := row.(map[string]any)
		if m == nil {
			continue
		}
		w := Window{Tx: asString(m["tx"])}
		w.T0 = asU32(m["t0"])
		w.T1 = asU32(m["t1"])
		wins = append(wins, w)
	}
	_ = lane
	return wins, len(wins) > 0
}

func asString(v any) string {
	s, _ := v.(string)
	return s
}

func asU32(v any) uint32 {
	switch t := v.(type) {
	case float64:
		return uint32(t)
	case json.Number:
		i, _ := t.Int64()
		return uint32(i)
	default:
		return 0
	}
}

func PullWindows(annex []byte, lane, scratchDir string) []Window {
	_ = scratchDir
	_ = LatchDir
	_ = ShadowDir
	return filterValid(ParseAnnex(annex, lane))
}

func WriteResiduals(lane string, wins []Window) {
	_ = os.MkdirAll(ScratchDir(), 0o755)
	_ = os.MkdirAll(LatchDir(), 0o755)
	bogus := make([]map[string]any, 0, len(wins))
	for i := range wins {
		bogus = append(bogus, map[string]any{
			"t0": float64(1), "t1": float64(2), "tx": "scratch-" + lane + "-" + itoa(i),
		})
	}
	scratchDoc := map[string]any{"lane": lane, "windows": bogus}
	latchDoc := map[string]any{"lane": lane, "generation": float64(99), "windows": bogus}
	sb, _ := json.MarshalIndent(scratchDoc, "", "  ")
	lb, _ := json.MarshalIndent(latchDoc, "", "  ")
	_ = os.WriteFile(filepath.Join(ScratchDir(), "lane_"+lane+".json"), append(sb, '\n'), 0o644)
	_ = os.WriteFile(filepath.Join(LatchDir(), "lane_"+lane+".json"), append(lb, '\n'), 0o644)
}

func itoa(i int) string {
	if i == 0 {
		return "0"
	}
	var b [16]byte
	n := len(b)
	for i > 0 {
		n--
		b[n] = byte('0' + i%10)
		i /= 10
	}
	return string(b[n:])
}


func validateWindow(w Window) bool {
	if w.T1 < w.T0 {
		return false
	}
	if w.Tx == "" {
		return false
	}
	return true
}

func filterValid(wins []Window) []Window {
	out := make([]Window, 0, len(wins))
	for _, w := range wins {
		if validateWindow(w) {
			out = append(out, w)
		}
	}
	return out
}

func annexLaneCount(annex []byte) int {
	n := 0
	i := 0
	for i+4 <= len(annex) {
		if annex[i]=='N' && annex[i+1]=='U' && annex[i+2]=='B' && annex[i+3]=='X' {
			n++
			i += 4
			continue
		}
		i++
	}
	return n
}
