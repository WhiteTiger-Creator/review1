import fs from 'node:fs/promises';
import { AuroraError } from '../errors.mjs';

export async function loadJson(filePath) {
  try {
    const raw = await fs.readFile(filePath, 'utf8');
    return JSON.parse(raw);
  } catch (err) {
    throw new AuroraError(`Failed to load JSON ${filePath}: ${err.message}`, { code: 'IO_ERROR' });
  }
}
