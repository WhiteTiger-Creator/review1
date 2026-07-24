#!/usr/bin/env bash
set -euo pipefail

export PATH=/usr/local/go/bin:/go/bin:$PATH
export GOPROXY=off GOSUMDB=off GOTOOLCHAIN=local
export GOCACHE=/opt/go-cache

cd /app

rm -f kernel/kernel_loader/loader.go
rm -f kernel/kernel_verdict/verdict.go
rm -f kernel/kernel_main/main.go

cat > kernel/kernel_loader/loader.go <<'GO_EOF'
package loader

type Sentinel struct{}
GO_EOF

cat > kernel/kernel_verdict/verdict.go <<'GO_EOF'
package verdict

type Sentinel struct{}
GO_EOF

cat > kernel/kernel_main/main.go <<'GO_EOF'
package main

import (
	"bufio"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"
)

type Row struct {
	Feed         string
	TripID       string
	RouteID      string
	StartDate    string
	ReceivedTS   string
	IngestTS     string
	Schedule     string
	BadSeq       bool
	HasSkipped   bool
	BadTimestamp bool
	Stale        bool
	Quarantine   bool
}

type Decision struct {
	Feed       string `json:"feed"`
	TripID     string `json:"trip_id"`
	RouteID    string `json:"route_id"`
	ReceivedTS string `json:"received_ts"`
	Verdict    string `json:"verdict"`
	Ordinal    int    `json:"ordinal"`
}

type Seal struct {
	Feed       string
	TripID     string
	ReceivedTS string
	SealHex    string
}

const sentinelMaxTS = "9999-12-31T23:59:59Z"

var allVerdicts = []string{
	"ADMITTED_SCHEDULED", "ADMITTED_ADDED", "ADMITTED_NO_DATA", "ADMITTED_UNSCHEDULED",
	"CANCELED_TRIP", "SKIPPED_STOP",
	"DEDUP_DUPLICATE", "CAP_EXCEEDED", "CASCADE_SUPPRESSED",
	"SEQUENCE_REJECTED", "PIN_RESCUED", "TIMESTAMP_REJECTED",
	"ROUTE_UNKNOWN", "STALE_INGEST",
}

var (
	tsGrammar             *regexp.Regexp
	pinSecret             string
	staleThresholdSeconds int = 21600
	activeSeals           []Seal
	knownRoutes           = map[string]bool{}
	criticalRoutes        = map[string]bool{}
	standardCap           = 3
	criticalCap           = 2
	windowStart           string
	windowEnd             string
	feedByExt             = map[string]string{}
	allRoutes             []string
)

type rawRec struct {
	TripID     string            `json:"trip_id"`
	RouteID    string            `json:"route_id"`
	StartDate  string            `json:"start_date"`
	ReceivedTS string            `json:"received_ts"`
	IngestTS   string            `json:"ingest_ts"`
	Schedule   string            `json:"schedule_relationship"`
	Stops      []json.RawMessage `json:"stop_time_updates"`
}

