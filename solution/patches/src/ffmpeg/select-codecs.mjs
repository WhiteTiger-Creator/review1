import { AuroraError } from '../errors.mjs';

function hasEncoder(caps, name) {
  return caps.encoders.includes(name);
}
function hasMuxer(caps, name) {
  return caps.muxers.includes(name);
}
function requireEncoder(caps, name) {
  if (!hasEncoder(caps, name)) {
    throw new AuroraError(`Missing required encoder: ${name}`, { code: 'MISSING_CAPABILITY' });
  }
}
function requireMuxer(caps, name) {
  if (!hasMuxer(caps, name)) {
    throw new AuroraError(`Missing required muxer: ${name}`, { code: 'MISSING_CAPABILITY' });
  }
}

function isHdrAsset(asset) {
  const ct = asset.video?.color_transfer;
  return ct === 'smpte2084' || ct === 'arib-std-b67' || ct === 'hdr';
}

export function selectCodecs({ asset, resolvedProfile, capabilities }) {
  const delivery = resolvedProfile.output?.delivery_profile || 'web-sdr';
  const toneMap = Boolean(resolvedProfile.video?.tone_map);
  const hdr = isHdrAsset(asset);
  const alpha = Boolean(asset.video?.has_alpha);

  if (delivery === 'audio-preview') {
    requireEncoder(capabilities, 'aac');
    requireMuxer(capabilities, 'ipod');
    return {
      container: 'm4a',
      video: null,
      audio: { codec: 'aac' },
    };
  }

  if (delivery === 'web-sdr') {
    requireEncoder(capabilities, 'libx264');
    requireMuxer(capabilities, 'mp4');
    return {
      container: resolvedProfile.output?.container || 'mp4',
      video: { codec: 'libx264', pixel_format: 'yuv420p', tone_map_chain: hdr && toneMap },
      audio: { codec: 'aac' },
    };
  }

  if (delivery === 'web-hdr') {
    requireEncoder(capabilities, 'libx265');
    requireMuxer(capabilities, 'mp4');
    return {
      container: resolvedProfile.output?.container || 'mp4',
      video: { codec: 'libx265', pixel_format: 'yuv420p10le', tag: 'hvc1' },
      audio: { codec: 'aac' },
    };
  }

  if (delivery === 'archive') {
    requireEncoder(capabilities, 'prores_ks');
    requireMuxer(capabilities, 'mov');
    if (alpha) {
      return {
        container: 'mov',
        video: { codec: 'prores_ks', profile: 4, pixel_format: 'yuva444p10le' },
        audio: { codec: 'pcm_s24le' },
      };
    }
    return {
      container: 'mov',
      video: { codec: 'prores_ks', profile: 3, pixel_format: 'yuv422p10le' },
      audio: { codec: 'pcm_s24le' },
    };
  }

  throw new AuroraError(`Unknown delivery_profile: ${delivery}`, { code: 'INVALID_PROFILE' });
}
