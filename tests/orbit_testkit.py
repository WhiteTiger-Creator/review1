"""Independent reference helpers for the orbital PSF release verifier."""
from __future__ import annotations

import contextlib
import hashlib
import json
import math
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import struct
import zlib
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Iterator

import numpy as np

APP = Path('/app')
DB = APP / 'data/orbit.sqlite3'
PUBLISH = APP / 'out'
FEATURE_NAMES = [
    'mean_intensity', 'std_intensity', 'radial_log_1', 'radial_log_2',
    'radial_log_3', 'radial_log_4', 'radial_log_5', 'radial_log_6',
    'high_low_ratio',
]

@dataclass
class HTTPResult:
    status_code: int
    headers: Any
    content: bytes
    url: str
    @property
    def text(self) -> str:
        return self.content.decode('utf-8')
    def json(self) -> Any:
        return json.loads(self.content)

def http_get(url: str, *, params: dict[str, Any] | None = None, timeout: float = 2.0) -> HTTPResult:
    if params:
        separator = '&' if '?' in url else '?'
        url = url + separator + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, method='GET')
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return HTTPResult(response.status, response.headers, response.read(), response.geturl())
    except urllib.error.HTTPError as error:
        return HTTPResult(error.code, error.headers, error.read(), error.geturl())

def _chunk(kind: bytes, body: bytes) -> bytes:
    return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xFFFFFFFF)

def rgb_png_bytes(array: np.ndarray) -> bytes:
    height, width = array.shape
    raw = bytearray()
    for row in array.astype(np.uint8):
        raw.append(0)
        raw.extend(np.repeat(row[:, None], 3, axis=1).tobytes())
    return (b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) + _chunk(b'IDAT', zlib.compress(bytes(raw), 9)) + _chunk(b'IEND', b''))

def decode_grayscale_png(body: bytes) -> np.ndarray:
    if not body.startswith(b'\x89PNG\r\n\x1a\n'):
        raise ValueError('invalid PNG signature')
    position = 8; width = height = None; color_type = None; compressed = bytearray()
    while position < len(body):
        if position + 12 > len(body): raise ValueError('truncated PNG')
        length = struct.unpack('>I', body[position:position+4])[0]
        kind = body[position+4:position+8]; data = body[position+8:position+8+length]
        if len(data) != length: raise ValueError('truncated PNG chunk')
        position += 12 + length
        if kind == b'IHDR':
            width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack('>IIBBBBB', data)
            if bit_depth != 8 or color_type != 0 or compression != 0 or filtering != 0 or interlace != 0:
                raise ValueError('unsupported PNG')
        elif kind == b'IDAT': compressed.extend(data)
        elif kind == b'IEND': break
    if width is None or height is None or color_type != 0: raise ValueError('missing grayscale IHDR')
    raw = zlib.decompress(bytes(compressed)); stride = width; expected = height * (stride + 1)
    if len(raw) != expected: raise ValueError('unexpected PNG data length')
    result = np.zeros((height, width), dtype=np.uint8); previous = np.zeros(width, dtype=np.uint8); offset = 0
    for row_index in range(height):
        filter_type = raw[offset]; offset += 1
        encoded = np.frombuffer(raw[offset:offset+stride], dtype=np.uint8).astype(np.int16); offset += stride
        decoded = np.zeros(stride, dtype=np.int16)
        for column in range(stride):
            left = int(decoded[column-1]) if column else 0
            up = int(previous[column])
            up_left = int(previous[column-1]) if column else 0
            value = int(encoded[column])
            if filter_type == 0: predictor = 0
            elif filter_type == 1: predictor = left
            elif filter_type == 2: predictor = up
            elif filter_type == 3: predictor = (left + up) // 2
            elif filter_type == 4:
                p = left + up - up_left; pa, pb, pc = abs(p-left), abs(p-up), abs(p-up_left)
                predictor = left if pa <= pb and pa <= pc else (up if pb <= pc else up_left)
            else: raise ValueError('unsupported PNG filter')
            decoded[column] = (value + predictor) & 0xFF
        result[row_index] = decoded.astype(np.uint8); previous = result[row_index]
    return result

def run(command: list[str], *, timeout: float = 120, check: bool = False, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, text=True, capture_output=True, timeout=timeout, env=env)
    if check and result.returncode != 0:
        raise AssertionError(f"command failed {command}:\nstdout={result.stdout}\nstderr={result.stderr}")
    return result

_BUILT = False

def build() -> None:
    global _BUILT
    if _BUILT:
        return
    run(['make', '-C', '/app', 'clean'], check=True)
    run(['make', '-C', '/app', 'build'], timeout=300, check=True)
    _BUILT = True