func main() {
	feedsDir := "/app/feeds"
	outPath := "/app/ledger/output.json"

	loadRouteRegistry("/app/timetable/timetable_routes.tsv")
	loadCaps("/app/envelope/envelope_caps.ini")
	loadSeals("/app/envelope/envelope_seals.json5")
	loadFeedRoutes("/app/orbital/manifest.toml")

	var rows []Row
	entries, err := os.ReadDir(feedsDir)
	if err != nil {
		panic(err)
	}
	names := []string{}
	for _, e := range entries {
		if !e.IsDir() {
			names = append(names, e.Name())
		}
	}
	sort.Strings(names)
	for _, name := range names {
		full := filepath.Join(feedsDir, name)
		feed, ext := matchExtension(name)
		if feed == "" {
			continue
		}
		rs, err := loadFeed(feed, ext, full)
		if err != nil {
			panic(err)
		}
		rows = append(rows, rs...)
	}

	sort.SliceStable(rows, func(i, j int) bool {
		ki := sortKey(rows[i])
		kj := sortKey(rows[j])
		if ki != kj {
			return ki < kj
		}
		if rows[i].TripID != rows[j].TripID {
			return rows[i].TripID < rows[j].TripID
		}
		return rows[i].Feed < rows[j].Feed
	})

	seen := map[string]bool{}
	capCount := map[string]int{}
	dedupPerHour := map[string]int{}
	decisions := make([]Decision, len(rows))
	for i, r := range rows {
		decisions[i] = decide(r, seen, capCount, dedupPerHour)
	}

	armedHours := map[string]bool{}
	for hour, cnt := range dedupPerHour {
		if cnt >= 2 {
			armedHours[nextHourOf(hour)] = true
		}
	}
	cascadeFired := map[string]bool{}
	for i, d := range decisions {
		if d.Verdict != "CAP_EXCEEDED" {
			continue
		}
		h := hourOf(rows[i].ReceivedTS)
		if armedHours[h] && !cascadeFired[h] {
			decisions[i].Verdict = "CASCADE_SUPPRESSED"
			cascadeFired[h] = true
		}
	}

	totals := map[string]int{}
	for _, v := range allVerdicts {
		totals[v] = 0
	}
	routeShare := map[string]int{}
	for _, r := range allRoutes {
		routeShare[r] = 0
	}
	for i := range decisions {
		decisions[i].Ordinal = i + 1
		totals[decisions[i].Verdict]++
		if isAdmit(decisions[i].Verdict) {
			routeShare[decisions[i].RouteID]++
		}
	}

	parts := make([]string, 0, len(decisions))
	for _, d := range decisions {
		parts = append(parts, strconv.Itoa(d.Ordinal)+":"+d.Verdict+":"+d.TripID)
	}
	preimage := "tripfix-v1|" + strconv.Itoa(len(decisions)) + "|" + strings.Join(parts, ";")
	sum := sha256.Sum256([]byte(preimage))
	digest := hex.EncodeToString(sum[:])[:16]

	out := map[string]any{
		"report_id":     "tripfix-v1",
		"window":        map[string]string{"start": windowStart, "end": windowEnd},
		"report_digest": digest,
		"decisions":     decisions,
		"totals":        totals,
		"route_share":   routeShare,
	}

	body, err := json.MarshalIndent(out, "", "  ")
	if err != nil {
		panic(err)
	}
	if err := os.MkdirAll(filepath.Dir(outPath), 0o755); err != nil {
		panic(err)
	}
	if err := os.WriteFile(outPath, body, 0o644); err != nil {
		panic(err)
	}
}

func isAdmit(v string) bool {
	switch v {
	case "ADMITTED_SCHEDULED", "ADMITTED_ADDED", "ADMITTED_NO_DATA", "ADMITTED_UNSCHEDULED":
		return true
	}
	return false
}

func sortKey(r Row) string {
	if r.BadTimestamp {
		return sentinelMaxTS
	}
	return r.ReceivedTS
}

func hourOf(ts string) string {
	t, err := time.Parse(time.RFC3339, ts)
	if err != nil {
		return sentinelMaxTS
	}
	return t.UTC().Format("2006-01-02T15") + ":00:00Z"
}

func nextHourOf(h string) string {
	t, err := time.Parse(time.RFC3339, h)
	if err != nil {
		return h
	}
	return t.Add(time.Hour).Format("2006-01-02T15:04:05Z")
}

