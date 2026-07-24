import { AuroraError } from '../errors.mjs';

function clone(value) {
  return structuredClone(value);
}

/** Presence-aware merge: Object.hasOwn on child keys; null removes; arrays replace; objects deep-merge. */
export function mergePresenceAware(parent, child) {
  const result = parent ? clone(parent) : {};
  if (!child || typeof child !== 'object') return result;
  for (const key of Object.keys(child)) {
    if (key === 'extends') continue;
    if (!Object.hasOwn(child, key)) continue;
    const childVal = child[key];
    if (childVal === null) {
      delete result[key];
      continue;
    }
    if (Array.isArray(childVal)) {
      result[key] = clone(childVal);
      continue;
    }
    if (typeof childVal === 'object') {
      result[key] = mergePresenceAware(result[key] ?? {}, childVal);
      continue;
    }
    result[key] = childVal;
  }
  return result;
}

export function resolveProfile(profiles, name, stack = []) {
  const node = profiles[name];
  if (!node) {
    throw new AuroraError(`Unknown profile: ${name}`, { code: 'UNKNOWN_PROFILE' });
  }
  if (stack.includes(name)) {
    throw new AuroraError(`Profile inheritance cycle: ${[...stack, name].join(' -> ')}`, { code: 'PROFILE_CYCLE' });
  }
  const parentName = node.extends;
  const base = parentName ? resolveProfile(profiles, parentName, [...stack, name]) : {};
  return mergePresenceAware(base, node);
}
