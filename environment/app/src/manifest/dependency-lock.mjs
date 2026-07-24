import { fingerprintCanonical } from '../util/digest.mjs';
import { canonicalize } from '../util/ordered-value.mjs';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const APP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

export function buildDependencyLock(probeResult) {
  const config = JSON.parse(fs.readFileSync(path.join(APP_ROOT, 'config/generator.json'), 'utf8'));
  const body = {
    format: config.dependency_lock_format,
    executable: probeResult.executable,
    binary_digest: probeResult.binary_digest,
    version: probeResult.version,
    capabilities: probeResult.capabilities,
  };
  const fingerprint = fingerprintCanonical(body, config);
  return { ...body, fingerprint };
}
