import fs from 'node:fs/promises';
import path from 'node:path';
import { AuroraError } from '../errors.mjs';

export async function writeAtomicOutput(outputDir, artifacts, hooks) {
  await fs.mkdir(outputDir, { recursive: true });
  const names = Object.keys(artifacts);
  const buildPlanName = names.find((n) => n.endsWith('build-plan.json')) || names[0];
  const buildPlanPath = path.join(outputDir, buildPlanName);
  await fs.writeFile(buildPlanPath, artifacts[buildPlanName], 'utf8');
  const staged = {};
  for (const [name, content] of Object.entries(artifacts)) {
    staged[name] = path.join(outputDir, `.staging-${name}`);
    await fs.writeFile(staged[name], content, 'utf8');
  }
  try {
    await hooks.validateAll(staged);
    for (const [name, file] of Object.entries(staged)) {
      if (name === buildPlanName) continue;
      await fs.rename(file, path.join(outputDir, name));
    }
  } catch (err) {
    for (const file of Object.values(staged)) await fs.rm(file, { force: true }).catch(() => {});
    throw err instanceof AuroraError ? err : new AuroraError(err.message, { code: 'OUTPUT_ATOMIC_FAILURE' });
  }
}
