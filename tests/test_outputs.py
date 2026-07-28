"""Behavioral verification for orbital PSF ensemble release certification."""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path

import sqlite3
import pytest
import urllib.parse

from orbit_testkit import (
    APP,
    DB,
    FixtureServer,
    api_server,
    build,
    catalog,
    certify,
    clean_publish,
    current_release,
    evaluations_from_files,
    http_get,
    reference_report,
    run,
)

ASSET_HASHES = json.loads(Path('/tests/asset_hashes.json').read_text())


def copy_db(tmp_path: Path) -> Path:
    """Copy the seeded SQLite registry into a writable verifier fixture."""
    destination = tmp_path / 'campaign.sqlite3'
    shutil.copy2(DB, destination)
    return destination


def mutate(db: Path, statement: str) -> None:
    """Apply one deterministic catalog mutation to a verifier-only database."""
    connection = sqlite3.connect(str(db))
    try:
        connection.execute(statement)
        connection.commit()
    finally:
        connection.close()


def test_authoritative_inputs_and_generated_database_are_intact() -> None:
    """All contracts, fixtures, dashboard assets, tiles, and audit records remain byte-preserved and the SQLite registry still matches the seed manifest."""
    for relative, expected in ASSET_HASHES.items():
        actual = hashlib.sha256((APP / relative).read_bytes()).hexdigest()
        assert actual == expected, relative
    exported = catalog()['campaigns']
    manifest = json.loads((APP / 'fixtures/seed.json').read_text())['campaigns']
    assert len(exported) == len(manifest) == 1
    current, seeded = exported[0], manifest[0]
    for key in (
        'campaign_id', 'model_revision', 'feature_revision', 'expected_sample_count',
        'feature_count', 'decision_threshold', 'abstain_spread',
        'bootstrap_replicates', 'ece_bins', 'min_coverage',
        'min_balanced_accuracy_lower', 'max_brier', 'max_ece', 'max_fpr_gap',
        'max_feature_drift',
    ):
        assert current[key] == seeded[key]
    assert current['samples'] == seeded['samples']
    assert current['heads'] == [
        {**head, 'weight_indices': list(range(len(head['weights'])))}
        for head in seeded['heads']
    ]
    assert current['feature_references'] == seeded['feature_references']


def test_build_outputs_native_binaries_and_exact_fftw_linkage() -> None:
    """The documented build creates native ELF tools and the certifier dynamically resolves FFTW 3.3.10."""
    build()
    for name in ('orbit-api', 'orbit-certify', 'fft-check'):
        path = APP / 'bin' / name
        assert path.is_file() and os.access(path, os.X_OK)
        file_result = run(['file', str(path)], check=True)
        assert 'ELF' in file_result.stdout
    linkage = run(['ldd', '/app/bin/orbit-certify'], check=True).stdout
    assert 'libfftw3.so' in linkage
    smoke_lines = [line.strip() for line in run(['/app/bin/fft-check'], check=True).stdout.splitlines()]
    assert any(re.fullmatch(r'47x47 assigned=\d+', line) for line in smoke_lines)
    assert any(re.fullmatch(r'48x48 assigned=\d+', line) for line in smoke_lines)


def test_api_binds_revision_metadata_cache_and_dashboard_routes(tmp_path: Path) -> None:
    """The live Go HTTP service enforces the tile contract, release lookup behavior, and dashboard asset routes."""
    publish = tmp_path / 'publish'; publish.mkdir()
    campaign = catalog()['campaigns'][0]; sample = campaign['samples'][0]
    with api_server(publish=publish) as origin:
        response = http_get(
            f"{origin}/v1/campaigns/{campaign['campaign_id']}/samples/0/tile",
            params={'revision': campaign['model_revision']}, timeout=2,
        )
        assert response.status_code == 200
        assert response.headers['Content-Type'] == 'image/png'
        assert response.headers['Cache-Control'] == 'no-store'
        expected_headers = {
            'X-Campaign-ID': campaign['campaign_id'], 'X-Sample-ID': sample['sample_id'],
            'X-Sample-Index': '0', 'X-Site-ID': sample['site_id'],
            'X-Device-Family': sample['device_family'], 'X-Label': str(sample['label']),
            'X-Model-Revision': str(campaign['model_revision']),
        }
        for name, value in expected_headers.items(): assert response.headers[name] == value
        assert response.headers['ETag'] == f'"sha256:{hashlib.sha256(response.content).hexdigest()}"'
        assert http_get(response.url.replace(f"revision={campaign['model_revision']}", 'revision=22'), timeout=2).status_code == 409
        assert http_get(origin + '/v1/campaigns/x/samples/not-a-number/tile?revision=23', timeout=2).status_code == 400
        assert http_get(origin + '/dashboard', timeout=2).status_code == 200
        assert http_get(origin + '/assets/app.js', timeout=2).status_code == 200
        assert http_get(origin + '/assets/styles.css', timeout=2).status_code == 200
        assert http_get(origin + '/v1/releases/current?campaign=orbital-psf-q3', timeout=2).status_code == 404


