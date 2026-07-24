# Aurora Trailer Kit Release Handbook
## Table of Contents
1. Release-system overview
2. Normative hierarchy and contract versions
3. Inventory v2 contract
4. Content digest verification
5. Profile v3 structure
6. Profile inheritance and explicit-value semantics
7. Legacy profile v1 compatibility
8. FFmpeg executable selection and capability probing
9. Container policy
10. Video codec and pixel-format matrix
11. Audio policy
12. Video filter phase model
13. Audio filter phase model
14. Subtitle burn-in and sidecar policy
15. Artifact naming and collision behavior
16. Build-plan schema field semantics
17. Dependency-lock semantics
18. Canonical serialization and cache keys
19. Makefile variable, target, and escaping rules
20. Transactional output and failure behavior
21. Worked current-release examples
22. Troubleshooting guide
23. Archived 2.x operational handbook (SUPERSEDED)
24. Archived 1.x profile reference (legacy input only)
25. Current errata and migration notes

## 2. Normative hierarchy
Current Contract 3.x normative statements control current planning. The legacy v1 appendix is normative only for interpreting v1 input defaults. Historical examples are non-normative unless a current chapter incorporates them. Errata in section 25 override earlier current paragraphs they identify.

### 6. Profile inheritance
A missing key inherits. A present scalar replaces the inherited value even when false, 0, or empty string. A present array replaces; arrays are never concatenated. A present object deep-merges by key. A present null removes an optional inherited setting. Profile inheritance cycles are errors.

Inheritance resolves the profile before filter emission. Resolved zeros and empty strings remain present per this section; whether a filter emits for those values is governed by section 12 and erratum 5, not by inheritance alone.

### 7. Legacy v1 compatibility
When subtitle_mode is omitted in aurora-profile-v1, the default is none, not sidecar. When audio_normalization is omitted, no loudness filter is applied.

### 8. FFmpeg executable selection and capability probing (CLI)
The CLI accepts `--inventory`, `--profiles`, `--output-dir`, optional `--ffmpeg`, `--check`, and `--explain`. Capability listings may cite enablement strings such as `--enable-gpl`, `--enable-libx264`, and `--enable-libx265`. Lab probe builds may identify as `6.1.0-aurora-fake` or `6.1.1-aurora-fake`.

Capability probing runs the selected ffmpeg with `-encoders`, `-filters`, and `-muxers`. Listings follow the stock ffmpeg shape: a header (`Encoders:` / `Filters:` / `Muxers:`), an optional legend block ended by a `------` separator, then one capability per line with a leading flag column and the capability name as the next whitespace-delimited token (optional trailing description ignored). Parse capability **names** from those lines; do not treat legend text or the separator as names.

### 10. Codec matrix
| Mode | Container | Video | Pixel format |
| web-sdr SDR | mp4 | libx264 | yuv420p |
| web-sdr HDR+tone_map | mp4 | libx264 | yuv420p with zscale/tonemap |
| web-hdr | mp4 | libx265 | yuv420p10le hvc1 |
| archive no alpha | mov | prores_ks profile 3 | yuv422p10le |
| archive alpha | mov | prores_ks profile 4 | yuva444p10le |
| audio-preview | m4a | none | AAC stereo |

For audio-preview, the planned container field is `m4a`, but FFmpeg registers that muxer under the name `ipod`. Capability gating must require the `ipod` muxer (and `aac` encoder), not a muxer literally named `m4a`.

### 12. Video filter phases
| Phase | Filters |
| 10 | transpose |
| 20 | trim |
| 30 | setpts |
| 40 | crop, scale |
| 50 | zscale, tonemap, zscale (preserve duplicates) |
| 60 | fps |
| 70 | subtitles (burn-in) |
| 80 | setsar |
| 90 | format |

Phase 40 `scale` emits only when both `target_width` and `target_height` are positive after inheritance. An explicit resolved `0` suppresses scale (it does not mean “scale to zero”). Phase 80 `setsar` emits only when `sar` is a non-empty string after inheritance.

When phase 50’s emission preconditions hold (erratum 5), the three nodes use these exact argument strings, in order:
1. `zscale` — `transfer=linear:npl=100`
2. `tonemap` — `tonemap=hable:desat=0`
3. `zscale` — `transfer=bt709:matrix=bt709:primaries=bt709`

Do not rely on ffmpeg filter defaults for these arguments (for example, `tonemap` desat defaults to 2 unless overridden).

### 11. Audio policy
When audio normalization is present on the resolved profile, emit a `loudnorm` filter. When normalization is omitted (legacy v1) or removed with null, do not emit `loudnorm`.