func decide(r Row, seen map[string]bool, capCount map[string]int, dedupPerHour map[string]int) Decision {
	d := Decision{Feed: r.Feed, TripID: r.TripID, RouteID: r.RouteID, ReceivedTS: r.ReceivedTS}
	if r.Quarantine {
		d.Verdict = "SEQUENCE_REJECTED"
		return d
	}
	if r.BadTimestamp {
		d.Verdict = "TIMESTAMP_REJECTED"
		return d
	}
	if !knownRoutes[r.RouteID] {
		d.Verdict = "ROUTE_UNKNOWN"
		return d
	}
	if r.BadSeq {
		if isSealed(r) {
			d.Verdict = "PIN_RESCUED"
		} else {
			d.Verdict = "SEQUENCE_REJECTED"
		}
		return d
	}
	if r.Stale {
		d.Verdict = "STALE_INGEST"
		return d
	}
	key := r.TripID + "|" + r.StartDate
	if seen[key] {
		d.Verdict = "DEDUP_DUPLICATE"
		dedupPerHour[hourOf(r.ReceivedTS)]++
		return d
	}
	seen[key] = true
	if r.Schedule == "CANCELED" {
		d.Verdict = "CANCELED_TRIP"
		return d
	}
	h := hourOf(r.ReceivedTS)
	capKey := r.RouteID + "|" + h
	var limit int
	if criticalRoutes[r.RouteID] {
		limit = criticalCap
	} else {
		limit = standardCap
	}
	if capCount[capKey] >= limit {
		d.Verdict = "CAP_EXCEEDED"
		return d
	}
	if r.HasSkipped {
		d.Verdict = "SKIPPED_STOP"
		capCount[capKey]++
		return d
	}
	switch r.Schedule {
	case "SCHEDULED":
		d.Verdict = "ADMITTED_SCHEDULED"
	case "ADDED":
		d.Verdict = "ADMITTED_ADDED"
	case "NO_DATA":
		d.Verdict = "ADMITTED_NO_DATA"
	case "UNSCHEDULED":
		d.Verdict = "ADMITTED_UNSCHEDULED"
	default:
		d.Verdict = "ADMITTED_SCHEDULED"
	}
	capCount[capKey]++
	return d
}

func isSealed(r Row) bool {
	for _, s := range activeSeals {
		if s.Feed == r.Feed && s.TripID == r.TripID && s.ReceivedTS == r.ReceivedTS {
			mac := hmac.New(sha256.New, []byte(pinSecret))
			mac.Write([]byte(s.Feed + "|" + s.TripID + "|" + s.ReceivedTS))
			got := hex.EncodeToString(mac.Sum(nil))[:16]
			if got == s.SealHex {
				return true
			}
		}
	}
	return false
}

func matchExtension(name string) (feed, ext string) {
	candidates := make([]string, 0, len(feedByExt))
	for e := range feedByExt {
		candidates = append(candidates, e)
	}
	sort.Slice(candidates, func(i, j int) bool { return len(candidates[i]) > len(candidates[j]) })
	for _, e := range candidates {
		if strings.HasSuffix(name, e) {
			return feedByExt[e], e
		}
	}
	return "", ""
}

func loadFeed(feed, ext, path string) ([]Row, error) {
	switch feed {
	case "quarantine":
		return loadQuarantine(feed, path)
	}
	switch ext {
	case ".ndjson":
		return loadNDJSON(feed, path)
	case ".tsv":
		return loadDelim(feed, path, "\t")
	case ".psv":
		return loadDelim(feed, path, "|")
	case ".bin":
		return loadBinary(feed, path)
	}
	return nil, nil
}

func loadNDJSON(feed, path string) ([]Row, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var rows []Row
	scanner := bufio.NewScanner(strings.NewReader(string(data)))
	scanner.Buffer(make([]byte, 1024*1024), 1024*1024)
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		var rr rawRec
		if err := json.Unmarshal([]byte(line), &rr); err != nil {
			continue
		}
		rows = append(rows, toRow(feed, rr))
	}
	return rows, nil
}

func loadDelim(feed, path, sep string) ([]Row, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	lines := strings.Split(strings.TrimRight(string(data), "\n"), "\n")
	if len(lines) < 2 {
		return nil, nil
	}
	headers := strings.Split(lines[0], sep)
	idx := map[string]int{}
	for i, h := range headers {
		idx[h] = i
	}
	var rows []Row
	for _, line := range lines[1:] {
		if line == "" {
			continue
		}
		fields := strings.Split(line, sep)
		rr := rawRec{
			TripID:     fieldAt(fields, idx, "trip_id"),
			RouteID:    fieldAt(fields, idx, "route_id"),
			StartDate:  fieldAt(fields, idx, "start_date"),
			ReceivedTS: fieldAt(fields, idx, "received_ts"),
			IngestTS:   fieldAt(fields, idx, "ingest_ts"),
			Schedule:   fieldAt(fields, idx, "schedule_relationship"),
		}
		stopsJSON := fieldAt(fields, idx, "stops_json")
		if stopsJSON != "" && stopsJSON != "[]" {
			var stops []json.RawMessage
			_ = json.Unmarshal([]byte(stopsJSON), &stops)
			rr.Stops = stops
		}
		rows = append(rows, toRow(feed, rr))
	}
	return rows, nil
}

