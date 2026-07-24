import { stableSortStrings } from './stable-sort.mjs';

export function codePointCompare(a, b) {
  return String(a).localeCompare(String(b));
}

function shouldSortArray(path, config) {
  return (config.set_like_array_paths || []).some((p) => path.includes(p.split('.').pop()));
}

function shouldPreserveOrder(path, config) {
  return (config.preserve_order_array_paths || []).some((p) => path.endsWith(p));
}

export function canonicalize(value, config = {}, path = '') {
  if (value === null || typeof value !== 'object') return value;
  if (Array.isArray(value)) {
    if (shouldPreserveOrder(path, config)) {
      return value.map((item, idx) => canonicalize(item, config, `${path}[${idx}]`));
    }
    const mapped = value.map((item, idx) => canonicalize(item, config, `${path}[${idx}]`));
    if (shouldSortArray(path, config) && mapped.every((x) => typeof x === 'string')) {
      return stableSortStrings(mapped);
    }
    return mapped;
  }
  const keys = Object.keys(value).sort((a, b) => a.localeCompare(b));
  const out = {};
  for (const key of keys) {
    out[key] = canonicalize(value[key], config, path ? `${path}.${key}` : key);
  }
  return out;
}

export function canonicalStringify(value, config = {}) {
  return JSON.stringify(canonicalize(value, config));
}