def test_reference_campaign_matches_independent_features_inference_metrics_and_publication(tmp_path: Path) -> None:
    """A complete run matches an independent NumPy/HTTP reference down to canonical JSON, provenance, hashes, gates, and manifest paths."""
    publish = tmp_path / 'publish'; clean_publish(publish)
    campaign = catalog()['campaigns'][0]
    expected_report, expected_bytes, expected_dot = reference_report(campaign, evaluations_from_files(campaign))
    with api_server(publish=publish) as origin:
        result = certify(origin, publish)
        assert result.returncode == 0, result.stderr
    actual_report, actual_bytes, actual_dot, manifest = current_release(publish)
    assert actual_report == expected_report
    assert actual_bytes == expected_bytes
    assert actual_dot == expected_dot
    assert actual_report['release_status'] == 'accepted'
    assert all(actual_report['gates'].values())
    assert manifest == {
        'schema_version': 'orbital-publication/v1',
        'campaign_id': campaign['campaign_id'],
        'model_revision': campaign['model_revision'],
        'generation': expected_report['content_sha256'],
        'release': f"releases/{expected_report['content_sha256']}/release.json",
        'provenance': f"releases/{expected_report['content_sha256']}/provenance.dot",
    }


def test_dynamic_gate_rejection_uses_database_thresholds_not_bundled_answers(tmp_path: Path) -> None:
    """Changing a gate in a verifier-only SQLite registry yields the independently expected rejected release without altering model computations."""
    db = copy_db(tmp_path); mutate(db, 'UPDATE campaigns SET max_brier = 0.000001')
    publish = tmp_path / 'publish'; clean_publish(publish)
    campaign = catalog(db)['campaigns'][0]
    expected_report, expected_bytes, expected_dot = reference_report(campaign, evaluations_from_files(campaign))
    assert expected_report['release_status'] == 'rejected' and not expected_report['gates']['brier']
    with api_server(db=db, publish=publish) as origin:
        result = certify(origin, publish, db=db)
        assert result.returncode == 0, result.stderr
    actual_report, actual_bytes, actual_dot, _ = current_release(publish)
    assert actual_report == expected_report
    assert actual_bytes == expected_bytes and actual_dot == expected_dot


@pytest.mark.parametrize('statement', [
    'DELETE FROM samples WHERE sample_index = 0',
    "DELETE FROM model_weights WHERE head_id = 'psf-linear-1' AND feature_index = 8",
    'DELETE FROM feature_references WHERE feature_index = 8',
    "UPDATE samples SET site_id = 'single-site'",
])
def test_catalog_and_model_invariants_fail_before_acquisition(tmp_path: Path, statement: str) -> None:
    """Malformed sample, head, reference, and cohort catalogs are rejected before any HTTP request or publication mutation."""
    db = copy_db(tmp_path); mutate(db, statement)
    publish = tmp_path / 'publish'; clean_publish(publish)
    sentinel = b'old-current\n'; (publish / 'current.json').write_bytes(sentinel)
    campaign = json.loads((APP / 'fixtures/seed.json').read_text())['campaigns'][0]
    with FixtureServer(campaign) as server:
        result = certify(server.origin, publish, db=db)
    assert result.returncode == 3
    assert server.requests == []
    assert (publish / 'current.json').read_bytes() == sentinel
    assert not list(publish.rglob('.stage-*')) and not list(publish.glob('.current-*.tmp'))


@pytest.mark.parametrize('mutation', ['etag', 'metadata', 'content_type', 'cache', 'color', 'redirect', 'oversized'])
def test_protocol_corruption_fails_closed_and_preserves_current_release(tmp_path: Path, mutation: str) -> None:
    """Digest, metadata, content-type, cache, and grayscale corruptions stop the run without replacing the current release or leaving stages."""
    publish = tmp_path / 'publish'; clean_publish(publish)
    sentinel = b'previous-current\n'; (publish / 'current.json').write_bytes(sentinel)
    campaign = catalog()['campaigns'][0]
    with FixtureServer(campaign, mutation=mutation) as server:
        result = certify(server.origin, publish)
    assert result.returncode == 3
    assert 1 <= len(server.requests) <= len(campaign['samples'])
    if mutation == 'redirect': assert len(server.requests) == 1
    assert (publish / 'current.json').read_bytes() == sentinel
    assert not list(publish.rglob('.stage-*')) and not list(publish.glob('.current-*.tmp'))