func loadBinary(feed, path string) ([]Row, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var rows []Row
	p := 0
	for p+4 <= len(data) {
		n := int(binary.LittleEndian.Uint32(data[p : p+4]))
		p += 4
		if p+n > len(data) {
			break
		}
		payload := data[p : p+n]
		p += n
		var rr rawRec
		if err := json.Unmarshal(payload, &rr); err != nil {
			continue
		}
		rows = append(rows, toRow(feed, rr))
	}
	return rows, nil
}

func loadQuarantine(feed, path string) ([]Row, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	var rows []Row
	scanner := bufio.NewScanner(strings.NewReader(string(data)))
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		var rr rawRec
		_ = json.Unmarshal([]byte(line), &rr)
		r := toRow(feed, rr)
		r.Quarantine = true
		rows = append(rows, r)
	}
	return rows, nil
}

func fieldAt(fields []string, idx map[string]int, name string) string {
	i, ok := idx[name]
	if !ok || i >= len(fields) {
		return ""
	}
	return fields[i]
}

func toRow(feed string, rr rawRec) Row {
	r := Row{
		Feed:       feed,
		TripID:     rr.TripID,
		RouteID:    rr.RouteID,
		StartDate:  rr.StartDate,
		ReceivedTS: rr.ReceivedTS,
		IngestTS:   rr.IngestTS,
		Schedule:   rr.Schedule,
	}
	if tsGrammar == nil || !tsGrammar.MatchString(rr.ReceivedTS) {
		r.BadTimestamp = true
	} else if _, err := time.Parse(time.RFC3339, rr.ReceivedTS); err != nil {
		r.BadTimestamp = true
	}
	if !r.BadTimestamp {
		if ing, errI := time.Parse(time.RFC3339, rr.IngestTS); errI == nil {
			if rec, errR := time.Parse(time.RFC3339, rr.ReceivedTS); errR == nil {
				if ing.Sub(rec).Seconds() > float64(staleThresholdSeconds) {
					r.Stale = true
				}
			}
		}
	}
	for _, s := range rr.Stops {
		var m map[string]any
		if err := json.Unmarshal(s, &m); err != nil {
			r.BadSeq = true
			continue
		}
		if seq, ok := m["stop_sequence"]; ok {
			switch v := seq.(type) {
			case float64:
				if v != float64(int(v)) {
					r.BadSeq = true
				}
			case string:
				if _, err := strconv.Atoi(v); err != nil {
					r.BadSeq = true
				}
			default:
				r.BadSeq = true
			}
		}
		if sched, ok := m["schedule_relationship"]; ok {
			if ss, ok := sched.(string); ok && ss == "SKIPPED" {
				r.HasSkipped = true
			}
		}
	}
	if _, err := strconv.Atoi(rr.StartDate); err != nil || len(rr.StartDate) != 8 {
		r.BadSeq = true
	}
	return r
}

func loadRouteRegistry(path string) {
	data, err := os.ReadFile(path)
	if err != nil {
		return
	}
	lines := strings.Split(strings.TrimRight(string(data), "\n"), "\n")
	if len(lines) < 2 {
		return
	}
	header := strings.Split(lines[0], "\t")
	idxR, idxC := -1, -1
	for i, h := range header {
		if h == "route_id" {
			idxR = i
		}
		if h == "route_class" {
			idxC = i
		}
	}
	for _, ln := range lines[1:] {
		fields := strings.Split(ln, "\t")
		if idxR >= 0 && idxR < len(fields) && fields[idxR] != "" {
			knownRoutes[fields[idxR]] = true
			allRoutes = append(allRoutes, fields[idxR])
			if idxC >= 0 && idxC < len(fields) && fields[idxC] == "CRITICAL" {
				criticalRoutes[fields[idxR]] = true
			}
		}
	}
	sort.Strings(allRoutes)
}

