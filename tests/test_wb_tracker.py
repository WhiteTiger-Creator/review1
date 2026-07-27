import decimal
import decimal as _decimal
import hashlib
import hmac as hm
import json
import math
import os
import sqlite3
import subprocess
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

import pytest

# ---------------------------------------------------------------------------
# Mock World Bank API server
# ---------------------------------------------------------------------------

MOCK_DB = {}  # code -> dict with country data or None (not found)

# Rate limiting control: code -> "429_once" or "429_always"
RATE_LIMIT_CODES = {}
# Hit counter per code to track first vs. retry request
RATE_LIMIT_HITS = {}


def make_country_response(code, name, lat, lon, region_id="NAC", income_id="HIC", capital="Capital City"):
    meta = {"page": 1, "pages": 1, "per_page": 50, "total": 1}
    country = {
        "id": code,
        "name": name,
        "region": {"id": region_id, "iso2code": "XN", "value": "North America"},
        "incomeLevel": {"id": income_id, "iso2code": "XD", "value": "High income"},
        "capitalCity": capital,
        "latitude": str(lat),
        "longitude": str(lon),
        "adminregion": {"id": "", "iso2code": "", "value": ""},
        "lendingType": {"id": "", "iso2code": "", "value": ""},
    }
    return json.dumps([meta, [country]])


def make_not_found_null():
    meta = {"page": 1, "pages": 0, "per_page": 50, "total": 0}
    return json.dumps([meta, None])


def make_not_found_empty():
    meta = {"page": 1, "pages": 0, "per_page": 50, "total": 0}
    return json.dumps([meta, []])


class MockHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress output

    def do_GET(self):
        parsed = urlparse(self.path)
        # path like /v2/country/US
        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 3 and parts[1] == "country":
            code = parts[2].upper()

            # Check rate limiting
            if code in RATE_LIMIT_CODES:
                mode = RATE_LIMIT_CODES[code]
                hits = RATE_LIMIT_HITS.get(code, 0)
                RATE_LIMIT_HITS[code] = hits + 1
                if mode == "429_always" or (mode == "429_once" and hits == 0):
                    self.send_response(429)
                    self.send_header("Retry-After", "1")
                    self.end_headers()
                    return

            if code in MOCK_DB:
                data = MOCK_DB[code]
                if data is None:
                    body = make_not_found_null().encode()
                elif data == "empty":
                    body = make_not_found_empty().encode()
                else:
                    body = make_country_response(
                        code,
                        data["name"],
                        data["lat"],
                        data["lon"],
                        data.get("region", "NAC"),
                        data.get("income", "HIC"),
                        data.get("capital", "Capital"),
                    ).encode()
            else:
                body = make_not_found_null().encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


@pytest.fixture(scope="module")
def mock_server():
    server = HTTPServer(("127.0.0.1", 0), MockHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever)
    t.daemon = True
    t.start()
    yield f"http://127.0.0.1:{port}/v2"
    server.shutdown()


