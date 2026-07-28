package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"database/sql"
	"encoding/json"
	"fmt"
	"math"
	"net/http"
	"os"
	"sort"
	"strconv"
	"strings"
	"time"

	_ "modernc.org/sqlite"
)

const dbPath = "/app/wb.db"
const hmacKey = "wb-tracker-secret-2026"

// canonicalizeZero normalizes IEEE 754 negative zero (-0.0) to positive zero
// so formatted output never prints a leading "-" for a mathematically-zero
// result. Negative zero can arise from floating-point cancellation in
// subtraction-based formulas (e.g. HHI normalization, covariance,
// correlation) or from negating a positive zero product (e.g. entropy's
// -sum(p*log2(p)) collapsing to -(1.0*0.0) for a single-category
// distribution). Go's == treats +0.0 and -0.0 as equal, so this only ever
// rewrites the sign bit of an exact zero and leaves every other value
// untouched.
func canonicalizeZero(f float64) float64 {
	if f == 0 {
		return 0.0
	}
	return f
}

func apiBaseURL() string {
	if v := os.Getenv("API_BASE_URL"); v != "" {
		return strings.TrimRight(v, "/")
	}
	return "https://api.worldbank.org/v2"
}

func openDB() *sql.DB {
	db, err := sql.Open("sqlite", dbPath)
	if err != nil {
		fmt.Fprintln(os.Stderr, "failed to open db:", err)
		os.Exit(1)
	}
	return db
}

func cmdInit() {
	db := openDB()
	defer db.Close()
	_, err := db.Exec(`CREATE TABLE IF NOT EXISTS countries (
		code TEXT PRIMARY KEY,
		name TEXT,
		region TEXT,
		income_level TEXT,
		capital TEXT,
		latitude REAL,
		longitude REAL
	)`)
	if err != nil {
		fmt.Fprintln(os.Stderr, "create countries:", err)
		os.Exit(1)
	}
	_, err = db.Exec(`CREATE TABLE IF NOT EXISTS audit_log (
		seq INTEGER PRIMARY KEY,
		country_code TEXT,
		latitude REAL,
		longitude REAL,
		kurtosis_at_insert TEXT,
		skewness_at_insert TEXT,
		p50_at_insert REAL NOT NULL DEFAULT 0.0,
		mad_at_insert TEXT NOT NULL DEFAULT 'NULL',
		prev_hash TEXT,
		entry_hash TEXT
	)`)
	if err != nil {
		fmt.Fprintln(os.Stderr, "create audit_log:", err)
		os.Exit(1)
	}
	fmt.Println("OK")
}

type WBMeta struct {
	Total int `json:"total"`
}

type WBCountry struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	Region      struct{ ID string `json:"id"` } `json:"region"`
	IncomeLevel struct{ ID string `json:"id"` } `json:"incomeLevel"`
	CapitalCity string `json:"capitalCity"`
	Latitude    string `json:"latitude"`
	Longitude   string `json:"longitude"`
}

func computeHMAC(seq int, code string, lat, lon float64, skew, kurt string, p50 float64, mad, prevHash string) string {
	msg := fmt.Sprintf("%d|%s|%.6f|%.6f|%s|%s|%.6f|%s|%s", seq, code, lat, lon, skew, kurt, p50, mad, prevHash)
	mac := hmac.New(sha256.New, []byte(hmacKey))
	mac.Write([]byte(msg))
	return fmt.Sprintf("%x", mac.Sum(nil))
}

// computeP50AtInsert returns the median of xs using HALF_EVEN rounding for even N.
// Returns 0.0 if N < 2.
func computeP50AtInsert(xs []float64) float64 {
	n := len(xs)
	if n < 2 {
		return 0.0
	}
	sorted := make([]float64, n)
	copy(sorted, xs)
	sort.Float64s(sorted)
	if n%2 == 1 {
		return sorted[(n-1)/2]
	}
	// Even N: average of two middle values with HALF_EVEN rounding to 6dp
	lo := sorted[n/2-1]
	hi := sorted[n/2]
	avg := (lo + hi) / 2.0
	// Apply HALF_EVEN (banker's) rounding to 6 decimal places
	return bankersRound6(avg)
}

// bankersRound6 rounds x to 6 decimal places using HALF_EVEN (banker's rounding).
func bankersRound6(x float64) float64 {
	factor := 1e6
	scaled := x * factor
	floor := math.Floor(scaled)
	frac := scaled - floor
	const eps = 1e-9
	if math.Abs(frac-0.5) < eps {
		// Exactly half: round to even
		if int64(floor)%2 == 0 {
			return canonicalizeZero(floor / factor)
		}
		return canonicalizeZero((floor + 1) / factor)
	}
	return canonicalizeZero(math.Round(scaled) / factor)
}

// computeMADAtInsert returns the Median Absolute Deviation of xs formatted to
// 8 decimal places, or "NULL" if N < 2. Both the center and the deviation
// median use the nearest-rank rule (rank = ceil(0.5*N), index = rank-1) — the
// same algorithm as the country-mad command, NOT the interpolated HALF_EVEN
// median used for p50_at_insert.
func computeMADAtInsert(xs []float64) string {
	n := len(xs)
	if n < 2 {
		return "NULL"
	}
	sorted := make([]float64, n)
	copy(sorted, xs)
	sort.Float64s(sorted)
	medRank := int(math.Ceil(0.5 * float64(n)))
	median := sorted[medRank-1]
	devs := make([]float64, n)
	for i, v := range xs {
		devs[i] = math.Abs(v - median)
	}
	sort.Float64s(devs)
	mad := devs[medRank-1]
	return fmt.Sprintf("%.8f", canonicalizeZero(mad))
}

func popMean(xs []float64) float64 {
	s := 0.0
	for _, v := range xs {
		s += v
	}
	return s / float64(len(xs))
}

func popVar(xs []float64) float64 {
	m := popMean(xs)
	s := 0.0
	for _, v := range xs {
		d := v - m
		s += d * d
	}
	return s / float64(len(xs))
}

func computeSkewStr(xs []float64) string {
	n := len(xs)
	if n < 3 {
		return "NULL"
	}
	m := popMean(xs)
	v := popVar(xs)
	if v == 0 {
		return "NULL"
	}
	m3 := 0.0
	for _, x := range xs {
		d := x - m
		m3 += d * d * d
	}
	m3 /= float64(n)
	return fmt.Sprintf("%.8f", canonicalizeZero(m3/math.Pow(v, 1.5)))
}