func parseIniSections(path string) map[string]map[string]string {
	out := map[string]map[string]string{}
	data, err := os.ReadFile(path)
	if err != nil {
		return out
	}
	section := ""
	for _, raw := range strings.Split(string(data), "\n") {
		line := strings.TrimSpace(raw)
		if line == "" || strings.HasPrefix(line, ";") || strings.HasPrefix(line, "#") {
			continue
		}
		if strings.HasPrefix(line, "[") && strings.HasSuffix(line, "]") {
			section = strings.TrimSpace(line[1 : len(line)-1])
			if _, ok := out[section]; !ok {
				out[section] = map[string]string{}
			}
			continue
		}
		eq := strings.Index(line, "=")
		if eq < 0 {
			continue
		}
		key := strings.TrimSpace(line[:eq])
		val := strings.TrimSpace(line[eq+1:])
		key = strings.Trim(key, `"`)
		val = strings.Trim(val, `"`)
		if section != "" {
			out[section][key] = val
		}
	}
	return out
}

func loadCaps(path string) {
	sections := parseIniSections(path)
	if v, ok := sections["caps"]["window_start"]; ok {
		windowStart = v
	}
	if v, ok := sections["caps"]["window_end"]; ok {
		windowEnd = v
	}
	if v, ok := sections["tier_caps"]["STANDARD"]; ok {
		if n, err := strconv.Atoi(v); err == nil {
			standardCap = n
		}
	}
	if v, ok := sections["tier_caps"]["CRITICAL"]; ok {
		if n, err := strconv.Atoi(v); err == nil {
			criticalCap = n
		}
	}
	if v, ok := sections["stale_ingest"]["threshold_seconds"]; ok {
		if n, err := strconv.Atoi(v); err == nil {
			staleThresholdSeconds = n
		}
	}
	if v, ok := sections["timestamp_grammar"]["regex"]; ok {
		tsGrammar = regexp.MustCompile(v)
	}
}

func loadSeals(path string) {
	data, err := os.ReadFile(path)
	if err != nil {
		return
	}
	cleaned := stripJSON5(string(data))
	var cfg struct {
		PinSecret   string `json:"pin_secret"`
		ActiveSeals []struct {
			Feed       string `json:"feed"`
			TripID     string `json:"trip_id"`
			ReceivedTS string `json:"received_ts"`
			SealHex    string `json:"seal_hex"`
		} `json:"active_seals"`
	}
	if err := json.Unmarshal([]byte(cleaned), &cfg); err != nil {
		return
	}
	pinSecret = cfg.PinSecret
	for _, s := range cfg.ActiveSeals {
		activeSeals = append(activeSeals, Seal{Feed: s.Feed, TripID: s.TripID, ReceivedTS: s.ReceivedTS, SealHex: s.SealHex})
	}
}

func stripJSON5(s string) string {
	var lines []string
	for _, line := range strings.Split(s, "\n") {
		inStr := false
		out := []byte{}
		for i := 0; i < len(line); i++ {
			c := line[i]
			if c == '"' && (i == 0 || line[i-1] != '\\') {
				inStr = !inStr
			}
			if !inStr && i+1 < len(line) && line[i] == '/' && line[i+1] == '/' {
				break
			}
			out = append(out, c)
		}
		lines = append(lines, string(out))
	}
	cleaned := strings.Join(lines, "\n")
	re := regexp.MustCompile(`([\{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)`)
	cleaned = re.ReplaceAllString(cleaned, `$1"$2"$3`)
	return cleaned
}

func loadFeedRoutes(path string) {
	sections := parseIniSections(path)
	for k, v := range sections["feed_routes"] {
		feedByExt[k] = v
	}
}
GO_EOF

rm -rf binary
mkdir -p binary ledger
go build -o binary/tripfix ./kernel/kernel_main
./binary/tripfix
