package kilnemit

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"cdnqual/captureload"
	"cdnqual/duplexstitch"
	"cdnqual/l2anvil"
	"cdnqual/qualityemit"
	"cdnqual/tensorloom"
)

type Wire struct {
	Policy      string `json:"policy"`
	CaptureRoot string `json:"capture_root"`
	Labels      string `json:"labels"`
	OutDir      string `json:"out_dir"`
}

type Policy struct {
	Schema              string `json:"schema"`
	RidgeLambda         int    `json:"ridge_lambda"`
	FeatureDim          int    `json:"feature_dim"`
	ScoreThresholdMilli int    `json:"score_threshold_milli"`
}

type FeatureRow struct {
	BoutID string `json:"bout_id"`
	X      []int  `json:"x"`
}

type Weights struct {
	Dim          int      `json:"dim"`
	Lambda       int      `json:"lambda"`
	WMilli       []int    `json:"w_milli"`
	TrainBoutIDs []string `json:"train_bout_ids"`
}

type Prediction struct {
	BoutID     string `json:"bout_id"`
	Y          int    `json:"y"`
	YHat       int    `json:"yhat"`
	ScoreMilli int    `json:"score_milli"`
}

type Ledger struct {
	Schema          string       `json:"schema"`
	BoutCount       int          `json:"bout_count"`
	TrainCount      int          `json:"train_count"`
	AccuracyMilli   int          `json:"accuracy_milli"`
	MeanAbsErrMilli int          `json:"mean_abs_err_milli"`
	PayloadHash     string       `json:"payload_hash"`
	PolicyLambda    int          `json:"policy_lambda"`
	CaptureRoot     string       `json:"capture_root"`
	Predictions     []Prediction `json:"predictions"`
}

type Digest struct {
	Schema          string   `json:"schema"`
	FeaturesSHA256  string   `json:"features_sha256"`
	WeightsSHA256   string   `json:"weights_sha256"`
	LedgerSHA256    string   `json:"ledger_sha256"`
	BoutIDs         []string `json:"bout_ids"`
	FeatureRowCount int      `json:"feature_row_count"`
}