def test_escaped_campaign_route_is_fetched_once_in_catalog_order(tmp_path: Path) -> None:
    """A campaign identifier containing reserved path characters is escaped as one segment while samples remain exactly-once and ordered."""
    manifest = json.loads((APP / 'fixtures/seed.json').read_text())
    manifest['campaigns'][0]['campaign_id'] = 'orbital/psf q3'
    manifest_path = tmp_path / 'seed.json'; manifest_path.write_text(json.dumps(manifest))
    db = tmp_path / 'escaped.sqlite3'
    seed = run(['/usr/local/bin/orbit-seed', '--schema', '/app/db/schema.sql', '--manifest', str(manifest_path), '--db', str(db)])
    assert seed.returncode == 0, seed.stderr
    campaign = catalog(db)['campaigns'][0]
    publish = tmp_path / 'publish'; clean_publish(publish)
    with FixtureServer(campaign) as server:
        result = certify(server.origin, publish, db=db)
    assert result.returncode == 0, result.stderr
    decoded = [urllib.parse.unquote(path.split('?')[0]) for path in server.requests]
    expected = [f"/v1/campaigns/{campaign['campaign_id']}/samples/{index}/tile" for index in range(len(campaign['samples']))]
    assert decoded == expected
    assert all(urllib.parse.parse_qs(urllib.parse.urlparse(path).query) == {'revision': [str(campaign['model_revision'])]} for path in server.requests)
    assert server.accept_headers == ['image/png'] * len(expected)
    assert len(server.requests) == len(set(server.requests)) == len(expected)


@pytest.mark.parametrize('arguments', [
    [], ['--db', '/app/data/orbit.sqlite3'],
    ['--db', 'relative.sqlite3', '--api', 'http://127.0.0.1:1', '--publish-dir', '/tmp/x'],
    ['--db', '/app/data/orbit.sqlite3', '--api', 'https://example.test', '--publish-dir', '/tmp/x'],
    ['--db', '/app/data/orbit.sqlite3', '--api', 'http://example.test/path', '--publish-dir', '/tmp/x'],
    ['--db', '/app/data/orbit.sqlite3', '--api', 'http://127.0.0.1:1', '--publish-dir', 'relative'],
    ['--db', '/app/data/orbit.sqlite3', '--api', 'http://127.0.0.1:1', '--publish-dir', '/tmp/x', '--timeout-ms', '0'],
    ['--db', '/app/data/orbit.sqlite3', '--api', 'http://127.0.0.1:1', '--publish-dir', '/tmp/x', '--extra'],
])
def test_cli_argument_contract_uses_exit_two(arguments: list[str]) -> None:
    """Missing, relative, non-origin, non-positive, trailing, and unknown CLI shapes fail with argument exit code 2."""
    build(); result = run(['/app/bin/orbit-certify', *arguments])
    assert result.returncode == 2


def test_http_timeout_is_runtime_failure_and_cleans_publication_state(tmp_path: Path) -> None:
    """A tile response exceeding the positive timeout exits 3, preserves the current manifest, and removes all temporary publication paths."""
    publish = tmp_path / 'publish'; clean_publish(publish)
    sentinel = b'timeout-current\n'; (publish / 'current.json').write_bytes(sentinel)
    campaign = catalog()['campaigns'][0]
    with FixtureServer(campaign, delay=0.25) as server:
        result = certify(server.origin, publish, timeout_ms=40)
    assert result.returncode == 3
    assert (publish / 'current.json').read_bytes() == sentinel
    assert not list(publish.rglob('.stage-*')) and not list(publish.glob('.current-*.tmp'))


def test_concurrent_and_repeated_publication_creates_one_identical_generation(tmp_path: Path) -> None:
    """Four simultaneous certifiers plus a repeated run converge on one content-addressed generation and byte-identical current manifest."""
    publish = tmp_path / 'publish'; clean_publish(publish)
    with api_server(publish=publish) as origin:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda _: certify(origin, publish), range(4)))
        assert all(result.returncode == 0 for result in results), [result.stderr for result in results]
        first_current = (publish / 'current.json').read_bytes()
        repeat = certify(origin, publish)
        assert repeat.returncode == 0, repeat.stderr
    assert (publish / 'current.json').read_bytes() == first_current
    generations = [path for path in (publish / 'releases').iterdir() if path.is_dir() and not path.name.startswith('.')]
    assert len(generations) == 1
    assert sorted(path.name for path in generations[0].iterdir()) == ['provenance.dot', 'release.json']
    assert not list(publish.rglob('.stage-*')) and not list(publish.glob('.current-*.tmp'))


