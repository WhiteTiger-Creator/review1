import crypto from 'node:crypto';
import { canonicalStringify } from './ordered-value.mjs';

export function sha256Hex(data) {
  const buf = typeof data === 'string' ? Buffer.from(data, 'utf8') : data;
  return crypto.createHash('sha256').update(buf).digest('hex');
}

export function sha256Prefixed(data) {
  return `sha256:${sha256Hex(data)}`;
}

export function fingerprintCanonical(value, config = {}) {
  return sha256Prefixed(canonicalStringify(value, config));
}
