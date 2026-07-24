import fs from 'node:fs/promises';
import YAML from 'yaml';
import { AuroraError } from '../errors.mjs';

export async function loadYaml(filePath) {
  try {
    const raw = await fs.readFile(filePath, 'utf8');
    return YAML.parse(raw);
  } catch (err) {
    throw new AuroraError(`Failed to load YAML ${filePath}: ${err.message}`, { code: 'IO_ERROR' });
  }
}
