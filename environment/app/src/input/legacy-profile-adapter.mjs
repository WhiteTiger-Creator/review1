export function adaptLegacyProfiles(doc) {
  if (doc.format !== 'aurora-profile-v1') return doc;
  const profiles = {};
  for (const [name, flat] of Object.entries(doc.profiles || {})) {
    profiles[name] = {
      output: {
        delivery_profile: flat.delivery_profile,
        container: flat.container ?? 'mp4',
      },
      video: {
        target_width: flat.width ?? 1920,
        target_height: flat.height ?? 1080,
        tone_map: flat.tone_map ?? false,
      },
      audio: {
        normalization: flat.audio_normalization ?? { loudness: -16 },
      },
      subtitles: {
        mode: flat.subtitle_mode ?? 'sidecar',
        languages: flat.subtitle_languages ?? ['eng'],
        burn_in_language: flat.burn_in_language ?? null,
      },
    };
  }
  return { format: 'aurora-profiles-v3', profiles, jobs: doc.jobs ?? [] };
}
