package state

import (
	"encoding/json"
	"os"
	"path/filepath"
)

type Tokens struct {
	Pos string `json:"pos"`
	Neg string `json:"neg"`
}

type Pack struct {
	PackID    string   `json:"pack_id"`
	Scenarios []string `json:"scenarios"`
	Tokens    Tokens   `json:"tokens"`
}

type Row struct {
	ID   string `json:"id"`
	Seq  int    `json:"seq"`
	Mark bool   `json:"mark"`
}

type Peer struct {
	ID  string `json:"id"`
	Key string `json:"key"`
}

type CorpusEntry struct {
	ScenarioID string `json:"scenario_id"`
	Rows       []Row  `json:"rows"`
	Peers      []Peer `json:"peers"`
	Gen        int    `json:"gen"`
	Stamp      int64  `json:"stamp"`
	Epoch      int    `json:"epoch"`
	ProbeOK    bool   `json:"probe_ok"`
}

type PairIndex struct {
	Pairs map[string]string `json:"pairs"`
}

type SlotWin struct {
	Legacy int  `json:"legacy"`
	Tip    int  `json:"tip"`
	Dual   bool `json:"dual"`
	A      int  `json:"a"`
	B      int  `json:"b"`
}

type WindowTable struct {
	Slots map[string]SlotWin `json:"slots"`
}

type RevokeLedger struct {
	Gone map[string]map[string]bool `json:"gone"`
}

type EpochTable struct {
	Rows map[string]int `json:"rows"`
}

type GraceRow struct {
	Deadline int64  `json:"deadline"`
	Skew     int    `json:"skew"`
	Held     string `json:"held"`
	Next     string `json:"next"`
}

type GraceTable struct {
	Rows map[string]GraceRow `json:"rows"`
}

type Bundle struct {
	Root       string
	Pack       Pack
	Pairs      map[string]string
	Gone       map[string]map[string]bool
	Windows    map[string]SlotWin
	Epochs     map[string]int
	Graces     map[string]GraceRow
	Corpus     map[string]CorpusEntry
	ScenarioID string
	Tokens     Tokens
}

func LoadRoot(root string) (*Bundle, error) {
	packPath := filepath.Join(root, "data", "scenario_pack.json")
	raw, err := os.ReadFile(packPath)
	if err != nil {
		return nil, err
	}
	var pack Pack
	if err := json.Unmarshal(raw, &pack); err != nil {
		return nil, err
	}
	pairs, err := readJSON[PairIndex](filepath.Join(root, "data", "corpus", "pair_index.json"))
	if err != nil {
		return nil, err
	}
	ledger, err := readJSON[RevokeLedger](filepath.Join(root, "data", "anchors", "revoke_ledger.json"))
	if err != nil {
		return nil, err
	}
	wins, err := readJSON[WindowTable](filepath.Join(root, "data", "anchors", "window_table.json"))
	if err != nil {
		return nil, err
	}
	epochs, err := readJSON[EpochTable](filepath.Join(root, "data", "cache", "epoch_table.json"))
	if err != nil {
		return nil, err
	}
	graces, err := readJSON[GraceTable](filepath.Join(root, "data", "cache", "grace_table.json"))
	if err != nil {
		return nil, err
	}
	corpus := map[string]CorpusEntry{}
	for _, id := range pack.Scenarios {
		ce, err := readJSON[CorpusEntry](filepath.Join(root, "data", "corpus", id+".json"))
		if err != nil {
			return nil, err
		}
		corpus[id] = ce
	}
	return &Bundle{
		Root:    root,
		Pack:    pack,
		Pairs:   pairs.Pairs,
		Gone:    ledger.Gone,
		Windows: wins.Slots,
		Epochs:  epochs.Rows,
		Graces:  graces.Rows,
		Corpus:  corpus,
		Tokens:  pack.Tokens,
	}, nil
}

func readJSON[T any](path string) (T, error) {
	var out T
	raw, err := os.ReadFile(path)
	if err != nil {
		return out, err
	}
	err = json.Unmarshal(raw, &out)
	return out, err
}

func (s *Bundle) RowsFor(id string) []Row {
	return s.Corpus[id].Rows
}

func (s *Bundle) PeersFor(id string) []Peer {
	return s.Corpus[id].Peers
}

func (s *Bundle) GenFor(id string) int {
	return s.Corpus[id].Gen
}

func (s *Bundle) StampFor(id string) int64 {
	return s.Corpus[id].Stamp
}

func (s *Bundle) EpochFor(id string) int {
	if v, ok := s.Epochs[id]; ok {
		return v
	}
	return s.Corpus[id].Epoch
}

func (s *Bundle) GraceFor(id string) GraceRow {
	return s.Graces[id]
}

func (s *Bundle) WinFor(slot string) (SlotWin, bool) {
	w, ok := s.Windows[slot]
	return w, ok
}

func (s *Bundle) IsGone(slot string, gen int) bool {
	m, ok := s.Gone[slot]
	if !ok {
		return false
	}
	key := itoa(gen)
	return m[key]
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	var buf [16]byte
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		buf[i] = '-'
	}
	return string(buf[i:])
}
