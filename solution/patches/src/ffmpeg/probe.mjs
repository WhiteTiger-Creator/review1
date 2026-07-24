import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import fs from 'node:fs/promises';
import path from 'node:path';
import { sha256Prefixed } from '../util/digest.mjs';
import { stableSortStrings } from '../util/stable-sort.mjs';
import { AuroraError } from '../errors.mjs';

const execFileAsync = promisify(execFile);

function parseVersion(stdout) {
  const line = stdout.split('\n')[0] || '';
  const m = line.match(/ffmpeg version\s+(\S+)/);
  return m ? m[1] : line.trim();
}

function parseCapabilities(stdout) {
  const names = [];
  for (const line of stdout.split('\n')) {
    const m = line.match(/^\s*[A-Z.SXFDCTIPBN\.]+\s+(\S+)/);
    if (!m) continue;
    const name = m[1];
    if (name === '------' || name.startsWith('=')) continue;
    names.push(name);
  }
  return stableSortStrings([...new Set(names)]);
}

async function runFfmpeg(ffmpegPath, args) {
  try {
    const { stdout } = await execFileAsync(ffmpegPath, args, { maxBuffer: 16 * 1024 * 1024 });
    return stdout;
  } catch (err) {
    throw new AuroraError(`ffmpeg probe failed (${args.join(' ')}): ${err.message}`, { code: 'FFMPEG_PROBE' });
  }
}

export async function probeFfmpeg(ffmpegPath) {
  const resolved = path.resolve(ffmpegPath);
  const binary = await fs.readFile(resolved);
  const binary_digest = sha256Prefixed(binary);
  const executable = path.basename(resolved);

  const versionOut = await runFfmpeg(resolved, ['-version']);
  const encodersOut = await runFfmpeg(resolved, ['-encoders']);
  const filtersOut = await runFfmpeg(resolved, ['-filters']);
  const muxersOut = await runFfmpeg(resolved, ['-muxers']);

  return {
    executable,
    binary_digest,
    version: parseVersion(versionOut),
    capabilities: {
      encoders: parseCapabilities(encodersOut),
      filters: parseCapabilities(filtersOut),
      muxers: parseCapabilities(muxersOut),
    },
  };
}
