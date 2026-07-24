import { resolveProfile } from '../profile/resolve-inheritance.mjs';
import { validateResolvedProfile } from '../profile/validate-request.mjs';
import { selectCodecs } from '../ffmpeg/select-codecs.mjs';
import { planFilters } from '../ffmpeg/plan-filters.mjs';
import { planSubtitleArtifacts } from '../ffmpeg/plan-subtitles.mjs';
import { outputFilename } from './artifact-names.mjs';
import { sha256Prefixed } from '../util/digest.mjs';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const APP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

export function buildPlan({ inventory, profilesDoc, lock, probeCapabilities }) {
  const config = JSON.parse(fs.readFileSync(path.join(APP_ROOT, 'config/generator.json'), 'utf8'));
  const jobs = [];
  const preLockFingerprint = 'sha256:' + '0'.repeat(64);

  for (const req of profilesDoc.jobs) {
    const asset = inventory.assetsById.get(req.asset_id);
    const resolved = resolveProfile(profilesDoc.profiles, req.profile);
    validateResolvedProfile(resolved, { asset, profileName: req.profile });
    const codecSelection = selectCodecs({ asset, resolvedProfile: resolved, capabilities: probeCapabilities });
    const filters = planFilters({ asset, resolvedProfile: resolved, codecSelection });
    const subtitlePlan = planSubtitleArtifacts({ asset, resolvedProfile: resolved, artifactName: req.artifact_name });

    const cache_key = sha256Prefixed(JSON.stringify({
      source_root: inventory.source_root,
      content_digest: asset.content_digest,
      resolved_profile: resolved,
      filters,
      lock_fingerprint: preLockFingerprint,
    }));

    const output = {
      filename: outputFilename(req.artifact_name, codecSelection.container),
      container: codecSelection.container,
    };
    if (codecSelection.video) {
      output.video_codec = codecSelection.video.codec;
      output.pixel_format = codecSelection.video.pixel_format;
    }
    if (codecSelection.audio) output.audio_codec = codecSelection.audio.codec;

    jobs.push({
      job_id: `${req.asset_id}:${req.profile}`,
      asset_id: req.asset_id,
      profile: req.profile,
      artifact_name: req.artifact_name,
      cache_key,
      output,
      filters,
      subtitle_artifacts: subtitlePlan.artifacts,
    });
  }

  return {
    format: config.build_plan_format,
    generator: { id: config.generator_id, version: config.generator_version },
    lock_fingerprint: lock?.fingerprint ?? preLockFingerprint,
    jobs,
  };
}