// RunCast executes the kiln pipeline using the linked packages.
func RunCast(wirePath string) error {
	raw, err := os.ReadFile(wirePath)
	if err != nil {
		return err
	}
	var wire Wire
	if err := json.Unmarshal(raw, &wire); err != nil {
		return err
	}
	if v := strings.TrimSpace(os.Getenv("CDNQUAL_CAPTURE_ROOT")); v != "" {
		wire.CaptureRoot = v
	}
	if v := strings.TrimSpace(os.Getenv("CDNQUAL_LABELS")); v != "" {
		wire.Labels = v
	}
	polRaw, err := os.ReadFile(wire.Policy)
	if err != nil {
		return err
	}
	var pol Policy
	if err := json.Unmarshal(polRaw, &pol); err != nil {
		return err
	}
	if pol.Schema != "cdnqual.policy.v1" || pol.FeatureDim != 12 {
		return fmt.Errorf("policy guard failed")
	}
	if pol.ScoreThresholdMilli == 0 {
		pol.ScoreThresholdMilli = 500
	}

	labels, err := loadLabels(wire.Labels)
	if err != nil {
		return err
	}

	pcaps, err := filepath.Glob(filepath.Join(wire.CaptureRoot, "*.pcap"))
	if err != nil {
		return err
	}
	sort.Strings(pcaps)
	if len(pcaps) == 0 {
		return fmt.Errorf("no pcaps under %s", wire.CaptureRoot)
	}

	type boutPack struct {
		bout duplexstitch.Bout
		x    []int
		y    int
		hasY bool
	}
	packs := make([]boutPack, 0, len(pcaps))
	var payloadBlob []byte
	boutIDs := make([]string, 0, len(pcaps))

	for _, p := range pcaps {
		base := strings.TrimSuffix(filepath.Base(p), ".pcap")
		pkts, err := captureload.LoadCapture(p)
		if err != nil {
			return err
		}
		b := duplexstitch.ReassembleBout(base, pkts)
		x := tensorloom.Knit(b)
		y, ok := labels[base]
		packs = append(packs, boutPack{bout: b, x: x, y: y, hasY: ok})
		boutIDs = append(boutIDs, base)
		payloadBlob = append(payloadBlob, b.ClientPayload...)
		payloadBlob = append(payloadBlob, b.ServerPayload...)
	}

	var samples []l2anvil.Sample
	for _, p := range packs {
		if p.hasY {
			samples = append(samples, l2anvil.Sample{BoutID: p.bout.ID, X: p.x, Y: p.y})
		}
	}
	wMilli, trainIDs, err := l2anvil.Fit(samples, pol.RidgeLambda)
	if err != nil {
		return err
	}

	if err := os.MkdirAll(wire.OutDir, 0o755); err != nil {
		return err
	}

	var featBuf strings.Builder
	for _, p := range packs {
		row := FeatureRow{BoutID: p.bout.ID, X: p.x}
		b, _ := json.Marshal(row)
		featBuf.Write(b)
		featBuf.WriteByte('\n')
	}
	featPath := filepath.Join(wire.OutDir, "session_features.jsonl")
	if err := qualityemit.WriteArtifact(wire.OutDir, "session_features.jsonl", []byte(featBuf.String())); err != nil {
		return err
	}

	weights := Weights{Dim: 13, Lambda: pol.RidgeLambda, WMilli: wMilli, TrainBoutIDs: trainIDs}
	wBytes, err := json.Marshal(weights)
	if err != nil {
		return err
	}
	wBytes = append(wBytes, '\n')
	wPath := filepath.Join(wire.OutDir, "ridge_weights.json")
	if err := qualityemit.WriteArtifact(wire.OutDir, "ridge_weights.json", wBytes); err != nil {
		return err
	}

	var preds []Prediction
	correct := 0
	var absErrSum float64
	evalN := 0
	for _, p := range packs {
		if !p.hasY {
			continue
		}
		yhat, scoreMilli := l2anvil.Predict(wMilli, p.x, pol.ScoreThresholdMilli)
		preds = append(preds, Prediction{BoutID: p.bout.ID, Y: p.y, YHat: yhat, ScoreMilli: scoreMilli})
		if yhat == p.y {
			correct++
		}
		s := float64(l2anvil.ScoreMilli(wMilli, p.x)) / 1_000_000.0
		absErrSum += abs(float64(p.y) - s)
		evalN++
	}
	sort.Slice(preds, func(i, j int) bool { return preds[i].BoutID < preds[j].BoutID })
	acc := 0
	mae := 0
	if evalN > 0 {
		acc = 1000 * correct / evalN
		mae = int(absErrSum * 1000 / float64(evalN))
	}
	sum := sha256.Sum256(payloadBlob)
	ledger := Ledger{
		Schema:          "cdnqual.ledger.v1",
		BoutCount:       len(packs),
		TrainCount:      len(trainIDs),
		AccuracyMilli:   acc,
		MeanAbsErrMilli: mae,
		PayloadHash:     hex.EncodeToString(sum[:]),
		PolicyLambda:    pol.RidgeLambda,
		CaptureRoot:     wire.CaptureRoot,
		Predictions:     preds,
	}
	lBytes, err := json.Marshal(ledger)
	if err != nil {
		return err
	}
	lBytes = append(lBytes, '\n')
	lPath := filepath.Join(wire.OutDir, "eval_ledger.json")
	if err := qualityemit.WriteArtifact(wire.OutDir, "eval_ledger.json", lBytes); err != nil {
		return err
	}
	// Checkpoint mirror of the ledger for rerun/idempotency checks.
	snapDir := filepath.Join(wire.OutDir, "checkpoint")
	if err := qualityemit.WriteArtifact(snapDir, "eval_ledger.snap.json", lBytes); err != nil {
		return err
	}

	featBytes, _ := os.ReadFile(featPath)
	wDisk, _ := os.ReadFile(wPath)
	lDisk, _ := os.ReadFile(lPath)
	digest := Digest{
		Schema:          "cdnqual.digest.v1",
		FeaturesSHA256:  shaHex(featBytes),
		WeightsSHA256:   shaHex(wDisk),
		LedgerSHA256:    shaHex(lDisk),
		BoutIDs:         boutIDs,
		FeatureRowCount: len(packs),
	}
	dBytes, err := json.Marshal(digest)
	if err != nil {
		return err
	}
	dBytes = append(dBytes, '\n')
	return qualityemit.WriteArtifact(wire.OutDir, "feature_digest.json", dBytes)
}

func loadLabels(path string) (map[string]int, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	out := map[string]int{}
	for _, line := range strings.Split(string(raw), "\n") {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		var row struct {
			BoutID string `json:"bout_id"`
			Y      int    `json:"y"`
		}
		if err := json.Unmarshal([]byte(line), &row); err != nil {
			return nil, err
		}
		out[row.BoutID] = row.Y
	}
	return out, nil
}

func shaHex(b []byte) string {
	sum := sha256.Sum256(b)
	return hex.EncodeToString(sum[:])
}

func abs(v float64) float64 {
	if v < 0 {
		return -v
	}
	return v
}
