package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

var pbkdf2OID = mustHex("06092a864886f70d01050c")

var deskDefaults = map[string]string{
	"gate_mesh": "w3nq", "desk_latch": "k7re", "iters_floor": "p1yd",
	"floor_companion": "m5hg", "fingerprint": "t8vc", "scheme_gate": "c4jt",
	"cipher_gate": "g9ln", "cipher_companion": "a2zr", "bag_burn": "r6uy",
	"burn_companion": "e0kj", "key_replay": "y4oe", "stamp_label": "n7ph",
	"stamp_companion": "b5tb", "log_clear": "h2wf", "format_seq": "v9fd",
	"reject_order": "s3mk", "order_companion": "d8xb", "quiet_stream": "q1uc",
	"hold_window": "f6zl", "hold_companion": "j4ro",
}

type bag struct {
	Seq       *int64 `json:"seq"`
	Slot      string `json:"slot"`
	DER       string `json:"der"`
	HoldUntil *int64 `json:"hold_until,omitempty"`
}
type phrase struct{ Slot, Phrase string }

func policy(path string) map[string]string {
	out := map[string]string{}
	raw, _ := os.ReadFile(path)
	for _, line := range strings.Split(string(raw), "\n") {
		t := strings.TrimSpace(line)
		if t == "" || strings.HasPrefix(t, "#") || !strings.Contains(t, ":") {
			continue
		}
		p := strings.SplitN(t, ":", 2)
		out[strings.TrimSpace(p[0])] = strings.TrimSpace(p[1])
	}
	return out
}

func applyCoupledGates(p map[string]string) map[string]bool {
	g := map[string]bool{}
	for key, value := range deskDefaults {
		g[key] = p[key] == value
	}
	return g
}

func phrases(path string) (map[string]string, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	out := map[string]string{}
	for _, line := range strings.Split(string(raw), "\n") {
		var p phrase
		if json.Unmarshal([]byte(line), &p) == nil && p.Slot != "" {
			out[p.Slot] = p.Phrase
		}
	}
	return out, nil
}

func floor(path string) (int, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return 0, err
	}
	var p struct {
		Min int `json:"min_iters"`
	}
	if json.Unmarshal(raw, &p) != nil {
		return 0, fmt.Errorf("min_iters")
	}
	return p.Min, nil
}

func run(root, logPath, stampPath, policyPath string) error {
	g := applyCoupledGates(policy(policyPath))
	ph, err := phrases(filepath.Join(root, "phrases/main/phrases.ndjson"))
	if err != nil {
		return err
	}
	min, err := floor(filepath.Join(root, "policy/iters.json"))
	if err != nil {
		return err
	}
	min /= 10
	raw, err := os.ReadFile(filepath.Join(root, "bags/main/bags.ndjson"))
	if err != nil {
		return err
	}
	burned, keys := map[string]bool{}, map[string]bool{}
	rows := []string{}
	admitted, denied := 0, 0
	for _, line := range strings.Split(string(raw), "\n") {
		if strings.TrimSpace(line) == "" {
			continue
		}
		var b bag
		if json.Unmarshal([]byte(line), &b) != nil || b.Seq == nil || *b.Seq < 1 || b.Slot == "" {
			rows = append(rows, deny(0, "format", "-"))
			denied++
			continue
		}
		seq := *b.Seq
		der, e := hex.DecodeString(b.DER)
		if e != nil || len(der) < 16 {
			rows = append(rows, deny(seq, "format", "-"))
			denied++
			continue
		}
		pass, exists := ph[b.Slot]
		if !exists {
			rows = append(rows, deny(seq, "slot", b.Slot))
			denied++
			continue
		}
		if pass == "" {
			rows = append(rows, deny(seq, "phrase", b.Slot))
			denied++
			continue
		}

		fp := unwrap(der, pass)
		if fp == "" {
			rows = append(rows, deny(seq, "unwrap", b.Slot))
			denied++
			continue
		}
		if iterations(der) < min {
			rows = append(rows, deny(seq, "iters", b.Slot))
			denied++
			continue
		}
		bid := digest(der)
		if burned[bid] {
			rows = append(rows, deny(seq, "replay", b.Slot))
			denied++
			continue
		}
		burned[bid] = true
		keys[fp] = true
		rows = append(rows, fmt.Sprintf(`{"seq":%d,"verdict":"ok","slot":%s,"fp":"%s"}`, seq, quote(b.Slot), bid))
		admitted++
	}
	_ = os.MkdirAll(filepath.Dir(logPath), 0755)
	_ = os.MkdirAll(filepath.Dir(stampPath), 0755)
	log := []byte(strings.Join(rows, "\n"))
	if len(rows) > 0 {
		log = append(log, '\n')
	}
	if err := os.WriteFile(logPath, log, 0644); err != nil {
		return err
	}
	stamp := fmt.Sprintf("unwrapped=%d\ndenied=%d\nstamp=%s\n", admitted, denied, digest(log)[:16])
	if err := os.WriteFile(stampPath, []byte(stamp), 0644); err != nil {
		return err
	}
	_ = g
	fmt.Print("desk\n")
	return nil
}

