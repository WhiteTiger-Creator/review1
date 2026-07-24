import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { AuroraError } from '../errors.mjs';

const APP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

function loadSchema(name) {
  const raw = fs.readFileSync(path.join(APP_ROOT, 'schemas', name), 'utf8');
  return JSON.parse(raw);
}

export function createValidator() {
  const ajv = new Ajv2020({ allErrors: true, strict: false });
  addFormats(ajv);
  const schemas = {
    inventory: loadSchema('inventory-v2.schema.json'),
    profiles: loadSchema('profiles-v3.schema.json'),
    legacyProfiles: loadSchema('legacy-profiles-v1.schema.json'),
    buildPlan: loadSchema('build-plan-v3.schema.json'),
    dependencyLock: loadSchema('dependency-lock-v1.schema.json'),
  };
  const validate = {
    inventory: ajv.compile(schemas.inventory),
    profiles: ajv.compile(schemas.profiles),
    legacyProfiles: ajv.compile(schemas.legacyProfiles),
    buildPlan: ajv.compile(schemas.buildPlan),
    dependencyLock: ajv.compile(schemas.dependencyLock),
  };

  function assertOk(fn, data, label) {
    if (!fn(data)) {
      throw new AuroraError(`Schema validation failed for ${label}`, {
        code: 'SCHEMA_INVALID',
        details: fn.errors,
      });
    }
  }

  return {
    validateInventory: (d) => assertOk(validate.inventory, d, 'inventory'),
    validateProfiles: (d) => assertOk(validate.profiles, d, 'profiles'),
    validateLegacyProfiles: (d) => assertOk(validate.legacyProfiles, d, 'legacy-profiles'),
    validateBuildPlan: (d) => assertOk(validate.buildPlan, d, 'build-plan'),
    validateDependencyLock: (d) => assertOk(validate.dependencyLock, d, 'dependency-lock'),
    validateCrossField(buildPlan, lock) {
      if (buildPlan.lock_fingerprint !== lock.fingerprint) {
        throw new AuroraError('build-plan lock_fingerprint does not match dependency-lock fingerprint', {
          code: 'CROSS_FIELD_INVALID',
        });
      }
    },
  };
}
