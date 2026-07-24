package record

import (
	"archive/zip"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"time"
)

// Manifest is TRACE-12 fixed-order JSON.
type Manifest struct {
	Format                string   `json:"format"`
	NetworkSHA256         string   `json:"network_sha256"`
	RampSHA256            string   `json:"ramp_sha256"`
	Status                string   `json:"status"`
	CriticalLambda        float64  `json:"critical_lambda"`
	PointCount            int      `json:"point_count"`
	EventCount            int      `json:"event_count"`
	LimitingBuses         []string `json:"limiting_buses"`
	VoltageViolationCount int      `json:"voltage_violation_count"`
	MaxPowerMismatch      float64  `json:"max_power_mismatch"`
	MaxArcResidual        float64  `json:"max_arc_residual"`
	TotalActiveLoss       float64  `json:"total_active_loss"`
	TotalReactiveLoss     float64  `json:"total_reactive_loss"`
}

// CurveRow is one curve.csv row.
type CurveRow struct {
	Index               int
	ArcLength           float64
	Lambda              float64
	StepSize            float64
	CorrectorIterations int
	MaxPowerMismatch    float64
	ArcResidual         float64
	MinVoltageBus       string
	MinVoltagePU        float64
	TangentLambda       float64
}

// EventRow is one events.csv row.
type EventRow struct {
	Index     int
	Lambda    float64
	BusID     string
	Kind      string
	QLimit    float64
	VoltagePU float64
}

// BusRow is one critical_bus.csv row.
type BusRow struct {
	BusID        string
	FinalType    string
	VoltagePU    float64
	AngleDeg     float64
	PGen         float64
	QGen         float64
	PLoad        float64
	QLoad        float64
	VoltageState string
}

// BranchRow is one critical_branch.csv row.
type BranchRow struct {
	BranchID string
	Status   string
	From     string
	To       string
	PFrom    float64
	QFrom    float64
	PTo      float64
	QTo      float64
	PLoss    float64
	QLoss    float64
}

var zipEpoch = time.Date(1980, 1, 1, 0, 0, 0, 0, time.UTC)

// WriteMap atomically publishes the voltage-collapse map archive.
func WriteMap(path string, man Manifest, curve []CurveRow, events []EventRow, buses []BusRow, branches []BranchRow) error {
	if path == "" || path[0] != '/' {
		return fmt.Errorf("map path must be absolute")
	}
	if filepath.Ext(path) != ".vcm" {
		return fmt.Errorf("map must use .vcm extension")
	}
	dir := filepath.Dir(path)
	tmp, err := os.OpenFile(filepath.Join(dir, ".vcm-"+filepath.Base(path)+".tmp"), os.O_WRONLY|os.O_CREATE|os.O_EXCL, 0o600)
	if err != nil {
		return err
	}
	tmpName := tmp.Name()
	removeTmp := true
	defer func() {
		if removeTmp {
			_ = os.Remove(tmpName)
		}
	}()

	zw := zip.NewWriter(tmp)
	entries := []struct {
		name string
		body []byte
	}{
		{"manifest.json", MustManifestJSON(man)},
		{"curve.csv", CurveCSV(curve)},
		{"events.csv", EventsCSV(events)},
		{"critical_bus.csv", BusCSV(buses)},
		{"critical_branch.csv", BranchCSV(branches)},
	}
	for _, e := range entries {
		hdr := &zip.FileHeader{
			Name:   e.name,
			Method: zip.Store,
		}
		hdr.SetMode(0o644)
		hdr.Modified = zipEpoch
		w, err := zw.CreateHeader(hdr)
		if err != nil {
			_ = tmp.Close()
			return err
		}
		if _, err := w.Write(e.body); err != nil {
			_ = tmp.Close()
			return err
		}
	}
	if err := zw.Close(); err != nil {
		_ = tmp.Close()
		return err
	}
	if err := tmp.Sync(); err != nil {
		_ = tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	if err := os.Rename(tmpName, path); err != nil {
		return err
	}
	removeTmp = false
	if d, err := os.Open(dir); err == nil {
		_ = d.Sync()
		_ = d.Close()
	}
	return nil
}

// RemovePrivateSibling deletes a leftover private temp if present (best-effort).
func RemovePrivateSibling(path string) {
	_ = os.Remove(filepath.Join(filepath.Dir(path), ".vcm-"+filepath.Base(path)+".tmp"))
}

// MustManifestJSON encodes with two-space indent and stable field order via struct tags.
func MustManifestJSON(man Manifest) []byte {
	if man.LimitingBuses == nil {
		man.LimitingBuses = []string{}
	}
	buf := &bytes.Buffer{}
	enc := json.NewEncoder(buf)
	enc.SetEscapeHTML(false)
	enc.SetIndent("", "  ")
	if err := enc.Encode(man); err != nil {
		panic(err)
	}
	// Encode adds trailing newline already.
	return buf.Bytes()
}

// CopyFile is unused helper retained for protected checks.
func CopyFile(src, dst string) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	out, err := os.OpenFile(dst, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, 0o644)
	if err != nil {
		return err
	}
	defer out.Close()
	_, err = io.Copy(out, in)
	return err
}
