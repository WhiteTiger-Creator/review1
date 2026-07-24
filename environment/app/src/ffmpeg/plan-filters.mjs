import { AuroraError } from '../errors.mjs';

export function planFilters({ asset, resolvedProfile, codecSelection }) {
  const byName = {};
  const video = resolvedProfile.video ?? {};
  const rotation = asset.video?.rotation ?? 0;
  if (rotation === 90) byName.transpose = { name: 'transpose', args: '1' };
  if (video.target_width && video.target_height) {
    byName.scale = { name: 'scale', args: `${video.target_width}:${video.target_height}` };
  }
  if (video.fps) byName.fps = { name: 'fps', args: video.fps };
  if (codecSelection.video?.pixel_format) {
    byName.format = { name: 'format', args: codecSelection.video.pixel_format };
  }
  const names = Object.keys(byName).sort((a, b) => a.localeCompare(b));
  return names.map((n, idx) => ({ phase: (idx + 1) * 10, sequence: 1, ...byName[n] }));
}