def test_existing_generation_byte_drift_is_rejected_without_pointer_change(tmp_path: Path) -> None:
    """A corrupted pre-existing content-addressed generation causes exit 3 and leaves the current manifest unchanged."""
    publish = tmp_path / 'publish'; clean_publish(publish)
    with api_server(publish=publish) as origin:
        first = certify(origin, publish); assert first.returncode == 0, first.stderr
        _, _, _, manifest = current_release(publish)
        current_before = (publish / 'current.json').read_bytes()
        release_path = publish / manifest['release']; release_path.write_bytes(release_path.read_bytes() + b'corruption')
        second = certify(origin, publish)
    assert second.returncode == 3
    assert (publish / 'current.json').read_bytes() == current_before
    assert not list(publish.rglob('.stage-*')) and not list(publish.glob('.current-*.tmp'))


class IDParser(HTMLParser):
    """Collect element identifiers from the dashboard markup."""
    def __init__(self) -> None:
        super().__init__(); self.ids: set[str] = set(); self.scripts: list[str] = []
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        mapping = dict(attrs)
        if mapping.get('id'): self.ids.add(str(mapping['id']))
        if tag == 'script' and mapping.get('src'): self.scripts.append(str(mapping['src']))


def test_dashboard_exposes_current_release_and_complete_visual_sections(tmp_path: Path) -> None:
    """The browser console serves semantic metric, gate, cohort, and sample sections and retrieves the exact current release without caching."""
    publish = tmp_path / 'publish'; clean_publish(publish)
    campaign = catalog()['campaigns'][0]
    with api_server(publish=publish) as origin:
        result = certify(origin, publish); assert result.returncode == 0, result.stderr
        html = http_get(origin + '/dashboard', timeout=2).text
        parser = IDParser(); parser.feed(html)
        assert {'release-state', 'metric-grid', 'gate-table', 'cohort-table', 'sample-table'} <= parser.ids
        assert parser.scripts == ['/assets/app.js']
        script = http_get(origin + '/assets/app.js', timeout=2).text
        assert 'textContent' in script and 'innerHTML' not in script
        assert 'cache: \'no-store\'' in script
        response = http_get(origin + f"/v1/releases/current?campaign={campaign['campaign_id']}", timeout=2)
        assert response.status_code == 200 and response.headers['Cache-Control'] == 'no-store'
        assert response.headers['ETag'] == f'"sha256:{hashlib.sha256(response.content).hexdigest()}"'
        assert response.json()['samples'] and response.json()['cohorts']


def test_audit_archive_index_hashes_every_record() -> None:
    """The 180-file historical model audit archive is complete, uniquely indexed, and internally hash-consistent."""
    root = APP / 'reference/model-audit-archive'
    index = json.loads((root / 'index.json').read_text())
    assert index['schema_version'] == 'model-audit-index/v1'
    assert len(index['records']) == 180
    paths = [entry['path'] for entry in index['records']]
    assert len(paths) == len(set(paths))
    for entry in index['records']:
        body = (root / entry['path']).read_bytes()
        assert hashlib.sha256(body).hexdigest() == entry['sha256']


