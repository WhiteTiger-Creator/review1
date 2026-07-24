import { AuroraError } from '../errors.mjs';

const PHASE = {
  orientation: 10,
  trim: 20,
  setpts: 30,
  crop_scale: 40,
  tone_map: 50,
  fps: 60,
  subtitles: 70,
  setsar: 80,
  format: 90,
};

function pushFilter(filters, phase, name, args) {
  const sequence = filters.filter((f) => f.phase === phase).length + 1;
  filters.push({ phase, sequence, name, args });
}

function isHdrAsset(asset) {
  const ct = asset.video?.color_transfer;
  return ct === 'smpte2084' || ct === 'arib-std-b67' || ct === 'hdr';
}

export function planFilters({ asset, resolvedProfile, codecSelection }) {
  const filters = [];
  const video = resolvedProfile.video ?? {};
  const rotation = asset.video?.rotation ?? 0;

  if (rotation === 90) pushFilter(filters, PHASE.orientation, 'transpose', '1');
  else if (rotation === 180) {
    pushFilter(filters, PHASE.orientation, 'transpose', '1');
    pushFilter(filters, PHASE.orientation, 'transpose', '1');
  } else if (rotation === 270) pushFilter(filters, PHASE.orientation, 'transpose', '2');

  if (video.trim_in_ms != null || video.trim_out_ms != null) {
    const start = ((video.trim_in_ms ?? 0) / 1000).toFixed(3);
    const end = video.trim_out_ms != null ? (video.trim_out_ms / 1000).toFixed(3) : '';
    pushFilter(filters, PHASE.trim, 'trim', end ? `start=${start}:end=${end}` : `start=${start}`);
  }

  if (video.setpts) {
    pushFilter(filters, PHASE.setpts, 'setpts', video.setpts);
  }

  if (video.crop) {
    pushFilter(filters, PHASE.crop_scale, 'crop', video.crop);
  }
  if (video.target_width && video.target_height) {
    pushFilter(filters, PHASE.crop_scale, 'scale', `${video.target_width}:${video.target_height}`);
  }

  const hdr = isHdrAsset(asset);
  const toneMap = Boolean(video.tone_map);
  if (hdr && toneMap && codecSelection.video?.tone_map_chain) {
    pushFilter(filters, PHASE.tone_map, 'zscale', 'transfer=linear:npl=100');
    pushFilter(filters, PHASE.tone_map, 'tonemap', 'tonemap=hable:desat=0');
    pushFilter(filters, PHASE.tone_map, 'zscale', 'transfer=bt709:matrix=bt709:primaries=bt709');
  }

  if (video.fps) {
    pushFilter(filters, PHASE.fps, 'fps', video.fps);
  }

  const subMode = resolvedProfile.subtitles?.mode ?? 'none';
  if (subMode === 'burn_in' && resolvedProfile.subtitles?.burn_in_language) {
    pushFilter(filters, PHASE.subtitles, 'subtitles', `filename=${resolvedProfile.subtitles.burn_in_language}`);
  }

  if (video.sar) {
    pushFilter(filters, PHASE.setsar, 'setsar', String(video.sar));
  }

  if (codecSelection.video?.pixel_format) {
    pushFilter(filters, PHASE.format, 'format', codecSelection.video.pixel_format);
  }

  return filters;
}
