import fs from 'node:fs/promises';
import path from 'node:path';
import { AuroraError } from '../errors.mjs';

/**
 * Stage all artifacts, validate, then commit atomically.
 * @param {string} outputDir
 * @param {Record<string, string>} artifacts map of filename -> content
 * @param {{ validateAll: (staged: Record<string,string>) => Promise<void> }} hooks
 */
export async function writeAtomicOutput(outputDir, artifacts, hooks) {
  const stagingDir = path.join(outputDir, `.aurora-staging-${process.pid}-${Date.now()}`);
  await fs.mkdir(stagingDir, { recursive: true });
  const staged = {};
  const committed = [];
  try {
    for (const [name, content] of Object.entries(artifacts)) {
      const file = path.join(stagingDir, name);
      await fs.writeFile(file, content, 'utf8');
      staged[name] = file;
    }
    await hooks.validateAll(staged);
    await fs.mkdir(outputDir, { recursive: true });
    for (const [name, file] of Object.entries(staged)) {
      const dest = path.join(outputDir, name);
      await fs.rename(file, dest);
      committed.push(dest);
    }
    await fs.rmdir(stagingDir).catch(() => fs.rm(stagingDir, { recursive: true, force: true }));
  } catch (err) {
    for (const dest of committed) {
      await fs.rm(dest, { force: true }).catch(() => {});
    }
    await fs.rm(stagingDir, { recursive: true, force: true }).catch(() => {});
    if (err instanceof AuroraError) throw err;
    throw new AuroraError(err.message, { code: 'OUTPUT_ATOMIC_FAILURE', details: err });
  }
}