def test_native_radial_helper_is_guarded_and_ubsan_clean_for_odd_and_even_sizes(tmp_path: Path) -> None:
    """The C radial helper respects guarded caller buffers and has no undefined behavior for odd and even dimensions."""
    harness = tmp_path / 'radial_guard_harness.c'
    harness.write_text(r"""#include "orbit_fft.h"
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

typedef struct {
    void *mapping;
    size_t mapping_size;
    unsigned char *data;
    size_t bytes;
    size_t page_size;
    size_t usable_size;
} guarded_buffer;

static int guarded_alloc(guarded_buffer *buffer, size_t bytes, int place_at_end) {
    const long page = sysconf(_SC_PAGESIZE);
    if (page <= 0 || bytes == 0) return 1;
    const size_t page_size = (size_t)page;
    const size_t usable_pages = (bytes + page_size - 1U) / page_size;
    const size_t mapping_size = (usable_pages + 2U) * page_size;
    unsigned char *mapping = mmap(NULL, mapping_size, PROT_READ | PROT_WRITE,
                                  MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    if (mapping == MAP_FAILED) return 1;
    if (mprotect(mapping, page_size, PROT_NONE) != 0 ||
        mprotect(mapping + page_size + usable_pages * page_size,
                 page_size, PROT_NONE) != 0) {
        munmap(mapping, mapping_size);
        return 1;
    }
    buffer->mapping = mapping;
    buffer->mapping_size = mapping_size;
    buffer->page_size = page_size;
    buffer->usable_size = usable_pages * page_size;
    buffer->bytes = bytes;
    buffer->data = mapping + page_size;
    if (place_at_end) buffer->data += buffer->usable_size - bytes;
    return 0;
}

static void guarded_free(guarded_buffer *buffer) {
    if (buffer->mapping != NULL) munmap(buffer->mapping, buffer->mapping_size);
    memset(buffer, 0, sizeof(*buffer));
}

static int run_case(int width, int height, int place_at_end) {
    const int spectrum_width = width / 2 + 1;
    const int bin_count = 6;
    const size_t power_count = (size_t)height * (size_t)spectrum_width;
    guarded_buffer power_buffer = {0};
    guarded_buffer sums_buffer = {0};
    guarded_buffer counts_buffer = {0};
    if (guarded_alloc(&power_buffer, power_count * sizeof(double), place_at_end) != 0 ||
        guarded_alloc(&sums_buffer, (size_t)bin_count * sizeof(double), place_at_end) != 0 ||
        guarded_alloc(&counts_buffer, (size_t)bin_count * sizeof(uint64_t), place_at_end) != 0) {
        guarded_free(&power_buffer);
        guarded_free(&sums_buffer);
        guarded_free(&counts_buffer);
        return 2;
    }
    double *power = (double *)power_buffer.data;
    double *sums = (double *)sums_buffer.data;
    uint64_t *counts = (uint64_t *)counts_buffer.data;
    double expected_sums[6] = {0};
    uint64_t expected_counts[6] = {0};
    for (size_t index = 0; index < power_count; ++index) power[index] = (double)(index + 1U);
    for (int y = 0; y < height; ++y) {
        const int ky = y <= height / 2 ? y : y - height;
        for (int x = 0; x < spectrum_width; ++x) {
            const int bin = (int)floor(hypot((double)x, (double)ky));
            if (bin >= 1 && bin <= bin_count) {
                const uint64_t multiplicity =
                    (x == 0 || (width % 2 == 0 && x == width / 2)) ? 1U : 2U;
                const size_t offset = (size_t)y * (size_t)spectrum_width + (size_t)x;
                expected_sums[bin - 1] += power[offset] * (double)multiplicity;
                expected_counts[bin - 1] += multiplicity;
            }
        }
    }
    unsigned char *power_pages = (unsigned char *)power_buffer.mapping + power_buffer.page_size;
    if (mprotect(power_pages, power_buffer.usable_size, PROT_READ) != 0) return 3;
    const int result = orbit_radial_accumulate(
        power, width, height, spectrum_width, sums, counts, bin_count
    );
    if (result != 0) return 4;
    for (int index = 0; index < bin_count; ++index) {
        if (counts[index] != expected_counts[index] ||
            fabs(sums[index] - expected_sums[index]) > 1e-12) return 5;
    }
    guarded_free(&power_buffer);
    guarded_free(&sums_buffer);
    guarded_free(&counts_buffer);
    return 0;
}

int main(void) {
    const int dimensions[][2] = {{47, 47}, {48, 48}};
    for (size_t index = 0; index < sizeof(dimensions) / sizeof(dimensions[0]); ++index) {
        if (run_case(dimensions[index][0], dimensions[index][1], 0) != 0) return 10;
        if (run_case(dimensions[index][0], dimensions[index][1], 1) != 0) return 11;
    }
    return 0;
}
""")
    binary = tmp_path / 'radial-guard-ubsan'
    compile_result = run([
        'gcc', '-O2', '-g', '-std=c11', '-Wall', '-Wextra', '-Werror',
        '-D_GNU_SOURCE', '-D_FORTIFY_SOURCE=3', '-fstack-protector-strong',
        '-fno-omit-frame-pointer', '-fsanitize=undefined',
        '-fno-sanitize-recover=undefined', '-I/app/c', str(harness),
        '/app/c/radial.c', '-o', str(binary), '-lm',
    ], timeout=60)
    assert compile_result.returncode == 0, compile_result.stderr
    result = run([str(binary)], timeout=60, env={
        **os.environ,
        'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1',
    })
    assert result.returncode == 0, result.stderr
