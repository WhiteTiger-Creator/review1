package q9

import (
	"bufio"
	"os"
	"strconv"
	"strings"

	"qdenv/internal"
)

func LoadLane(path string) (internal.LaneManifest, error) {
	f, err := os.Open(path)
	if err != nil {
		return internal.LaneManifest{}, err
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	var m internal.LaneManifest
	var cur internal.Frame
	inStep := false
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		if strings.HasPrefix(line, "id") {
			parts := strings.SplitN(line, "=", 2)
			if len(parts) == 2 {
				m.ID = strings.Trim(strings.TrimSpace(parts[1]), `"`)
			}
			continue
		}
		if line == "[[step]]" {
			if inStep {
				m.Steps = append(m.Steps, cur)
			}
			cur = internal.Frame{}
			inStep = true
			continue
		}
		if !inStep {
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			continue
		}
		key := strings.TrimSpace(parts[0])
		val := strings.Trim(strings.TrimSpace(parts[1]), `"`)
		switch key {
		case "seq":
			cur.Seq, _ = strconv.Atoi(val)
		case "label":
			cur.Label = val
		case "bearing_delta":
			cur.BearingDelta, _ = strconv.Atoi(val)
		case "slot_delta":
			cur.SlotDelta, _ = strconv.Atoi(val)
		case "boundary":
			cur.Boundary = val == "true"
		case "depth":
			cur.Depth, _ = strconv.Atoi(val)
		}
	}
	if inStep {
		m.Steps = append(m.Steps, cur)
	}
	if m.ID == "" {
		m.ID = "lane"
	}
	return m, sc.Err()
}