func computeKurtStr(xs []float64) string {
	n := len(xs)
	if n < 4 {
		return "NULL"
	}
	m := popMean(xs)
	v := popVar(xs)
	if v == 0 {
		return "NULL"
	}
	m4 := 0.0
	for _, x := range xs {
		d := x - m
		m4 += d * d * d * d
	}
	m4 /= float64(n)
	return fmt.Sprintf("%.8f", canonicalizeZero(m4/(v*v)-3.0))
}

func doFetchRequest(client *http.Client, url string) (*http.Response, error) {
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("User-Agent", "worldbank-country-tracker/1.0")
	return client.Do(req)
}

func cmdFetchCountry(code string) {
	code = strings.ToUpper(code)
	db := openDB()
	defer db.Close()

	// Check if exists
	var exists int
	err := db.QueryRow("SELECT COUNT(*) FROM countries WHERE code=?", code).Scan(&exists)
	if err != nil {
		fmt.Fprintln(os.Stderr, "db error:", err)
		os.Exit(1)
	}
	if exists > 0 {
		fmt.Println("exists")
		os.Exit(0)
	}

	// Fetch from API
	url := fmt.Sprintf("%s/country/%s?format=json", apiBaseURL(), code)
	client := &http.Client{}
	resp, err := doFetchRequest(client, url)
	if err != nil {
		fmt.Fprintln(os.Stderr, "http error:", err)
		os.Exit(1)
	}

	// Handle HTTP 429 rate limiting
	if resp.StatusCode == 429 {
		resp.Body.Close()
		// Read Retry-After header
		retryAfterStr := resp.Header.Get("Retry-After")
		retryAfterSecs := 1
		if retryAfterStr != "" {
			if n, parseErr := strconv.Atoi(retryAfterStr); parseErr == nil && n > 0 {
				retryAfterSecs = n
			}
		}
		time.Sleep(time.Duration(retryAfterSecs) * time.Second)

		// Retry once
		resp, err = doFetchRequest(client, url)
		if err != nil {
			fmt.Fprintln(os.Stderr, "http error:", err)
			os.Exit(1)
		}
		if resp.StatusCode == 429 {
			resp.Body.Close()
			fmt.Println("rate_limited")
			os.Exit(2)
		}
	}
	defer resp.Body.Close()

	var raw []json.RawMessage
	if err := json.NewDecoder(resp.Body).Decode(&raw); err != nil || len(raw) < 2 {
		fmt.Fprintf(os.Stderr, "not_found: %s\n", code)
		os.Exit(1)
	}

	var meta WBMeta
	json.Unmarshal(raw[0], &meta)
	if meta.Total == 0 {
		fmt.Fprintf(os.Stderr, "not_found: %s\n", code)
		os.Exit(1)
	}

	// Second element may be null or empty array
	if string(raw[1]) == "null" {
		fmt.Fprintf(os.Stderr, "not_found: %s\n", code)
		os.Exit(1)
	}

	var countries []WBCountry
	json.Unmarshal(raw[1], &countries)
	if len(countries) == 0 {
		fmt.Fprintf(os.Stderr, "not_found: %s\n", code)
		os.Exit(1)
	}

	c := countries[0]
	lat, err1 := strconv.ParseFloat(c.Latitude, 64)
	lon, err2 := strconv.ParseFloat(c.Longitude, 64)
	if err1 != nil {
		lat = 0
	}
	if err2 != nil {
		lon = 0
	}

	// Compute skewness/kurtosis of existing latitudes BEFORE insert
	var existingLats []float64
	latRows, _ := db.Query("SELECT latitude FROM countries")
	for latRows.Next() {
		var latVal float64
		latRows.Scan(&latVal)
		existingLats = append(existingLats, latVal)
	}
	latRows.Close()

	skewAtInsert := computeSkewStr(existingLats)
	kurtAtInsert := computeKurtStr(existingLats)
	p50AtInsert := computeP50AtInsert(existingLats)
	madAtInsert := computeMADAtInsert(existingLats)

	// Get next seq and prev_hash
	var seq int
	var prevHash string
	err = db.QueryRow("SELECT COALESCE(MAX(seq),0) FROM audit_log").Scan(&seq)
	if err != nil {
		fmt.Fprintln(os.Stderr, "seq query error:", err)
		os.Exit(1)
	}
	if seq == 0 {
		prevHash = strings.Repeat("0", 64)
	} else {
		err = db.QueryRow("SELECT entry_hash FROM audit_log ORDER BY seq DESC LIMIT 1").Scan(&prevHash)
		if err != nil {
			fmt.Fprintln(os.Stderr, "prev_hash query error:", err)
			os.Exit(1)
		}
	}
	seq++

	entryHash := computeHMAC(seq, code, lat, lon, skewAtInsert, kurtAtInsert, p50AtInsert, madAtInsert, prevHash)

	tx, err := db.Begin()
	if err != nil {
		fmt.Fprintln(os.Stderr, "tx error:", err)
		os.Exit(1)
	}
	_, err = tx.Exec("INSERT INTO countries (code,name,region,income_level,capital,latitude,longitude) VALUES (?,?,?,?,?,?,?)",
		code, c.Name, c.Region.ID, c.IncomeLevel.ID, c.CapitalCity, lat, lon)
	if err != nil {
		tx.Rollback()
		fmt.Fprintln(os.Stderr, "insert countries:", err)
		os.Exit(1)
	}
	_, err = tx.Exec("INSERT INTO audit_log (seq,country_code,latitude,longitude,kurtosis_at_insert,skewness_at_insert,p50_at_insert,mad_at_insert,prev_hash,entry_hash) VALUES (?,?,?,?,?,?,?,?,?,?)",
		seq, code, lat, lon, kurtAtInsert, skewAtInsert, p50AtInsert, madAtInsert, prevHash, entryHash)
	if err != nil {
		tx.Rollback()
		fmt.Fprintln(os.Stderr, "insert audit_log:", err)
		os.Exit(1)
	}
	tx.Commit()

	fmt.Printf("ok country=%s name=%s\n", code, c.Name)
}