### 14. Subtitles
Modes: none, sidecar, burn_in. burn_in requires burn_in_language. Sidecar outputs use .vtt extension with language suffix. Sidecar `languages` lists (for example `en` and `fr`) select which subtitle tracks become `.vtt` sidecars. A profile that requests burn_in without `burn_in_language` is invalid.

### 16. Build-plan schema field semantics
Job records expose `job_id`, `cache_key`, `filters`, `subtitle_artifacts`, `artifact_name`, and nested `output` with `filename` and `video_codec`. Inventory assets use `relative_path`. Filter nodes carry `phase`, `sequence`, `name`, and `args`. Planner outputs are the `build_plan` and `dependency_lock` artifacts (plus the makefile).

### 18. Canonical serialization and cache keys
Build dependency lock before cache keys. Fingerprint is sha256 of canonical lock body excluding fingerprint. Cache keys exclude source_root and record order. Regression runs set `SOURCE_DATE_EPOCH=1704067200` (see container environment) for deterministic timestamps.

## 19. Makefile escaping
Use separate escaping for Make targets, recipe dollar signs, and shell arguments. Variables: ASSET_ROOT, OUTPUT_ROOT, CACHE_ROOT, FFMPEG. System ffmpeg may be invoked at `/usr/bin/ffmpeg` in lightweight execution checks. Makefile recipes must parse under GNU make and preserve argv-sensitive paths (spaces, `#`) through dry-run and execute paths.

## 20. Transactional output
Stage all three artifacts, validate JSON schemas, then commit. Failed runs must not modify prior valid outputs (transactional failure leaves prior artifacts byte-identical). `--check` mode validates without writing outputs.

## 21. Worked current-release examples
Illustrative artifact names appearing in release fixtures include `hero-web`, `hero-sub`, `hdr-square`, `interview-tiny`, `legacy-hero`, and `inherit-child`. The heavy HDR filter fixture uses profile `filter-heavy` producing artifact `hdr-square`.

For that HDR web-sdr job with tone mapping, rotation 90°, crop, positive target dimensions, fps, and burn-in subtitles, a representative filter list (phases ascending, `sequence` restarting per phase) is:

- phase 10: `transpose`
- phase 30: `setpts`
- phase 40: `crop`, then `scale`
- phase 50: the three tone-map nodes with the exact args in section 12
- phase 60: `fps`
- phase 70: `subtitles`
- phase 90: `format`

Omit phase 20 when no trim bounds apply, and omit phase 80 when `sar` is absent or empty.

## 22. Troubleshooting guide
Capture the inventory case id, generator version, and dependency-lock fingerprint when comparing two build plans. Re-run synthesis with `--check` before writing outputs when validating profile edits offline.

## 23. Archived 2.x (SUPERSEDED)
Historical 2.x recommended AV1 for all web deliveries. This is superseded by current Contract 3.x section 10.

## 25. Errata
Erratum 1: Section 23 AV1 guidance is non-normative for current v3 planning.

Erratum 2 (section 8 — executable field): The dependency-lock `executable` field stores the ffmpeg **basename** (e.g. `"ffmpeg"`), not the resolved absolute path. Fingerprints depend on binary bytes and probed capabilities, not install location.

Erratum 3 (section 4 — digest verification): During synthesis, trust inventory `content_digest` values. Do not read asset files to re-verify digests; missing on-disk assets must not cause planning to fail.

Erratum 4 (section 10 — capability scope): Capability probing gates only the encoder and muxer required for the selected delivery profile (see section 10 matrix). Archive delivery requires `prores_ks` and `mov` in the probe; `pcm_s24le` may appear in the build plan without being listed in probed encoders. Audio-preview delivery requires `aac` and `ipod` (see section 10 note on the M4A muxer name).

Erratum 5 (section 12 — filter emission): Beyond the phase table, emit filters only when their preconditions hold: phase 20 trim when either trim bound is set; phase 30 setpts when `setpts` is a non-empty string; phase 40 scale only when both target dimensions are positive; phase 50 HDR tonemap chain only when the source is HDR, `tone_map` is true, and the codec selection enables `tone_map_chain` (web-sdr HDR sources); phase 80 setsar when `sar` is a non-empty string. Phase 50 emits zscale, tonemap, zscale in that order with the exact args listed in section 12. `sequence` increments per phase starting at 1.

Erratum 6 (sections 17–18 — cache key payload): After building the dependency lock, each job cache key is `sha256:` of canonical JSON with exactly: `content_digest`, `resolved_profile`, `filters`, `lock_fingerprint`. No other keys (notably exclude `source_root`). Capability lists in the lock use codepoint-sorted canonical form per `generator.json`.
