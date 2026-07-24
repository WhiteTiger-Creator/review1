import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import fs from 'node:fs/promises';
import path from 'node:path';
import { sha256Prefixed } from '../util/digest.mjs';
import { AuroraError } from '../errors.mjs';

const execFileAsync = promisify(execFile);

export async function probeFfmpeg(ffmpegPath) {
  const resolved = path.resolve(ffmpegPath);
  const binary = await fs.readFile(resolved);
  const binary_digest = sha256Prefixed(binary);
  const executable = resolved;

  async function run(args) {
    const { stdout } = await execFileAsync(resolved, args, { maxBuffer: 8 * 1024 * 1024 });
    return stdout;
  }

  const versionOut = await run(['-version']);
  const version = versionOut.split('\n')[0];

  function parseList(out) {
    return out.split(/\s+/).filter((t) => t && !t.startsWith('-') && t.length > 2);
  }

  return {
    executable,
    binary_digest,
    version,
    capabilities: {
      encoders: parseList(await run(['-encoders'])),
      filters: parseList(await run(['-filters'])),
      muxers: parseList(await run(['-muxers'])),
    },
  };
}
