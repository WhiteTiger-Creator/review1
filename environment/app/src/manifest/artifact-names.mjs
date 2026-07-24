const EXT = { mp4: 'mp4', mov: 'mov', m4a: 'm4a', ipod: 'm4a' };

export function slugArtifactName(name) {
  return String(name)
    .trim()
    .replace(/[^A-Za-z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '') || 'artifact';
}

export function outputFilename(artifactName, container) {
  const slug = slugArtifactName(artifactName);
  const ext = EXT[container] || container;
  return `${slug}.${ext}`;
}
