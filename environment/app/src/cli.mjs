import path from 'node:path';
import fs from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { loadJson } from './io/load-json.mjs';
import { loadYaml } from './io/load-yaml.mjs';
import { writeAtomicOutput } from './io/atomic-output.mjs';
import { normalizeInventory } from './input/normalize-inventory.mjs';
import { normalizeProfiles } from './input/normalize-profiles.mjs';
import { probeFfmpeg } from './ffmpeg/probe.mjs';
import { buildDependencyLock } from './manifest/dependency-lock.mjs';
import { buildPlan } from './manifest/build-plan.mjs';
import { renderMakefile } from './render/makefile.mjs';
import { createValidator } from './schema/validator.mjs';
import { canonicalStringify } from './util/ordered-value.mjs';
import { AuroraError } from './errors.mjs';

const APP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function parseArgs(argv) {
  const args = argv.slice(2);
  if (args[0] !== 'synthesize') {
    throw new AuroraError('Usage: aurora-build.mjs synthesize --inventory PATH --profiles PATH --output-dir PATH [--ffmpeg PATH] [--check] [--explain FILE]');
  }
  const opts = { ffmpeg: 'ffmpeg', check: false, explain: null };
  for (let i = 1; i < args.length; i++) {
    const a = args[i];
    if (a === '--inventory') opts.inventory = args[++i];
    else if (a === '--profiles') opts.profiles = args[++i];
    else if (a === '--output-dir') opts.outputDir = args[++i];
    else if (a === '--ffmpeg') opts.ffmpeg = args[++i];
    else if (a === '--check') opts.check = true;
    else if (a === '--explain') opts.explain = args[++i];
    else throw new AuroraError(`Unknown argument: ${a}`);
  }
  if (!opts.inventory || !opts.profiles || !opts.outputDir) {
    throw new AuroraError('Missing required --inventory, --profiles, or --output-dir');
  }
  return opts;
}

async function loadProfiles(profilesPath) {
  if (/\.(ya?ml)$/i.test(profilesPath)) return loadYaml(profilesPath);
  return loadJson(profilesPath);
}

export async function synthesize(opts) {
  const validator = createValidator();
  const inventoryRaw = await loadJson(opts.inventory);
  const profilesRaw = await loadProfiles(opts.profiles);
  const inventory = normalizeInventory(inventoryRaw, validator);
  const profilesDoc = normalizeProfiles(profilesRaw, validator);
  const probe = await probeFfmpeg(opts.ffmpeg);
  const lock = buildDependencyLock(probe);
  const buildPlan = buildPlanDoc(inventory, profilesDoc, lock, probe.capabilities);
  validator.validateCrossField(buildPlan, lock);
  const makefile = renderMakefile({ buildPlan, inventory: inventoryRaw });

  const config = JSON.parse(await fs.readFile(path.join(APP_ROOT, 'config/generator.json'), 'utf8'));
  const artifacts = {
    [config.artifacts.build_plan]: canonicalStringify(buildPlan, config) + '\n',
    [config.artifacts.dependency_lock]: canonicalStringify(lock, config) + '\n',
    [config.artifacts.makefile]: makefile + '\n',
  };

  const explain = {
    inventory_path: path.resolve(opts.inventory),
    profiles_path: path.resolve(opts.profiles),
    job_count: buildPlan.jobs.length,
    lock_fingerprint: lock.fingerprint,
    decisions: buildPlan.jobs.map((j) => ({ job_id: j.job_id, cache_key: j.cache_key, filters: j.filters.length })),
  };

  return { artifacts, buildPlan, lock, explain };
}

function buildPlanDoc(inventory, profilesDoc, lock, capabilities) {
  return buildPlan({ inventory, profilesDoc, lock, probeCapabilities: capabilities });
}

export async function runCli(argv) {
  try {
    const opts = parseArgs(argv);
    const { artifacts, explain } = await synthesize(opts);

    if (opts.explain) {
      await fs.writeFile(opts.explain, JSON.stringify(explain, null, 2) + '\n', 'utf8');
    }

    if (!opts.check) {
      const validator = createValidator();
      const config = JSON.parse(await fs.readFile(path.join(APP_ROOT, 'config/generator.json'), 'utf8'));
      await writeAtomicOutput(opts.outputDir, artifacts, {
        async validateAll(staged) {
          const buildPlan = JSON.parse(await fs.readFile(staged[config.artifacts.build_plan], 'utf8'));
          const lock = JSON.parse(await fs.readFile(staged[config.artifacts.dependency_lock], 'utf8'));
          validator.validateBuildPlan(buildPlan);
          validator.validateDependencyLock(lock);
          validator.validateCrossField(buildPlan, lock);
        },
      });
    }
  } catch (err) {
    const message = err instanceof AuroraError ? err.message : String(err);
    console.error(message);
    process.exit(1);
  }
}
