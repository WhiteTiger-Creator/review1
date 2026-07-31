# Sideline idle decoy

Package /app/decoy contains an idle spectrogram lure. It must not be imported by `cmd/cdnqual` or any kiln package on the cast path. The rebuild script must not require it. Artifact `decoy_consulted` must never appear in qualitycast outputs.