func cmdListCountries(args []string) {
	// Parse --limit and --offset flags
	limit := -1  // -1 means no limit (return all)
	offset := 0
	for i := 0; i < len(args); i++ {
		if args[i] == "--limit" && i+1 < len(args) {
			if n, err := strconv.Atoi(args[i+1]); err == nil {
				limit = n
			}
			i++
		} else if args[i] == "--offset" && i+1 < len(args) {
			if n, err := strconv.Atoi(args[i+1]); err == nil {
				offset = n
			}
			i++
		}
	}

	// If limit is 0, print nothing
	if limit == 0 {
		return
	}

	db := openDB()
	defer db.Close()

	var rows *sql.Rows
	var err error
	if limit < 0 {
		rows, err = db.Query("SELECT code,name,region,income_level,capital FROM countries ORDER BY name ASC, code ASC LIMIT -1 OFFSET ?", offset)
	} else {
		rows, err = db.Query("SELECT code,name,region,income_level,capital FROM countries ORDER BY name ASC, code ASC LIMIT ? OFFSET ?", limit, offset)
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, "query error:", err)
		os.Exit(1)
	}
	defer rows.Close()
	for rows.Next() {
		var code, name, region, income, capital string
		rows.Scan(&code, &name, &region, &income, &capital)
		fmt.Printf("%s\t%s\t%s\t%s\t%s\n", code, name, region, income, capital)
	}
}

type latLon struct {
	code string
	lat  float64
	lon  float64
}

func cmdCountryStats() {
	db := openDB()
	defer db.Close()
	rows, err := db.Query("SELECT latitude, longitude FROM countries")
	if err != nil {
		fmt.Fprintln(os.Stderr, "query error:", err)
		os.Exit(1)
	}
	defer rows.Close()
	var lats []float64
	var lons []float64
	for rows.Next() {
		var lat, lon float64
		rows.Scan(&lat, &lon)
		lats = append(lats, lat)
		lons = append(lons, lon)
	}

	n := len(lats)
	if n == 0 {
		fmt.Println("count=0")
		fmt.Println("avg_latitude=NULL")
		fmt.Println("stddev_latitude=NULL")
		fmt.Println("p75_latitude=NULL")
		fmt.Println("p90_latitude=NULL")
		fmt.Println("skewness_latitude=NULL")
		fmt.Println("kurtosis_latitude=NULL")
		fmt.Println("p90_longitude=NULL")
		fmt.Println("stddev_longitude=NULL")
		return
	}

	// avg latitude
	sumLat := 0.0
	for _, v := range lats {
		sumLat += v
	}
	avgLat := sumLat / float64(n)

	// population variance latitude
	varLat := 0.0
	for _, v := range lats {
		d := v - avgLat
		varLat += d * d
	}
	varLat /= float64(n)

	// stddev latitude
	var stddevLatStr string
	if n < 2 {
		stddevLatStr = "NULL"
	} else {
		stddevLatStr = fmt.Sprintf("%.6f", math.Sqrt(varLat))
	}

	// sorted lats for percentiles
	sortedLats := make([]float64, len(lats))
	copy(sortedLats, lats)
	sort.Float64s(sortedLats)

	p75rank := int(math.Ceil(0.75 * float64(n)))
	p90rank := int(math.Ceil(0.90 * float64(n)))
	p75lat := sortedLats[p75rank-1]
	p90lat := sortedLats[p90rank-1]

	// skewness latitude: M3 / var^1.5
	var skewStr string
	if n < 3 || varLat == 0 {
		skewStr = "NULL"
	} else {
		m3 := 0.0
		for _, v := range lats {
			d := v - avgLat
			m3 += d * d * d
		}
		m3 /= float64(n)
		skewStr = fmt.Sprintf("%.8f", canonicalizeZero(m3/math.Pow(varLat, 1.5)))
	}

	// kurtosis latitude: M4 / var^2 - 3
	var kurtStr string
	if n < 4 || varLat == 0 {
		kurtStr = "NULL"
	} else {
		m4 := 0.0
		for _, v := range lats {
			d := v - avgLat
			m4 += d * d * d * d
		}
		m4 /= float64(n)
		kurtStr = fmt.Sprintf("%.8f", canonicalizeZero(m4/(varLat*varLat)-3.0))
	}

	// longitude stats
	sumLon := 0.0
	for _, v := range lons {
		sumLon += v
	}
	avgLon := sumLon / float64(n)

	varLon := 0.0
	for _, v := range lons {
		d := v - avgLon
		varLon += d * d
	}
	varLon /= float64(n)

	var stddevLonStr string
	if n < 2 {
		stddevLonStr = "NULL"
	} else {
		stddevLonStr = fmt.Sprintf("%.6f", math.Sqrt(varLon))
	}

	sortedLons := make([]float64, len(lons))
	copy(sortedLons, lons)
	sort.Float64s(sortedLons)
	p90lonRank := int(math.Ceil(0.90 * float64(n)))
	p90lon := sortedLons[p90lonRank-1]

	fmt.Printf("count=%d\n", n)
	fmt.Printf("avg_latitude=%.6f\n", avgLat)
	if stddevLatStr == "NULL" {
		fmt.Println("stddev_latitude=NULL")
	} else {
		fmt.Printf("stddev_latitude=%s\n", stddevLatStr)
	}
	fmt.Printf("p75_latitude=%.6f\n", p75lat)
	fmt.Printf("p90_latitude=%.6f\n", p90lat)
	if skewStr == "NULL" {
		fmt.Println("skewness_latitude=NULL")
	} else {
		fmt.Printf("skewness_latitude=%s\n", skewStr)
	}
	if kurtStr == "NULL" {
		fmt.Println("kurtosis_latitude=NULL")
	} else {
		fmt.Printf("kurtosis_latitude=%s\n", kurtStr)
	}
	fmt.Printf("p90_longitude=%.6f\n", p90lon)
	if stddevLonStr == "NULL" {
		fmt.Println("stddev_longitude=NULL")
	} else {
		fmt.Printf("stddev_longitude=%s\n", stddevLonStr)
	}
}

