#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
patch -d /app -p0 < fold_build.patch
patch -d /app -p0 < budget_build.patch
patch -d /app -p0 < emit_build.patch

python3 - <<'PY'
from pathlib import Path

Path("/app/environment/eng/seal.go").write_text(r'''package eng

import (
	"encoding/binary"
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
)

// Seal is the durable evaluation lineage record under /app/var/psr.
type Seal struct {
	Stage   string `json:"stage"`
	Gen     int    `json:"gen"`
	EvalFP  string `json:"eval_fp"`
	BindHex string `json:"bind_hex"`
}

func sealPath() string {
	return "/app/var/psr/eval_seal.json"
}

func fnvMix(h uint32, b byte) uint32 {
	h ^= uint32(b)
	return h * 16777619
}

func emit8(h uint32) string {
	const hexdigits = "0123456789abcdef"
	out := make([]byte, 8)
	for i := 7; i >= 0; i-- {
		out[i] = hexdigits[h&0xf]
		h >>= 4
	}
	return string(out)
}

func walkCorp(root string) ([]string, error) {
	dir := filepath.Join(root, "fixtures")
	out := []string{}
	err := filepath.Walk(dir, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		if info.IsDir() {
			return nil
		}
		if filepath.Ext(path) == ".json" {
			out = append(out, path)
		}
		return nil
	})
	if err != nil {
		return nil, err
	}
	sort.Strings(out)
	return out, nil
}

// EvalFP fingerprints every JSON pack under root/fixtures.
func EvalFP(root string) (string, error) {
	files, err := walkCorp(root)
	if err != nil {
		return "", err
	}
	h := uint32(2166136261)
	for _, path := range files {
		b, err := os.ReadFile(path)
		if err != nil {
			return "", err
		}
		for _, c := range b {
			h = fnvMix(h, c)
		}
	}
	return emit8(h), nil
}

// BindHex binds observation digests to lineage.
func BindHex(primBand, holdBand, primQ, holdQ, fp string, gen int) string {
	h := uint32(2166136261)
	for _, s := range []string{primBand, holdBand, primQ, holdQ, fp} {
		for i := 0; i < len(s); i++ {
			h = fnvMix(h, s[i])
		}
	}
	var buf [8]byte
	binary.LittleEndian.PutUint64(buf[:], uint64(gen))
	for _, c := range buf {
		h = fnvMix(h, c)
	}
	return emit8(h)
}

// LoadSeal reads the durable seal when present.
func LoadSeal() (Seal, bool) {
	b, err := os.ReadFile(sealPath())
	if err != nil {
		return Seal{}, false
	}
	var s Seal
	if err := json.Unmarshal(b, &s); err != nil {
		return Seal{}, false
	}
	return s, true
}

func writeSeal(s Seal) error {
	if err := os.MkdirAll(filepath.Dir(sealPath()), 0o755); err != nil {
		return err
	}
	f, err := os.Create(sealPath())
	if err != nil {
		return err
	}
	defer f.Close()
	enc := json.NewEncoder(f)
	enc.SetEscapeHTML(false)
	return enc.Encode(s)
}

// OpenSeal stages OPEN and selects the lineage generation.
func OpenSeal(root string) (Seal, error) {
	fp, err := EvalFP(root)
	if err != nil {
		return Seal{}, err
	}
	gen := 1
	if prev, ok := LoadSeal(); ok && prev.Stage == "COMMIT" && prev.EvalFP == fp && prev.Gen > 0 {
		gen = prev.Gen
	} else if prev, ok := LoadSeal(); ok && prev.Gen > 0 {
		gen = prev.Gen + 1
	}
	s := Seal{Stage: "OPEN", Gen: gen, EvalFP: fp, BindHex: ""}
	if err := writeSeal(s); err != nil {
		return Seal{}, err
	}
	return s, nil
}

// CommitSeal promotes the seal after digests are known.
func CommitSeal(s Seal, primBand, holdBand, primQ, holdQ string) error {
	s.Stage = "COMMIT"
	s.BindHex = BindHex(primBand, holdBand, primQ, holdQ, s.EvalFP, s.Gen)
	return writeSeal(s)
}

// AcceptRecover reports whether recover may rebuild from the ledger.
func AcceptRecover(root string, ledgerGen int, ledgerFP string) bool {
	s, ok := LoadSeal()
	if !ok {
		return false
	}
	if s.Stage != "COMMIT" {
		return false
	}
	live, err := EvalFP(root)
	if err != nil {
		return false
	}
	if s.EvalFP != live || s.EvalFP != ledgerFP {
		return false
	}
	if s.Gen != ledgerGen || s.Gen < 1 {
		return false
	}
	return true
}
''')

Path("/app/environment/eng/recover.go").write_text(r'''package eng

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
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
	if !AcceptRecover(root, gen, fp) {
		return fmt.Errorf("eval seal rejects recover")
	}
	byRoot := map[string][]LedgerLine{}
	for _, ln := range lines {
		byRoot[ln.Root] = append(byRoot[ln.Root], ln)
	}
	prim, err := rootFromLedger("primary", byRoot["primary"], gen, fp)
	if err != nil {
		return err
	}
	hold, err := rootFromLedger("hold", byRoot["hold"], gen, fp)
	if err != nil {
		return err
	}
	if err := writeObs(filepath.Join(out, "obs_primary.json"), prim); err != nil {
		return err
	}
	if err := writeObs(filepath.Join(out, "obs_hold.json"), hold); err != nil {
		return err
	}
	allRows := append([]gate.Row{}, prim.Rows...)
	allRows = append(allRows, hold.Rows...)
	neg := gate.NegOf(allRows)
	if err := gate.Emit(out, allRows, neg); err != nil {
		return err
	}
	seal := Seal{Stage: "COMMIT", Gen: gen, EvalFP: fp}
	return patchSheet(out, prim, hold, neg, seal)
}

func rootFromLedger(name string, lines []LedgerLine, gen int, fp string) (obsRoot, error) {
	rows := make([]gate.Row, 0, len(lines))
	bandMap := map[string][]float64{}
	qMap := map[string][]float64{}
	sids := []string{}
	for _, ln := range lines {
		row := gate.Row{Sid: ln.Sid, Bands: ln.Bands, Cls: ln.Cls, Q: ln.Q, Fld: ln.Fld}
		rows = append(rows, row)
		bandMap[ln.Sid] = ln.Bands
		qMap[ln.Sid] = ln.Q
		sids = append(sids, ln.Sid)
	}
	return obsRoot{
		Root:       name,
		Rows:       rows,
		BandDigest: HexDigest(JoinBands(sids, bandMap)),
		QDigest:    HexDigest(JoinBands(sids, qMap)),
		Gen:        gen,
		EvalFP:     fp,
	}, nil
}
''')
print("seal+recover written")
PY

exec bash /app/environment/drive_k4.sh
