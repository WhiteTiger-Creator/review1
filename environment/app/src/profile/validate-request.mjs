import { AuroraError } from '../errors.mjs';

export function validateResolvedProfile(resolved, { asset, profileName }) {
  const subtitles = resolved.subtitles ?? {};
  const mode = subtitles.mode ?? 'none';
  const burnIn = subtitles.burn_in_language;
  const langs = subtitles.languages ?? [];

  if (mode === 'burn_in') {
    if (!burnIn) {
      throw new AuroraError(`Profile ${profileName} burn_in mode requires burn_in_language`, { code: 'INVALID_PROFILE' });
    }
    const matches = (asset.subtitle_tracks ?? []).filter((t) => t.language === burnIn);
    if (matches.length !== 1) {
      throw new AuroraError(`Ambiguous or missing burn_in_language ${burnIn} for asset ${asset.id}`, {
        code: 'AMBIGUOUS_BURN_IN',
      });
    }
  }

  if (mode === 'sidecar' && langs.length === 0) {
    throw new AuroraError(`Profile ${profileName} sidecar mode requires subtitle languages`, { code: 'INVALID_PROFILE' });
  }
}