func cmdCountryZscores(args []string) {
	// Accept optional <db> arg but always use /app/wb.db
	_ = args
	db := openDB()
	defer db.Close()

	rows, err := db.Query("SELECT code, latitude, longitude FROM countries")
	if err != nil {
		fmt.Fprintln(os.Stderr, "query error:", err)
		os.Exit(1)
	}
	defer rows.Close()

	var entries []latLon
	for rows.Next() {
		var e latLon
		rows.Scan(&e.code, &e.lat, &e.lon)
		entries = append(entries, e)
	}

	n := len(entries)
	if n < 2 {
		fmt.Println("insufficient data")
		return
	}

	sumLat, sumLon := 0.0, 0.0
	for _, e := range entries {
		sumLat += e.lat
		sumLon += e.lon
	}
	avgLat := sumLat / float64(n)
	avgLon := sumLon / float64(n)

	varLat, varLon := 0.0, 0.0
	for _, e := range entries {
		dl := e.lat - avgLat
		varLat += dl * dl
		dl2 := e.lon - avgLon
		varLon += dl2 * dl2
	}
	varLat /= float64(n)
	varLon /= float64(n)
	stdLat := math.Sqrt(varLat)
	stdLon := math.Sqrt(varLon)

	type zsEntry struct {
		code    string
		zLat    float64
		zLatStr string
		zLonStr string
	}

	var zEntries []zsEntry
	for _, e := range entries {
		var zlatStr, zlonStr string
		var zLatVal float64
		if stdLat == 0 {
			zlatStr = "NULL"
			zLatVal = 0
		} else {
			zLatVal = canonicalizeZero((e.lat - avgLat) / stdLat)
			zlatStr = fmt.Sprintf("%.8f", zLatVal)
		}
		if stdLon == 0 {
			zlonStr = "NULL"
		} else {
			zlonStr = fmt.Sprintf("%.8f", canonicalizeZero((e.lon-avgLon)/stdLon))
		}
		zEntries = append(zEntries, zsEntry{e.code, zLatVal, zlatStr, zlonStr})
	}

	// Sort by z_lat ASC then code ASC
	sort.Slice(zEntries, func(i, j int) bool {
		if zEntries[i].zLat != zEntries[j].zLat {
			return zEntries[i].zLat < zEntries[j].zLat
		}
		return zEntries[i].code < zEntries[j].code
	})

	for _, e := range zEntries {
		fmt.Printf("%s\t%s\t%s\n", e.code, e.zLatStr, e.zLonStr)
	}
}

func cmdAuditVerify() {
	db := openDB()
	defer db.Close()
	rows, err := db.Query("SELECT seq,country_code,latitude,longitude,kurtosis_at_insert,skewness_at_insert,p50_at_insert,mad_at_insert,prev_hash,entry_hash FROM audit_log ORDER BY seq ASC")
	if err != nil {
		fmt.Fprintln(os.Stderr, "query error:", err)
		os.Exit(1)
	}
	defer rows.Close()

	type Entry struct {
		Seq       int
		Code      string
		Lat, Lon  float64
		Kurt      string
		Skew      string
		P50       float64
		Mad       string
		PrevHash  string
		EntryHash string
	}
	var entries []Entry
	for rows.Next() {
		var e Entry
		rows.Scan(&e.Seq, &e.Code, &e.Lat, &e.Lon, &e.Kurt, &e.Skew, &e.P50, &e.Mad, &e.PrevHash, &e.EntryHash)
		entries = append(entries, e)
	}

	n := len(entries)
	for i, e := range entries {
		expectedSeq := i + 1
		// seq_gap check
		if e.Seq != expectedSeq {
			fmt.Printf("TAMPERED seq=%d reason=seq_gap\n", e.Seq)
			os.Exit(1)
		}
		// prev_hash check
		var expectedPrev string
		if i == 0 {
			expectedPrev = strings.Repeat("0", 64)
		} else {
			expectedPrev = entries[i-1].EntryHash
		}
		if e.PrevHash != expectedPrev {
			fmt.Printf("TAMPERED seq=%d reason=prev_hash_mismatch\n", e.Seq)
			os.Exit(1)
		}
		// entry_hash check
		expected := computeHMAC(e.Seq, e.Code, e.Lat, e.Lon, e.Skew, e.Kurt, e.P50, e.Mad, e.PrevHash)
		if e.EntryHash != expected {
			fmt.Printf("TAMPERED seq=%d reason=entry_hash_mismatch\n", e.Seq)
			os.Exit(1)
		}
	}

	fmt.Printf("ok chain_length=%d\n", n)
}

type rankEntry struct {
	code   string
	lat    float64
	region string
}

// regionCoreCap bounds how many countries in a single region can hold the
// "core" tier at once. See docs/regional-classification.md for the scoring
// and tie-break rule that decides which countries currently occupy those
// slots.
const regionCoreCap = 3

// regionCoreTier recomputes tier membership for `region` from scratch over
// every country in `all` that currently shares it, so the result reflects
// the live state of the countries table rather than anything decided once
// and stored away.
func regionCoreTier(all []rankEntry, region string, code string) string {
	var group []rankEntry
	for _, e := range all {
		if e.region == region {
			group = append(group, e)
		}
	}

	if len(group) <= regionCoreCap {
		return "core"
	}

	lats := make([]float64, len(group))
	for i, e := range group {
		lats[i] = e.lat
	}
	mean := popMean(lats)
	stddev := math.Sqrt(popVar(lats))

	type scoredCode struct {
		code  string
		score float64
	}
	scored := make([]scoredCode, len(group))
	for i, e := range group {
		s := 0.0
		if stddev != 0 {
			s = math.Abs(e.lat-mean) / stddev
		}
		scored[i] = scoredCode{e.code, s}
	}

	sort.Slice(scored, func(i, j int) bool {
		if scored[i].score != scored[j].score {
			return scored[i].score > scored[j].score
		}
		return scored[i].code < scored[j].code
	})

	for i, s := range scored {
		if s.code == code {
			if i < regionCoreCap {
				return "core"
			}
			return "peripheral"
		}
	}
	return "peripheral"
}

