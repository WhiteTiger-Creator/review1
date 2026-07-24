import { AuroraError } from '../errors.mjs';

export function selectCodecs({ asset, resolvedProfile, capabilities }) {
  const container = resolvedProfile.output?.container || 'mp4';
  if (container === 'm4a') {
    return { container: 'm4a', video: null, audio: { codec: 'aac' } };
  }
  if (container === 'mov') {
    return { container: 'mov', video: { codec: 'prores_ks', pixel_format: 'yuv422p10le', profile: 3 }, audio: { codec: 'pcm_s24le' } };
  }
  return { container: 'mp4', video: { codec: 'libx264', pixel_format: 'yuv420p' }, audio: { codec: 'aac' } };
}
