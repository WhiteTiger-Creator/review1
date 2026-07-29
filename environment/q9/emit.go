package q9

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"

	"qdenv/internal"
)

func TickDigest(lines []internal.TickLine) string {
	parts := make([]string, 0, len(lines))
	for _, row := range lines {
		parts = append(parts, strings.Join([]string{
			strconv.Itoa(row.Seq),
			row.Label,
			strconv.Itoa(row.Bearing),
			strconv.Itoa(row.SlotIdx),
			strconv.Itoa(row.SegCRC),
		}, "|"))
	}
	sort.Strings(parts)
	payload := strings.Join(parts, "\n")
	mask64 := uint64(1<<64 - 1)
	var total uint64
	for i, ch := range payload {
		addend := uint64((i+1)*int(ch)) & mask64
		total = (total + addend) & mask64
	}
	return sprintfHex8(uint32(total & 0xffffffff))
}

func sprintfHex8(v uint32) string {
	const hexdigits = "0123456789abcdef"
	out := make([]byte, 8)
	for i := 7; i >= 0; i-- {
		out[i] = hexdigits[v&0xf]
		v >>= 4
	}
	return string(out)
}

// WriteOutputs writes tick_trace.jsonl and lineage_bundle.json under outDir.
func WriteOutputs(lines []internal.TickLine, tbl internal.EntityTbl, laneID, outDir string) error {
	if err := os.MkdirAll(outDir, 0o755); err != nil {
		return err
	}
	tracePath := filepath.Join(outDir, "tick_trace.jsonl")
	f, err := os.Create(tracePath)
	if err != nil {
		return err
	}
	enc := json.NewEncoder(f)
	for _, line := range lines {
		if err := enc.Encode(line); err != nil {
			f.Close()
			return err
		}
	}
	if err := f.Close(); err != nil {
		return err
	}
	bundle := internal.LineageBundle{
		LaneID:     laneID,
		TickDigest: TickDigest(lines),
		EntityRows: tbl.Slots,
		LineCount:  len(lines),
	}
	data, err := json.MarshalIndent(bundle, "", "  ")
	if err != nil {
		return err
	}
	data = append(data, '\n')
	return os.WriteFile(filepath.Join(outDir, "lineage_bundle.json"), data, 0o644)
}
