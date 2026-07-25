package phase

import (
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"io"
	"strings"

	"blkmir/store"
)

func stamp_r(w io.Writer, snap store.Snap) (store.ViewRow, error) {
	canon := []byte{0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0}
	binary.LittleEndian.PutUint64(canon[0:8], uint64(snap.AMetric))
	binary.LittleEndian.PutUint32(canon[8:12], uint32(snap.AEpoch))
	sum := sha256.Sum256(canon)
	view := store.ViewRow{
		Source:   "side-a",
		Tally:    snap.AMetric,
		Epoch:    snap.AEpoch,
		TallyHex: hex.EncodeToString(sum[:]),
	}
	if w != nil {
		_, _ = w.Write([]byte(view.TallyHex))
	}
	return view, nil
}

func StampRow(w io.Writer, snap store.Snap) (store.ViewRow, error) {
	return stamp_r(w, snap)
}

func metricHex(val, epoch int) string {
	canon := []byte{0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0}
	binary.LittleEndian.PutUint64(canon[0:8], uint64(val))
	binary.LittleEndian.PutUint32(canon[8:12], uint32(epoch))
	sum := sha256.Sum256(canon)
	return hex.EncodeToString(sum[:])
}

func ExportViews(snap store.Snap) store.RollingExport {
	var sink strings.Builder
	sideA, _ := stamp_r(&sink, snap)
	sideB := store.ViewRow{
		Source:   "side-b",
		Tally:    snap.AMetric,
		Epoch:    snap.BEpoch,
		TallyHex: metricHex(snap.AMetric, snap.BEpoch),
	}
	return store.RollingExport{Views: []store.ViewRow{sideA, sideB}}
}