func cmdCountryRank(code string) {
	code = strings.ToUpper(code)
	db := openDB()
	defer db.Close()

	rows, err := db.Query("SELECT code, latitude, region FROM countries ORDER BY latitude ASC, code ASC")
	if err != nil {
		fmt.Fprintln(os.Stderr, "query error:", err)
		os.Exit(1)
	}
	defer rows.Close()

	var entries []rankEntry
	for rows.Next() {
		var e rankEntry
		rows.Scan(&e.code, &e.lat, &e.region)
		entries = append(entries, e)
	}

	total := len(entries)
	rank := -1
	var region string
	for i, e := range entries {
		if e.code == code {
			rank = i + 1 // 1-based
			region = e.region
			break
		}
	}

	if rank == -1 {
		fmt.Println("not_found")
		os.Exit(1)
	}

	pct := float64(rank) / float64(total) * 100
	fmt.Printf("rank=%d\n", rank)
	fmt.Printf("total=%d\n", total)
	fmt.Printf("pct=%.2f\n", pct)
	fmt.Printf("tier=%s\n", regionCoreTier(entries, region, code))
}

func cmdAuditStats() {
	db := openDB()
	defer db.Close()

	var chainLength int
	err := db.QueryRow("SELECT COUNT(*) FROM audit_log").Scan(&chainLength)
	if err != nil {
		fmt.Fprintln(os.Stderr, "query error:", err)
		os.Exit(1)
	}

	if chainLength == 0 {
		fmt.Println("chain_length=0")
		fmt.Println("unique_codes=0")
		fmt.Println("first_code=none")
		fmt.Println("last_code=none")
		return
	}

	var uniqueCodes int
	err = db.QueryRow("SELECT COUNT(DISTINCT country_code) FROM audit_log").Scan(&uniqueCodes)
	if err != nil {
		fmt.Fprintln(os.Stderr, "query error:", err)
		os.Exit(1)
	}

	var firstCode string
	err = db.QueryRow("SELECT country_code FROM audit_log WHERE seq=1").Scan(&firstCode)
	if err != nil {
		fmt.Fprintln(os.Stderr, "query error:", err)
		os.Exit(1)
	}

	var lastCode string
	err = db.QueryRow("SELECT country_code FROM audit_log WHERE seq=(SELECT MAX(seq) FROM audit_log)").Scan(&lastCode)
	if err != nil {
		fmt.Fprintln(os.Stderr, "query error:", err)
		os.Exit(1)
	}

	fmt.Printf("chain_length=%d\n", chainLength)
	fmt.Printf("unique_codes=%d\n", uniqueCodes)
	fmt.Printf("first_code=%s\n", firstCode)
	fmt.Printf("last_code=%s\n", lastCode)
}

// auditBaselineWindowCap and auditBaselineReturnDelay are the non-inferable
// constants for audit-baseline-window; see /docs/audit-baseline-window.md.
const auditBaselineWindowCap = 2
const auditBaselineReturnDelay = 3

func cmdAuditBaselineWindow() {
	db := openDB()
	defer db.Close()

	rows, err := db.Query("SELECT seq, country_code FROM audit_log ORDER BY seq ASC")
	if err != nil {
		fmt.Fprintln(os.Stderr, "query error:", err)
		os.Exit(1)
	}
	defer rows.Close()

	type sampleEntry struct {
		seq  int
		code string
	}
	var entries []sampleEntry
	for rows.Next() {
		var e sampleEntry
		if err := rows.Scan(&e.seq, &e.code); err != nil {
			fmt.Fprintln(os.Stderr, "scan error:", err)
			os.Exit(1)
		}
		entries = append(entries, e)
	}

	if len(entries) == 0 {
		fmt.Println("empty")
		return
	}

	openSlots := auditBaselineWindowCap
	joinedSince := make(map[int]int)
	aged := make(map[int]bool)
	var pending []int

	for _, e := range entries {
		seq := e.seq

		// Aging phase: any baseline row that has held its slot for
		// auditBaselineReturnDelay more rows ages out and frees the slot.
		// The age-out point is anchored to the step at which the row
		// itself joined the baseline (joinedSince), not the row's
		// original seq.
		for s, js := range joinedSince {
			if !aged[s] && js+auditBaselineReturnDelay == seq {
				openSlots++
				aged[s] = true
			}
		}

		// This step's row joins the back of the pending line; it does
		// not preempt anyone already waiting, even if its own arrival
		// is what indirectly aged a slot open this step.
		pending = append(pending, seq)

		// Admit into the baseline strictly in log order while slots remain.
		for openSlots > 0 && len(pending) > 0 {
			s := pending[0]
			pending = pending[1:]
			joinedSince[s] = seq
			openSlots--
		}
	}

	for _, e := range entries {
		status := "provisional"
		if _, ok := joinedSince[e.seq]; ok {
			status = "baseline"
		}
		fmt.Printf("%d\t%s\tstatus=%s\n", e.seq, e.code, status)
	}
	fmt.Printf("window_remaining=%d\n", openSlots)
}

func cmdCountryGini() {
	db := openDB()
	defer db.Close()
	rows, err := db.Query("SELECT latitude FROM countries ORDER BY latitude ASC")
	if err != nil {
		fmt.Fprintln(os.Stderr, "query error:", err)
		os.Exit(1)
	}
	defer rows.Close()
	var lats []float64
	for rows.Next() {
		var v float64
		rows.Scan(&v)
		lats = append(lats, v)
	}
	n := len(lats)
	if n < 2 {
		fmt.Println("insufficient_data")
		os.Exit(1)
	}
	// Shift to strictly positive: shifted_i = lat_i - min + 1
	minLat := lats[0]
	for _, v := range lats {
		if v < minLat {
			minLat = v
		}
	}
	shifted := make([]float64, n)
	for i, v := range lats {
		shifted[i] = v - minLat + 1.0
	}
	sort.Float64s(shifted)
	totalSum := 0.0
	for _, v := range shifted {
		totalSum += v
	}
	rankSum := 0.0
	for i, v := range shifted {
		rank := float64(i + 1)
		rankSum += rank * v
	}
	gini := (2*rankSum)/(float64(n)*totalSum) - float64(n+1)/float64(n)
	fmt.Printf("gini=%.8f\n", canonicalizeZero(gini))
}

