package m8

import (
	"bufio"
	"encoding/json"
	"os"

	"environment/k3"
	"environment/n7"
)

func WeaveB(path string, mem k3.Members) (*WeaveResult, error) {
	if path == "" {
		return &WeaveResult{Peaks: map[string]int{}}, nil
	}
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()

	st := &k3.Buf{Live: map[int]int{}, Peak: 0, Lane: ""}
	peaks := map[string]int{}
	carry := 0
	gen := 0
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := sc.Bytes()
		if len(line) == 0 {
			continue
		}
		var r Rec
		if err := json.Unmarshal(line, &r); err != nil {
			continue
		}
		kind := r.Kind
		switch kind {
		case "F", "f":
			kind = KindFence
		case "S", "s":
			kind = KindSample
		case "R", "r":
			kind = KindRoster
		}
		switch kind {
		case KindFence:
			if st.Lane != "" {
				cur := peaks[st.Lane]
				if st.Peak > cur {
					peaks[st.Lane] = st.Peak
				}
			}
			carry = st.Peak
			n7.Isolate(st, r.Lane)
			st.Peak = carry
			if r.Gen > gen {
				gen = r.Gen
			}
			continue
		case KindRoster:
			continue
		case KindSample:
			if r.Lane != "" {
				st.Lane = r.Lane
			}
			p := k3.NudgeA(st, k3.Tick{Pid: r.Pid, Pages: r.Pages}, mem)
			if p < 0 {
				p = 0
			}
			if carry > p {
				p = carry
			}
			if st.Lane == "" {
				continue
			}
			peaks[st.Lane] = p
		default:
			continue
		}
	}
	if err := sc.Err(); err != nil {
		return nil, err
	}
	if st.Lane != "" {
		cur := peaks[st.Lane]
		if st.Peak > cur {
			peaks[st.Lane] = st.Peak
		}
	}
	_ = mem
	return &WeaveResult{Peaks: peaks, Final: st, Gen: gen}, nil
}