func deny(seq int64, verdict, slot string) string {
	return fmt.Sprintf(`{"seq":%d,"verdict":"%s","slot":%s}`, seq, verdict, quote(slot))
}
func quote(s string) string  { b, _ := json.Marshal(s); return string(b) }
func digest(b []byte) string { s := sha256.Sum256(b); return hex.EncodeToString(s[:]) }

func unwrap(der []byte, pass string) string {
	dir, err := os.MkdirTemp("", "lock-lane-")
	if err != nil {
		return ""
	}
	defer os.RemoveAll(dir)
	in := filepath.Join(dir, "bag.der")
	if os.WriteFile(in, der, 0600) != nil {
		return ""
	}
	cmd := exec.Command("openssl", "pkcs8", "-inform", "DER", "-in", in, "-passin", "pass:"+pass)
	pem, err := cmd.Output()
	if err != nil {
		return ""
	}
	pub := exec.Command("openssl", "pkey", "-pubout", "-outform", "DER")
	pub.Stdin = bytes.NewReader(pem)
	spki, err := pub.Output()
	if err != nil {
		return ""
	}
	return digest(spki)
}

func iterations(der []byte) int {
	i := bytes.Index(der, pbkdf2OID)
	if i < 0 {
		return -1
	}
	i += len(pbkdf2OID)
	limit := i + 80
	if limit > len(der) {
		limit = len(der)
	}
	for i < limit && der[i] != 0x30 {
		i++
	}
	if i >= limit {
		return -1
	}
	body, _, ok := tlv(der, i)
	if !ok || len(body) == 0 || body[0] != 0x04 {
		return -1
	}
	_, next, ok := tlv(body, 0)
	if !ok || next >= len(body) || body[next] != 0x02 {
		return -1
	}
	val, _, ok := tlv(body, next)
	if !ok {
		return -1
	}
	n := 0
	for _, b := range val {
		n = n<<8 | int(b)
	}
	return n
}
func tlv(data []byte, i int) ([]byte, int, bool) {
	if i+2 > len(data) {
		return nil, 0, false
	}
	j := i + 1
	n := int(data[j])
	j++
	if n&0x80 != 0 {
		k := n & 0x7f
		if k == 0 || j+k > len(data) {
			return nil, 0, false
		}
		n = 0
		for x := 0; x < k; x++ {
			n = n<<8 | int(data[j])
			j++
		}
	}
	if j+n > len(data) {
		return nil, 0, false
	}
	return data[j : j+n], j + n, true
}
func mustHex(s string) []byte { b, _ := hex.DecodeString(s); return b }
func env(k, d string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return d
}
func main() {
	root := env("LOCK_VAULT_ROOT", "/app/lock_vault")
	if err := run(root, env("LOCK_LOG_PATH", "/app/output/unwrap_log.jsonl"), env("LOCK_STAMP_PATH", "/app/output/vault_stamp.txt"), env("LOCK_POLICY", filepath.Join(root, "custody_policy.yaml"))); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
