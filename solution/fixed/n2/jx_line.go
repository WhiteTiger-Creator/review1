package n2

import (
	"bufio"
	"encoding/json"
	"hxenv/lib/core"
	"os"
	"path/filepath"
)

func Path(v string) string { return filepath.Join(v, "ledger.jsonl") }

func Read(v string) ([]core.Journal, error) {
	f, e := os.Open(Path(v))
	if os.IsNotExist(e) {
		return nil, nil
	}
	if e != nil {
		return nil, e
	}
	defer f.Close()
	out := []core.Journal{}
	s := bufio.NewScanner(f)
	for s.Scan() {
		line := bytesTrim(s.Bytes())
		if len(line) == 0 {
			continue
		}
		var j core.Journal
		if e = json.Unmarshal(line, &j); e != nil {
			return out, nil
		}
		out = append(out, j)
	}
	return out, s.Err()
}

func bytesTrim(b []byte) []byte {
	i, j := 0, len(b)
	for i < j && (b[i] == ' ' || b[i] == '\t' || b[i] == '\r') {
		i++
	}
	for j > i && (b[j-1] == ' ' || b[j-1] == '\t' || b[j-1] == '\r') {
		j--
	}
	return b[i:j]
}

func Append(v string, j core.Journal) error {
	if e := os.MkdirAll(v, 0755); e != nil {
		return e
	}
	f, e := os.OpenFile(Path(v), os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644)
	if e != nil {
		return e
	}
	defer f.Close()
	b, _ := json.Marshal(j)
	_, e = f.Write(append(b, '\n'))
	return e
}

func committedPrefix(rows []core.Journal) []core.Journal {
	kept := []core.Journal{}
	parent := ""
	for _, j := range rows {
		if j.ParentSeal != parent || j.PlanDigest != core.DigestPlan(j.Plan) {
			break
		}
		if j.Soft {
			kept = append(kept, j)
			continue
		}
		kept = append(kept, j)
		parent = core.RecordSeal(j)
	}
	return kept
}

func writeCommittedOnly(v string, rows []core.Journal) error {
	f, e := os.Create(Path(v))
	if e != nil {
		return e
	}
	defer f.Close()
	for _, j := range rows {
		if j.Soft {
			continue
		}
		b, _ := json.Marshal(j)
		if _, e = f.Write(append(b, '\n')); e != nil {
			return e
		}
	}
	return nil
}

func RewriteValid(v string) error {
	rows, e := Read(v)
	if e != nil {
		return e
	}
	kept := committedPrefix(rows)
	if e = writeCommittedOnly(v, kept); e != nil {
		return e
	}
	hard := []core.Journal{}
	for _, j := range kept {
		if !j.Soft {
			hard = append(hard, j)
		}
	}
	if len(hard) == 0 {
		_ = os.Remove(filepath.Join(v, "snapshot.json"))
		return ClearShade(v)
	}
	tip := hard[len(hard)-1]
	if e = Save(v, core.Snapshot{Journal: tip, Seal: core.RecordSeal(tip)}); e != nil {
		return e
	}
	return ClearShade(v)
}

func Squash(v string) error {
	rows, e := Read(v)
	if e != nil {
		return e
	}
	kept := []core.Journal{}
	parent := ""
	for _, j := range rows {
		if j.Soft {
			continue
		}
		if j.ParentSeal != parent || j.PlanDigest != core.DigestPlan(j.Plan) {
			break
		}
		kept = append(kept, j)
		parent = core.RecordSeal(j)
	}
	f, e := os.Create(Path(v))
	if e != nil {
		return e
	}
	defer f.Close()
	for _, j := range kept {
		b, _ := json.Marshal(j)
		if _, e = f.Write(append(b, '\n')); e != nil {
			return e
		}
	}
	_ = ClearShade(v)
	if len(kept) == 0 {
		_ = os.Remove(filepath.Join(v, "snapshot.json"))
		return nil
	}
	tip := kept[len(kept)-1]
	return Save(v, core.Snapshot{Journal: tip, Seal: core.RecordSeal(tip)})
}

func StripSoft(v string) error {
	rows, e := Read(v)
	if e != nil {
		return e
	}
	kept := committedPrefix(rows)
	if e = writeCommittedOnly(v, kept); e != nil {
		return e
	}
	return ClearShade(v)
}