func cmdCountryEntropy() {
	db := openDB()
	defer db.Close()
	rows, err := db.Query("SELECT region FROM countries")
	if err != nil {
		fmt.Fprintln(os.Stderr, "query error:", err)
		os.Exit(1)
	}
	defer rows.Close()
	regionCounts := map[string]int{}
	total := 0
	for rows.Next() {
		var region string
		rows.Scan(&region)
		regionCounts[region]++
		total++
	}
	if total < 2 {
		fmt.Println("insufficient_data")
		os.Exit(1)
	}
	entropy := 0.0
	for _, count := range regionCounts {
		p := float64(count) / float64(total)
		entropy -= p * math.Log2(p)
	}
	// Canonicalize away IEEE 754 negative zero: a single-region (uniform)
	// distribution has zero entropy, but computing it as -(p*log2(p)) with
	// p=1.0 (log2(1.0)=+0.0) can yield -0.0 depending on how the terms are
	// combined, which would otherwise print as "-0.00000000".
	fmt.Printf("entropy=%.8f\n", canonicalizeZero(entropy))
}

func cmdCountryAtkinson() {
	db := openDB()
	defer db.Close()
	rows, err := db.Query("SELECT latitude FROM countries")
	if err != nil {
		fmt.Fprintln(os.Stderr, "query error:", err)
		os.Exit(1)
	}
	defer rows.Close()
	var lats []float64
	for rows.Next() {
		var v float64
		rows.Scan(&v)
		lats = append(lats, v)
	}
	n := len(lats)
	if n < 2 {
		fmt.Println("insufficient_data")
		os.Exit(1)
	}
	minLat := lats[0]
	for _, v := range lats {
		if v < minLat {
			minLat = v
		}
	}
	sumShifted := 0.0
	sumSqrt := 0.0
	for _, v := range lats {
		shifted := v - minLat + 1.0
		sumShifted += shifted
		sumSqrt += math.Sqrt(shifted)
	}
	meanShifted := sumShifted / float64(n)
	meanSqrt := sumSqrt / float64(n)
	if meanShifted == 0 {
		fmt.Println("insufficient_data")
		os.Exit(1)
	}
	atkinson := 1.0 - (meanSqrt*meanSqrt)/meanShifted
	fmt.Printf("atkinson=%.8f\n", canonicalizeZero(atkinson))
}

func cmdCountryTheil() {
	db := openDB()
	defer db.Close()
	rows, err := db.Query("SELECT latitude FROM countries")
	if err != nil {
		fmt.Fprintln(os.Stderr, "query error:", err)
		os.Exit(1)
	}
	defer rows.Close()
	var lats []float64
	for rows.Next() {
		var v float64
		rows.Scan(&v)
		lats = append(lats, v)
	}
	n := len(lats)
	if n < 2 {
		fmt.Println("theil: NULL")
		return
	}
	// Use absolute values of latitude
	absLats := make([]float64, n)
	for i, v := range lats {
		absLats[i] = math.Abs(v)
	}
	mu := 0.0
	for _, v := range absLats {
		mu += v
	}
	mu /= float64(n)
	if mu == 0 {
		fmt.Println("theil: NULL")
		return
	}
	theil := 0.0
	for _, v := range absLats {
		ratio := v / mu
		theil += ratio * math.Log(ratio) // natural log (ln), NOT log2
	}
	theil /= float64(n)
	fmt.Printf("theil: %.6f\n", canonicalizeZero(theil))
}

func cmdCountryForecast() {
	db := openDB()
	defer db.Close()
	// Order rows by country_name ASC then id ASC (rowid); assign 1-indexed positions
	rows, err := db.Query("SELECT latitude FROM countries ORDER BY name ASC, rowid ASC")
	if err != nil {
		fmt.Fprintln(os.Stderr, "query error:", err)
		os.Exit(1)
	}
	defer rows.Close()
	var lats []float64
	for rows.Next() {
		var v float64
		rows.Scan(&v)
		lats = append(lats, v)
	}
	n := len(lats)
	if n < 2 {
		fmt.Println("forecast: NULL")
		return
	}
	// OLS linear regression: x = 1-indexed position (1..N), y = latitude
	// slope = (N*sum_xy - sum_x*sum_y) / (N*sum_x2 - sum_x^2)
	// intercept = (sum_y - slope*sum_x) / N
	sumX := 0.0
	sumY := 0.0
	sumXY := 0.0
	sumX2 := 0.0
	fn := float64(n)
	for i, y := range lats {
		x := float64(i + 1) // 1-indexed
		sumX += x
		sumY += y
		sumXY += x * y
		sumX2 += x * x
	}
	denom := fn*sumX2 - sumX*sumX
	if denom == 0 {
		fmt.Println("forecast: NULL")
		return
	}
	slope := (fn*sumXY - sumX*sumY) / denom
	intercept := (sumY - slope*sumX) / fn
	// Forecast at position N+1
	forecast := intercept + slope*float64(n+1)
	fmt.Printf("forecast: %.6f\n", canonicalizeZero(forecast))
}

func cmdCountryHHI() {
	db := openDB()
	defer db.Close()
	rows, err := db.Query("SELECT region FROM countries")
	if err != nil {
		fmt.Fprintln(os.Stderr, "query error:", err)
		os.Exit(1)
	}
	defer rows.Close()
	regionCounts := map[string]int{}
	total := 0
	for rows.Next() {
		var region string
		rows.Scan(&region)
		regionCounts[region]++
		total++
	}
	k := len(regionCounts)
	if total < 2 || k < 2 {
		fmt.Println("insufficient_data")
		os.Exit(1)
	}
	rawHHI := 0.0
	for _, count := range regionCounts {
		s := float64(count) / float64(total)
		rawHHI += s * s
	}
	// Normalized HHI = (rawHHI - 1/K) / (1 - 1/K)
	normHHI := (rawHHI - 1.0/float64(k)) / (1.0 - 1.0/float64(k))
	fmt.Printf("hhi=%.8f\n", canonicalizeZero(normHHI))
}

// bankersRound rounds x to `places` decimal places using round-half-to-even (banker's rounding).
func bankersRound(x float64, places int) float64 {
	shift := math.Pow(10, float64(places))
	// Multiply, then apply banker's rounding
	shifted := x * shift
	floor := math.Floor(shifted)
	frac := shifted - floor
	var rounded float64
	if frac < 0.5 {
		rounded = floor
	} else if frac > 0.5 {
		rounded = floor + 1
	} else {
		// Exactly 0.5: round to even
		if math.Mod(floor, 2) == 0 {
			rounded = floor
		} else {
			rounded = floor + 1
		}
	}
	return canonicalizeZero(rounded / shift)
}

