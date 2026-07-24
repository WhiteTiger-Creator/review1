package cx

import (
	"encoding/json"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// Row is one emitted observation channel.
type Row struct {
	Sid   string    `json:"sid"`
	Bands []float64 `json:"bands"`
	Cls   []int     `json:"cls"`
	Q     []float64 `json:"q"`
	Fld   int       `json:"fld"`
}

func accOf(cls []int) string {
	if len(cls) == 0 {
		return "full"
	}
	for _, c := range cls {
		if c < 2 {
			return "full"
		}
	}
	return "limited"
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	neg := false
	if n < 0 {
		neg = true
		n = -n
	}
	var b [16]byte
	i := len(b)
	for n > 0 {
		i--
		b[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		b[i] = '-'
	}
	return string(b[i:])
}

func negSet(rows []Row) []string {
	seen := map[int]struct{}{}
	for _, r := range rows {
		prev := -1
		for _, c := range r.Cls {
			if prev >= 0 && c != prev {
				break
			}
			if c >= 2 {
				seen[c] = struct{}{}
			}
			prev = c
		}
	}
	keys := make([]int, 0, len(seen))
	for k := range seen {
		keys = append(keys, k)
	}
	sort.Ints(keys)
	out := make([]string, 0, len(keys))
	for _, k := range keys {
		out = append(out, "ng:"+itoa(k))
	}
	return out
}

func writeJSON(path string, v any) error {
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		return err
	}
	f, err := os.Create(path)
	if err != nil {
		return err
	}
	defer f.Close()
	enc := json.NewEncoder(f)
	enc.SetEscapeHTML(false)
	return enc.Encode(v)
}

// Emit is the package entry used by eng for rights sheet and transparency output.
func Emit(out string, rows []Row, neg []string) error {
	return mix_c(out, rows, neg)
}

// NegOf derives non-goal tokens for eng assembly.
func NegOf(rows []Row) []string {
	return negSet(rows)
}

// AccOf maps a ladder vector to an access grant string for eng assembly.
func AccOf(cls []int) string {
	return accOf(cls)
}

// mix_c materializes the rights artifact and transparency file under out.
func mix_c(out string, rows []Row, neg []string) error {
	keys := negSet(rows)
	if len(neg) > 0 {
		keys = neg
	}
	grants := make([]map[string]string, 0, len(rows))
	seenSid := map[string]struct{}{}
	fldAny := 0
	for _, r := range rows {
		if _, ok := seenSid[r.Sid]; ok {
			continue
		}
		seenSid[r.Sid] = struct{}{}
		grants = append(grants, map[string]string{"sid": r.Sid, "acc": accOf(r.Cls)})
		if r.Fld == 1 {
			fldAny = 1
		}
	}
	sort.Slice(grants, func(i, j int) bool { return grants[i]["sid"] < grants[j]["sid"] })
	doc := map[string]any{
		"version": "k4-1",
		"grants":  grants,
		"digests": map[string]string{"primary": "", "hold": ""},
		"qdig":    map[string]string{"primary": "", "hold": ""},
		"neg":     keys,
		"fld_any": fldAny,
	}
	if err := writeJSON(filepath.Join(out, "rights_map.json"), doc); err != nil {
		return err
	}
	body := ""
	if len(keys) > 0 {
		body = strings.Join(keys, "\n") + "\n"
	}
	return os.WriteFile(filepath.Join(out, "transparency.txt"), []byte(body), 0o644)
}