def catalog(db: Path = DB) -> dict[str, Any]:
    result = run(['/usr/local/bin/orbit-registry', 'export', '--db', str(db)], check=True)
    return json.loads(result.stdout)

def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return int(sock.getsockname()[1])

@contextlib.contextmanager
def api_server(db: Path = DB, publish: Path = PUBLISH, port: int | None = None) -> Iterator[str]:
    build()
    selected = port or free_port()
    process = subprocess.Popen(
        ['/app/bin/orbit-api', '--db', str(db), '--publish-dir', str(publish), '--web', '/app/web', '--listen', f'127.0.0.1:{selected}'],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    origin = f'http://127.0.0.1:{selected}'
    try:
        deadline = time.time() + 8
        while time.time() < deadline:
            if process.poll() is not None:
                stdout, stderr = process.communicate(timeout=1)
                raise AssertionError(f'API exited early: {stdout} {stderr}')
            try:
                if http_get(origin + '/health', timeout=0.2).status_code == 200:
                    break
            except Exception:
                time.sleep(0.05)
        else:
            raise AssertionError('API did not become ready')
        yield origin
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait(timeout=3)

def reference_features(sample: dict[str, Any]) -> list[float]:
    image = decode_grayscale_png(Path(sample['tile_path']).read_bytes()).astype(np.float64)
    x, y, size = sample['roi_x'], sample['roi_y'], sample['roi_size']
    roi = image[y:y+size, x:x+size]
    if roi.shape != (size, size):
        raise ValueError('ROI outside tile')
    q = (roi - sample['intensity_offset']) * sample['intensity_gain']
    mean = float(q.mean())
    std = float(q.std(ddof=0))
    u = 0.5 * (1 - np.cos(2 * np.pi * np.arange(size) / (size - 1)))
    window = np.outer(u, u)
    transformed = np.fft.rfft2((q - mean) * window)
    power = (transformed.real**2 + transformed.imag**2) / float(window.sum() ** 2)
    sums = np.zeros(6, dtype=np.float64)
    counts = np.zeros(6, dtype=np.int64)
    for row in range(size):
        ky = row if row <= size // 2 else row - size
        for column in range(size // 2 + 1):
            bin_index = int(math.floor(math.hypot(column, ky)))
            if 1 <= bin_index <= 6:
                multiplicity = 1 if column == 0 or (size % 2 == 0 and column == size // 2) else 2
                sums[bin_index - 1] += power[row, column] * multiplicity
                counts[bin_index - 1] += multiplicity
    if np.any(counts == 0):
        raise ValueError('empty radial bin')
    radial = sums / counts
    values = [mean / 255.0, std / 255.0]
    values.extend(np.log1p(radial).tolist())
    values.append(math.log1p(float(radial[3:].sum() / max(float(radial[:3].sum()), 1e-30))))
    return [float(value) for value in values]

def sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value); return 1 / (1 + z)
    z = math.exp(value); return z / (1 + z)

def infer(campaign: dict[str, Any], sample: dict[str, Any], features: list[float], etag: str) -> dict[str, Any]:
    head_probabilities = []
    weighted = total = 0.0
    for head in campaign['heads']:
        logit = head['intercept'] + sum(weight * feature for weight, feature in zip(head['weights'], features, strict=True))
        probability = sigmoid(logit / head['temperature'])
        head_probabilities.append(probability)
        weighted += probability * head['vote_weight']; total += head['vote_weight']
    probability = weighted / total
    uncertainty = max(head_probabilities) - min(head_probabilities)
    return {
        'sample': sample, 'features': features, 'probability': probability,
        'uncertainty': uncertainty, 'abstained': uncertainty > campaign['abstain_spread'],
        'prediction': int(probability >= campaign['decision_threshold']), 'etag': etag,
    }

def balanced_accuracy(evaluations: list[dict[str, Any]], indices: list[int]) -> float:
    correct = [0, 0]; total = [0, 0]
    for index in indices:
        item = evaluations[index]
        if item['abstained']:
            continue
        label = item['sample']['label']; total[label] += 1
        if item['prediction'] == label: correct[label] += 1
    if not all(total): raise ValueError('both labels required')
    return 0.5 * (correct[0] / total[0] + correct[1] / total[1])

def bootstrap_ci(campaign: dict[str, Any], evaluations: list[dict[str, Any]]) -> tuple[float, float]:
    strata: dict[tuple[str, int], list[int]] = defaultdict(list)
    for index, item in enumerate(evaluations):
        strata[(item['sample']['site_id'], item['sample']['label'])].append(index)
    scores = []
    seed = f"{campaign['campaign_id']}|{campaign['model_revision']}"
    for replicate in range(campaign['bootstrap_replicates']):
        selected = []
        for site, label in sorted(strata):
            pool = strata[(site, label)]
            for draw in range(len(pool)):
                digest = hashlib.sha256(f'{seed}|{replicate}|{site}|{label}|{draw}'.encode()).digest()
                selected.append(pool[int.from_bytes(digest[:8], 'big') % len(pool)])
        scores.append(balanced_accuracy(evaluations, selected))
    scores.sort(); count = len(scores)
    return scores[math.floor(0.025 * count)], scores[math.ceil(0.975 * count) - 1]

def metrics(campaign: dict[str, Any], evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    covered = [item for item in evaluations if not item['abstained']]
    coverage = len(covered) / len(evaluations)
    balanced = balanced_accuracy(evaluations, list(range(len(evaluations))))
    brier = sum((item['probability'] - item['sample']['label']) ** 2 for item in evaluations) / len(evaluations)
    ece = 0.0
    for bin_index in range(campaign['ece_bins']):
        low, high = bin_index / campaign['ece_bins'], (bin_index + 1) / campaign['ece_bins']
        members = [item for item in evaluations if item['probability'] >= low and (item['probability'] < high or (bin_index == campaign['ece_bins'] - 1 and item['probability'] <= high))]
        if members:
            mean_probability = sum(item['probability'] for item in members) / len(members)
            mean_label = sum(item['sample']['label'] for item in members) / len(members)
            ece += len(members) / len(evaluations) * abs(mean_probability - mean_label)
    cohorts = []
    for site in sorted({item['sample']['site_id'] for item in evaluations}):
        site_all = [item for item in evaluations if item['sample']['site_id'] == site]
        site_covered = [item for item in site_all if not item['abstained']]
        positives = [item for item in site_covered if item['sample']['label'] == 1]
        negatives = [item for item in site_covered if item['sample']['label'] == 0]
        cohorts.append({'site_id': site, 'count': len(site_all), 'coverage': len(site_covered) / len(site_all), 'tpr': sum(item['prediction'] == 1 for item in positives) / len(positives), 'fpr': sum(item['prediction'] == 1 for item in negatives) / len(negatives)})
    fprs = [item['fpr'] for item in cohorts]
    drift = []
    for index, reference in enumerate(campaign['feature_references']):
        observed = sum(item['features'][index] for item in evaluations) / len(evaluations)
        score = abs(observed - reference['mean']) / reference['scale']
        drift.append({'feature_index': index, 'feature_name': reference['feature_name'], 'observed_mean': observed, 'reference_mean': reference['mean'], 'score': score})
    low, high = bootstrap_ci(campaign, evaluations)
    return {'coverage': coverage, 'balanced_accuracy': balanced, 'ci': [low, high], 'brier': brier, 'ece': ece, 'fpr_gap': max(fprs) - min(fprs), 'max_feature_drift': max(item['score'] for item in drift), 'cohorts': cohorts, 'drift': drift}

def round9(value: float) -> float:
    rounded = math.floor(value * 1_000_000_000 + 0.5) / 1_000_000_000 if value >= 0 else math.ceil(value * 1_000_000_000 - 0.5) / 1_000_000_000
    return 0.0 if rounded == 0 else rounded

def go_float(value: float) -> str:
    """Format a finite float like Go strconv.FormatFloat with fmt='g', prec=-1."""
    if not math.isfinite(value):
        raise ValueError('non-finite JSON number')
    if value == 0:
        return '0'
    text = repr(value)
    if 'e' not in text and 'E' not in text:
        if text.endswith('.0'):
            return text[:-2]
        return text
    mantissa, exponent_text = text.lower().split('e')
    exponent = int(exponent_text)
    if -6 <= exponent < 21:
        from decimal import Decimal
        fixed = format(Decimal(text), 'f')
        if '.' in fixed:
            fixed = fixed.rstrip('0').rstrip('.')
        return fixed
    sign = '+' if exponent >= 0 else '-'
    return f"{mantissa}e{sign if exponent >= 0 else '-'}{abs(exponent)}" if exponent >= 0 else f"{mantissa}e-{abs(exponent)}"

def go_json(value: Any, *, indent: int | None = None, level: int = 0) -> str:
    if value is None:
        return 'null'
    if value is True:
        return 'true'
    if value is False:
        return 'false'
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return go_float(value)
    if isinstance(value, list):
        if not value:
            return '[]'
        if indent is None:
            return '[' + ','.join(go_json(item, indent=None) for item in value) + ']'
        prefix = ' ' * (indent * (level + 1)); closing = ' ' * (indent * level)
        return '[\n' + ',\n'.join(prefix + go_json(item, indent=indent, level=level + 1) for item in value) + '\n' + closing + ']'
    if isinstance(value, dict):
        if not value:
            return '{}'
        if indent is None:
            return '{' + ','.join(json.dumps(str(key), ensure_ascii=False) + ':' + go_json(item, indent=None) for key, item in value.items()) + '}'
        prefix = ' ' * (indent * (level + 1)); closing = ' ' * (indent * level)
        return '{\n' + ',\n'.join(prefix + json.dumps(str(key), ensure_ascii=False) + ': ' + go_json(item, indent=indent, level=level + 1) for key, item in value.items()) + '\n' + closing + '}'
    raise TypeError(type(value))

def canonical_bytes(value: Any) -> bytes:
    return (go_json(value, indent=2) + '\n').encode()

def compact_go_bytes(value: Any) -> bytes:
    return go_json(value, indent=None).encode()

def reference_report(campaign: dict[str, Any], evaluations: list[dict[str, Any]], fftw_version: str = '3.3.10') -> tuple[dict[str, Any], bytes, bytes]:
    stat = metrics(campaign, evaluations)
    gates = {
        'coverage': stat['coverage'] >= campaign['min_coverage'],
        'balanced_accuracy_lower': stat['ci'][0] >= campaign['min_balanced_accuracy_lower'],
        'brier': stat['brier'] <= campaign['max_brier'],
        'ece': stat['ece'] <= campaign['max_ece'],
        'fpr_gap': stat['fpr_gap'] <= campaign['max_fpr_gap'],
        'feature_drift': stat['max_feature_drift'] <= campaign['max_feature_drift'],
    }
    heads = []
    for head in campaign['heads']:
        payload = {'head_id': head['head_id'], 'head_order': head['head_order'], 'intercept': head['intercept'], 'temperature': head['temperature'], 'vote_weight': head['vote_weight'], 'weights': head['weights']}
        heads.append({'head_id': head['head_id'], 'sha256': hashlib.sha256(compact_go_bytes(payload)).hexdigest()})
    report = {
        'schema_version': 'orbital-ensemble-release/v1', 'campaign_id': campaign['campaign_id'],
        'model_revision': campaign['model_revision'], 'feature_revision': campaign['feature_revision'],
        'release_status': 'accepted' if all(gates.values()) else 'rejected', 'content_sha256': '',
        'fftw_version': fftw_version, 'sample_count': len(evaluations),
        'coverage': round9(stat['coverage']), 'balanced_accuracy': round9(stat['balanced_accuracy']),
        'balanced_accuracy_ci95': [round9(stat['ci'][0]), round9(stat['ci'][1])],
        'brier_score': round9(stat['brier']), 'ece': round9(stat['ece']),
        'fpr_gap': round9(stat['fpr_gap']), 'max_feature_drift': round9(stat['max_feature_drift']),
        'gates': gates, 'heads': heads,
        'cohorts': [{'site_id': item['site_id'], 'count': item['count'], 'coverage': round9(item['coverage']), 'tpr': round9(item['tpr']), 'fpr': round9(item['fpr'])} for item in stat['cohorts']],
        'feature_drift': [{'feature_index': item['feature_index'], 'feature_name': item['feature_name'], 'observed_mean': round9(item['observed_mean']), 'reference_mean': round9(item['reference_mean']), 'score': round9(item['score'])} for item in stat['drift']],
        'samples': [{'sample_index': item['sample']['sample_index'], 'sample_id': item['sample']['sample_id'], 'site_id': item['sample']['site_id'], 'device_family': item['sample']['device_family'], 'label': item['sample']['label'], 'probability': round9(item['probability']), 'uncertainty': round9(item['uncertainty']), 'abstained': item['abstained'], 'prediction': item['prediction'], 'source_etag': item['etag']} for item in evaluations],
    }
    report['content_sha256'] = hashlib.sha256(canonical_bytes(report)).hexdigest()
    raw = canonical_bytes(report)
    lines = ['digraph orbital_release {', '  graph [rankdir=LR];', '  node [shape=box];', f'  campaign [label={json.dumps("campaign " + report["campaign_id"])}];', f'  model [label={json.dumps("model revision " + str(report["model_revision"]))}];', f'  features [label={json.dumps("features " + report["feature_revision"])}];', f'  metrics [label={json.dumps("status " + report["release_status"])}];', f'  release [label={json.dumps("sha256 " + report["content_sha256"])}];', '  campaign -> features;', '  campaign -> model;', '  features -> metrics;', '  model -> metrics;', '  metrics -> release;']
    for index, head in enumerate(report['heads']):
        lines.append(f'  head_{index} [label={json.dumps(head["head_id"] + " " + head["sha256"])}];')
        lines.append(f'  head_{index} -> model;')
    lines.append('}')
    return report, raw, ('\n'.join(lines) + '\n').encode()

def evaluations_from_files(campaign: dict[str, Any]) -> list[dict[str, Any]]:
    values = []
    for sample in campaign['samples']:
        body = Path(sample['tile_path']).read_bytes()
        etag = f'"sha256:{hashlib.sha256(body).hexdigest()}"'
        values.append(infer(campaign, sample, reference_features(sample), etag))
    return values

def certify(origin: str, publish: Path, db: Path = DB, timeout_ms: int = 5000, timeout: float = 180) -> subprocess.CompletedProcess[str]:
    build()
    return run(['/app/bin/orbit-certify', '--db', str(db), '--api', origin, '--publish-dir', str(publish), '--timeout-ms', str(timeout_ms)], timeout=timeout)

def current_release(publish: Path) -> tuple[dict[str, Any], bytes, bytes, dict[str, Any]]:
    manifest = json.loads((publish / 'current.json').read_text())
    release_bytes = (publish / manifest['release']).read_bytes()
    provenance_bytes = (publish / manifest['provenance']).read_bytes()
    return json.loads(release_bytes), release_bytes, provenance_bytes, manifest

class FixtureServer:
    def __init__(self, campaign: dict[str, Any], mutation: str | None = None, delay: float = 0.0):
        self.campaign = campaign; self.mutation = mutation; self.delay = delay; self.requests: list[str] = []; self.accept_headers: list[str | None] = []
        self.port = free_port(); outer = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_: Any) -> None: pass
            def do_GET(self) -> None:
                outer.requests.append(self.path); outer.accept_headers.append(self.headers.get('Accept'))
                if outer.delay: time.sleep(outer.delay)
                parsed = urllib.parse.urlparse(self.path)
                parts = parsed.path.split('/')
                try:
                    campaign_id = urllib.parse.unquote(parts[3]); index = int(parts[5]); sample = outer.campaign['samples'][index]
                    query = urllib.parse.parse_qs(parsed.query, strict_parsing=True)
                    valid = campaign_id == outer.campaign['campaign_id'] and query == {'revision': [str(outer.campaign['model_revision'])]} and self.headers.get('Accept') == 'image/png'
                except Exception:
                    valid = False
                if not valid:
                    self.send_response(404); self.end_headers(); return
                if outer.mutation == 'redirect':
                    self.send_response(302); self.send_header('Location', f'/v1/campaigns/{urllib.parse.quote(campaign_id, safe="")}/samples/{(index + 1) % len(outer.campaign["samples"])}/tile?revision={outer.campaign["model_revision"]}'); self.end_headers(); return
                body = Path(sample['tile_path']).read_bytes()
                if outer.mutation == 'color':
                    array = decode_grayscale_png(body)
                    body = rgb_png_bytes(array)
                if outer.mutation == 'oversized':
                    body = body + b'0' * ((8 << 20) + 1)
                digest = hashlib.sha256(body).hexdigest()
                self.send_response(200)
                self.send_header('Content-Type', 'image/png' if outer.mutation != 'content_type' else 'application/octet-stream')
                self.send_header('Cache-Control', 'no-store' if outer.mutation != 'cache' else 'max-age=3600')
                headers = {'X-Campaign-ID': campaign_id, 'X-Sample-ID': sample['sample_id'], 'X-Sample-Index': str(index), 'X-Site-ID': sample['site_id'], 'X-Device-Family': sample['device_family'], 'X-Label': str(sample['label']), 'X-Model-Revision': str(outer.campaign['model_revision'])}
                if outer.mutation == 'metadata': headers['X-Site-ID'] = 'wrong-site'
                for name, value in headers.items(): self.send_header(name, value)
                etag = f'"sha256:{digest}"' if outer.mutation != 'etag' else '"sha256:' + '0'*64 + '"'
                self.send_header('ETag', etag); self.end_headers(); self.wfile.write(body)
        self.server = ThreadingHTTPServer(('127.0.0.1', self.port), Handler)
        import threading
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
    def __enter__(self) -> 'FixtureServer': self.thread.start(); return self
    def __exit__(self, *_: Any) -> None: self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=2)
    @property
    def origin(self) -> str: return f'http://127.0.0.1:{self.port}'

def clean_publish(path: Path) -> None:
    if path.exists(): shutil.rmtree(path)
    path.mkdir(parents=True)