func cmdCountryChainDual() {
	db := openDB()
	defer db.Close()

	type auditRow struct {
		seq     int
		code    string
		lat     float64
		lon     float64
		entHash string
	}

	rows, err := db.Query("SELECT seq, country_code, latitude, longitude, entry_hash FROM audit_log ORDER BY seq ASC")
	if err != nil {
		fmt.Fprintln(os.Stderr, "query error:", err)
		os.Exit(1)
	}
	defer rows.Close()

	var entries []auditRow
	for rows.Next() {
		var r auditRow
		rows.Scan(&r.seq, &r.code, &r.lat, &r.lon, &r.entHash)
		entries = append(entries, r)
	}

	zeros := strings.Repeat("0", 64)
	if len(entries) == 0 {
		fmt.Printf("fwd=%s\nrev=%s\n", zeros, zeros)
		return
	}

	// Forward: entry_hash of the row with maximum seq
	fwdHash := entries[len(entries)-1].entHash

	// Reverse: iterate descending, HMAC key = "wb-tracker-reverse-2026"
	revKey := []byte("wb-tracker-reverse-2026")
	prevRevHash := zeros
	for i := len(entries) - 1; i >= 0; i-- {
		r := entries[i]
		msg := fmt.Sprintf("%d|%s|%.6f|%.6f|%s", r.seq, r.code, r.lat, r.lon, prevRevHash)
		mac := hmac.New(sha256.New, revKey)
		mac.Write([]byte(msg))
		prevRevHash = fmt.Sprintf("%x", mac.Sum(nil))
	}

	fmt.Printf("fwd=%s\nrev=%s\n", fwdHash, prevRevHash)
}

func cmdCountryCovar() {
	db := openDB()
	defer db.Close()
	rows, err := db.Query("SELECT latitude, longitude FROM countries")
	if err != nil {
		fmt.Fprintln(os.Stderr, "query error:", err)
		os.Exit(1)
	}
	defer rows.Close()
	var lats []float64
	var lons []float64
	for rows.Next() {
		var lat, lon float64
		rows.Scan(&lat, &lon)
		lats = append(lats, lat)
		lons = append(lons, lon)
	}
	n := len(lats)
	if n < 2 {
		fmt.Println("covar: NULL")
		return
	}
	// population covariance: divide by N (NOT N-1)
	meanLat := 0.0
	meanLon := 0.0
	for i := range lats {
		meanLat += lats[i]
		meanLon += lons[i]
	}
	meanLat /= float64(n)
	meanLon /= float64(n)
	covar := 0.0
	for i := range lats {
		covar += (lats[i] - meanLat) * (lons[i] - meanLon)
	}
	covar /= float64(n)
	fmt.Printf("covar: %.8f\n", canonicalizeZero(covar))
}

func cmdCountryEWMA() {
	db := openDB()
	defer db.Close()
	// Order by code ASC — seed from first (smallest code)
	rows, err := db.Query("SELECT latitude FROM countries ORDER BY code ASC")
	if err != nil {
		fmt.Fprintln(os.Stderr, "query error:", err)
		os.Exit(1)
	}
	defer rows.Close()
	var lats []float64
	for rows.Next() {
		var v float64
		rows.Scan(&v)
		lats = append(lats, v)
	}
	n := len(lats)
	if n == 0 {
		fmt.Println("ewma: NULL")
		return
	}
	alpha := 0.3
	// Seed with first (smallest code), apply HALF_EVEN round to 6dp after each step
	ewma := bankersRound6(lats[0])
	for i := 1; i < n; i++ {
		raw := alpha*lats[i] + (1-alpha)*ewma
		ewma = bankersRound6(raw)
	}
	fmt.Printf("ewma: %.6f\n", ewma)
}

func cmdCountryWeightedStats() {
	db := openDB()
	defer db.Close()

	rows, err := db.Query("SELECT name, code, latitude FROM countries ORDER BY name ASC, code ASC")
	if err != nil {
		fmt.Fprintln(os.Stderr, "query error:", err)
		os.Exit(1)
	}
	defer rows.Close()

	type row struct {
		name string
		code string
		lat  float64
	}
	var entries []row
	for rows.Next() {
		var r row
		rows.Scan(&r.name, &r.code, &r.lat)
		entries = append(entries, r)
	}

	n := len(entries)
	if n < 2 {
		fmt.Println("insufficient_data")
		os.Exit(1)
	}

	fn := float64(n)
	weightedSum := 0.0
	sumLat := 0.0
	for i, e := range entries {
		pos := float64(i + 1)
		weightedSum += pos * e.lat
		sumLat += e.lat
	}
	denom := fn * (fn + 1) / 2
	W := weightedSum / denom
	M := sumLat / fn

	var momentum float64
	if M == 0 {
		momentum = 0.0
	} else {
		momentum = W / M
	}

	// Use banker's rounding for all output values
	Wf := bankersRound(W, 6)
	Mf := bankersRound(M, 6)
	momf := bankersRound(momentum, 6)

	fmt.Printf("weighted_mean=%.6f\nmean=%.6f\nmomentum=%.6f\n", Wf, Mf, momf)
}

// bankersRound8 rounds x to 8 decimal places using HALF_EVEN (banker's rounding).
func bankersRound8(x float64) float64 {
	factor := 1e8
	scaled := x * factor
	floor := math.Floor(scaled)
	frac := scaled - floor
	const eps = 1e-9
	if math.Abs(frac-0.5) < eps {
		// Exactly half: round to even
		if int64(floor)%2 == 0 {
			return canonicalizeZero(floor / factor)
		}
		return canonicalizeZero((floor + 1) / factor)
	}
	return canonicalizeZero(math.Round(scaled) / factor)
}

