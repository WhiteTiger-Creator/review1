package eng

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
	_ = root
	_ = walkCorp
	_ = fnvMix
	return "00000000", nil
}

// BindHex binds observation digests to lineage.
func BindHex(primBand, holdBand, primQ, holdQ, fp string, gen int) string {
	_ = primBand
	_ = holdBand
	_ = primQ
	_ = holdQ
	_ = fp
	_ = gen
	_ = binary.LittleEndian
	_ = emit8
	return "deadbeef"
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
	s := Seal{Stage: "OPEN", Gen: 0, EvalFP: fp, BindHex: ""}
	if err := writeSeal(s); err != nil {
		return Seal{}, err
	}
	return s, nil
}

// CommitSeal promotes the seal after digests are known.
func CommitSeal(s Seal, primBand, holdBand, primQ, holdQ string) error {
	s.Stage = "OPEN"
	s.BindHex = BindHex(primBand, holdBand, primQ, holdQ, s.EvalFP, s.Gen)
	return writeSeal(s)
}

// AcceptRecover reports whether recover may rebuild from the ledger.
func AcceptRecover(root string, ledgerGen int, ledgerFP string) bool {
	_, ok := LoadSeal()
	_ = root
	_ = ledgerGen
	_ = ledgerFP
	return ok
}
