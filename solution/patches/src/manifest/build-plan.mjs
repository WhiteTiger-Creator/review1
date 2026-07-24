import { resolveProfile } from '../profile/resolve-inheritance.mjs';
import { validateResolvedProfile } from '../profile/validate-request.mjs';
import { selectCodecs } from '../ffmpeg/select-codecs.mjs';
import { planFilters } from '../ffmpeg/plan-filters.mjs';
import { planSubtitleArtifacts } from '../ffmpeg/plan-subtitles.mjs';
import { outputFilename } from './artifact-names.mjs';
import { fingerprintCanonical, sha256Prefixed } from '../util/digest.mjs';
import { canonicalize } from '../util/ordered-value.mjs';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const APP_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');

function cacheKeyPayload({ asset, resolvedProfile, filters, lockFingerprint, config }) {
  return canonicalize(
    {
      content_digest: asset.content_digest,
      resolved_profile: resolvedProfile,
      filters,
      lock_fingerprint: lockFingerprint,
    },
    config,
  );
}

export function buildPlan({ inventory, profilesDoc, lock, probeCapabilities }) {
  const config = JSON.parse(fs.readFileSync(path.join(APP_ROOT, 'config/generator.json'), 'utf8'));
  const jobs = [];

  for (const req of profilesDoc.jobs) {
    const asset = inventory.assetsById.get(req.asset_id);
    if (!asset) {
      throw new Error(`Unknown asset_id in job: ${req.asset_id}`);
    }
    const resolved = resolveProfile(profilesDoc.profiles, req.profile);
    validateResolvedProfile(resolved, { asset, profileName: req.profile });
    const codecSelection = selectCodecs({ asset, resolvedProfile: resolved, capabilities: probeCapabilities });
    const filters = planFilters({ asset, resolvedProfile: resolved, codecSelection });
    const subtitlePlan = planSubtitleArtifacts({ asset, resolvedProfile: resolved, artifactName: req.artifact_name });

    const cache_key = sha256Prefixed(
      JSON.stringify(cacheKeyPayload({
        asset,
        resolvedProfile: resolved,
        filters,
        lockFingerprint: lock.fingerprint,
        config,
      })),
    );

    const output = {
      filename: outputFilename(req.artifact_name, codecSelection.container),
      container: codecSelection.container,
    };
    if (codecSelection.video) {
      output.video_codec = codecSelection.video.codec;
      output.pixel_format = codecSelection.video.pixel_format;
      if (codecSelection.video.profile != null) output.video_profile = codecSelection.video.profile;
      if (codecSelection.video.tag) output.video_tag = codecSelection.video.tag;
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

  jobs.sort((a, b) => (a.job_id < b.job_id ? -1 : a.job_id > b.job_id ? 1 : 0));

  return {
    format: config.build_plan_format,
    generator: { id: config.generator_id, version: config.generator_version },
    lock_fingerprint: lock.fingerprint,
    jobs,
  };
}
