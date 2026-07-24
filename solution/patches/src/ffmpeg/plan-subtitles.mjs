import { stableSortStrings } from '../util/stable-sort.mjs';

export function planSubtitleArtifacts({ asset, resolvedProfile, artifactName }) {
  const subtitles = resolvedProfile.subtitles ?? { mode: 'none' };
  const mode = subtitles.mode ?? 'none';
  const languages = stableSortStrings(subtitles.languages ?? []);
  const artifacts = [];

  if (mode === 'sidecar') {
    for (const lang of languages) {
      const track = (asset.subtitle_tracks ?? []).find((t) => t.language === lang);
      if (!track) continue;
      artifacts.push({
        language: lang,
        filename: `${artifactName}.${lang}.vtt`,
        stream_index: track.index,
        kind: 'sidecar',
      });
    }
  }

  return { mode, languages, burn_in_language: subtitles.burn_in_language ?? null, artifacts };
}