func cmdCountryPearson() {
	db := openDB()
	defer db.Close()
	rows, err := db.Query("SELECT latitude FROM countries ORDER BY code ASC")
	if err != nil {
		fmt.Fprintln(os.Stderr, "query error:", err)
		os.Exit(1)
	}
	defer rows.Close()
	var lats []float64
	for rows.Next() {
		var v float64
		rows.Scan(&v)
		lats = append(lats, v)
	}
	n := len(lats)
	if n < 2 {
		fmt.Println("pearson: NULL")
		return
	}
	fn := float64(n)
	sumX := 0.0
	sumY := 0.0
	sumXY := 0.0
	sumX2 := 0.0
	sumY2 := 0.0
	for i, y := range lats {
		x := float64(i + 1)
		sumX += x
		sumY += y
		sumXY += x * y
		sumX2 += x * x
		sumY2 += y * y
	}
	denomA := fn*sumX2 - sumX*sumX
	denomB := fn*sumY2 - sumY*sumY
	denom := denomA * denomB
	if denom <= 0 {
		fmt.Println("pearson: NULL")
		return
	}
	r := (fn*sumXY - sumX*sumY) / math.Sqrt(denom)
	result := bankersRound8(r)
	fmt.Printf("pearson: %.8f\n", result)
}

func cmdCountryAutocorr() {
	db := openDB()
	defer db.Close()
	rows, err := db.Query("SELECT latitude FROM countries ORDER BY code ASC")
	if err != nil {
		fmt.Fprintln(os.Stderr, "query error:", err)
		os.Exit(1)
	}
	defer rows.Close()
	var lats []float64
	for rows.Next() {
		var v float64
		rows.Scan(&v)
		lats = append(lats, v)
	}
	n := len(lats)
	if n < 2 {
		fmt.Println("autocorr: NULL")
		return
	}
	fn := float64(n)
	mean := 0.0
	for _, v := range lats {
		mean += v
	}
	mean /= fn
	popVar := 0.0
	for _, v := range lats {
		d := v - mean
		popVar += d * d
	}
	popVar /= fn
	if popVar == 0 {
		fmt.Println("autocorr: NULL")
		return
	}
	cov1 := 0.0
	for t := 0; t < n-1; t++ {
		cov1 += (lats[t] - mean) * (lats[t+1] - mean)
	}
	cov1 /= fn
	autocorr := cov1 / popVar
	result := bankersRound8(autocorr)
	fmt.Printf("autocorr: %.8f\n", result)
}

func cmdCountryMAD() {
	db := openDB()
	defer db.Close()
	rows, err := db.Query("SELECT latitude FROM countries")
	if err != nil {
		fmt.Fprintln(os.Stderr, "query error:", err)
		os.Exit(1)
	}
	defer rows.Close()
	var lats []float64
	for rows.Next() {
		var v float64
		rows.Scan(&v)
		lats = append(lats, v)
	}
	n := len(lats)
	if n < 2 {
		fmt.Println("mad: NULL")
		return
	}
	sorted := make([]float64, n)
	copy(sorted, lats)
	sort.Float64s(sorted)
	// nearest-rank median: rank = ceil(0.5 * N), index = rank - 1
	medRank := int(math.Ceil(0.5 * float64(n)))
	median := sorted[medRank-1]
	// compute absolute deviations
	devs := make([]float64, n)
	for i, v := range lats {
		devs[i] = math.Abs(v - median)
	}
	sort.Float64s(devs)
	// median of deviations using same nearest-rank rule
	mad := devs[medRank-1]
	fmt.Printf("mad: %.8f\n", mad)
}

func cmdCountryHoover() {
	db := openDB()
	defer db.Close()
	rows, err := db.Query("SELECT latitude FROM countries")
	if err != nil {
		fmt.Fprintln(os.Stderr, "query error:", err)
		os.Exit(1)
	}
	defer rows.Close()
	var lats []float64
	for rows.Next() {
		var v float64
		rows.Scan(&v)
		lats = append(lats, v)
	}
	n := len(lats)
	if n < 2 {
		fmt.Println("hoover: NULL")
		return
	}
	// Shift to strictly positive: shifted_i = lat_i - min(lats) + 1.0
	minLat := lats[0]
	for _, v := range lats {
		if v < minLat {
			minLat = v
		}
	}
	shifted := make([]float64, n)
	totalSum := 0.0
	for i, v := range lats {
		shifted[i] = v - minLat + 1.0
		totalSum += shifted[i]
	}
	if totalSum == 0 {
		fmt.Println("hoover: NULL")
		return
	}
	// Population mean
	meanShifted := totalSum / float64(n)
	// Hoover = sum(|x_i - mean|) / (2 * sum(x_i))
	absDevSum := 0.0
	for _, v := range shifted {
		absDevSum += math.Abs(v - meanShifted)
	}
	hoover := absDevSum / (2.0 * totalSum)
	fmt.Printf("hoover: %.8f\n", hoover)
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "usage: wb-tracker <command> [args]")
		os.Exit(1)
	}
	switch os.Args[1] {
	case "init":
		cmdInit()
	case "fetch-country":
		if len(os.Args) < 3 {
			fmt.Fprintln(os.Stderr, "usage: wb-tracker fetch-country <code>")
			os.Exit(1)
		}
		cmdFetchCountry(os.Args[2])
	case "list-countries":
		cmdListCountries(os.Args[2:])
	case "country-stats":
		cmdCountryStats()
	case "country-zscores":
		cmdCountryZscores(os.Args[2:])
	case "audit-verify":
		cmdAuditVerify()
	case "country-rank":
		if len(os.Args) < 3 {
			fmt.Fprintln(os.Stderr, "usage: wb-tracker country-rank <code>")
			os.Exit(1)
		}
		cmdCountryRank(os.Args[2])
	case "audit-stats":
		cmdAuditStats()
	case "audit-baseline-window":
		cmdAuditBaselineWindow()
	case "country-gini":
		cmdCountryGini()
	case "country-entropy":
		cmdCountryEntropy()
	case "country-atkinson":
		cmdCountryAtkinson()
	case "country-theil":
		cmdCountryTheil()
	case "country-forecast":
		cmdCountryForecast()
	case "country-hhi":
		cmdCountryHHI()
	case "country-chain-dual":
		cmdCountryChainDual()
	case "country-weighted-stats":
		cmdCountryWeightedStats()
	case "country-covar":
		cmdCountryCovar()
	case "country-ewma":
		cmdCountryEWMA()
	case "country-pearson":
		cmdCountryPearson()
	case "country-autocorr":
		cmdCountryAutocorr()
	case "country-mad":
		cmdCountryMAD()
	case "country-hoover":
		cmdCountryHoover()
	default:
		fmt.Fprintln(os.Stderr, "unknown command:", os.Args[1])
		os.Exit(1)
	}
}
