/**
 * Map aurora-profile-v1 flat profiles to internal v3 shape BEFORE inheritance.
 * Legacy omission defaults: subtitle_mode -> "none"; omitted audio_normalization -> no loudness filter.
 */
export function adaptLegacyProfiles(doc) {
  if (doc.format !== 'aurora-profile-v1') return doc;
  const profiles = {};
  for (const [name, flat] of Object.entries(doc.profiles || {})) {
    profiles[name] = {
      output: {
        delivery_profile: flat.delivery_profile,
        container: flat.container ?? null,
      },
      video: {
        target_width: flat.width ?? null,
        target_height: flat.height ?? null,
        fps: flat.fps ?? null,
        crop: flat.crop ?? null,
        tone_map: flat.tone_map ?? false,
        trim_in_ms: flat.trim_in_ms ?? null,
        trim_out_ms: flat.trim_out_ms ?? null,
        setpts: flat.setpts ?? null,
        sar: flat.sar ?? null,
      },
      audio: {
        normalization: Object.hasOwn(flat, 'audio_normalization') ? flat.audio_normalization : null,
        language: flat.audio_language ?? null,
      },
      subtitles: {
        mode: Object.hasOwn(flat, 'subtitle_mode') ? flat.subtitle_mode : 'none',
        languages: flat.subtitle_languages ?? [],
        burn_in_language: flat.burn_in_language ?? null,
      },
    };
  }
  return {
    format: 'aurora-profiles-v3',
    profiles,
    jobs: doc.jobs ?? [],
  };
}
