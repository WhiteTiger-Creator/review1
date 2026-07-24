import { AuroraError } from '../errors.mjs';

export function normalizeInventory(raw, validator) {
  if (raw.format !== 'aurora-inventory-v2') {
    throw new AuroraError(`Unsupported inventory format: ${raw.format}`, { code: 'INVALID_FORMAT' });
  }
  validator.validateInventory(raw);
  const assetsById = new Map();
  for (const asset of raw.assets) {
    if (assetsById.has(asset.id)) {
      throw new AuroraError(`Duplicate asset id: ${asset.id}`, { code: 'INVALID_INVENTORY' });
    }
    assetsById.set(asset.id, asset);
  }
  return { ...raw, assetsById };
}
