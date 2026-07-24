import { escapeShellArg } from '../util/escaping.mjs';
import { outputFilename } from '../manifest/artifact-names.mjs';

export function renderMakefile({ buildPlan, inventory }) {
  const lines = [];
  lines.push('ASSET_ROOT ?= /assets');
  lines.push('OUTPUT_ROOT ?= /output');
  lines.push('CACHE_ROOT ?= /cache');
  lines.push('FFMPEG ?= ffmpeg');
  lines.push('');
  lines.push('.PHONY: all');
  lines.push('all: ' + buildPlan.jobs.map((j) => escapeShellArg(j.output.filename)).join(' '));
  lines.push('');
  const assetById = new Map(inventory.assets.map((a) => [a.id, a]));
  for (const job of buildPlan.jobs) {
    const asset = assetById.get(job.asset_id);
    const target = escapeShellArg(job.output.filename);
    const prereq = escapeShellArg(`$(ASSET_ROOT)/${asset.relative_path}`);
    lines.push(`${target}: ${prereq}`);
    lines.push(`\t$(FFMPEG) -y -i ${prereq} -c:v ${escapeShellArg(job.output.video_codec || 'copy')} ${escapeShellArg('$(OUTPUT_ROOT)/' + job.output.filename)}`);
    lines.push('');
  }
  return lines.join('\n');
}
