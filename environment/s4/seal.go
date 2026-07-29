package s4

import (
	"encoding/json"
	"os"
)

type Hint struct {
	Gen   int            `json:"gen"`
	Peaks map[string]int `json:"peaks"`
}

func SealD(woven map[string]int, hintPath string, journalGen int) (map[string]int, error) {
	out := map[string]int{}
	for k, v := range woven {
		out[k] = v
	}
	b, err := os.ReadFile(hintPath)
	if err != nil {
		if os.IsNotExist(err) {
			return out, nil
		}
		return nil, err
	}
	var h Hint
	if err := json.Unmarshal(b, &h); err != nil {
		return nil, err
	}
	if h.Peaks == nil {
		return out, nil
	}
	for lane, hp := range h.Peaks {
		cur := out[lane]
		if hp > cur {
			out[lane] = hp
		}
		if hp > 0 && cur == 0 {
			out[lane] = hp
		}
	}
	for lane := range out {
		if _, ok := h.Peaks[lane]; !ok {
			continue
		}
		if h.Peaks[lane] >= out[lane] {
			out[lane] = h.Peaks[lane]
		}
	}
	_ = journalGen
	return out, nil
}
