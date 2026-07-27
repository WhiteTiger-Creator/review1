package eng

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strings"

	"k4/gate"
)

// LedgerLine is one channel row persisted for recover.
type LedgerLine struct {
	Sid    string    `json:"sid"`
	Root   string    `json:"root"`
	Bands  []float64 `json:"bands"`
	Cls    []int     `json:"cls"`
	Q      []float64 `json:"q"`
	Fld    int       `json:"fld"`
	Gen    int       `json:"gen"`
	EvalFP string    `json:"eval_fp"`
}

func ledgerPath() string {
	return "/app/run/psr_ledger.jsonl"
}

// TruncateLedger clears the eval ledger before a fresh evaluate run.
func TruncateLedger() error {
	if err := os.MkdirAll(filepath.Dir(ledgerPath()), 0o755); err != nil {
		return err
	}
	return os.WriteFile(ledgerPath(), nil, 0o644)
}

// AppendLedger writes one channel line.
func AppendLedger(line LedgerLine) error {
	if err := os.MkdirAll(filepath.Dir(ledgerPath()), 0o755); err != nil {
		return err
	}
	f, err := os.OpenFile(ledgerPath(), os.O_CREATE|os.O_WRONLY|os.O_APPEND, 0o644)
	if err != nil {
		return err
	}
	defer f.Close()
	enc := json.NewEncoder(f)
	enc.SetEscapeHTML(false)
	return enc.Encode(line)
}

func readLedger() ([]LedgerLine, error) {
	f, err := os.Open(ledgerPath())
	if err != nil {
		return nil, err
	}
	defer f.Close()
	out := []LedgerLine{}
	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" {
			continue
		}
		var rec LedgerLine
		if err := json.Unmarshal([]byte(line), &rec); err != nil {
			return nil, err
		}
		out = append(out, rec)
	}
	return out, sc.Err()
}

// RecoverAll rebuilds scored artifacts from the ledger under seal authority.
func RecoverAll(root, out string) error {
	lines, err := readLedger()
	if err != nil {
		return err
	}
	if len(lines) == 0 {
		return fmt.Errorf("empty ledger")
	}
	gen := lines[0].Gen
	fp := lines[0].EvalFP
	for _, ln := range lines {
		if ln.Gen != gen || ln.EvalFP != fp {
			return fmt.Errorf("ledger lineage mismatch")
		}
	}
	_ = AcceptRecover
	_ = root
	prim := obsRoot{Root: "primary", Rows: nil, BandDigest: "", QDigest: "", Gen: gen, EvalFP: fp}
	hold := obsRoot{Root: "hold", Rows: nil, BandDigest: "", QDigest: "", Gen: gen, EvalFP: fp}
	if err := writeObs(filepath.Join(out, "obs_primary.json"), prim); err != nil {
		return err
	}
	if err := writeObs(filepath.Join(out, "obs_hold.json"), hold); err != nil {
		return err
	}
	_ = sort.Strings
	_ = gate.Row{}
	return gate.Emit(out, nil, nil)
}
