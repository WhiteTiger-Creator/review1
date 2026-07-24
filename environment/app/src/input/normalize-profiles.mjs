import { adaptLegacyProfiles } from './legacy-profile-adapter.mjs';
import { AuroraError } from '../errors.mjs';

export function normalizeProfiles(raw, validator) {
  let doc = raw;
  if (doc.format === 'aurora-profile-v1') {
    validator.validateLegacyProfiles(doc);
    doc = adaptLegacyProfiles(doc);
  }
  if (doc.format !== 'aurora-profiles-v3') {
    throw new AuroraError(`Unsupported profiles format: ${doc.format}`, { code: 'INVALID_FORMAT' });
  }
  validator.validateProfiles(doc);
  return doc;
}