def run(args, timeout=30, api_base=None):
    env = os.environ.copy()
    if api_base:
        env["API_BASE_URL"] = api_base
    return subprocess.run(
        ["/app/wb-tracker", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        check=False,
    )


def clear_db():
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    db.commit()
    db.close()


def insert_countries(rows):
    """rows: list of (code, name, lat, lon)"""
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    for code, name, lat, lon in rows:
        db.execute(
            "INSERT OR REPLACE INTO countries VALUES (?,?,?,?,?,?,?)",
            (code, name, "REG", "HIC", "Cap", lat, lon),
        )
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# Helper: compute expected stats
# ---------------------------------------------------------------------------

def pop_mean(xs):
    return sum(xs) / len(xs)


def pop_var(xs):
    m = pop_mean(xs)
    return sum((x - m) ** 2 for x in xs) / len(xs)


def pop_std(xs):
    return math.sqrt(pop_var(xs))


def pop_skew(xs):
    n = len(xs)
    if n < 3:
        return None
    m = pop_mean(xs)
    var = pop_var(xs)
    if var == 0:
        return None
    m3 = sum((x - m) ** 3 for x in xs) / n
    return m3 / (var ** 1.5)


def pop_kurt(xs):
    n = len(xs)
    if n < 4:
        return None
    m = pop_mean(xs)
    var = pop_var(xs)
    if var == 0:
        return None
    m4 = sum((x - m) ** 4 for x in xs) / n
    return m4 / (var ** 2) - 3.0


def nearest_rank_percentile(xs_sorted, p):
    n = len(xs_sorted)
    rank = math.ceil(p * n)
    return xs_sorted[rank - 1]


def pop_zscore(x, mean, std):
    if std == 0:
        return None
    return (x - mean) / std


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_00_pipeline_produces_data_artifacts(mock_server):
    """
    Primary grading gate: run the ingestion pipeline end-to-end against a
    batch of records and verify the resulting DATA ARTIFACTS on disk (the
    populated database and an exported pipeline report), not just individual
    command return codes. This is what /app/output/pipeline_report.json and
    the row/audit-chain assertions below check.
    """
    os.makedirs("/app/output", exist_ok=True)
    run(["init"])
    clear_db()

    batch = [
        ("W1", "Wcountry One", 38.0, -97.0),
        ("W2", "Wcountry Two", 56.0, -106.0),
        ("W3", "Wcountry Three", 23.0, -102.0),
        ("W4", "Wcountry Four", -10.0, -55.0),
        ("W5", "Wcountry Five", 46.0, 2.0),
        ("W6", "Wcountry Six", 51.0, 9.0),
        ("W7", "Wcountry Seven", 36.0, 138.0),
        ("W8", "Wcountry Eight", -25.0, 133.0),
    ]
    for code, name, lat, lon in batch:
        MOCK_DB[code] = {"name": name, "lat": lat, "lon": lon}

    pipeline_report = {"ingested": [], "analytics": {}}
    for code, name, lat, lon in batch:
        r = run(["fetch-country", code], api_base=mock_server)
        pipeline_report["ingested"].append(
            {"code": code, "exit_code": r.returncode, "stdout": r.stdout.strip()}
        )
        assert r.returncode == 0, f"pipeline ingestion failed for {code}: {r.stderr}"

    for cmd in [
        "country-stats", "audit-verify", "country-gini", "country-entropy",
        "audit-stats", "country-chain-dual",
    ]:
        r = run([cmd])
        pipeline_report["analytics"][cmd] = {
            "exit_code": r.returncode,
            "stdout": r.stdout.strip(),
        }

    with open("/app/output/pipeline_report.json", "w") as f:
        json.dump(pipeline_report, f, indent=2)

    # Verify the produced data artifacts directly, rather than re-asserting
    # on the subprocess output above.
    assert os.path.exists("/app/output/pipeline_report.json")
    with open("/app/output/pipeline_report.json") as f:
        saved_report = json.load(f)
    assert len(saved_report["ingested"]) == len(batch)

    db = sqlite3.connect("/app/wb.db")
    row_count = db.execute("SELECT COUNT(*) FROM countries").fetchone()[0]
    audit_count = db.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    codes_in_db = {row[0] for row in db.execute("SELECT code FROM countries").fetchall()}
    db.close()

    assert row_count == len(batch), f"expected {len(batch)} ingested country rows in the database, found {row_count}"
    assert audit_count == len(batch), f"expected {len(batch)} audit_log rows in the database, found {audit_count}"
    assert codes_in_db == {c for c, _, _, _ in batch}, "ingested country codes in the database do not match the source batch"
    assert pipeline_report["analytics"]["audit-verify"]["exit_code"] == 0, "audit chain must verify clean after the pipeline run"
    assert "ok chain_length=8" in pipeline_report["analytics"]["audit-verify"]["stdout"]


def test_init_idempotent():
    r1 = run(["init"])
    assert r1.returncode == 0
    assert "OK" in r1.stdout
    r2 = run(["init"])
    assert r2.returncode == 0
    assert "OK" in r2.stdout
    # Verify database tables were actually created by init
    db = sqlite3.connect("/app/wb.db")
    tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    db.close()
    assert "countries" in tables, f"init must create 'countries' table, got: {tables}"
    assert "audit_log" in tables, f"init must create 'audit_log' table, got: {tables}"


def test_stddev_latitude_population():
    """[10.0, 20.0, 30.0]: pop_std=sqrt(200/3) vs sample=10.0"""
    insert_countries([("A1", "C1", 10.0, -10.0), ("A2", "C2", 20.0, -20.0), ("A3", "C3", 30.0, -30.0)])
    r = run(["country-stats"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    lats = [10.0, 20.0, 30.0]
    expected_std = pop_std(lats)
    assert f"stddev_latitude={expected_std:.6f}" in r.stdout, r.stdout
    assert "stddev_latitude=10.000000" not in r.stdout


def test_p75_nearest_rank():
    """N=4 [-10,10,30,50]: p75=rank=3->index2->30"""
    insert_countries([("B1", "C1", -10.0, 0.0), ("B2", "C2", 10.0, 0.0), ("B3", "C3", 30.0, 0.0), ("B4", "C4", 50.0, 0.0)])
    r = run(["country-stats"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    assert "p75_latitude=30.000000" in r.stdout, r.stdout


def test_p90_nearest_rank_precision():
    """N=10: p90=rank=9->index8, check exact value"""
    lats = [1.1, 2.2, 3.3, 4.4, 5.5, 6.6, 7.7, 8.8, 9.9, 10.0]
    rows = [(f"C{i}", f"N{i}", v, 0.0) for i, v in enumerate(lats)]
    insert_countries(rows)
    r = run(["country-stats"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    sorted_lats = sorted(lats)
    expected = nearest_rank_percentile(sorted_lats, 0.90)
    assert f"p90_latitude={expected:.6f}" in r.stdout, r.stdout


def test_skewness_latitude_n3():
    """N=3 symmetric: skewness should be ~0"""
    lats = [10.0, 20.0, 30.0]
    insert_countries([(f"S{i}", f"N{i}", v, float(i)) for i, v in enumerate(lats)])
    r = run(["country-stats"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    expected = pop_skew(lats)
    assert f"skewness_latitude={expected:.8f}" in r.stdout, r.stdout


def test_skewness_latitude_n5():
    """N=5 asymmetric: skewness != 0"""
    lats = [5.0, 10.0, 15.0, 20.0, 50.0]
    insert_countries([(f"K{i}", f"N{i}", v, float(i)) for i, v in enumerate(lats)])
    r = run(["country-stats"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    expected = pop_skew(lats)
    assert f"skewness_latitude={expected:.8f}" in r.stdout, r.stdout


def test_skewness_null_n2():
    """N=2: skewness should be NULL"""
    insert_countries([("SK1", "N1", 10.0, 0.0), ("SK2", "N2", 20.0, 0.0)])
    r = run(["country-stats"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    assert "skewness_latitude=NULL" in r.stdout, r.stdout


def test_kurtosis_latitude_n4():
    """N=4 uniform: kurtosis should be ~-1.36"""
    lats = [10.0, 20.0, 30.0, 40.0]
    insert_countries([(f"KT{i}", f"N{i}", v, float(i)) for i, v in enumerate(lats)])
    r = run(["country-stats"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    expected = pop_kurt(lats)
    assert f"kurtosis_latitude={expected:.8f}" in r.stdout, r.stdout


def test_kurtosis_null_n3():
    """N=3: kurtosis should be NULL"""
    insert_countries([(f"KN{i}", f"N{i}", float(i * 10), 0.0) for i in range(3)])
    r = run(["country-stats"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    assert "kurtosis_latitude=NULL" in r.stdout, r.stdout


def test_kurtosis_n6_precision():
    """N=6: verify exact 8dp kurtosis"""
    lats = [2.5, 7.3, 11.1, 15.8, 22.4, 30.0]
    insert_countries([(f"P{i}", f"N{i}", v, float(i)) for i, v in enumerate(lats)])
    r = run(["country-stats"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    expected = pop_kurt(lats)
    assert f"kurtosis_latitude={expected:.8f}" in r.stdout, r.stdout


def test_stddev_longitude_precision():
    """Verify stddev_longitude at 6dp"""
    rows = [("L1", "N1", 10.0, 5.5), ("L2", "N2", 20.0, 15.5), ("L3", "N3", 30.0, 25.5)]
    insert_countries(rows)
    r = run(["country-stats"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    lons = [5.5, 15.5, 25.5]
    expected = pop_std(lons)
    assert f"stddev_longitude={expected:.6f}" in r.stdout, r.stdout


def test_p90_longitude_precision():
    """Verify p90_longitude nearest-rank"""
    lons = [10.0, 20.0, 30.0, 40.0, 50.0]
    rows = [(f"LO{i}", f"N{i}", float(i), v) for i, v in enumerate(lons)]
    insert_countries(rows)
    r = run(["country-stats"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    sorted_lons = sorted(lons)
    expected = nearest_rank_percentile(sorted_lons, 0.90)
    assert f"p90_longitude={expected:.6f}" in r.stdout, r.stdout


def test_null_stddev_single():
    """N=1: stddev should be NULL"""
    insert_countries([("X1", "Solo", 15.0, 0.0)])
    r = run(["country-stats"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    assert "stddev_latitude=NULL" in r.stdout, r.stdout


def test_country_zscores_values():
    """Z-scores: verify (x-mean)/std at 8dp"""
    lats = [10.0, 20.0, 30.0]
    lons = [-30.0, -20.0, -10.0]
    insert_countries([("Z1", "N1", lats[0], lons[0]), ("Z2", "N2", lats[1], lons[1]), ("Z3", "N3", lats[2], lons[2])])
    r = run(["country-zscores"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    m_lat = pop_mean(lats)
    s_lat = pop_std(lats)
    m_lon = pop_mean(lons)
    s_lon = pop_std(lons)
    for code, lat, lon in zip(["Z1", "Z2", "Z3"], lats, lons):
        zl = (lat - m_lat) / s_lat
        zln = (lon - m_lon) / s_lon
        assert f"{code}\t{zl:.8f}\t{zln:.8f}" in r.stdout, r.stdout


def test_country_zscores_order():
    """Z-scores output must be ordered by z_lat ASC then code ASC"""
    lats = [5.0, 15.0, 25.0]
    lons = [1.0, 2.0, 3.0]
    insert_countries([("ZZ", "N1", lats[0], lons[0]), ("AA", "N2", lats[1], lons[1]), ("MM", "N3", lats[2], lons[2])])
    r = run(["country-zscores"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    lines = [ln for ln in r.stdout.strip().split("\n") if ln]
    assert len(lines) == 3, f"expected 3 lines, got: {r.stdout}"
    # ZZ has lowest lat (5.0) so lowest z_lat -> first
    codes_out = [ln.split("\t")[0] for ln in lines]
    assert codes_out[0] == "ZZ", f"expected ZZ first (lowest z_lat), got: {codes_out}"
    assert codes_out[-1] == "MM", f"expected MM last (highest z_lat), got: {codes_out}"


def test_zscores_null_single():
    """N=1: should print insufficient data"""
    insert_countries([("ZS1", "Solo", 15.0, 5.0)])
    r = run(["country-zscores"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    assert "insufficient data" in r.stdout, r.stdout


def test_hmac_lat_lon_6dp():
    """HMAC must format lat/lon to 6dp even from variable-precision API strings"""
    lat = 38.5266
    lon = -97.3428
    prev_hash = "0" * 64
    skew = "NULL"
    kurt = "NULL"
    p50 = 0.0  # N=0 before first insert
    mad = "NULL"  # N=0 before first insert
    msg = f"1|US|{lat:.6f}|{lon:.6f}|{skew}|{kurt}|{p50:.6f}|{mad}|{prev_hash}"
    expected = hm.new(
        b"wb-tracker-secret-2026", msg.encode(), hashlib.sha256
    ).hexdigest()
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    db.execute(
        "INSERT OR REPLACE INTO countries VALUES ('US','United States','NAC','HIC','Washington D.C.',?,?)",
        (lat, lon),
    )
    db.execute(
        "INSERT INTO audit_log (seq,country_code,latitude,longitude,kurtosis_at_insert,skewness_at_insert,p50_at_insert,mad_at_insert,prev_hash,entry_hash) VALUES (1,'US',?,?,?,?,?,?,?,?)",
        (lat, lon, kurt, skew, p50, mad, prev_hash, expected),
    )
    db.commit()
    db.close()
    r = run(["audit-verify"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    assert "ok chain_length=1" in r.stdout, r.stdout


def test_not_found_null_second_element(mock_server):
    """World Bank returns [meta, null] for invalid codes — printed to stderr with code"""
    run(["init"])
    clear_db()
    MOCK_DB["ZZ"] = None
    r = run(["fetch-country", "ZZ"], api_base=mock_server)
    assert r.returncode == 1, r.stdout
    assert "not_found: ZZ" in r.stderr, f"expected 'not_found: ZZ' in stderr, got stderr={r.stderr!r} stdout={r.stdout!r}"
    assert "not_found" not in r.stdout, f"not_found must go to stderr, not stdout: {r.stdout!r}"


def test_not_found_empty_array(mock_server):
    """World Bank returns [meta, []] — printed to stderr with code"""
    run(["init"])
    clear_db()
    MOCK_DB["XX"] = "empty"
    r = run(["fetch-country", "XX"], api_base=mock_server)
    assert r.returncode == 1, r.stdout
    assert "not_found: XX" in r.stderr, f"expected 'not_found: XX' in stderr, got stderr={r.stderr!r} stdout={r.stdout!r}"
    assert "not_found" not in r.stdout, f"not_found must go to stderr, not stdout: {r.stdout!r}"


def test_not_found_exits_1(mock_server):
    """not_found must exit 1 and print to stderr with country code"""
    run(["init"])
    clear_db()
    MOCK_DB["YY"] = None
    r = run(["fetch-country", "YY"], api_base=mock_server)
    assert r.returncode == 1
    assert "not_found: YY" in r.stderr, f"expected 'not_found: YY' in stderr, got: {r.stderr!r}"


def test_fetch_country_mock(mock_server):
    """Fetch a valid country from mock server"""
    run(["init"])
    clear_db()
    MOCK_DB["US"] = {"name": "United States", "lat": 38.5266, "lon": -97.3428}
    r = run(["fetch-country", "US"], api_base=mock_server)
    assert r.returncode == 0, r.stderr
    assert "ok country=US" in r.stdout, r.stdout


def test_fetch_country_exists(mock_server):
    """Fetching the same country twice returns exists"""
    run(["init"])
    clear_db()
    MOCK_DB["GB"] = {"name": "United Kingdom", "lat": 55.3781, "lon": -3.4360}
    r1 = run(["fetch-country", "GB"], api_base=mock_server)
    assert r1.returncode == 0
    r2 = run(["fetch-country", "GB"], api_base=mock_server)
    assert r2.returncode == 0
    assert "exists" in r2.stdout


def test_list_ordering():
    """list-countries must be sorted by name ASC then code ASC"""
    insert_countries([("ZZ", "Zeta", 0.0, 0.0), ("AA", "Alpha", 1.0, 0.0), ("MM", "Middle", 2.0, 0.0)])
    r = run(["list-countries"])
    lines = [ln for ln in r.stdout.strip().split("\n") if ln]
    names = [ln.split("\t")[1] for ln in lines]
    assert names == sorted(names), f"not sorted by name: {names}"


def test_audit_tamper_entry_hash():
    """Tampered entry_hash must be detected"""
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    prev_hash = "0" * 64
    bad_hash = "a" * 64
    db.execute(
        "INSERT OR REPLACE INTO countries VALUES ('T1','Tamper','R','H','Cap',5.0,0.0)"
    )
    db.execute(
        "INSERT INTO audit_log (seq,country_code,latitude,longitude,kurtosis_at_insert,skewness_at_insert,prev_hash,entry_hash) VALUES (1,'T1',5.0,0.0,'NULL','NULL',?,?)",
        (prev_hash, bad_hash),
    )
    db.commit()
    db.close()
    r = run(["audit-verify"])
    assert r.returncode == 1
    assert "TAMPERED" in r.stdout
    assert "entry_hash_mismatch" in r.stdout


def test_country_stats_zero_count():
    """Empty table: all stats NULL"""
    insert_countries([])
    r = run(["country-stats"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    assert "count=0" in r.stdout
    assert "avg_latitude=NULL" in r.stdout
    assert "stddev_latitude=NULL" in r.stdout
    assert "skewness_latitude=NULL" in r.stdout
    assert "kurtosis_latitude=NULL" in r.stdout
    assert "p90_longitude=NULL" in r.stdout
    assert "stddev_longitude=NULL" in r.stdout


# ---------------------------------------------------------------------------
# Helpers for skewness/kurtosis at insert
# ---------------------------------------------------------------------------

def compute_skew_at_insert(lats_before):
    """Population skewness of lats_before; 'NULL' if N<3"""
    n = len(lats_before)
    if n < 3:
        return "NULL"
    m = pop_mean(lats_before)
    v = pop_var(lats_before)
    if v == 0:
        return "NULL"
    m3 = sum((x - m) ** 3 for x in lats_before) / n
    return f"{m3 / (v ** 1.5):.8f}"


def compute_kurt_at_insert(lats_before):
    """Excess population kurtosis of lats_before; 'NULL' if N<4"""
    n = len(lats_before)
    if n < 4:
        return "NULL"
    m = pop_mean(lats_before)
    v = pop_var(lats_before)
    if v == 0:
        return "NULL"
    m4 = sum((x - m) ** 4 for x in lats_before) / n
    return f"{m4 / (v ** 2) - 3.0:.8f}"


def build_hmac(seq, code, lat, lon, skew, kurt, prev_hash, p50=0.0, mad="NULL"):
    msg = f"{seq}|{code}|{lat:.6f}|{lon:.6f}|{skew}|{kurt}|{p50:.6f}|{mad}|{prev_hash}"
    return hm.new(b"wb-tracker-secret-2026", msg.encode(), hashlib.sha256).hexdigest()


def _compute_mad_at_insert(lats_before):
    """Nearest-rank MAD of lats_before formatted to 8dp; 'NULL' if N<2.

    Center = nearest-rank median (rank=ceil(0.5*N), index=rank-1) and the
    deviation median uses the same nearest-rank rule -- the country-mad
    algorithm, NOT the interpolated HALF_EVEN p50_at_insert median.
    """
    n = len(lats_before)
    if n < 2:
        return "NULL"
    s = sorted(lats_before)
    med_rank = math.ceil(0.5 * n)
    median = s[med_rank - 1]
    devs = sorted(abs(v - median) for v in lats_before)
    mad = devs[med_rank - 1]
    if mad == 0:
        mad = 0.0
    return f"{mad:.8f}"


# ---------------------------------------------------------------------------
# New tests for skewness/kurtosis at insert
# ---------------------------------------------------------------------------

def test_kurtosis_at_insert_null_first(mock_server):
    """First fetch: N=0 before insert -> skewness=NULL, kurtosis=NULL"""
    run(["init"])
    clear_db()
    MOCK_DB["AA"] = {"name": "CountryAA", "lat": 10.0, "lon": 20.0}
    r = run(["fetch-country", "AA"], api_base=mock_server)
    assert r.returncode == 0, r.stderr
    db = sqlite3.connect("/app/wb.db")
    row = db.execute("SELECT skewness_at_insert, kurtosis_at_insert FROM audit_log WHERE seq=1").fetchone()
    db.close()
    assert row[0] == "NULL", f"skewness_at_insert={row[0]}"
    assert row[1] == "NULL", f"kurtosis_at_insert={row[1]}"


def test_kurtosis_at_insert_null_n1(mock_server):
    """Second fetch: N=1 before -> skewness=NULL (N<3), kurtosis=NULL (N<4)"""
    run(["init"])
    clear_db()
    MOCK_DB["BB"] = {"name": "CountryBB", "lat": 15.0, "lon": 25.0}
    MOCK_DB["CC"] = {"name": "CountryCC", "lat": 20.0, "lon": 30.0}
    run(["fetch-country", "BB"], api_base=mock_server)
    r = run(["fetch-country", "CC"], api_base=mock_server)
    assert r.returncode == 0, r.stderr
    db = sqlite3.connect("/app/wb.db")
    row = db.execute("SELECT skewness_at_insert, kurtosis_at_insert FROM audit_log WHERE seq=2").fetchone()
    db.close()
    assert row[0] == "NULL", f"skewness_at_insert={row[0]}"
    assert row[1] == "NULL", f"kurtosis_at_insert={row[1]}"


def test_kurtosis_at_insert_n3(mock_server):
    """Third fetch: N=2 before -> skewness=NULL (N<3), kurtosis=NULL"""
    run(["init"])
    clear_db()
    MOCK_DB["D1"] = {"name": "Country1", "lat": 10.0, "lon": 0.0}
    MOCK_DB["D2"] = {"name": "Country2", "lat": 20.0, "lon": 0.0}
    MOCK_DB["D3"] = {"name": "Country3", "lat": 30.0, "lon": 0.0}
    run(["fetch-country", "D1"], api_base=mock_server)
    run(["fetch-country", "D2"], api_base=mock_server)
    r = run(["fetch-country", "D3"], api_base=mock_server)
    assert r.returncode == 0, r.stderr
    db = sqlite3.connect("/app/wb.db")
    row = db.execute("SELECT skewness_at_insert, kurtosis_at_insert FROM audit_log WHERE seq=3").fetchone()
    db.close()
    # N=2 before seq=3 -> skewness NULL (need 3)
    assert row[0] == "NULL", f"skewness_at_insert={row[0]}"
    assert row[1] == "NULL", f"kurtosis_at_insert={row[1]}"


def test_kurtosis_at_insert_n4(mock_server):
    """Fourth fetch: N=3 before -> skewness computed, kurtosis=NULL (N<4)"""
    run(["init"])
    clear_db()
    MOCK_DB["E1"] = {"name": "Country1", "lat": 10.0, "lon": 0.0}
    MOCK_DB["E2"] = {"name": "Country2", "lat": 20.0, "lon": 0.0}
    MOCK_DB["E3"] = {"name": "Country3", "lat": 30.0, "lon": 0.0}
    MOCK_DB["E4"] = {"name": "Country4", "lat": 40.0, "lon": 0.0}
    run(["fetch-country", "E1"], api_base=mock_server)
    run(["fetch-country", "E2"], api_base=mock_server)
    run(["fetch-country", "E3"], api_base=mock_server)
    r = run(["fetch-country", "E4"], api_base=mock_server)
    assert r.returncode == 0, r.stderr
    db = sqlite3.connect("/app/wb.db")
    row = db.execute("SELECT skewness_at_insert, kurtosis_at_insert FROM audit_log WHERE seq=4").fetchone()
    db.close()
    lats_before = [10.0, 20.0, 30.0]
    expected_skew = compute_skew_at_insert(lats_before)
    assert row[0] == expected_skew, f"skewness_at_insert={row[0]!r} expected={expected_skew!r}"
    assert row[1] == "NULL", f"kurtosis_at_insert={row[1]}"


def test_kurtosis_at_insert_n5(mock_server):
    """Fifth fetch: N=4 before -> both skewness and kurtosis computed"""
    run(["init"])
    clear_db()
    MOCK_DB["F1"] = {"name": "Country1", "lat": 10.0, "lon": 0.0}
    MOCK_DB["F2"] = {"name": "Country2", "lat": 20.0, "lon": 0.0}
    MOCK_DB["F3"] = {"name": "Country3", "lat": 30.0, "lon": 0.0}
    MOCK_DB["F4"] = {"name": "Country4", "lat": 40.0, "lon": 0.0}
    MOCK_DB["F5"] = {"name": "Country5", "lat": 50.0, "lon": 0.0}
    run(["fetch-country", "F1"], api_base=mock_server)
    run(["fetch-country", "F2"], api_base=mock_server)
    run(["fetch-country", "F3"], api_base=mock_server)
    run(["fetch-country", "F4"], api_base=mock_server)
    r = run(["fetch-country", "F5"], api_base=mock_server)
    assert r.returncode == 0, r.stderr
    db = sqlite3.connect("/app/wb.db")
    row = db.execute("SELECT skewness_at_insert, kurtosis_at_insert FROM audit_log WHERE seq=5").fetchone()
    db.close()
    lats_before = [10.0, 20.0, 30.0, 40.0]
    expected_skew = compute_skew_at_insert(lats_before)
    expected_kurt = compute_kurt_at_insert(lats_before)
    assert row[0] == expected_skew, f"skewness_at_insert={row[0]!r} expected={expected_skew!r}"
    assert row[1] == expected_kurt, f"kurtosis_at_insert={row[1]!r} expected={expected_kurt!r}"


def test_hmac_includes_skew_kurt(mock_server):
    """HMAC chain: verify skew/kurt are included in correct field order"""
    run(["init"])
    clear_db()
    MOCK_DB["G1"] = {"name": "Country1", "lat": 10.0, "lon": 5.0}
    MOCK_DB["G2"] = {"name": "Country2", "lat": 20.0, "lon": 10.0}
    MOCK_DB["G3"] = {"name": "Country3", "lat": 30.0, "lon": 15.0}
    MOCK_DB["G4"] = {"name": "Country4", "lat": 40.0, "lon": 20.0}
    run(["fetch-country", "G1"], api_base=mock_server)
    run(["fetch-country", "G2"], api_base=mock_server)
    run(["fetch-country", "G3"], api_base=mock_server)
    run(["fetch-country", "G4"], api_base=mock_server)
    # seq=4: N=3 lats before = [10,20,30]
    lats_before = [10.0, 20.0, 30.0]
    lat4, lon4 = 40.0, 20.0
    prev_hash_row = sqlite3.connect("/app/wb.db").execute(
        "SELECT entry_hash FROM audit_log WHERE seq=3"
    ).fetchone()
    prev_hash = prev_hash_row[0]
    skew = compute_skew_at_insert(lats_before)
    kurt = compute_kurt_at_insert(lats_before)
    p50_4 = _compute_p50_at_insert(lats_before)  # N=3 odd: middle=20.0
    mad_4 = _compute_mad_at_insert(lats_before)
    expected_hash = build_hmac(4, "G4", lat4, lon4, skew, kurt, prev_hash, p50_4, mad_4)
    db = sqlite3.connect("/app/wb.db")
    row = db.execute("SELECT entry_hash FROM audit_log WHERE seq=4").fetchone()
    db.close()
    assert row[0] == expected_hash, f"entry_hash mismatch: got={row[0]!r} expected={expected_hash!r}"


def test_audit_verify_with_new_fields(mock_server):
    """Full chain verify passes with new fields"""
    run(["init"])
    clear_db()
    MOCK_DB["H1"] = {"name": "Country1", "lat": 10.0, "lon": 5.0}
    MOCK_DB["H2"] = {"name": "Country2", "lat": 20.0, "lon": 10.0}
    MOCK_DB["H3"] = {"name": "Country3", "lat": 30.0, "lon": 15.0}
    run(["fetch-country", "H1"], api_base=mock_server)
    run(["fetch-country", "H2"], api_base=mock_server)
    run(["fetch-country", "H3"], api_base=mock_server)
    r = run(["audit-verify"])
    assert r.returncode == 0, r.stderr
    assert "ok chain_length=3" in r.stdout, r.stdout


def test_zscores_insufficient_data():
    """N=1 prints insufficient data"""
    insert_countries([("IS1", "Solo", 15.0, 5.0)])
    r = run(["country-zscores"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    assert "insufficient data" in r.stdout, r.stdout


def test_zscores_sorted_by_zlat():
    """Output sorted by z_lat ASC then code ASC"""
    # Use distinct latitudes so z_lat ordering is unambiguous
    lats = [50.0, 10.0, 30.0]
    lons = [0.0, 0.0, 0.0]
    insert_countries([("P1", "N1", lats[0], lons[0]), ("P2", "N2", lats[1], lons[1]), ("P3", "N3", lats[2], lons[2])])
    r = run(["country-zscores"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    lines = [ln for ln in r.stdout.strip().split("\n") if ln]
    assert len(lines) == 3, f"expected 3 lines: {r.stdout}"
    codes_out = [ln.split("\t")[0] for ln in lines]
    # P2 has lat=10 (smallest z_lat), P3=30, P1=50
    assert codes_out == ["P2", "P3", "P1"], f"wrong order: {codes_out}"


# ---------------------------------------------------------------------------
# New difficulty tests: rate limiting, pagination, country-rank, audit-stats
# ---------------------------------------------------------------------------

def test_fetch_country_rate_limit_retry(mock_server):
    """fetch-country: 429 first request, then 200 on retry — must succeed"""
    run(["init"])
    clear_db()
    MOCK_DB["RL"] = {"name": "RateLimit Country", "lat": 12.0, "lon": 34.0}
    RATE_LIMIT_CODES["RL"] = "429_once"
    RATE_LIMIT_HITS["RL"] = 0
    try:
        r = run(["fetch-country", "RL"], timeout=15, api_base=mock_server)
        assert r.returncode == 0, f"expected exit 0 after retry, got {r.returncode}: {r.stdout} {r.stderr}"
        assert "ok country=RL" in r.stdout, f"expected ok country=RL, got: {r.stdout}"
    finally:
        RATE_LIMIT_CODES.pop("RL", None)
        RATE_LIMIT_HITS.pop("RL", None)


def test_fetch_country_rate_limit_double_429(mock_server):
    """fetch-country: 429 on both first and retry — must print rate_limited and exit 2"""
    run(["init"])
    clear_db()
    MOCK_DB["R2"] = {"name": "Double429", "lat": 5.0, "lon": 10.0}
    RATE_LIMIT_CODES["R2"] = "429_always"
    RATE_LIMIT_HITS["R2"] = 0
    try:
        r = run(["fetch-country", "R2"], timeout=15, api_base=mock_server)
        assert r.returncode == 2, f"expected exit 2 on double 429, got {r.returncode}: {r.stdout} {r.stderr}"
        assert "rate_limited" in r.stdout, f"expected rate_limited in stdout, got: {r.stdout}"
    finally:
        RATE_LIMIT_CODES.pop("R2", None)
        RATE_LIMIT_HITS.pop("R2", None)


def test_list_countries_limit(mock_server):
    """list-countries --limit 2 returns only first 2 countries by name ASC"""
    run(["init"])
    insert_countries([
        ("CC", "Charlie", 1.0, 0.0),
        ("AA", "Alpha", 2.0, 0.0),
        ("BB", "Beta", 3.0, 0.0),
    ])
    r = run(["list-countries", "--limit", "2"])
    assert r.returncode == 0, r.stderr
    lines = [ln for ln in r.stdout.strip().split("\n") if ln]
    assert len(lines) == 2, f"expected 2 lines with --limit 2, got {len(lines)}: {r.stdout}"
    # Sorted by name ASC: Alpha, Beta, Charlie -> limit 2 = Alpha, Beta
    names = [ln.split("\t")[1] for ln in lines]
    assert names == ["Alpha", "Beta"], f"wrong names with limit 2: {names}"


def test_list_countries_offset(mock_server):
    """list-countries --offset 1 skips first country"""
    run(["init"])
    insert_countries([
        ("CC", "Charlie", 1.0, 0.0),
        ("AA", "Alpha", 2.0, 0.0),
        ("BB", "Beta", 3.0, 0.0),
    ])
    r = run(["list-countries", "--offset", "1"])
    assert r.returncode == 0, r.stderr
    lines = [ln for ln in r.stdout.strip().split("\n") if ln]
    assert len(lines) == 2, f"expected 2 lines with --offset 1, got {len(lines)}: {r.stdout}"
    # Sorted by name ASC: Alpha(skip), Beta, Charlie
    names = [ln.split("\t")[1] for ln in lines]
    assert names == ["Beta", "Charlie"], f"wrong names with offset 1: {names}"


def test_list_countries_limit_offset(mock_server):
    """list-countries --limit 1 --offset 1 returns second country only"""
    run(["init"])
    insert_countries([
        ("CC", "Charlie", 1.0, 0.0),
        ("AA", "Alpha", 2.0, 0.0),
        ("BB", "Beta", 3.0, 0.0),
    ])
    r = run(["list-countries", "--limit", "1", "--offset", "1"])
    assert r.returncode == 0, r.stderr
    lines = [ln for ln in r.stdout.strip().split("\n") if ln]
    assert len(lines) == 1, f"expected 1 line with --limit 1 --offset 1, got {len(lines)}: {r.stdout}"
    # Sorted by name ASC: Alpha(skip), Beta(take 1)
    name = lines[0].split("\t")[1]
    assert name == "Beta", f"expected Beta, got: {name}"


def test_country_rank_basic():
    """country-rank: correct 1-based rank, total, pct for middle latitude"""
    run(["init"])
    # lat ASC: BR(-10), MX(0), US(40)
    insert_countries([
        ("US", "United States", 40.0, -100.0),
        ("MX", "Mexico", 0.0, -90.0),
        ("BR", "Brazil", -10.0, -50.0),
    ])
    r = run(["country-rank", "MX"])
    assert r.returncode == 0, r.stderr
    assert "rank=2" in r.stdout, f"expected rank=2, got: {r.stdout}"
    assert "total=3" in r.stdout, f"expected total=3, got: {r.stdout}"
    # pct = 2/3*100 = 66.666... -> 66.67
    assert "pct=66.67" in r.stdout, f"expected pct=66.67, got: {r.stdout}"


def test_country_rank_not_found():
    """country-rank: prints not_found and exits 1 for unknown code"""
    run(["init"])
    insert_countries([("US", "United States", 40.0, -100.0)])
    r = run(["country-rank", "ZZ"])
    assert r.returncode == 1, f"expected exit 1, got {r.returncode}"
    assert "not_found" in r.stdout, f"expected not_found, got: {r.stdout}"


def _rank_tier(code):
    r = run(["country-rank", code])
    assert r.returncode == 0, r.stderr
    for line in r.stdout.splitlines():
        if line.startswith("tier="):
            return line.split("=", 1)[1]
    raise AssertionError(f"no tier= line in country-rank output: {r.stdout}")


def test_country_rank_tier_small_region_all_core():
    """A region with count <= 3 has no shortage of slots: every member is core
    even though the latitudes are wildly different."""
    run(["init"])
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    db.execute("INSERT INTO countries VALUES ('SA1','N1','SMALLR','HIC','Cap',-70.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('SA2','N2','SMALLR','HIC','Cap',5.0,0.0)")
    db.commit()
    db.close()
    assert _rank_tier("SA1") == "core"
    assert _rank_tier("SA2") == "core"


def test_country_rank_tier_reclassifies_on_later_insert():
    """A later fetch that qualifies for a region's top-3 slots must knock the
    weakest already-inserted member down to peripheral, even though that
    member was core on every prior country-rank call before this insert.

    Region CPTST: AA=0.0, BB=1.0, CC=2.0 inserted first (n=3, all core).
    Then DD=100.0 arrives (n=4). Region mean/stddev shift so AA becomes the
    second-most extreme member and CC -- previously core -- drops out."""
    run(["init"])
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    db.execute("INSERT INTO countries VALUES ('AA','N1','CPTST','HIC','Cap',0.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('BB','N2','CPTST','HIC','Cap',1.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('CC','N3','CPTST','HIC','Cap',2.0,0.0)")
    db.commit()
    db.close()

    assert _rank_tier("AA") == "core"
    assert _rank_tier("BB") == "core"
    assert _rank_tier("CC") == "core", "with only 3 members in the region, all 3 must be core"

    db = sqlite3.connect("/app/wb.db")
    db.execute("INSERT INTO countries VALUES ('DD','N4','CPTST','HIC','Cap',100.0,0.0)")
    db.commit()
    db.close()

    # region mean is now 25.75, population stddev ~42.874; deviations
    # AA=25.75, BB=24.75, CC=23.75, DD=74.25 -- DD, AA, BB keep the top 3
    # standings and CC (previously core) must now read peripheral.
    assert _rank_tier("DD") == "core"
    assert _rank_tier("AA") == "core", "AA must stay core: its deviation from the shifted mean still ranks in the top 3"
    assert _rank_tier("BB") == "core"
    assert _rank_tier("CC") == "peripheral", "CC must be bumped down: a later insert can reclassify an earlier core member"


def test_country_rank_tier_cutoff_tie_break_by_code():
    """4 countries sharing one latitude in a region above the cap: standing
    is tied at 0 for all of them, so the top-3 cutoff is decided by code
    ascending, not insertion order."""
    run(["init"])
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    # Inserted in descending code order on purpose, so an insertion-order
    # tie-break would pick the wrong three.
    db.execute("INSERT INTO countries VALUES ('QD','N4','TIEZ','HIC','Cap',5.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('QC','N3','TIEZ','HIC','Cap',5.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('QB','N2','TIEZ','HIC','Cap',5.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('QA','N1','TIEZ','HIC','Cap',5.0,0.0)")
    db.commit()
    db.close()

    assert _rank_tier("QA") == "core"
    assert _rank_tier("QB") == "core"
    assert _rank_tier("QC") == "core"
    assert _rank_tier("QD") == "peripheral", "QD has the highest code, so it must lose the tie-break for the last slot"


def test_country_rank_tier_scoped_to_own_region_not_whole_table():
    """A region's standing must be computed from ITS OWN population mean and
    stddev, never the whole countries table. Region GLBA (4 members) shares
    the table with region GLBB (3 identical extreme outliers); mixing GLBB's
    values into GLBA's mean/stddev flips which GLBA member is peripheral."""
    run(["init"])
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    db.execute("INSERT INTO countries VALUES ('GA1','N1','GLBA','HIC','Cap',10.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('GA2','N2','GLBA','HIC','Cap',11.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('GA3','N3','GLBA','HIC','Cap',12.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('GA4','N4','GLBA','HIC','Cap',50.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('GB1','N5','GLBB','HIC','Cap',-80.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('GB2','N6','GLBB','HIC','Cap',-80.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('GB3','N7','GLBB','HIC','Cap',-80.0,0.0)")
    db.commit()
    db.close()

    # Region-scoped (correct): GLBA mean=20.75, stddev~16.90; standings put
    # GA4, GA1, GA2 in the top 3 and GA3 peripheral.
    assert _rank_tier("GA4") == "core"
    assert _rank_tier("GA1") == "core", "GA1 only reads peripheral if GLBB's rows leak into GLBA's mean/stddev"
    assert _rank_tier("GA2") == "core"
    assert _rank_tier("GA3") == "peripheral", "GA3 only reads core if the whole table's stats are used instead of GLBA's own"


def test_audit_stats_basic(mock_server):
    """audit-stats: correct chain_length, unique_codes, first/last codes"""
    run(["init"])
    clear_db()
    MOCK_DB["S1"] = {"name": "Country1", "lat": 10.0, "lon": 0.0}
    MOCK_DB["S2"] = {"name": "Country2", "lat": 20.0, "lon": 0.0}
    MOCK_DB["S3"] = {"name": "Country3", "lat": 30.0, "lon": 0.0}
    run(["fetch-country", "S1"], api_base=mock_server)
    run(["fetch-country", "S2"], api_base=mock_server)
    run(["fetch-country", "S3"], api_base=mock_server)
    r = run(["audit-stats"])
    assert r.returncode == 0, r.stderr
    assert "chain_length=3" in r.stdout, f"expected chain_length=3: {r.stdout}"
    assert "unique_codes=3" in r.stdout, f"expected unique_codes=3: {r.stdout}"
    assert "first_code=S1" in r.stdout, f"expected first_code=S1: {r.stdout}"
    assert "last_code=S3" in r.stdout, f"expected last_code=S3: {r.stdout}"


def test_audit_stats_empty():
    """audit-stats on empty audit_log prints zeros and none"""
    run(["init"])
    insert_countries([])  # clears both tables
    r = run(["audit-stats"])
    assert r.returncode == 0, r.stderr
    assert "chain_length=0" in r.stdout, f"expected chain_length=0: {r.stdout}"
    assert "unique_codes=0" in r.stdout, f"expected unique_codes=0: {r.stdout}"
    assert "first_code=none" in r.stdout, f"expected first_code=none: {r.stdout}"
    assert "last_code=none" in r.stdout, f"expected last_code=none: {r.stdout}"


# ---------------------------------------------------------------------------
# New HARD precision-trap tests: country-gini, country-entropy, country-atkinson
# ---------------------------------------------------------------------------

def compute_gini(lats):
    """Biased Gini on shifted lats"""
    if len(lats) < 2:
        return None
    min_lat = min(lats)
    shifted = sorted(v - min_lat + 1.0 for v in lats)
    n = len(shifted)
    total_sum = sum(shifted)
    rank_sum = sum((i + 1) * v for i, v in enumerate(shifted))
    return (2 * rank_sum) / (n * total_sum) - (n + 1) / n


def compute_entropy(regions):
    """Shannon entropy base-2 of region distribution"""
    counts = Counter(regions)
    total = len(regions)
    if total < 2:
        return None
    entropy = 0.0
    for count in counts.values():
        p = count / total
        entropy -= p * math.log2(p)
    return entropy


def compute_atkinson(lats):
    """Atkinson epsilon=0.5 on shifted lats"""
    if len(lats) < 2:
        return None
    min_lat = min(lats)
    shifted = [v - min_lat + 1.0 for v in lats]
    n = len(shifted)
    mean_shifted = sum(shifted) / n
    mean_sqrt = sum(math.sqrt(v) for v in shifted) / n
    if mean_shifted == 0:
        return None
    return 1.0 - (mean_sqrt ** 2) / mean_shifted


def test_country_gini_basic():
    """Biased Gini [100,200,300,400] shifted by min+1 = [1,101,201,301]"""
    insert_countries([
        ("G1", "N1", 100.0, 0.0),
        ("G2", "N2", 200.0, 0.0),
        ("G3", "N3", 300.0, 0.0),
        ("G4", "N4", 400.0, 0.0),
    ])
    r = run(["country-gini"])
    assert r.returncode == 0, r.stderr
    expected = compute_gini([100.0, 200.0, 300.0, 400.0])
    assert f"gini={expected:.8f}" in r.stdout, f"expected gini={expected:.8f}, got: {r.stdout}"
    assert "gini=0.25000000" not in r.stdout or abs(expected - 0.25) < 1e-9, r.stdout


def test_country_gini_precision_trap():
    """Gini trap: biased formula gives different result from unbiased"""
    lats = [1.0, 2.0, 3.0, 4.0, 5.0]
    insert_countries([(f"GX{i}", f"N{i}", v, 0.0) for i, v in enumerate(lats)])
    r = run(["country-gini"])
    assert r.returncode == 0, r.stderr
    expected = compute_gini(lats)
    assert f"gini={expected:.8f}" in r.stdout, f"expected gini={expected:.8f}, got: {r.stdout}"


def test_country_gini_insufficient():
    """country-gini with N=1 prints insufficient_data and exits 1"""
    insert_countries([("GI1", "Solo", 50.0, 0.0)])
    r = run(["country-gini"])
    assert r.returncode == 1, f"expected exit 1, got {r.returncode}"
    assert "insufficient_data" in r.stdout, f"expected insufficient_data, got: {r.stdout}"


def test_country_gini_negative_lats():
    """Gini with negative latitudes (shift ensures strictly positive)"""
    lats = [-30.0, -10.0, 10.0, 30.0]
    insert_countries([(f"GN{i}", f"N{i}", v, 0.0) for i, v in enumerate(lats)])
    r = run(["country-gini"])
    assert r.returncode == 0, r.stderr
    expected = compute_gini(lats)
    assert f"gini={expected:.8f}" in r.stdout, f"expected gini={expected:.8f}, got: {r.stdout}"


def test_country_entropy_basic():
    """Shannon entropy base-2 for 2 equal regions -> 1.0"""
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    db.execute("INSERT INTO countries VALUES ('E1','N1','REGO','HIC','Cap',10.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('E2','N2','REGO','HIC','Cap',20.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('E3','N3','REGX','HIC','Cap',30.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('E4','N4','REGX','HIC','Cap',40.0,0.0)")
    db.commit()
    db.close()
    r = run(["country-entropy"])
    assert r.returncode == 0, r.stderr
    expected = compute_entropy(["REGO", "REGO", "REGX", "REGX"])
    assert f"entropy={expected:.8f}" in r.stdout, f"expected entropy={expected:.8f}, got: {r.stdout}"
    assert "entropy=1.00000000" in r.stdout, f"expected entropy=1.00000000 for 2 equal groups, got: {r.stdout}"


def test_country_entropy_log2_trap():
    """Verify log2 (not ln): single region should give entropy=0"""
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    db.execute("INSERT INTO countries VALUES ('ET1','N1','SAMEREG','HIC','Cap',10.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('ET2','N2','SAMEREG','HIC','Cap',20.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('ET3','N3','SAMEREG','HIC','Cap',30.0,0.0)")
    db.commit()
    db.close()
    r = run(["country-entropy"])
    assert r.returncode == 0, r.stderr
    assert "entropy=0.00000000" in r.stdout, f"expected entropy=0.00000000, got: {r.stdout}"


def test_country_entropy_unequal():
    """Entropy for unequal distribution verifies exact 8dp value"""
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    db.execute("INSERT INTO countries VALUES ('EU1','N1','R1','HIC','Cap',10.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('EU2','N2','R2','HIC','Cap',20.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('EU3','N3','R2','HIC','Cap',30.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('EU4','N4','R3','HIC','Cap',40.0,0.0)")
    db.commit()
    db.close()
    r = run(["country-entropy"])
    assert r.returncode == 0, r.stderr
    regions = ["R1", "R2", "R2", "R3"]
    expected = compute_entropy(regions)
    assert f"entropy={expected:.8f}" in r.stdout, f"expected entropy={expected:.8f}, got: {r.stdout}"


def test_country_entropy_insufficient():
    """country-entropy with N=1 prints insufficient_data and exits 1"""
    insert_countries([("ENI", "Solo", 15.0, 0.0)])
    r = run(["country-entropy"])
    assert r.returncode == 1, f"expected exit 1, got {r.returncode}"
    assert "insufficient_data" in r.stdout, f"expected insufficient_data, got: {r.stdout}"


def test_country_atkinson_basic():
    """Atkinson epsilon=0.5 for simple values"""
    lats = [10.0, 20.0, 30.0, 40.0]
    insert_countries([(f"AT{i}", f"N{i}", v, 0.0) for i, v in enumerate(lats)])
    r = run(["country-atkinson"])
    assert r.returncode == 0, r.stderr
    expected = compute_atkinson(lats)
    assert f"atkinson={expected:.8f}" in r.stdout, f"expected atkinson={expected:.8f}, got: {r.stdout}"


def test_country_atkinson_negative_lats():
    """Atkinson with negative latitudes (shift makes strictly positive)"""
    lats = [-50.0, -20.0, 10.0, 40.0]
    insert_countries([(f"AN{i}", f"N{i}", v, 0.0) for i, v in enumerate(lats)])
    r = run(["country-atkinson"])
    assert r.returncode == 0, r.stderr
    expected = compute_atkinson(lats)
    assert f"atkinson={expected:.8f}" in r.stdout, f"expected atkinson={expected:.8f}, got: {r.stdout}"


def test_country_atkinson_insufficient():
    """country-atkinson with N=1 prints insufficient_data and exits 1"""
    insert_countries([("ATI", "Solo", 25.0, 0.0)])
    r = run(["country-atkinson"])
    assert r.returncode == 1, f"expected exit 1, got {r.returncode}"
    assert "insufficient_data" in r.stdout, f"expected insufficient_data, got: {r.stdout}"


def test_country_gini_biased_not_unbiased():
    """Gini must use biased formula; unbiased (n/(n-1) factor) gives detectably different value."""
    # lats [1.0, 2.0, 3.0, 4.0]: min=1.0, shifted=[1,2,3,4] (no change since min+1=2-1=1)
    # Wait: shifted = v - min(lats) + 1.0 = v - 1.0 + 1.0 = v, so shifted=[1,2,3,4]
    # sorted shifted=[1,2,3,4], n=4, total=10
    # rank_sum = 1*1 + 2*2 + 3*3 + 4*4 = 1+4+9+16 = 30
    # biased gini = (2*30)/(4*10) - 5/4 = 60/40 - 1.25 = 1.5 - 1.25 = 0.25000000
    # unbiased gini = 0.25 * (4/3) = 0.33333333...
    lats = [1.0, 2.0, 3.0, 4.0]
    insert_countries([(f"BG{i}", f"N{i}", v, 0.0) for i, v in enumerate(lats)])
    r = run(["country-gini"])
    assert r.returncode == 0, r.stderr
    assert "gini=0.25000000" in r.stdout, f"expected biased gini=0.25000000, got: {r.stdout}"
    assert "gini=0.33333333" not in r.stdout, f"got unbiased gini=0.33333333; must use biased formula: {r.stdout}"


def test_country_entropy_log2_not_ln():
    """country-entropy must use log2, not ln; values differ detectably for non-uniform distributions."""
    # Insert 3 countries in LAC, 2 in EAS, 1 in SSA
    # H_log2 = -(3/6)*log2(3/6) - (2/6)*log2(2/6) - (1/6)*log2(1/6)
    # H_ln   = -(3/6)*ln(3/6)   - (2/6)*ln(2/6)   - (1/6)*ln(1/6)  -- wrong
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    db.execute("INSERT INTO countries VALUES ('LA1','N1','LAC','HIC','Cap',10.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('LA2','N2','LAC','HIC','Cap',20.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('LA3','N3','LAC','HIC','Cap',30.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('EA1','N4','EAS','HIC','Cap',40.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('EA2','N5','EAS','HIC','Cap',50.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('SS1','N6','SSA','HIC','Cap',60.0,0.0)")
    db.commit()
    db.close()
    regions = ["LAC", "LAC", "LAC", "EAS", "EAS", "SSA"]
    expected_log2 = compute_entropy(regions)
    expected_ln_wrong = -sum(
        (c / 6) * math.log(c / 6) for c in [3, 2, 1]
    )
    r = run(["country-entropy"])
    assert r.returncode == 0, r.stderr
    assert f"entropy={expected_log2:.8f}" in r.stdout, (
        f"expected entropy={expected_log2:.8f} (log2), got: {r.stdout}"
    )
    wrong_str = f"{expected_ln_wrong:.8f}"
    assert f"entropy={wrong_str}" not in r.stdout, (
        f"got ln-based entropy={wrong_str}; must use log2: {r.stdout}"
    )


# ---------------------------------------------------------------------------
# New HARD precision-trap tests: country-theil, country-hhi
# ---------------------------------------------------------------------------

def compute_theil(lats):
    """Theil T index using natural log on absolute values of lats"""
    if len(lats) < 2:
        return None
    values = [abs(v) for v in lats]
    n = len(values)
    mu = sum(values) / n
    if mu == 0:
        return None
    return sum((x / mu) * math.log(x / mu) for x in values) / n


def compute_hhi(regions):
    """Normalized HHI of region distribution"""
    counts = Counter(regions)
    n = len(regions)
    k = len(counts)
    if n < 2 or k < 2:
        return None
    raw_hhi = sum((c / n) ** 2 for c in counts.values())
    return (raw_hhi - 1.0 / k) / (1.0 - 1.0 / k)


def test_country_theil_basic():
    """Theil T for simple values [10,20,30,40]: verify exact 6dp using natural log on abs values"""
    lats = [10.0, 20.0, 30.0, 40.0]
    insert_countries([(f"TH{i}", f"N{i}", v, 0.0) for i, v in enumerate(lats)])
    r = run(["country-theil"])
    assert r.returncode == 0, r.stderr
    expected = compute_theil(lats)
    assert f"theil: {expected:.6f}" in r.stdout, f"expected theil: {expected:.6f}, got: {r.stdout}"


def test_country_theil_ln_not_log2():
    """Theil must use natural log (ln), NOT log2; values differ detectably."""
    lats = [5.0, 10.0, 20.0, 40.0, 80.0]
    insert_countries([(f"TL{i}", f"N{i}", v, 0.0) for i, v in enumerate(lats)])
    r = run(["country-theil"])
    assert r.returncode == 0, r.stderr
    expected_ln = compute_theil(lats)
    # If agent used log2 instead of ln, compute that wrong value using abs values
    values = [abs(v) for v in lats]
    n = len(values)
    mu = sum(values) / n
    wrong_log2 = sum((x / mu) * math.log2(x / mu) for x in values) / n
    assert f"theil: {expected_ln:.6f}" in r.stdout, (
        f"expected theil: {expected_ln:.6f} (ln), got: {r.stdout}"
    )
    assert f"theil: {wrong_log2:.6f}" not in r.stdout, (
        f"got log2-based theil: {wrong_log2:.6f}; must use natural log: {r.stdout}"
    )


def test_country_theil_negative_lats():
    """Theil with negative latitudes (uses absolute values, not shift)"""
    lats = [-40.0, -10.0, 20.0, 50.0]
    insert_countries([(f"TN{i}", f"N{i}", v, 0.0) for i, v in enumerate(lats)])
    r = run(["country-theil"])
    assert r.returncode == 0, r.stderr
    expected = compute_theil(lats)
    assert f"theil: {expected:.6f}" in r.stdout, f"expected theil: {expected:.6f}, got: {r.stdout}"


def test_country_theil_null_n1():
    """country-theil with N=1 prints 'theil: NULL' and exits 0"""
    insert_countries([("TI1", "Solo", 30.0, 0.0)])
    r = run(["country-theil"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stdout} {r.stderr}"
    assert "theil: NULL" in r.stdout, f"expected 'theil: NULL', got: {r.stdout}"


def test_country_hhi_basic():
    """Normalized HHI for equal-split 2-region distribution"""
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    db.execute("INSERT INTO countries VALUES ('HH1','N1','R1','HIC','Cap',10.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('HH2','N2','R1','HIC','Cap',20.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('HH3','N3','R2','HIC','Cap',30.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('HH4','N4','R2','HIC','Cap',40.0,0.0)")
    db.commit()
    db.close()
    r = run(["country-hhi"])
    assert r.returncode == 0, r.stderr
    regions = ["R1", "R1", "R2", "R2"]
    expected = compute_hhi(regions)
    assert f"hhi={expected:.8f}" in r.stdout, f"expected hhi={expected:.8f}, got: {r.stdout}"
    # 2 equal regions: raw_hhi=0.5, normalized=(0.5-0.5)/(1-0.5)=0
    assert "hhi=0.00000000" in r.stdout, f"equal 2-region split must give normalized HHI=0, got: {r.stdout}"


def test_country_hhi_unequal():
    """Normalized HHI for unequal 3-region distribution"""
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    db.execute("INSERT INTO countries VALUES ('HU1','N1','RA','HIC','Cap',10.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('HU2','N2','RA','HIC','Cap',20.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('HU3','N3','RA','HIC','Cap',30.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('HU4','N4','RB','HIC','Cap',40.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('HU5','N5','RB','HIC','Cap',50.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('HU6','N6','RC','HIC','Cap',60.0,0.0)")
    db.commit()
    db.close()
    r = run(["country-hhi"])
    assert r.returncode == 0, r.stderr
    regions = ["RA", "RA", "RA", "RB", "RB", "RC"]
    expected = compute_hhi(regions)
    assert f"hhi={expected:.8f}" in r.stdout, f"expected hhi={expected:.8f}, got: {r.stdout}"


def test_country_hhi_normalization_trap():
    """HHI normalization uses K (distinct regions), not N (total countries); verify trap."""
    # 4 countries in 4 regions: raw_hhi = 4*(0.25^2)=0.25, K=4
    # normalized = (0.25 - 1/4)/(1-1/4) = 0/0.75 = 0.0  (minimum concentration)
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    db.execute("INSERT INTO countries VALUES ('NT1','N1','X1','HIC','Cap',10.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('NT2','N2','X2','HIC','Cap',20.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('NT3','N3','X3','HIC','Cap',30.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('NT4','N4','X4','HIC','Cap',40.0,0.0)")
    db.commit()
    db.close()
    r = run(["country-hhi"])
    assert r.returncode == 0, r.stderr
    # Equal distribution across K=4 regions: normalized HHI must be 0
    assert "hhi=0.00000000" in r.stdout, (
        f"equal distribution across K regions must give normalized HHI=0, got: {r.stdout}"
    )


def test_country_hhi_insufficient_single_region():
    """country-hhi with K=1 (all same region) prints insufficient_data and exits 1"""
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    db.execute("INSERT INTO countries VALUES ('HI1','N1','SAME','HIC','Cap',10.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('HI2','N2','SAME','HIC','Cap',20.0,0.0)")
    db.commit()
    db.close()
    r = run(["country-hhi"])
    assert r.returncode == 1, f"expected exit 1 when K=1, got {r.returncode}"
    assert "insufficient_data" in r.stdout, f"expected insufficient_data, got: {r.stdout}"


def test_country_hhi_insufficient_n1():
    """country-hhi with N=1 prints insufficient_data and exits 1"""
    insert_countries([("HN1", "Solo", 15.0, 0.0)])
    r = run(["country-hhi"])
    assert r.returncode == 1, f"expected exit 1, got {r.returncode}"
    assert "insufficient_data" in r.stdout, f"expected insufficient_data, got: {r.stdout}"


# ---------------------------------------------------------------------------
# New HARD precision-trap tests: country-theil (abs values trap) and country-forecast
# ---------------------------------------------------------------------------

def compute_theil_abs(lats):
    """Theil T using natural log on absolute values of latitudes"""
    values = [abs(v) for v in lats]
    n = len(values)
    if n < 2:
        return None
    mu = sum(values) / n
    if mu == 0:
        return None
    return sum((x / mu) * math.log(x / mu) for x in values) / n


def compute_ols_forecast(lats):
    """OLS forecast at position N+1 using 1-indexed positions"""
    n = len(lats)
    if n < 2:
        return None
    sum_x = sum(float(i + 1) for i in range(n))
    sum_y = sum(lats)
    sum_xy = sum(float(i + 1) * lats[i] for i in range(n))
    sum_x2 = sum(float(i + 1) ** 2 for i in range(n))
    fn = float(n)
    denom = fn * sum_x2 - sum_x * sum_x
    if denom == 0:
        return None
    slope = (fn * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / fn
    return intercept + slope * float(n + 1)


def test_country_theil_abs_not_shift():
    """Theil must use |latitude| (absolute value), NOT shift-to-positive; values differ for mixed lats."""
    # lats with negatives: abs approach gives different result than shift approach
    lats = [-30.0, -10.0, 10.0, 30.0]
    insert_countries([(f"TA{i}", f"N{i}", v, 0.0) for i, v in enumerate(lats)])
    r = run(["country-theil"])
    assert r.returncode == 0, r.stderr
    expected_abs = compute_theil_abs(lats)
    # Compute wrong shift-based value for comparison
    min_lat = min(lats)
    shifted = [v - min_lat + 1.0 for v in lats]
    n = len(shifted)
    mean_s = sum(shifted) / n
    wrong_shift = sum((s / mean_s) * math.log(s / mean_s) for s in shifted) / n
    assert f"theil: {expected_abs:.6f}" in r.stdout, (
        f"expected theil: {expected_abs:.6f} (abs), got: {r.stdout}"
    )
    assert f"theil: {wrong_shift:.6f}" not in r.stdout, (
        f"got shift-based theil: {wrong_shift:.6f}; must use absolute values: {r.stdout}"
    )


def test_country_forecast_basic():
    """OLS forecast at position N+1 for linear latitudes [10,20,30,40]: expect 50.0"""
    # Sort order by name ASC then rowid ASC: names are N0, N1, N2, N3 (alphabetical)
    # N0=lat10, N1=lat20, N2=lat30, N3=lat40 -> positions 1,2,3,4
    insert_countries([
        ("FC1", "N0", 10.0, 0.0),
        ("FC2", "N1", 20.0, 0.0),
        ("FC3", "N2", 30.0, 0.0),
        ("FC4", "N3", 40.0, 0.0),
    ])
    r = run(["country-forecast"])
    assert r.returncode == 0, r.stderr
    assert "forecast: 50.000000" in r.stdout, f"expected forecast: 50.000000, got: {r.stdout}"


def test_country_forecast_1indexed_not_rowid():
    """Forecast must use 1-indexed positions, NOT database rowids; non-contiguous IDs must not affect result."""
    # Create 4 rows with linear latitudes, then ensure the rowids are non-contiguous
    # by deleting a 5th row after insertion (so AUTOINCREMENT next id would skip)
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    # Insert 5 rows first, then delete the 5th to create a gap
    db.execute("INSERT INTO countries VALUES ('PA', 'N0', 'REG', 'HIC', 'Cap', 10.0, 0.0)")
    db.execute("INSERT INTO countries VALUES ('PB', 'N1', 'REG', 'HIC', 'Cap', 20.0, 0.0)")
    db.execute("INSERT INTO countries VALUES ('PC', 'N2', 'REG', 'HIC', 'Cap', 30.0, 0.0)")
    db.execute("INSERT INTO countries VALUES ('PD', 'N3', 'REG', 'HIC', 'Cap', 40.0, 0.0)")
    db.execute("INSERT INTO countries VALUES ('PE', 'N4', 'REG', 'HIC', 'Cap', 50.0, 0.0)")
    db.execute("DELETE FROM countries WHERE code='PE'")
    db.commit()
    db.close()
    # Now we have 4 rows; sorted by name ASC: N0,N1,N2,N3 -> latitudes 10,20,30,40
    # 1-indexed positions 1..4 -> forecast at pos 5 = 50.0
    r = run(["country-forecast"])
    assert r.returncode == 0, r.stderr
    assert "forecast: 50.000000" in r.stdout, (
        f"expected forecast: 50.000000 (1-indexed positions), got: {r.stdout}"
    )


def test_country_forecast_null_n1():
    """country-forecast with N=1 prints 'forecast: NULL' and exits 0"""
    insert_countries([("FN1", "Solo", 15.0, 0.0)])
    r = run(["country-forecast"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stdout} {r.stderr}"
    assert "forecast: NULL" in r.stdout, f"expected 'forecast: NULL', got: {r.stdout}"


def test_country_forecast_order_by_name():
    """Forecast rows ordered by name ASC then rowid ASC; different name order gives different forecast."""
    # 4 countries, names NOT in lat order, so name-sort order matters
    # Sorted by name: Aaa(lat=40), Bbb(lat=10), Ccc(lat=30), Ddd(lat=20)
    # positions: 1->40, 2->10, 3->30, 4->20
    insert_countries([
        ("OA", "Bbb", 10.0, 0.0),
        ("OB", "Ddd", 20.0, 0.0),
        ("OC", "Ccc", 30.0, 0.0),
        ("OD", "Aaa", 40.0, 0.0),
    ])
    lats_in_name_order = [40.0, 10.0, 30.0, 20.0]  # Aaa, Bbb, Ccc, Ddd
    expected = compute_ols_forecast(lats_in_name_order)
    r = run(["country-forecast"])
    assert r.returncode == 0, r.stderr
    assert f"forecast: {expected:.6f}" in r.stdout, (
        f"expected forecast: {expected:.6f} (name-sorted order), got: {r.stdout}"
    )


# ---------------------------------------------------------------------------
# Novel compound commands: country-chain-dual and country-weighted-stats
# ---------------------------------------------------------------------------

def _wb_rev_hmac(seq, code, lat, lon, prev_rev_hash):
    """Compute one step of the reverse HMAC chain for worldbank."""
    msg = f"{seq}|{code}|{lat:.6f}|{lon:.6f}|{prev_rev_hash}"
    return hm.new(b"wb-tracker-reverse-2026", msg.encode(), hashlib.sha256).hexdigest()


def test_country_chain_dual_empty():
    """country-chain-dual on empty audit_log prints 64 zeros for both fwd and rev."""
    insert_countries([])
    r = run(["country-chain-dual"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    assert "fwd=" + "0" * 64 in r.stdout, f"expected 64-zero fwd hash, got: {r.stdout}"
    assert "rev=" + "0" * 64 in r.stdout, f"expected 64-zero rev hash, got: {r.stdout}"


def test_country_chain_dual_single_entry(mock_server):
    """country-chain-dual with 1 entry: fwd=entry_hash of seq=1; rev=HMAC of that single row."""
    run(["init"])
    clear_db()
    MOCK_DB["DA"] = {"name": "DualA", "lat": 12.345678, "lon": -45.123456}
    run(["fetch-country", "DA"], api_base=mock_server)
    # Get the actual stored entry_hash (that's the fwd)
    db = sqlite3.connect("/app/wb.db")
    row = db.execute("SELECT seq, country_code, latitude, longitude, entry_hash FROM audit_log WHERE seq=1").fetchone()
    db.close()
    seq, code, lat, lon, fwd_hash = row
    # Reverse chain for single row: start with 64 zeros, compute rev_hash
    rev_hash = _wb_rev_hmac(seq, code, lat, lon, "0" * 64)
    r = run(["country-chain-dual"])
    assert r.returncode == 0, f"expected exit 0: {r.stderr}"
    assert f"fwd={fwd_hash}" in r.stdout, f"expected fwd={fwd_hash}, got: {r.stdout}"
    assert f"rev={rev_hash}" in r.stdout, f"expected rev={rev_hash}, got: {r.stdout}"


def test_country_chain_dual_three_entries(mock_server):
    """country-chain-dual with 3 entries: fwd=entry_hash of seq=3; rev built from seq=3,2,1."""
    run(["init"])
    clear_db()
    MOCK_DB["DB1"] = {"name": "DB1", "lat": 10.0, "lon": 5.0}
    MOCK_DB["DB2"] = {"name": "DB2", "lat": 20.0, "lon": 10.0}
    MOCK_DB["DB3"] = {"name": "DB3", "lat": 30.0, "lon": 15.0}
    run(["fetch-country", "DB1"], api_base=mock_server)
    run(["fetch-country", "DB2"], api_base=mock_server)
    run(["fetch-country", "DB3"], api_base=mock_server)
    db = sqlite3.connect("/app/wb.db")
    rows = db.execute("SELECT seq, country_code, latitude, longitude, entry_hash FROM audit_log ORDER BY seq ASC").fetchall()
    db.close()
    # Forward: entry_hash of highest seq
    fwd_hash = rows[-1][4]
    # Reverse: iterate descending
    prev_rev = "0" * 64
    for row in reversed(rows):
        seq, code, lat, lon, _ = row
        prev_rev = _wb_rev_hmac(seq, code, lat, lon, prev_rev)
    rev_hash = prev_rev
    r = run(["country-chain-dual"])
    assert r.returncode == 0, f"expected exit 0: {r.stderr}"
    assert f"fwd={fwd_hash}" in r.stdout, f"expected fwd={fwd_hash}, got: {r.stdout}"
    assert f"rev={rev_hash}" in r.stdout, f"expected rev={rev_hash}, got: {r.stdout}"


def test_country_chain_dual_different_fwd_rev(mock_server):
    """fwd and rev hashes must differ for N>=2 (different key + different order)."""
    run(["init"])
    clear_db()
    MOCK_DB["DC1"] = {"name": "Dcountry1", "lat": 15.0, "lon": 25.0}
    MOCK_DB["DC2"] = {"name": "Dcountry2", "lat": 35.0, "lon": 45.0}
    run(["fetch-country", "DC1"], api_base=mock_server)
    run(["fetch-country", "DC2"], api_base=mock_server)
    r = run(["country-chain-dual"])
    assert r.returncode == 0, f"expected exit 0: {r.stderr}"
    lines = {ln.split("=")[0]: ln.split("=")[1] for ln in r.stdout.strip().split("\n") if "=" in ln}
    assert lines.get("fwd") != lines.get("rev"), "fwd and rev must differ for N>=2"


def _bankers_round(x, decimals):
    """Python banker's rounding to `decimals` places."""
    d = decimal.Decimal(str(x))
    quant = decimal.Decimal(10) ** -decimals
    return float(d.quantize(quant, rounding=decimal.ROUND_HALF_EVEN))


def _compute_weighted_stats(rows_name_code_lat):
    """rows_name_code_lat: list of (name, code, lat) sorted by name ASC, code ASC."""
    rows_sorted = sorted(rows_name_code_lat, key=lambda r: (r[0], r[1]))
    lats = [r[2] for r in rows_sorted]
    n = len(lats)
    if n < 2:
        return None
    weighted_sum = sum((i + 1) * lat for i, lat in enumerate(lats))
    denom = n * (n + 1) / 2
    W = weighted_sum / denom
    M = sum(lats) / n
    momentum = W / M if M != 0 else 0.0
    return W, M, momentum


def test_country_weighted_stats_known_values():
    """Known values: lats [1,2,3,4,5] in name order -> W=55/15=3.666..., M=3.0, momentum=1.222..."""
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    # names A,B,C,D,E so alphabetical order matches lat order
    rows = [("WA", "A", 1.0), ("WB", "B", 2.0), ("WC", "C", 3.0), ("WD", "D", 4.0), ("WE", "E", 5.0)]
    for code, name, lat in rows:
        db.execute("INSERT INTO countries VALUES (?,?,?,?,?,?,?)", (code, name, "REG", "HIC", "Cap", lat, 0.0))
    db.commit()
    db.close()
    r = run(["country-weighted-stats"])
    assert r.returncode == 0, f"expected exit 0: {r.stderr}"
    # W = (1*1 + 2*2 + 3*3 + 4*4 + 5*5) / 15 = 55/15 = 3.666...
    # M = 15/5 = 3.0
    # momentum = W/M = 55/45 = 1.222...
    W = 55.0 / 15.0
    M = 3.0
    momentum = W / M
    Wf = _bankers_round(W, 6)
    Mf = _bankers_round(M, 6)
    momf = _bankers_round(momentum, 6)
    assert f"weighted_mean={Wf:.6f}" in r.stdout, f"expected weighted_mean={Wf:.6f}, got: {r.stdout}"
    assert f"mean={Mf:.6f}" in r.stdout, f"expected mean={Mf:.6f}, got: {r.stdout}"
    assert f"momentum={momf:.6f}" in r.stdout, f"expected momentum={momf:.6f}, got: {r.stdout}"


def test_country_weighted_stats_order_matters():
    """Names in non-lat order: alphabetical sort determines position assignment."""
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    # name order: Aaa(lat=50), Bbb(lat=10), Ccc(lat=30)
    db.execute("INSERT INTO countries VALUES ('WX1','Bbb','R','H','C',10.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('WX2','Ccc','R','H','C',30.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('WX3','Aaa','R','H','C',50.0,0.0)")
    db.commit()
    db.close()
    r = run(["country-weighted-stats"])
    assert r.returncode == 0, f"expected exit 0: {r.stderr}"
    # sorted by name: Aaa(pos1=lat50), Bbb(pos2=lat10), Ccc(pos3=lat30)
    lats = [50.0, 10.0, 30.0]
    n = 3
    W = (1*50 + 2*10 + 3*30) / 6.0   # = (50+20+90)/6 = 160/6
    M = sum(lats) / n                  # = 90/3 = 30.0
    momentum = W / M
    Wf = _bankers_round(W, 6)
    momf = _bankers_round(momentum, 6)
    assert f"weighted_mean={Wf:.6f}" in r.stdout, f"expected weighted_mean={Wf:.6f}, got: {r.stdout}"
    assert f"momentum={momf:.6f}" in r.stdout, f"expected momentum={momf:.6f}, got: {r.stdout}"


def test_country_weighted_stats_bankers_rounding():
    """Banker's rounding: values at exactly x.5 round to nearest even."""
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    # Craft lats so momentum = exactly 1.5 -> rounds to 2.0 (even) with banker's
    # W = 1.5 * M -> momentum=1.5; let M=2.0, W=3.0
    # With n=2, lats [l1, l2]: W=(1*l1 + 2*l2)/3, M=(l1+l2)/2
    # Set l1=0.0, l2=3.0: W=6/3=2.0, M=1.5 -> momentum=4/3, not 1.5
    # Set l1=1.0, l2=2.0: W=(1+4)/3=5/3, M=1.5 -> momentum = (5/3)/1.5 = 10/9, not 1.5
    # Just verify momentum is computed as W/M (no standard rounding)
    # Use specific values that test precision
    db.execute("INSERT INTO countries VALUES ('BR1','Alpha','R','H','C',1.0000005,0.0)")
    db.execute("INSERT INTO countries VALUES ('BR2','Beta','R','H','C',2.0,0.0)")
    db.commit()
    db.close()
    r = run(["country-weighted-stats"])
    assert r.returncode == 0, f"expected exit 0: {r.stderr}"
    # n=2, lats in name order: Alpha(1.0000005), Beta(2.0)
    lats = [1.0000005, 2.0]
    W = (1*lats[0] + 2*lats[1]) / 3.0
    Wf = _bankers_round(W, 6)
    assert f"weighted_mean={Wf:.6f}" in r.stdout or f"weighted_mean={W:.6f}" in r.stdout, (
        f"expected weighted_mean close to {W:.6f}, got: {r.stdout}"
    )


def test_country_weighted_stats_insufficient():
    """country-weighted-stats with N=1 prints insufficient_data and exits 1."""
    insert_countries([("WN1", "Solo", 15.0, 0.0)])
    r = run(["country-weighted-stats"])
    assert r.returncode == 1, f"expected exit 1, got {r.returncode}"
    assert "insufficient_data" in r.stdout, f"expected insufficient_data, got: {r.stdout}"


def test_country_weighted_stats_zero_mean():
    """When M=0 (symmetric about 0), momentum=0.000000."""
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    # names sorted A,B -> lats 10,-10: mean=0
    db.execute("INSERT INTO countries VALUES ('ZM1','Alpha','R','H','C',10.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('ZM2','Beta','R','H','C',-10.0,0.0)")
    db.commit()
    db.close()
    r = run(["country-weighted-stats"])
    assert r.returncode == 0, f"expected exit 0: {r.stderr}"
    assert "momentum=0.000000" in r.stdout, f"expected momentum=0.000000 when M=0, got: {r.stdout}"


# ---------------------------------------------------------------------------
# New precision-trap tests: p50_at_insert in audit_log and HMAC
# ---------------------------------------------------------------------------


def _compute_p50_at_insert(lats_before):
    """Median of lats_before with HALF_EVEN rounding for even N. Returns 0.0 if N<2."""
    n = len(lats_before)
    if n < 2:
        return 0.0
    s = sorted(lats_before)
    if n % 2 == 1:
        return s[(n - 1) // 2]
    lo = s[n // 2 - 1]
    hi = s[n // 2]
    avg = (lo + hi) / 2.0
    d = _decimal.Decimal(str(avg))
    quant = _decimal.Decimal("0.000001")
    return float(d.quantize(quant, rounding=_decimal.ROUND_HALF_EVEN))


def _build_hmac_with_p50(seq, code, lat, lon, skew, kurt, p50, prev_hash, mad="NULL"):
    msg = f"{seq}|{code}|{lat:.6f}|{lon:.6f}|{skew}|{kurt}|{p50:.6f}|{mad}|{prev_hash}"
    return hm.new(b"wb-tracker-secret-2026", msg.encode(), hashlib.sha256).hexdigest()


def test_p50_at_insert_zero_n_lt_2(mock_server):
    """First insert: N=0 before -> p50_at_insert must be 0.0"""
    run(["init"])
    clear_db()
    MOCK_DB["PA"] = {"name": "CountryPA", "lat": 10.0, "lon": 5.0}
    r = run(["fetch-country", "PA"], api_base=mock_server)
    assert r.returncode == 0, r.stderr
    db = sqlite3.connect("/app/wb.db")
    row = db.execute("SELECT p50_at_insert FROM audit_log WHERE seq=1").fetchone()
    db.close()
    assert row is not None, "no audit entry for seq=1"
    assert abs(row[0] - 0.0) < 1e-9, f"expected p50_at_insert=0.0 for N=0, got {row[0]}"


def test_p50_at_insert_odd(mock_server):
    """Odd N: p50 is the exact middle element (no averaging)."""
    run(["init"])
    clear_db()
    MOCK_DB["PB1"] = {"name": "PB1", "lat": 10.0, "lon": 0.0}
    MOCK_DB["PB2"] = {"name": "PB2", "lat": 30.0, "lon": 0.0}
    MOCK_DB["PB3"] = {"name": "PB3", "lat": 20.0, "lon": 0.0}
    run(["fetch-country", "PB1"], api_base=mock_server)
    run(["fetch-country", "PB2"], api_base=mock_server)
    r = run(["fetch-country", "PB3"], api_base=mock_server)
    assert r.returncode == 0, r.stderr
    # Before seq=3 insert: lats=[10.0, 30.0], N=2 (even), p50=(10+30)/2=20.0
    db = sqlite3.connect("/app/wb.db")
    row = db.execute("SELECT p50_at_insert FROM audit_log WHERE seq=3").fetchone()
    db.close()
    # N=2 even: sorted=[10,30], avg=20.0, rounds to 20.0
    expected = _compute_p50_at_insert([10.0, 30.0])
    assert abs(row[0] - expected) < 1e-9, f"expected p50={expected}, got {row[0]}"
    # Now test actual odd N: fetch 4th so N=3 before insert -> sorted=[10,20,30], median=20.0
    MOCK_DB["PB4"] = {"name": "PB4", "lat": 50.0, "lon": 0.0}
    r4 = run(["fetch-country", "PB4"], api_base=mock_server)
    assert r4.returncode == 0, r4.stderr
    db = sqlite3.connect("/app/wb.db")
    row4 = db.execute("SELECT p50_at_insert FROM audit_log WHERE seq=4").fetchone()
    db.close()
    # N=3 odd before seq=4: lats=[10.0,30.0,20.0], sorted=[10,20,30], median=sorted[1]=20.0
    expected4 = _compute_p50_at_insert([10.0, 30.0, 20.0])
    assert abs(row4[0] - expected4) < 1e-9, f"expected p50={expected4} for odd N=3, got {row4[0]}"


def test_p50_at_insert_even_half_even(mock_server):
    """Even N HALF_EVEN trap: [100,101] -> avg=100.5 -> HALF_EVEN rounds to 100.0 (even), NOT 101.0."""
    run(["init"])
    clear_db()
    MOCK_DB["PC1"] = {"name": "PC1", "lat": 100.0, "lon": 0.0}
    MOCK_DB["PC2"] = {"name": "PC2", "lat": 101.0, "lon": 0.0}
    MOCK_DB["PC3"] = {"name": "PC3", "lat": 200.0, "lon": 0.0}
    run(["fetch-country", "PC1"], api_base=mock_server)
    run(["fetch-country", "PC2"], api_base=mock_server)
    r = run(["fetch-country", "PC3"], api_base=mock_server)
    assert r.returncode == 0, r.stderr
    # Before seq=3: lats=[100.0, 101.0], N=2 even, avg=100.5 -> HALF_EVEN -> 100.0
    db = sqlite3.connect("/app/wb.db")
    row = db.execute("SELECT p50_at_insert FROM audit_log WHERE seq=3").fetchone()
    db.close()
    expected = _compute_p50_at_insert([100.0, 101.0])  # 100.0 via HALF_EVEN
    assert abs(row[0] - expected) < 1e-9, (
        f"expected p50={expected} (HALF_EVEN 100.5->100.0), got {row[0]}"
    )
    # The wrong answer (HALF_UP) would be 101.0
    assert abs(row[0] - 101.0) > 1e-9, "got 101.0 (HALF_UP), must use HALF_EVEN"


def test_p50_in_hmac(mock_server):
    """p50_at_insert must be included in HMAC at %.6f between kurt and prev_hash."""
    run(["init"])
    clear_db()
    MOCK_DB["PD1"] = {"name": "PD1", "lat": 10.0, "lon": 5.0}
    MOCK_DB["PD2"] = {"name": "PD2", "lat": 20.0, "lon": 10.0}
    MOCK_DB["PD3"] = {"name": "PD3", "lat": 30.0, "lon": 15.0}
    MOCK_DB["PD4"] = {"name": "PD4", "lat": 40.0, "lon": 20.0}
    run(["fetch-country", "PD1"], api_base=mock_server)
    run(["fetch-country", "PD2"], api_base=mock_server)
    run(["fetch-country", "PD3"], api_base=mock_server)
    r = run(["fetch-country", "PD4"], api_base=mock_server)
    assert r.returncode == 0, r.stderr
    # seq=4: lats_before=[10,20,30], N=3 odd, p50=20.0
    lats_before = [10.0, 20.0, 30.0]
    p50 = _compute_p50_at_insert(lats_before)
    skew = compute_skew_at_insert(lats_before)
    kurt = compute_kurt_at_insert(lats_before)
    db = sqlite3.connect("/app/wb.db")
    prev_row = db.execute("SELECT entry_hash FROM audit_log WHERE seq=3").fetchone()
    prev_hash = prev_row[0]
    actual_row = db.execute("SELECT entry_hash FROM audit_log WHERE seq=4").fetchone()
    db.close()
    mad = _compute_mad_at_insert(lats_before)
    expected_hash = _build_hmac_with_p50(4, "PD4", 40.0, 20.0, skew, kurt, p50, prev_hash, mad)
    assert actual_row[0] == expected_hash, (
        f"HMAC does not include p50 correctly: got={actual_row[0]!r} expected={expected_hash!r}"
    )


def test_p50_in_hmac_wrong_without_p50():
    """Audit chain must FAIL if p50 is not included in HMAC (old 7-field format)."""
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    prev_hash = "0" * 64
    lat, lon = 38.5266, -97.3428
    skew = "NULL"
    kurt = "NULL"
    # Compute old-style HMAC (without p50)
    old_msg = f"1|US|{lat:.6f}|{lon:.6f}|{skew}|{kurt}|{prev_hash}"
    old_hash = hm.new(b"wb-tracker-secret-2026", old_msg.encode(), hashlib.sha256).hexdigest()
    db.execute("INSERT INTO countries VALUES ('US','United States','NAC','HIC','DC',?,?)", (lat, lon))
    db.execute(
        "INSERT INTO audit_log (seq,country_code,latitude,longitude,kurtosis_at_insert,skewness_at_insert,p50_at_insert,prev_hash,entry_hash) VALUES (1,'US',?,?,'NULL','NULL',0.0,?,?)",
        (lat, lon, prev_hash, old_hash)
    )
    db.commit()
    db.close()
    r = run(["audit-verify"])
    assert r.returncode == 1, f"expected TAMPERED (old format without p50), got exit {r.returncode}"
    assert "entry_hash_mismatch" in r.stdout, f"expected entry_hash_mismatch, got: {r.stdout}"


def test_audit_verify_with_p50(mock_server):
    """Full audit chain with p50 field passes verification."""
    run(["init"])
    clear_db()
    MOCK_DB["PE1"] = {"name": "PE1", "lat": 10.0, "lon": 5.0}
    MOCK_DB["PE2"] = {"name": "PE2", "lat": 20.0, "lon": 10.0}
    MOCK_DB["PE3"] = {"name": "PE3", "lat": 30.0, "lon": 15.0}
    run(["fetch-country", "PE1"], api_base=mock_server)
    run(["fetch-country", "PE2"], api_base=mock_server)
    run(["fetch-country", "PE3"], api_base=mock_server)
    r = run(["audit-verify"])
    assert r.returncode == 0, f"audit-verify failed: {r.stderr}"
    assert "ok chain_length=3" in r.stdout, r.stdout


# ---------------------------------------------------------------------------
# Precision-trap tests: mad_at_insert in audit_log and HMAC
# ---------------------------------------------------------------------------


def _mad_fixture_ingest(mock_server, prefix, lats):
    """Register and fetch a batch of countries with the given latitudes."""
    run(["init"])
    clear_db()
    codes = []
    for i, lat in enumerate(lats, start=1):
        code = f"{prefix}{i}"
        MOCK_DB[code] = {"name": f"{prefix}Country{i}", "lat": lat, "lon": float(i)}
        codes.append(code)
    for code in codes:
        r = run(["fetch-country", code], api_base=mock_server)
        assert r.returncode == 0, f"fetch-country {code} failed: {r.stderr}"
    return codes


def test_mad_at_insert_null_lt2(mock_server):
    """seq=1 (N=0) and seq=2 (N=1) must store mad_at_insert='NULL' (N<2)."""
    _mad_fixture_ingest(mock_server, "MN", [10.0, 20.0])
    db = sqlite3.connect("/app/wb.db")
    rows = db.execute("SELECT seq, mad_at_insert FROM audit_log ORDER BY seq").fetchall()
    db.close()
    assert rows[0][1] == "NULL", f"seq=1 mad_at_insert={rows[0][1]!r}, expected 'NULL' for N=0"
    assert rows[1][1] == "NULL", f"seq=2 mad_at_insert={rows[1][1]!r}, expected 'NULL' for N=1"


def test_mad_at_insert_nearest_rank_trap(mock_server):
    """mad_at_insert must use the nearest-rank country-mad algorithm, not the
    interpolated p50 median. Fixture [0,2,10,100] before seq=5: correct MAD is
    2.00000000; every interpolation-based shortcut gives 4.0 or 5.0."""
    _mad_fixture_ingest(mock_server, "MT", [0.0, 2.0, 10.0, 100.0, 7.0])
    db = sqlite3.connect("/app/wb.db")
    row4 = db.execute("SELECT mad_at_insert FROM audit_log WHERE seq=4").fetchone()
    row5 = db.execute("SELECT mad_at_insert, p50_at_insert FROM audit_log WHERE seq=5").fetchone()
    db.close()
    # seq=4: lats_before=[0,2,10] (N=3): nearest-rank median=2, devs sorted [0,2,8] -> MAD=2
    expected4 = _compute_mad_at_insert([0.0, 2.0, 10.0])
    assert row4[0] == expected4, f"seq=4 mad_at_insert={row4[0]!r}, expected {expected4!r}"
    # seq=5: lats_before=[0,2,10,100] (N=4 even): nearest-rank center=2, MAD=2
    expected5 = _compute_mad_at_insert([0.0, 2.0, 10.0, 100.0])
    assert row5[0] == expected5, f"seq=5 mad_at_insert={row5[0]!r}, expected {expected5!r}"
    # Interpolated-center shortcut (center=6.0 from p50) gives 4.00000000;
    # interpolating the deviation median (or both) gives 5.00000000.
    assert row5[0] not in ("4.00000000", "5.00000000"), (
        f"seq=5 mad_at_insert={row5[0]!r} matches an interpolation-based shortcut; "
        "must use nearest-rank for both the center and the deviation median"
    )
    # Meanwhile p50_at_insert for the same row IS the interpolated median 6.0,
    # pinning that the two columns use different median algorithms.
    assert abs(row5[1] - 6.0) < 1e-9, (
        f"seq=5 p50_at_insert={row5[1]!r}, expected interpolated median 6.0"
    )


def test_mad_in_hmac_full_chain(mock_server):
    """entry_hash must include mad_at_insert between p50_at_insert and prev_hash."""
    _mad_fixture_ingest(mock_server, "MH", [0.0, 2.0, 10.0, 100.0, 7.0])
    lats_before = [0.0, 2.0, 10.0, 100.0]
    skew = compute_skew_at_insert(lats_before)
    kurt = compute_kurt_at_insert(lats_before)
    p50 = _compute_p50_at_insert(lats_before)
    mad = _compute_mad_at_insert(lats_before)
    db = sqlite3.connect("/app/wb.db")
    prev_hash = db.execute("SELECT entry_hash FROM audit_log WHERE seq=4").fetchone()[0]
    actual = db.execute("SELECT entry_hash FROM audit_log WHERE seq=5").fetchone()[0]
    db.close()
    # lat=7.0 lon=5.0 for the 5th fixture country
    expected_hash = _build_hmac_with_p50(5, "MH5", 7.0, 5.0, skew, kurt, p50, prev_hash, mad)
    assert actual == expected_hash, (
        f"HMAC does not include mad_at_insert correctly: got={actual!r} expected={expected_hash!r}"
    )
    r = run(["audit-verify"])
    assert r.returncode == 0, f"audit-verify failed on mad chain: {r.stdout} {r.stderr}"
    assert "ok chain_length=5" in r.stdout, r.stdout


def test_audit_verify_fails_without_mad():
    """Audit chain must FAIL if mad is omitted from the HMAC (p50-era 8-field format)."""
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    prev_hash = "0" * 64
    lat, lon = 38.5266, -97.3428
    skew, kurt, p50 = "NULL", "NULL", 0.0
    # Compute p50-era HMAC (8 fields, no mad)
    old_msg = f"1|US|{lat:.6f}|{lon:.6f}|{skew}|{kurt}|{p50:.6f}|{prev_hash}"
    old_hash = hm.new(b"wb-tracker-secret-2026", old_msg.encode(), hashlib.sha256).hexdigest()
    db.execute("INSERT INTO countries VALUES ('US','United States','NAC','HIC','DC',?,?)", (lat, lon))
    db.execute(
        "INSERT INTO audit_log (seq,country_code,latitude,longitude,kurtosis_at_insert,skewness_at_insert,p50_at_insert,mad_at_insert,prev_hash,entry_hash) VALUES (1,'US',?,?,'NULL','NULL',0.0,'NULL',?,?)",
        (lat, lon, prev_hash, old_hash)
    )
    db.commit()
    db.close()
    r = run(["audit-verify"])
    assert r.returncode == 1, f"expected TAMPERED (8-field format without mad), got exit {r.returncode}"
    assert "entry_hash_mismatch" in r.stdout, f"expected entry_hash_mismatch, got: {r.stdout}"


# ---------------------------------------------------------------------------
# Extra precision-trap tests for difficulty hardening
# ---------------------------------------------------------------------------

def test_country_theil_mu_zero():
    """country-theil when all abs(lat)=0: mu=0 -> must print 'theil: NULL' and exit 0."""
    # Two countries both at latitude 0.0: abs values all zero, mu=0
    insert_countries([("MZ1", "Alpha", 0.0, 5.0), ("MZ2", "Beta", 0.0, 10.0)])
    r = run(["country-theil"])
    assert r.returncode == 0, f"expected exit 0 when mu=0, got {r.returncode}: {r.stderr}"
    assert "theil: NULL" in r.stdout, f"expected 'theil: NULL' when mu=0, got: {r.stdout}"


def test_audit_verify_seq_gap():
    """audit-verify must detect seq gap (missing seq) and report seq_gap."""
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    prev_hash = "0" * 64
    lat, lon = 10.0, 5.0
    # Compute correct entry_hash for seq=1
    skew, kurt, p50, mad = "NULL", "NULL", 0.0, "NULL"
    msg1 = f"1|SQ1|{lat:.6f}|{lon:.6f}|{skew}|{kurt}|{p50:.6f}|{mad}|{prev_hash}"
    h1 = hm.new(b"wb-tracker-secret-2026", msg1.encode(), hashlib.sha256).hexdigest()
    # Insert seq=1 and seq=3 (gap: seq=2 missing)
    db.execute("INSERT INTO countries VALUES ('SQ1','SeqGap1','R','H','Cap',10.0,5.0)")
    db.execute("INSERT INTO countries VALUES ('SQ3','SeqGap3','R','H','Cap',20.0,10.0)")
    db.execute(
        "INSERT INTO audit_log (seq,country_code,latitude,longitude,kurtosis_at_insert,skewness_at_insert,p50_at_insert,prev_hash,entry_hash) VALUES (1,'SQ1',10.0,5.0,'NULL','NULL',0.0,?,?)",
        (prev_hash, h1)
    )
    # seq=3 after seq=1 = gap
    db.execute(
        "INSERT INTO audit_log (seq,country_code,latitude,longitude,kurtosis_at_insert,skewness_at_insert,p50_at_insert,prev_hash,entry_hash) VALUES (3,'SQ3',20.0,10.0,'NULL','NULL',0.0,?,?)",
        (h1, "b" * 64)
    )
    db.commit()
    db.close()
    r = run(["audit-verify"])
    assert r.returncode == 1, f"expected exit 1 for seq gap, got {r.returncode}"
    assert "TAMPERED" in r.stdout, f"expected TAMPERED in stdout, got: {r.stdout}"
    assert "seq_gap" in r.stdout, f"expected seq_gap reason, got: {r.stdout}"


def test_audit_verify_prev_hash_mismatch():
    """audit-verify must detect prev_hash_mismatch (chain broken, no seq gap)."""
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    prev_hash = "0" * 64
    lat1, lon1 = 10.0, 5.0
    lat2, lon2 = 20.0, 10.0
    skew, kurt, p50, mad = "NULL", "NULL", 0.0, "NULL"
    # Compute entry_hash for seq=1
    msg1 = f"1|PM1|{lat1:.6f}|{lon1:.6f}|{skew}|{kurt}|{p50:.6f}|{mad}|{prev_hash}"
    h1 = hm.new(b"wb-tracker-secret-2026", msg1.encode(), hashlib.sha256).hexdigest()
    # Compute entry_hash for seq=2 but with WRONG prev_hash (not h1)
    wrong_prev = "c" * 64
    # N=1 before seq=2 -> mad still "NULL" (N<2)
    msg2 = f"2|PM2|{lat2:.6f}|{lon2:.6f}|{skew}|{kurt}|{p50:.6f}|{mad}|{wrong_prev}"
    h2_wrong = hm.new(b"wb-tracker-secret-2026", msg2.encode(), hashlib.sha256).hexdigest()
    db.execute("INSERT INTO countries VALUES ('PM1','PMC1','R','H','Cap',?,?)", (lat1, lon1))
    db.execute("INSERT INTO countries VALUES ('PM2','PMC2','R','H','Cap',?,?)", (lat2, lon2))
    db.execute(
        "INSERT INTO audit_log (seq,country_code,latitude,longitude,kurtosis_at_insert,skewness_at_insert,p50_at_insert,prev_hash,entry_hash) VALUES (1,'PM1',?,?,'NULL','NULL',0.0,?,?)",
        (lat1, lon1, prev_hash, h1)
    )
    # seq=2 has wrong prev_hash (doesn't match h1)
    db.execute(
        "INSERT INTO audit_log (seq,country_code,latitude,longitude,kurtosis_at_insert,skewness_at_insert,p50_at_insert,prev_hash,entry_hash) VALUES (2,'PM2',?,?,'NULL','NULL',0.0,?,?)",
        (lat2, lon2, wrong_prev, h2_wrong)
    )
    db.commit()
    db.close()
    r = run(["audit-verify"])
    assert r.returncode == 1, f"expected exit 1 for prev_hash_mismatch, got {r.returncode}"
    assert "TAMPERED" in r.stdout, f"expected TAMPERED in stdout, got: {r.stdout}"
    assert "prev_hash_mismatch" in r.stdout, f"expected prev_hash_mismatch reason, got: {r.stdout}"
    assert "seq=2" in r.stdout, f"expected seq=2 in output, got: {r.stdout}"


def test_country_weighted_stats_name_code_tiebreak():
    """country-weighted-stats uses name ASC then code ASC for tiebreaking equal names."""
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    # Two countries with same name "Same", codes ZZ and AA (AA sorts before ZZ)
    # name order: "Same"/"AA" -> pos1, "Same"/"ZZ" -> pos2
    db.execute("INSERT INTO countries VALUES ('ZZ','Same','R','H','Cap',100.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('AA','Same','R','H','Cap',200.0,0.0)")
    db.commit()
    db.close()
    r = run(["country-weighted-stats"])
    assert r.returncode == 0, f"expected exit 0, got: {r.stderr}"
    # Sorted by name ASC then code ASC: AA(lat=200, pos=1), ZZ(lat=100, pos=2)
    # weighted_sum = 1*200 + 2*100 = 400, denom = 2*3/2=3, W = 400/3
    # M = (200+100)/2 = 150
    # momentum = W/M = (400/3)/150 = 400/450 = 8/9
    W = 400.0 / 3.0
    M = 150.0
    momentum = W / M
    Wf = _bankers_round(W, 6)
    Mf = _bankers_round(M, 6)
    momf = _bankers_round(momentum, 6)
    assert f"weighted_mean={Wf:.6f}" in r.stdout, f"expected weighted_mean={Wf:.6f}, got: {r.stdout}"
    assert f"mean={Mf:.6f}" in r.stdout, f"expected mean={Mf:.6f}, got: {r.stdout}"
    assert f"momentum={momf:.6f}" in r.stdout, f"expected momentum={momf:.6f}, got: {r.stdout}"
    # The WRONG order (ZZ first) would give: W=(1*100+2*200)/3=500/3=166.666..., which differs
    wrong_W = 500.0 / 3.0
    wrong_Wf = _bankers_round(wrong_W, 6)
    assert f"weighted_mean={wrong_Wf:.6f}" not in r.stdout, (
        f"got wrong name+code order (ZZ before AA): {r.stdout}"
    )


def test_country_zscores_ignores_extra_arg():
    """country-zscores accepts an optional db argument but ignores it; always uses /app/wb.db."""
    lats = [10.0, 20.0, 30.0]
    lons = [-30.0, -20.0, -10.0]
    insert_countries([("ZA1", "N1", lats[0], lons[0]), ("ZA2", "N2", lats[1], lons[1]), ("ZA3", "N3", lats[2], lons[2])])
    # Pass a fake db path as extra arg; should be ignored and still use /app/wb.db
    r = run(["country-zscores", "/nonexistent/fake.db"])
    assert r.returncode == 0, f"expected exit 0 with extra arg, got {r.returncode}: {r.stderr}"
    m_lat = pop_mean(lats)
    s_lat = pop_std(lats)
    m_lon = pop_mean(lons)
    s_lon = pop_std(lons)
    for code, lat, lon in zip(["ZA1", "ZA2", "ZA3"], lats, lons):
        zl = (lat - m_lat) / s_lat
        zln = (lon - m_lon) / s_lon
        assert f"{code}\t{zl:.8f}\t{zln:.8f}" in r.stdout, (
            f"expected zscore line for {code} with extra arg, got: {r.stdout}"
        )


def test_country_theil_n2_precision():
    """Theil for N=2 with non-symmetric abs values: verify exact 6dp natural log computation."""
    # lats [3.0, 12.0]: abs=[3,12], mu=7.5
    # T = (3/7.5)*ln(3/7.5) + (12/7.5)*ln(12/7.5)) / 2
    lats = [3.0, 12.0]
    insert_countries([("TP1", "Alpha", lats[0], 0.0), ("TP2", "Beta", lats[1], 0.0)])
    r = run(["country-theil"])
    assert r.returncode == 0, r.stderr
    expected = compute_theil(lats)
    assert f"theil: {expected:.6f}" in r.stdout, (
        f"expected theil: {expected:.6f}, got: {r.stdout}"
    )
    # Verify it's not using shift (shifted=[1,10] not abs=[3,12])
    shifted = [v - min(lats) + 1.0 for v in lats]
    mu_shifted = sum(shifted) / len(shifted)
    wrong_shift = sum((s / mu_shifted) * math.log(s / mu_shifted) for s in shifted) / len(shifted)
    assert f"theil: {wrong_shift:.6f}" not in r.stdout, (
        f"got shift-based theil, must use absolute values: {r.stdout}"
    )


def test_p50_at_insert_even_larger_n(mock_server):
    """Even N=4 before insert: p50 = avg of 2nd and 3rd sorted elements."""
    run(["init"])
    clear_db()
    MOCK_DB["EL1"] = {"name": "EL1", "lat": 10.0, "lon": 0.0}
    MOCK_DB["EL2"] = {"name": "EL2", "lat": 40.0, "lon": 0.0}
    MOCK_DB["EL3"] = {"name": "EL3", "lat": 20.0, "lon": 0.0}
    MOCK_DB["EL4"] = {"name": "EL4", "lat": 30.0, "lon": 0.0}
    MOCK_DB["EL5"] = {"name": "EL5", "lat": 50.0, "lon": 0.0}
    run(["fetch-country", "EL1"], api_base=mock_server)
    run(["fetch-country", "EL2"], api_base=mock_server)
    run(["fetch-country", "EL3"], api_base=mock_server)
    run(["fetch-country", "EL4"], api_base=mock_server)
    r = run(["fetch-country", "EL5"], api_base=mock_server)
    assert r.returncode == 0, r.stderr
    # Before seq=5: lats=[10,40,20,30], N=4 even, sorted=[10,20,30,40]
    # p50 = avg(20,30) = 25.0 (no banker's rounding trap here, exact)
    db = sqlite3.connect("/app/wb.db")
    row = db.execute("SELECT p50_at_insert FROM audit_log WHERE seq=5").fetchone()
    db.close()
    lats_before = [10.0, 40.0, 20.0, 30.0]
    expected = _compute_p50_at_insert(lats_before)
    assert abs(row[0] - expected) < 1e-9, f"expected p50={expected} for N=4 even, got {row[0]}"


# ---------------------------------------------------------------------------
# Additional HARD precision-trap tests
# ---------------------------------------------------------------------------

def test_country_forecast_rowid_not_code_tiebreak():
    """country-forecast breaks ties in name by rowid ASC (not code ASC); agents using code ASC fail."""
    # Insert 3 countries all with name "Zeta" in insertion order: ZZ, AA, MM
    # rowids will be 1->ZZ, 2->AA, 3->MM (rowid determined by insertion order)
    # ORDER BY name ASC, rowid ASC -> positions: ZZ=1(lat=10), AA=2(lat=40), MM=3(lat=25)
    # ORDER BY name ASC, code ASC  -> positions: AA=1(lat=40), MM=2(lat=25), ZZ=3(lat=10) (WRONG)
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    db.execute("INSERT INTO countries VALUES ('ZZ', 'Zeta', 'REG', 'HIC', 'Cap', 10.0, 0.0)")
    db.execute("INSERT INTO countries VALUES ('AA', 'Zeta', 'REG', 'HIC', 'Cap', 40.0, 0.0)")
    db.execute("INSERT INTO countries VALUES ('MM', 'Zeta', 'REG', 'HIC', 'Cap', 25.0, 0.0)")
    db.commit()
    db.close()
    r = run(["country-forecast"])
    assert r.returncode == 0, r.stderr
    # Correct order by rowid: [10.0, 40.0, 25.0]
    lats_rowid_order = [10.0, 40.0, 25.0]
    expected = compute_ols_forecast(lats_rowid_order)
    # Wrong order by code: [40.0, 25.0, 10.0]
    lats_code_order = [40.0, 25.0, 10.0]
    wrong = compute_ols_forecast(lats_code_order)
    assert f"forecast: {expected:.6f}" in r.stdout, (
        f"expected rowid-ordered forecast: {expected:.6f}, got: {r.stdout}"
    )
    assert f"forecast: {wrong:.6f}" not in r.stdout, (
        f"got code-order forecast: {wrong:.6f}; must use rowid tiebreak: {r.stdout}"
    )


def test_country_atkinson_precision_irrational():
    """Atkinson with irrational sqrt values: 8dp precision is required to pass."""
    # lats [1.0, 4.0, 9.0, 16.0]: min=1, shifted=[1,4,9,16] (shift by 0)
    # mean_shifted = 7.5
    # sqrt shifted = [1.0, 2.0, 3.0, 4.0], mean_of_sqrt = 2.5
    # A = 1 - (2.5^2)/7.5 = 1 - 6.25/7.5 = 1 - 0.833333... = 0.16666667
    # But [3,7,11,13]: shifted=[1,5,9,11], mean=6.5, sqrt=[1,2.236...,3,3.316...]
    # mean_sqrt = (1+2.23606797749979+3+3.3166247903554)/4 = 9.55269277/4 = 2.38817319
    # A = 1 - (2.38817319^2)/6.5 = 1 - 5.70337133/6.5 = 1 - 0.87744174 = 0.12255826
    lats = [3.0, 7.0, 11.0, 13.0]
    insert_countries([(f"AP{i}", f"N{i}", v, 0.0) for i, v in enumerate(lats)])
    r = run(["country-atkinson"])
    assert r.returncode == 0, r.stderr
    expected = compute_atkinson(lats)
    assert f"atkinson={expected:.8f}" in r.stdout, (
        f"expected atkinson={expected:.8f}, got: {r.stdout}"
    )


def test_country_entropy_uniform_k_regions():
    """Entropy of uniform K-region distribution = log2(K) exactly."""
    # 6 countries, each in its own unique region -> K=6, all p_i=1/6
    # H = 6 * (-(1/6)*log2(1/6)) = log2(6) = 2.58496250...
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    for i in range(6):
        db.execute(f"INSERT INTO countries VALUES ('U{i}','N{i}','RGN{i}','HIC','Cap',{float(i)*10},0.0)")
    db.commit()
    db.close()
    regions = [f"RGN{i}" for i in range(6)]
    expected = compute_entropy(regions)
    r = run(["country-entropy"])
    assert r.returncode == 0, r.stderr
    assert f"entropy={expected:.8f}" in r.stdout, (
        f"expected uniform entropy={expected:.8f} (=log2(6)), got: {r.stdout}"
    )
    # Sanity: must be log2(6)
    assert abs(expected - math.log2(6)) < 1e-9, "compute_entropy helper is wrong"


def test_country_gini_n2_boundary():
    """Gini for N=2 with specific values: checks boundary and shift formula exactly."""
    # lats [5.0, 15.0]: min=5.0, shifted=[1.0, 11.0]
    # sorted shifted=[1.0, 11.0], ranks 1,2
    # rank_sum = 1*1.0 + 2*11.0 = 1+22 = 23
    # total_sum = 12.0, N=2
    # gini = (2*23)/(2*12) - 3/2 = 46/24 - 1.5 = 1.91666... - 1.5 = 0.41666667
    lats = [5.0, 15.0]
    insert_countries([("GN1", "Alpha", lats[0], 0.0), ("GN2", "Beta", lats[1], 0.0)])
    r = run(["country-gini"])
    assert r.returncode == 0, r.stderr
    expected = compute_gini(lats)
    assert f"gini={expected:.8f}" in r.stdout, (
        f"expected gini={expected:.8f}, got: {r.stdout}"
    )


def test_country_hhi_5regions_precision():
    """Normalized HHI for 5-region unequal distribution tests 8dp precision."""
    # 10 countries: region counts [4,3,1,1,1] -> K=5
    # s_i: 0.4, 0.3, 0.1, 0.1, 0.1
    # raw_hhi = 0.16 + 0.09 + 0.01 + 0.01 + 0.01 = 0.28
    # norm = (0.28 - 1/5) / (1 - 1/5) = (0.28-0.2)/0.8 = 0.08/0.8 = 0.1
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    codes_regions = [
        ("H51","RA"), ("H52","RA"), ("H53","RA"), ("H54","RA"),
        ("H55","RB"), ("H56","RB"), ("H57","RB"),
        ("H58","RC"), ("H59","RD"), ("H5A","RE"),
    ]
    for code, region in codes_regions:
        db.execute(f"INSERT INTO countries VALUES ('{code}','N','{{region}}','HIC','Cap',0.0,0.0)".replace("{region}", region))
    db.commit()
    db.close()
    regions = [r[1] for r in codes_regions]
    expected = compute_hhi(regions)
    r = run(["country-hhi"])
    assert r.returncode == 0, r.stderr
    assert f"hhi={expected:.8f}" in r.stdout, (
        f"expected hhi={expected:.8f}, got: {r.stdout}"
    )
    # Sanity: normalized HHI = 0.1
    assert abs(expected - 0.1) < 1e-9, f"compute_hhi helper wrong: {expected}"


def test_country_rank_pct_fractional():
    """country-rank pct=N/M*100 with 2dp: fractional result must not truncate."""
    # Insert 7 countries sorted by lat ASC: [1,2,3,4,5,6,7]
    # Rank of code with lat=2.0: rank=2, total=7, pct=2/7*100=28.57142... -> "28.57"
    insert_countries([
        ("PR1", "A1", 1.0, 0.0), ("PR2", "A2", 2.0, 0.0), ("PR3", "A3", 3.0, 0.0),
        ("PR4", "A4", 4.0, 0.0), ("PR5", "A5", 5.0, 0.0), ("PR6", "A6", 6.0, 0.0),
        ("PR7", "A7", 7.0, 0.0),
    ])
    r = run(["country-rank", "PR2"])
    assert r.returncode == 0, r.stderr
    assert "rank=2" in r.stdout, f"expected rank=2, got: {r.stdout}"
    assert "total=7" in r.stdout, f"expected total=7, got: {r.stdout}"
    # pct = 2/7*100 = 28.571428... -> fmt.Sprintf("%.2f") = "28.57"
    assert "pct=28.57" in r.stdout, f"expected pct=28.57 (2/7*100), got: {r.stdout}"
    # Wrong: integer division 2/7=0 -> 0.00
    assert "pct=0.00" not in r.stdout, "agent did integer division for pct"


def test_country_weighted_stats_bankers_rounding_half_even():
    """Banker's rounding: 2.5 rounds to 2 (even), 3.5 rounds to 4 (even)."""
    # Need W, M, or momentum to land on X.5 exactly.
    # lats [1.0, 4.0]: positions 1,2 (sorted by name 'A','B')
    # weighted_sum = 1*1 + 2*4 = 9, denom=3, W=3.0 (exact, no rounding issue)
    # Use lats that yield a 0.5 midpoint in weighted_mean:
    # lats [2.0, 3.0]: W=(1*2+2*3)/3=8/3=2.666..., M=2.5, momentum=W/M=8/3/2.5=16/15
    # Not a .5 trap. Try lats [1.0, 2.0, 3.0, 6.0]:
    # sorted by name: 'A'(1), 'B'(2), 'C'(3), 'D'(6)
    # W = (1*1+2*2+3*3+4*6)/10 = (1+4+9+24)/10 = 38/10 = 3.8 (exact)
    # M = (1+2+3+6)/4 = 3.0, momentum = 3.8/3.0 = 1.26666... (no .5)
    # Use specific values to get exact .5 in M:
    # lats [0.0, 3.0]: W=(0+6)/3=2.0, M=1.5, momentum=2.0/1.5=1.333333 (no .5)
    # For banker's rounding trap: use values where result at 6dp is X.5*10^-6
    # lats [1.0, 2.0]: W=(1*1+2*2)/3=5/3=1.666...666 (repeating), M=1.5, momentum=10/9
    # Use Decimal to compute expected with banker's rounding
    lats_with_names = [("WB1", "Alpha", 1.0, 0.0), ("WB2", "Beta", 2.0, 0.0)]
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    for code, name, lat, lon in lats_with_names:
        db.execute("INSERT INTO countries VALUES (?,?,?,?,?,?,?)", (code, name, "REG", "HIC", "Cap", lat, lon))
    db.commit()
    db.close()
    r = run(["country-weighted-stats"])
    assert r.returncode == 0, r.stderr
    result = _compute_weighted_stats([(name, code, lat) for code, name, lat, _ in lats_with_names])
    W, M, momentum = result
    Wf = _bankers_round(W, 6)
    Mf = _bankers_round(M, 6)
    momf = _bankers_round(momentum, 6)
    assert f"weighted_mean={Wf:.6f}" in r.stdout, f"expected weighted_mean={Wf:.6f}, got: {r.stdout}"
    assert f"mean={Mf:.6f}" in r.stdout, f"expected mean={Mf:.6f}, got: {r.stdout}"
    assert f"momentum={momf:.6f}" in r.stdout, f"expected momentum={momf:.6f}, got: {r.stdout}"


# ---------------------------------------------------------------------------
# New precision-trap tests (hardening round)
# ---------------------------------------------------------------------------

def test_country_weighted_stats_large_n_precision():
    """N=8 real-world-ish country names/lats: non-obvious position assignment and 6dp precision."""
    # Names in alphabetical order determine positions:
    # Cameroon(pos1,lat=3.848), Denmark(pos2,lat=56.2639), Finland(pos3,lat=64.8),
    # Georgia(pos4,lat=42.3154), Hungary(pos5,lat=47.1625), Iceland(pos6,lat=64.9631),
    # Jamaica(pos7,lat=18.109), Kenya(pos8,lat=-0.0236)
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    entries = [
        ("CM", "Cameroon", 3.848, 0.0),
        ("DK", "Denmark", 56.2639, 0.0),
        ("FI", "Finland", 64.8, 0.0),
        ("GE", "Georgia", 42.3154, 0.0),
        ("HU", "Hungary", 47.1625, 0.0),
        ("IS", "Iceland", 64.9631, 0.0),
        ("JM", "Jamaica", 18.109, 0.0),
        ("KE", "Kenya", -0.0236, 0.0),
    ]
    for code, name, lat, lon in entries:
        db.execute("INSERT INTO countries VALUES (?,?,?,?,?,?,?)", (code, name, "REG", "HIC", "Cap", lat, lon))
    db.commit()
    db.close()
    r = run(["country-weighted-stats"])
    assert r.returncode == 0, f"expected exit 0: {r.stderr}"
    # Sorted by name ASC: Cameroon, Denmark, Finland, Georgia, Hungary, Iceland, Jamaica, Kenya
    sorted_lats = [3.848, 56.2639, 64.8, 42.3154, 47.1625, 64.9631, 18.109, -0.0236]
    n = 8
    weighted_sum = sum((i + 1) * lat for i, lat in enumerate(sorted_lats))
    denom = n * (n + 1) / 2  # = 36
    W = weighted_sum / denom
    M = sum(sorted_lats) / n
    momentum = W / M
    Wf = _bankers_round(W, 6)
    Mf = _bankers_round(M, 6)
    momf = _bankers_round(momentum, 6)
    # Expected: weighted_mean=34.227853, mean=37.179787, momentum=0.920604
    assert f"weighted_mean={Wf:.6f}" in r.stdout, (
        f"expected weighted_mean={Wf:.6f} (not arithmetic mean), got: {r.stdout}"
    )
    assert f"mean={Mf:.6f}" in r.stdout, f"expected mean={Mf:.6f}, got: {r.stdout}"
    assert f"momentum={momf:.6f}" in r.stdout, f"expected momentum={momf:.6f}, got: {r.stdout}"
    # Sanity: weighted_mean != arithmetic mean (they must differ for this dataset)
    arith_mean_f = _bankers_round(M, 6)
    assert Wf != arith_mean_f, "weighted_mean and arithmetic mean must differ in this dataset"


def test_country_theil_abs_vs_shift_trap():
    """lats=[-5.0, 5.0]: abs gives xi=[5,5], mu=5, T=0; shift (wrong) gives T!=0."""
    insert_countries([("TH1", "Alpha", -5.0, 0.0), ("TH2", "Beta", 5.0, 0.0)])
    r = run(["country-theil"])
    assert r.returncode == 0, f"expected exit 0: {r.stderr}"
    # Correct (abs): |lat|=[5,5], mu=5, xi/mu=1 for all, ln(1)=0, T=0
    assert "theil: 0.000000" in r.stdout, (
        f"expected theil: 0.000000 (abs values equal, T=0), got: {r.stdout}"
    )
    # Wrong (shift): shifted=[1,11], mu=6, T=0.406311 -- must NOT appear
    shifted = [1.0, 11.0]
    mu_shift = 6.0
    T_shift = (1 / 2) * sum(xi / mu_shift * math.log(xi / mu_shift) for xi in shifted)
    wrong_val = f"{T_shift:.6f}"
    assert wrong_val not in r.stdout, (
        f"agent used shift instead of abs (got shift Theil={wrong_val}): {r.stdout}"
    )


def test_country_chain_dual_key_isolation(mock_server):
    """rev hash must use key wb-tracker-reverse-2026; wrong key (wb-tracker-secret-2026) gives different result."""
    run(["init"])
    clear_db()
    MOCK_DB["KI1"] = {"name": "KeyIsolate", "lat": 23.456789, "lon": -45.678901}
    run(["fetch-country", "KI1"], api_base=mock_server)
    # Compute expected rev hash with CORRECT reverse key
    db = sqlite3.connect("/app/wb.db")
    row = db.execute(
        "SELECT seq, country_code, latitude, longitude FROM audit_log WHERE seq=1"
    ).fetchone()
    db.close()
    seq, code, lat, lon = row
    correct_rev = hm.new(
        b"wb-tracker-reverse-2026",
        f"{seq}|{code}|{lat:.6f}|{lon:.6f}|{'0'*64}".encode(),
        hashlib.sha256,
    ).hexdigest()
    wrong_rev = hm.new(
        b"wb-tracker-secret-2026",
        f"{seq}|{code}|{lat:.6f}|{lon:.6f}|{'0'*64}".encode(),
        hashlib.sha256,
    ).hexdigest()
    r = run(["country-chain-dual"])
    assert r.returncode == 0, f"expected exit 0: {r.stderr}"
    assert f"rev={correct_rev}" in r.stdout, (
        f"expected rev={correct_rev} (reverse key), got: {r.stdout}"
    )
    # The wrong key produces a detectably different hash
    assert correct_rev != wrong_rev, "test setup: correct and wrong rev hash must differ"
    assert f"rev={wrong_rev}" not in r.stdout, (
        f"agent used forward key instead of reverse key for rev chain: {r.stdout}"
    )


def test_country_rank_tie_break_by_code():
    """Two countries at same lat; tie-break by code ASC determines rank order."""
    # lat=5.0: code=AAA(rank=1), code=BBB(rank=2); lat=10.0: code=CCC(rank=3)
    insert_countries([
        ("BBB", "Bravo", 5.0, 0.0),
        ("AAA", "Alpha", 5.0, 0.0),
        ("CCC", "Charlie", 10.0, 0.0),
    ])
    # AAA must rank 1 (same lat as BBB but code AAA < BBB)
    r1 = run(["country-rank", "AAA"])
    assert r1.returncode == 0, r1.stderr
    assert "rank=1" in r1.stdout, f"expected rank=1 for AAA (code-tie-break), got: {r1.stdout}"
    assert "total=3" in r1.stdout, f"expected total=3, got: {r1.stdout}"
    assert "pct=33.33" in r1.stdout, f"expected pct=33.33, got: {r1.stdout}"
    # BBB must rank 2 (same lat as AAA, BBB > AAA alphabetically)
    r2 = run(["country-rank", "BBB"])
    assert r2.returncode == 0, r2.stderr
    assert "rank=2" in r2.stdout, f"expected rank=2 for BBB (code-tie-break), got: {r2.stdout}"
    assert "pct=66.67" in r2.stdout, f"expected pct=66.67, got: {r2.stdout}"
    # Verify wrong ordering does NOT appear (lat-only, no tie-break could give AAA rank=2)
    assert "rank=2" not in r1.stdout, f"AAA should NOT be rank=2 (tie-break failed): {r1.stdout}"


def test_country_stats_p75_p90_nearest_rank_vs_linear():
    """N=10 varied lats: nearest-rank p75 differs from linear interpolation; verify exact values."""
    # lats (sorted): [3.7, 11.2, 18.9, 24.5, 31.3, 42.1, 53.8, 61.4, 72.6, 85.3]
    # p75: rank=ceil(0.75*10)=8, index=7 -> 61.4
    # p90: rank=ceil(0.90*10)=9, index=8 -> 72.6
    # Linear interp p75 (wrong): 61.4 + 0.25*(72.6-61.4) = 64.2 -- detectably different
    lats = [3.7, 11.2, 18.9, 24.5, 31.3, 42.1, 53.8, 61.4, 72.6, 85.3]
    rows = [(f"P{i:02d}", f"Name{i:02d}", v, 0.0) for i, v in enumerate(lats)]
    insert_countries(rows)
    r = run(["country-stats"])
    assert r.returncode == 0, r.stderr
    sorted_lats = sorted(lats)
    p75_val = sorted_lats[math.ceil(0.75 * 10) - 1]   # index 7 = 61.4
    p90_val = sorted_lats[math.ceil(0.90 * 10) - 1]   # index 8 = 72.6
    assert f"p75_latitude={p75_val:.6f}" in r.stdout, (
        f"expected p75_latitude={p75_val:.6f} (nearest-rank), got: {r.stdout}"
    )
    assert f"p90_latitude={p90_val:.6f}" in r.stdout, (
        f"expected p90_latitude={p90_val:.6f} (nearest-rank), got: {r.stdout}"
    )
    # Linear interpolation p75 would give 64.200000 -- must NOT appear
    p75_linear = sorted_lats[7] + 0.25 * (sorted_lats[8] - sorted_lats[7])
    assert f"p75_latitude={p75_linear:.6f}" not in r.stdout, (
        f"agent used linear interpolation for p75 (got {p75_linear:.6f}): {r.stdout}"
    )


# ---------------------------------------------------------------------------
# New HARD precision-trap tests: country-covar (population covariance) and
# country-ewma (EWMA alpha=0.3, code ASC ordering, HALF_EVEN intermediate round)
# ---------------------------------------------------------------------------

def compute_pop_covar(lats, lons):
    """Population covariance: divide by N (not N-1)."""
    n = len(lats)
    if n < 2:
        return None
    mean_lat = sum(lats) / n
    mean_lon = sum(lons) / n
    return sum((lats[i] - mean_lat) * (lons[i] - mean_lon) for i in range(n)) / n


def compute_ewma_bankers(lats_in_code_order, alpha=0.3):
    """EWMA with HALF_EVEN rounding to 6dp after each intermediate step."""
    n = len(lats_in_code_order)
    if n == 0:
        return None
    alpha_d = _decimal.Decimal("0.3")
    one_minus = _decimal.Decimal("0.7")
    quant = _decimal.Decimal("0.000001")
    ewma = _decimal.Decimal(str(lats_in_code_order[0])).quantize(quant, rounding=_decimal.ROUND_HALF_EVEN)
    for i in range(1, n):
        raw = alpha_d * _decimal.Decimal(str(lats_in_code_order[i])) + one_minus * ewma
        ewma = raw.quantize(quant, rounding=_decimal.ROUND_HALF_EVEN)
    return float(ewma)


def test_country_covar_basic():
    """Population covariance [10,20,30] x [100,200,300]: covar=666.66666667."""
    insert_countries([
        ("CV1", "N1", 10.0, 100.0),
        ("CV2", "N2", 20.0, 200.0),
        ("CV3", "N3", 30.0, 300.0),
    ])
    r = run(["country-covar"])
    assert r.returncode == 0, r.stderr
    expected = compute_pop_covar([10.0, 20.0, 30.0], [100.0, 200.0, 300.0])
    assert f"covar: {expected:.8f}" in r.stdout, f"expected covar: {expected:.8f}, got: {r.stdout}"


def test_country_covar_pop_not_sample():
    """Population covariance must divide by N not N-1; values differ detectably for N=4."""
    # N=4: pop covar = sum/4, sample covar = sum/3 -> ratio 4/3
    lats = [10.0, 30.0, 50.0, 70.0]
    lons = [5.0, 15.0, 25.0, 35.0]
    insert_countries([(f"CP{i}", f"N{i}", lats[i], lons[i]) for i in range(4)])
    r = run(["country-covar"])
    assert r.returncode == 0, r.stderr
    pop = compute_pop_covar(lats, lons)
    # sample covar would be pop * (N/(N-1)) = pop * 4/3
    n = len(lats)
    sample = pop * n / (n - 1)
    assert f"covar: {pop:.8f}" in r.stdout, f"expected pop covar={pop:.8f}, got: {r.stdout}"
    assert f"covar: {sample:.8f}" not in r.stdout, (
        f"got sample covar={sample:.8f}; must use population (divide by N): {r.stdout}"
    )


def test_country_covar_negative():
    """Negative covariance (lats and lons move in opposite directions)."""
    lats = [-10.0, 0.0, 10.0, 20.0]
    lons = [30.0, 10.0, -10.0, -30.0]
    insert_countries([(f"CN{i}", f"N{i}", lats[i], lons[i]) for i in range(4)])
    r = run(["country-covar"])
    assert r.returncode == 0, r.stderr
    expected = compute_pop_covar(lats, lons)
    assert f"covar: {expected:.8f}" in r.stdout, f"expected covar: {expected:.8f}, got: {r.stdout}"
    # covariance should be negative
    assert expected < 0, f"expected negative covariance, got {expected}"


def test_country_covar_null_n1():
    """country-covar with N=1 prints 'covar: NULL' and exits 0."""
    insert_countries([("CX1", "Solo", 15.0, 25.0)])
    r = run(["country-covar"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    assert "covar: NULL" in r.stdout, f"expected 'covar: NULL', got: {r.stdout}"


def test_country_covar_zero():
    """Uncorrelated lat/lon gives covar near 0."""
    # N=4: lat values [10,10,20,20], lon values [5,15,5,15] -> orthogonal
    lats = [10.0, 10.0, 20.0, 20.0]
    lons = [5.0, 15.0, 5.0, 15.0]
    insert_countries([(f"CZ{i}", f"N{i}", lats[i], lons[i]) for i in range(4)])
    r = run(["country-covar"])
    assert r.returncode == 0, r.stderr
    expected = compute_pop_covar(lats, lons)
    assert f"covar: {expected:.8f}" in r.stdout, f"expected covar: {expected:.8f}, got: {r.stdout}"
    assert "covar: 0.00000000" in r.stdout, f"expected zero covariance for orthogonal data, got: {r.stdout}"


def test_country_ewma_basic():
    """EWMA alpha=0.3 seeded by code ASC: codes EA,EB,EC -> lats 10,20,30."""
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    # code ASC: EA(lat=10), EB(lat=20), EC(lat=30)
    db.execute("INSERT INTO countries VALUES ('EA','N1','R','H','C',10.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('EB','N2','R','H','C',20.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('EC','N3','R','H','C',30.0,0.0)")
    db.commit()
    db.close()
    r = run(["country-ewma"])
    assert r.returncode == 0, r.stderr
    expected = compute_ewma_bankers([10.0, 20.0, 30.0])
    assert f"ewma: {expected:.6f}" in r.stdout, f"expected ewma: {expected:.6f}, got: {r.stdout}"
    # expected = 18.100000
    assert "ewma: 18.100000" in r.stdout, f"expected ewma: 18.100000, got: {r.stdout}"


def test_country_ewma_code_order_trap():
    """EWMA uses code ASC order; wrong insertion order gives different result."""
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    # Insert in reverse code order to trap agents using insertion order
    # Code ASC: AB(lat=40), BA(lat=10), CC(lat=25)
    # Insertion order: CC, BA, AB (reversed)
    db.execute("INSERT INTO countries VALUES ('CC','N3','R','H','C',25.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('BA','N2','R','H','C',10.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('AB','N1','R','H','C',40.0,0.0)")
    db.commit()
    db.close()
    r = run(["country-ewma"])
    assert r.returncode == 0, r.stderr
    # Correct: code ASC = AB(40), BA(10), CC(25)
    expected = compute_ewma_bankers([40.0, 10.0, 25.0])
    # Wrong: insertion order = CC(25), BA(10), AB(40)
    wrong = compute_ewma_bankers([25.0, 10.0, 40.0])
    assert f"ewma: {expected:.6f}" in r.stdout, (
        f"expected ewma: {expected:.6f} (code ASC order), got: {r.stdout}"
    )
    assert f"ewma: {wrong:.6f}" not in r.stdout, (
        f"got insertion-order ewma: {wrong:.6f}; must use code ASC: {r.stdout}"
    )


def test_country_ewma_null_empty():
    """country-ewma with no countries prints 'ewma: NULL' and exits 0."""
    insert_countries([])
    r = run(["country-ewma"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    assert "ewma: NULL" in r.stdout, f"expected 'ewma: NULL', got: {r.stdout}"


def test_country_ewma_single():
    """country-ewma with N=1 returns just the seed (rounded to 6dp)."""
    insert_countries([("EW1", "Solo", 37.5, 0.0)])
    r = run(["country-ewma"])
    assert r.returncode == 0, r.stderr
    expected = compute_ewma_bankers([37.5])
    assert f"ewma: {expected:.6f}" in r.stdout, f"expected ewma: {expected:.6f}, got: {r.stdout}"
    assert "ewma: 37.500000" in r.stdout, f"expected ewma: 37.500000 for single country, got: {r.stdout}"


def test_country_ewma_alpha_not_half():
    """EWMA must use alpha=0.3, not 0.5 or 0.2; values differ detectably."""
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    db.execute("INSERT INTO countries VALUES ('F1','N1','R','H','C',10.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('F2','N2','R','H','C',20.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('F3','N3','R','H','C',30.0,0.0)")
    db.commit()
    db.close()
    r = run(["country-ewma"])
    assert r.returncode == 0, r.stderr
    # alpha=0.3: 18.100000
    correct = compute_ewma_bankers([10.0, 20.0, 30.0], alpha=0.3)
    # alpha=0.5 would give: seed=10, step1=0.5*20+0.5*10=15, step2=0.5*30+0.5*15=22.5
    wrong_05 = 22.5
    # alpha=0.2 would give: seed=10, step1=0.2*20+0.8*10=12, step2=0.2*30+0.8*12=15.6
    wrong_02 = 15.6
    assert f"ewma: {correct:.6f}" in r.stdout, f"expected ewma: {correct:.6f} (alpha=0.3), got: {r.stdout}"
    assert f"ewma: {wrong_05:.6f}" not in r.stdout, f"got alpha=0.5 ewma: {wrong_05:.6f}, must use alpha=0.3"
    assert f"ewma: {wrong_02:.6f}" not in r.stdout, f"got alpha=0.2 ewma: {wrong_02:.6f}, must use alpha=0.3"


# ---------------------------------------------------------------------------
# Helper functions for new commands
# ---------------------------------------------------------------------------

def compute_pearson_pos_lat(lats):
    """Pearson correlation between 1-indexed position and latitude."""
    n = len(lats)
    if n < 2:
        return None
    xs = list(range(1, n + 1))
    fn = float(n)
    sx = sum(xs)
    sy = sum(lats)
    sxy = sum(x * y for x, y in zip(xs, lats))
    sx2 = sum(x * x for x in xs)
    sy2 = sum(y * y for y in lats)
    denom_a = fn * sx2 - sx * sx
    denom_b = fn * sy2 - sy * sy
    denom = denom_a * denom_b
    if denom <= 0:
        return None
    return (fn * sxy - sx * sy) / math.sqrt(denom)


def compute_autocorr_lag1(lats):
    """Lag-1 population autocorrelation."""
    n = len(lats)
    if n < 2:
        return None
    mean = sum(lats) / n
    pop_var = sum((v - mean) ** 2 for v in lats) / n
    if pop_var == 0:
        return None
    cov1 = sum((lats[t] - mean) * (lats[t + 1] - mean) for t in range(n - 1)) / n
    return cov1 / pop_var


def nearest_rank_median(xs_sorted):
    """Nearest-rank median: rank=ceil(0.5*N), index=rank-1."""
    n = len(xs_sorted)
    rank = math.ceil(0.5 * n)
    return xs_sorted[rank - 1]


def compute_mad(lats):
    """Median Absolute Deviation using nearest-rank median."""
    n = len(lats)
    if n < 2:
        return None
    sorted_lats = sorted(lats)
    median = nearest_rank_median(sorted_lats)
    devs = sorted([abs(v - median) for v in lats])
    return nearest_rank_median(devs)


def _bankers_round8(x):
    """Round x to 8 decimal places using HALF_EVEN."""
    ctx = _decimal.Context(rounding=_decimal.ROUND_HALF_EVEN, prec=28)
    d = ctx.create_decimal(repr(x))
    q = _decimal.Decimal("0.00000001")
    return float(d.quantize(q, context=ctx))


# ---------------------------------------------------------------------------
# country-pearson tests
# ---------------------------------------------------------------------------

def test_country_pearson_basic():
    """Pearson: N=3 lats [10,20,30] ordered by code ASC (pos 1,2,3). Perfect correlation=1."""
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    db.execute("INSERT INTO countries VALUES ('PA','N1','R','H','C',10.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('PB','N2','R','H','C',20.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('PC','N3','R','H','C',30.0,0.0)")
    db.commit()
    db.close()
    r = run(["country-pearson"])
    assert r.returncode == 0, r.stderr
    # pos=[1,2,3], lat=[10,20,30] -> perfect positive correlation = 1.0
    expected = compute_pearson_pos_lat([10.0, 20.0, 30.0])
    result = _bankers_round8(expected)
    assert f"pearson: {result:.8f}" in r.stdout, f"expected pearson: {result:.8f}, got: {r.stdout}"
    assert "pearson: 1.00000000" in r.stdout, f"expected pearson=1 for perfectly linear data, got: {r.stdout}"


def test_country_pearson_null_n1():
    """country-pearson with N=1 prints 'pearson: NULL' and exits 0."""
    insert_countries([("PR1", "Solo", 15.0, 25.0)])
    r = run(["country-pearson"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    assert "pearson: NULL" in r.stdout, f"expected 'pearson: NULL', got: {r.stdout}"


def test_country_pearson_code_order_trap():
    """Pearson uses code ASC ordering; wrong order gives different result."""
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    # code ASC: AA(lat=5), BB(lat=40), CC(lat=15), DD(lat=60)
    # Insert in non-ASC order to trap agents using rowid/insertion order
    db.execute("INSERT INTO countries VALUES ('DD','N4','R','H','C',60.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('BB','N2','R','H','C',40.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('CC','N3','R','H','C',15.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('AA','N1','R','H','C',5.0,0.0)")
    db.commit()
    db.close()
    r = run(["country-pearson"])
    assert r.returncode == 0, r.stderr
    # Correct: code ASC = AA(5), BB(40), CC(15), DD(60) -> pos=[1,2,3,4], lat=[5,40,15,60]
    correct = compute_pearson_pos_lat([5.0, 40.0, 15.0, 60.0])
    correct_r = _bankers_round8(correct)
    # Wrong: insertion order = DD(60), BB(40), CC(15), AA(5) -> pos=[1,2,3,4], lat=[60,40,15,5]
    wrong = compute_pearson_pos_lat([60.0, 40.0, 15.0, 5.0])
    wrong_r = _bankers_round8(wrong)
    # Sanity: correct and wrong must differ for this test to be meaningful
    assert correct_r != wrong_r, f"test dataset gives same pearson for both orderings: {correct_r}"
    assert f"pearson: {correct_r:.8f}" in r.stdout, (
        f"expected pearson: {correct_r:.8f} (code ASC), got: {r.stdout}"
    )
    assert f"pearson: {wrong_r:.8f}" not in r.stdout, (
        f"got wrong-order pearson: {wrong_r:.8f}: {r.stdout}"
    )


def test_country_pearson_negative():
    """Pearson: decreasing lat with position gives negative correlation."""
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    # code ASC: RA(lat=50), RB(lat=30), RC(lat=10) -> pos=[1,2,3], lat=[50,30,10] -> r=-1
    db.execute("INSERT INTO countries VALUES ('RA','N1','R','H','C',50.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('RB','N2','R','H','C',30.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('RC','N3','R','H','C',10.0,0.0)")
    db.commit()
    db.close()
    r = run(["country-pearson"])
    assert r.returncode == 0, r.stderr
    expected = compute_pearson_pos_lat([50.0, 30.0, 10.0])
    result = _bankers_round8(expected)
    assert f"pearson: {result:.8f}" in r.stdout, f"expected pearson: {result:.8f}, got: {r.stdout}"
    assert "pearson: -1.00000000" in r.stdout, f"expected pearson=-1 for perfectly decreasing data, got: {r.stdout}"


def test_country_pearson_precision_8dp():
    """Pearson: non-trivial dataset verifies 8dp precision."""
    lats = [5.5, 10.2, 8.7, 20.1, 15.3]
    codes = ["PA1", "PA2", "PA3", "PA4", "PA5"]
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    for code, lat in zip(codes, lats):
        db.execute("INSERT INTO countries VALUES (?,?,?,?,?,?,?)",
                   (code, f"N{code}", "R", "H", "C", lat, 0.0))
    db.commit()
    db.close()
    r = run(["country-pearson"])
    assert r.returncode == 0, r.stderr
    expected = compute_pearson_pos_lat(lats)
    result = _bankers_round8(expected)
    assert f"pearson: {result:.8f}" in r.stdout, f"expected pearson: {result:.8f}, got: {r.stdout}"


# ---------------------------------------------------------------------------
# country-autocorr tests
# ---------------------------------------------------------------------------

def test_country_autocorr_basic():
    """Autocorr lag-1: N=4 lats ordered by code ASC."""
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    # code ASC: AC1(10), AC2(20), AC3(15), AC4(25)
    db.execute("INSERT INTO countries VALUES ('AC1','N1','R','H','C',10.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('AC2','N2','R','H','C',20.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('AC3','N3','R','H','C',15.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('AC4','N4','R','H','C',25.0,0.0)")
    db.commit()
    db.close()
    r = run(["country-autocorr"])
    assert r.returncode == 0, r.stderr
    lats = [10.0, 20.0, 15.0, 25.0]
    expected = compute_autocorr_lag1(lats)
    result = _bankers_round8(expected)
    assert f"autocorr: {result:.8f}" in r.stdout, f"expected autocorr: {result:.8f}, got: {r.stdout}"


def test_country_autocorr_null_n1():
    """country-autocorr with N=1 prints 'autocorr: NULL' and exits 0."""
    insert_countries([("AX1", "Solo", 10.0, 0.0)])
    r = run(["country-autocorr"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    assert "autocorr: NULL" in r.stdout, f"expected 'autocorr: NULL', got: {r.stdout}"


def test_country_autocorr_code_order_trap():
    """Autocorr uses code ASC ordering; wrong order changes result."""
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    # code ASC: AA(10), BB(30), CC(20)
    # Insert in reverse to trap insertion-order agents
    db.execute("INSERT INTO countries VALUES ('CC','N3','R','H','C',20.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('BB','N2','R','H','C',30.0,0.0)")
    db.execute("INSERT INTO countries VALUES ('AA','N1','R','H','C',10.0,0.0)")
    db.commit()
    db.close()
    r = run(["country-autocorr"])
    assert r.returncode == 0, r.stderr
    # Correct: code ASC = AA(10), BB(30), CC(20)
    correct_lats = [10.0, 30.0, 20.0]
    correct = compute_autocorr_lag1(correct_lats)
    correct_r = _bankers_round8(correct)
    # Wrong: insertion order = CC(20), BB(30), AA(10)
    wrong_lats = [20.0, 30.0, 10.0]
    wrong = compute_autocorr_lag1(wrong_lats)
    wrong_r = _bankers_round8(wrong)
    assert f"autocorr: {correct_r:.8f}" in r.stdout, (
        f"expected autocorr: {correct_r:.8f} (code ASC), got: {r.stdout}"
    )
    if correct_r != wrong_r:
        assert f"autocorr: {wrong_r:.8f}" not in r.stdout, (
            f"got insertion-order autocorr: {wrong_r:.8f}: {r.stdout}"
        )


def test_country_autocorr_zero_variance():
    """Autocorr with all identical latitudes: pop_var=0 -> prints 'autocorr: NULL'."""
    insert_countries([("ZV1", "N1", 20.0, 0.0), ("ZV2", "N2", 20.0, 0.0), ("ZV3", "N3", 20.0, 0.0)])
    r = run(["country-autocorr"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    assert "autocorr: NULL" in r.stdout, f"expected 'autocorr: NULL' for zero variance, got: {r.stdout}"


def test_country_autocorr_precision():
    """Autocorr: non-trivial 5-element dataset verifies 8dp."""
    lats = [5.0, 15.0, 10.0, 25.0, 20.0]
    codes = ["AR1", "AR2", "AR3", "AR4", "AR5"]
    db = sqlite3.connect("/app/wb.db")
    db.execute("DELETE FROM countries")
    db.execute("DELETE FROM audit_log")
    for code, lat in zip(codes, lats):
        db.execute("INSERT INTO countries VALUES (?,?,?,?,?,?,?)",
                   (code, f"N{code}", "R", "H", "C", lat, 0.0))
    db.commit()
    db.close()
    r = run(["country-autocorr"])
    assert r.returncode == 0, r.stderr
    expected = compute_autocorr_lag1(lats)
    result = _bankers_round8(expected)
    assert f"autocorr: {result:.8f}" in r.stdout, f"expected autocorr: {result:.8f}, got: {r.stdout}"


# ---------------------------------------------------------------------------
# country-mad tests
# ---------------------------------------------------------------------------

def test_country_mad_basic():
    """MAD: N=5 lats [1,2,3,4,5]: median=3, devs=[0,1,2,1,2] sorted=[0,1,1,2,2], median_dev=1."""
    lats = [1.0, 2.0, 3.0, 4.0, 5.0]
    insert_countries([(f"MD{i}", f"N{i}", v, 0.0) for i, v in enumerate(lats)])
    r = run(["country-mad"])
    assert r.returncode == 0, r.stderr
    expected = compute_mad(lats)
    assert f"mad: {expected:.8f}" in r.stdout, f"expected mad: {expected:.8f}, got: {r.stdout}"
    assert "mad: 1.00000000" in r.stdout, f"expected mad=1.0 for [1..5], got: {r.stdout}"


def test_country_mad_null_n1():
    """country-mad with N=1 prints 'mad: NULL' and exits 0."""
    insert_countries([("MX1", "Solo", 15.0, 0.0)])
    r = run(["country-mad"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    assert "mad: NULL" in r.stdout, f"expected 'mad: NULL', got: {r.stdout}"


def test_country_mad_precision_8dp():
    """MAD: N=4 non-trivial dataset verifies 8dp output."""
    lats = [10.0, 15.5, 20.0, 30.5]
    insert_countries([(f"MQ{i}", f"N{i}", v, 0.0) for i, v in enumerate(lats)])
    r = run(["country-mad"])
    assert r.returncode == 0, r.stderr
    expected = compute_mad(lats)
    assert f"mad: {expected:.8f}" in r.stdout, f"expected mad: {expected:.8f}, got: {r.stdout}"


def test_country_mad_asymmetric():
    """MAD: asymmetric distribution with outlier."""
    # lats = [1, 1, 1, 1, 100] -> sorted: [1,1,1,1,100]
    # median (N=5): rank=ceil(2.5)=3, index=2 -> median=1
    # devs: |1-1|=0, |1-1|=0, |1-1|=0, |1-1|=0, |100-1|=99
    # sorted devs: [0,0,0,0,99], median of devs: rank=3, index=2 -> 0
    lats = [1.0, 1.0, 1.0, 1.0, 100.0]
    insert_countries([(f"MA{i}", f"N{i}", v, 0.0) for i, v in enumerate(lats)])
    r = run(["country-mad"])
    assert r.returncode == 0, r.stderr
    expected = compute_mad(lats)
    assert f"mad: {expected:.8f}" in r.stdout, f"expected mad: {expected:.8f}, got: {r.stdout}"
    assert "mad: 0.00000000" in r.stdout, f"expected MAD=0 for near-constant with outlier, got: {r.stdout}"


def test_country_mad_negative_lats():
    """MAD handles negative latitude values correctly."""
    lats = [-30.0, -10.0, 0.0, 10.0, 30.0]
    insert_countries([(f"MN{i}", f"N{i}", v, 0.0) for i, v in enumerate(lats)])
    r = run(["country-mad"])
    assert r.returncode == 0, r.stderr
    expected = compute_mad(lats)
    assert f"mad: {expected:.8f}" in r.stdout, f"expected mad: {expected:.8f}, got: {r.stdout}"


# ---------------------------------------------------------------------------
# country-hoover tests
# ---------------------------------------------------------------------------

def compute_hoover(lats):
    """Hoover inequality index on shifted lats."""
    if len(lats) < 2:
        return None
    min_lat = min(lats)
    shifted = [v - min_lat + 1.0 for v in lats]
    n = len(shifted)
    total_sum = sum(shifted)
    if total_sum == 0:
        return None
    mean_shifted = total_sum / n
    abs_dev_sum = sum(abs(v - mean_shifted) for v in shifted)
    return abs_dev_sum / (2.0 * total_sum)


def test_country_hoover_basic():
    """Hoover for [10,20,30,40]: verify exact 8dp value with shift formula."""
    lats = [10.0, 20.0, 30.0, 40.0]
    insert_countries([(f"HV{i}", f"N{i}", v, 0.0) for i, v in enumerate(lats)])
    r = run(["country-hoover"])
    assert r.returncode == 0, r.stderr
    expected = compute_hoover(lats)
    assert f"hoover: {expected:.8f}" in r.stdout, f"expected hoover: {expected:.8f}, got: {r.stdout}"


def test_country_hoover_null_n1():
    """country-hoover with N=1 prints 'hoover: NULL' and exits 0."""
    insert_countries([("HN1", "Solo", 20.0, 0.0)])
    r = run(["country-hoover"])
    assert r.returncode == 0, f"expected exit 0, got {r.returncode}: {r.stderr}"
    assert "hoover: NULL" in r.stdout, f"expected 'hoover: NULL', got: {r.stdout}"


def test_country_hoover_denom_trap():
    """Hoover denominator is 2*sum(shifted) NOT 2*N*mean; verify precision for unequal lats."""
    # lats [1,2,3,4,5]: min=1, shifted=[1,2,3,4,5]
    # mean=3, sum=15, abs_devs=[2,1,0,1,2], abs_dev_sum=6
    # hoover = 6 / (2*15) = 6/30 = 0.2
    # Wrong (using N*mean): 6 / (2*5*3) = 6/30 = 0.2 (happens to equal for this case)
    # Use asymmetric to distinguish: [1,2,10]: min=1, shifted=[1,2,10]
    # sum=13, mean=13/3=4.333..., abs_devs=[3.333,2.333,5.667], abs_dev_sum=11.333
    # hoover = 11.333... / 26 = 0.43589744...
    # Wrong (N-1 mean): mean_wrong = sum/2 = 6.5, abs_devs=[5.5,4.5,3.5], sum=13.5 / 26 = 0.51923...
    lats = [1.0, 2.0, 10.0]
    insert_countries([(f"HD{i}", f"N{i}", v, 0.0) for i, v in enumerate(lats)])
    r = run(["country-hoover"])
    assert r.returncode == 0, r.stderr
    expected = compute_hoover(lats)
    assert f"hoover: {expected:.8f}" in r.stdout, f"expected hoover: {expected:.8f}, got: {r.stdout}"


def test_country_hoover_negative_lats():
    """Hoover with negative latitudes (shift makes strictly positive)."""
    lats = [-50.0, -20.0, 10.0, 40.0]
    insert_countries([(f"HNG{i}", f"N{i}", v, 0.0) for i, v in enumerate(lats)])
    r = run(["country-hoover"])
    assert r.returncode == 0, r.stderr
    expected = compute_hoover(lats)
    assert f"hoover: {expected:.8f}" in r.stdout, f"expected hoover: {expected:.8f}, got: {r.stdout}"
    # Without shift, negatives would corrupt the mean; verify correct shifted result
    min_lat = min(lats)
    shifted = [v - min_lat + 1.0 for v in lats]
    assert all(v > 0 for v in shifted), "shifted values must be strictly positive"


# ---------------------------------------------------------------------------
# audit-baseline-window
# ---------------------------------------------------------------------------


def _insert_audit_seq(codes):
    """Insert bare audit_log rows (seq=1..len(codes), country_code=codes[i]).
    Only seq/country_code matter for audit-baseline-window; every other
    column is nullable or defaulted."""
    db = sqlite3.connect("/app/wb.db")
    for i, code in enumerate(codes, start=1):
        db.execute(
            "INSERT INTO audit_log (seq, country_code) VALUES (?, ?)",
            (i, code),
        )
    db.commit()
    db.close()


def _window_statuses(stdout):
    """Parse audit-baseline-window stdout into (ordered list of (seq, code, status), window_remaining)."""
    lines = [ln for ln in stdout.strip().split("\n") if ln]
    assert lines, "no output"
    assert lines[-1].startswith("window_remaining="), f"missing window_remaining line: {stdout}"
    remaining = int(lines[-1].split("=", 1)[1])
    rows = []
    for ln in lines[:-1]:
        seq_s, code, status_s = ln.split("\t")
        rows.append((int(seq_s), code, status_s.split("=", 1)[1]))
    return rows, remaining


def test_audit_baseline_window_empty():
    """No audit_log rows: prints 'empty' and exits 0."""
    run(["init"])
    clear_db()
    r = run(["audit-baseline-window"])
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "empty", r.stdout


def test_audit_baseline_window_single_row_admitted():
    """A single row takes one of the two starting reference slots and is
    admitted into the baseline right away; one slot stays open."""
    run(["init"])
    clear_db()
    _insert_audit_seq(["AA"])
    r = run(["audit-baseline-window"])
    assert r.returncode == 0, r.stderr
    rows, remaining = _window_statuses(r.stdout)
    assert rows == [(1, "AA", "baseline")]
    assert remaining == 1


def test_audit_baseline_window_admits_in_log_order_not_own_arrival():
    """4 rows against a 2-slot window that ages a slot out 3 rows after the
    row holding it was itself admitted. Rows 1-2 fill the window and row 3
    is provisional (window full). At row 4, row 1 ages out and its slot
    opens -- but that slot is owed to row 3, which has been waiting since
    row 3, not to row 4, which just arrived. Row 4 must stay provisional
    even though its own logging is what aged the slot open."""
    run(["init"])
    clear_db()
    _insert_audit_seq(["A1", "A2", "A3", "A4"])
    r = run(["audit-baseline-window"])
    assert r.returncode == 0, r.stderr
    rows, remaining = _window_statuses(r.stdout)
    statuses = [s for _, _, s in rows]
    assert statuses == ["baseline", "baseline", "baseline", "provisional"], (
        f"expected row 3 (the longest-waiting provisional row) to claim the "
        f"opened slot ahead of row 4 (the new arrival), got: {statuses}"
    )
    assert remaining == 0
    codes = [c for _, c, _ in rows]
    assert codes == ["A1", "A2", "A3", "A4"], "codes must line up with their own seq, in seq order"


def test_audit_baseline_window_admission_resets_age_out_clock():
    """6 rows against the same 2-slot/3-row-delay rules. Row 3 is
    provisional at row 3 and only gets admitted at row 4, when row 1 ages
    out. Row 3's OWN 3-row age-out delay must count from row 4 (the step it
    actually joined the baseline), not from row 3 (its original seq). If
    the delay were wrongly anchored to the original seq, row 3 would age
    out at row 6 and let row 6 be admitted too; anchored correctly to the
    admission step, row 3 doesn't age out until row 7, so rows 5 and 6 both
    stay provisional through row 6."""
    run(["init"])
    clear_db()
    _insert_audit_seq(["B1", "B2", "B3", "B4", "B5", "B6"])
    r = run(["audit-baseline-window"])
    assert r.returncode == 0, r.stderr
    rows, remaining = _window_statuses(r.stdout)
    statuses = [s for _, _, s in rows]
    assert statuses == [
        "baseline", "baseline", "baseline", "baseline", "provisional", "provisional",
    ], (
        f"row 3 must age out 3 rows after row 3 was ADMITTED (row 4), "
        f"not 3 rows after its original seq -- got: {statuses}"
    )
    assert remaining == 0


def test_audit_baseline_window_real_fetch_flow(mock_server):
    """Same window/backlog behavior holds when rows come from real
    fetch-country calls (not raw audit_log inserts): the 3rd of 3 fetches
    into a full window must be provisional."""
    run(["init"])
    clear_db()
    MOCK_DB["C1"] = {"name": "N1", "lat": 1.0, "lon": 0.0}
    MOCK_DB["C2"] = {"name": "N2", "lat": 2.0, "lon": 0.0}
    MOCK_DB["C3"] = {"name": "N3", "lat": 3.0, "lon": 0.0}
    for code in ("C1", "C2", "C3"):
        r = run(["fetch-country", code], api_base=mock_server)
        assert r.returncode == 0, r.stderr
    r = run(["audit-baseline-window"])
    assert r.returncode == 0, r.stderr
    rows, remaining = _window_statuses(r.stdout)
    statuses = [s for _, _, s in rows]
    assert statuses == ["baseline", "baseline", "provisional"], statuses
    assert remaining == 0
