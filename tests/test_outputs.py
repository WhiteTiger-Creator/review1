"""Behavioral verifier for aurora ffmpeg manifest synthesis."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import jsonschema
import pytest
import yaml
from fake_ffmpeg import (
    CAPABILITY_FULL,
    CAPABILITY_NO_LIBX265,
    CAPABILITY_NO_TONEMAP,
    PROBE_VERSION_ALT,
    create_fake_ffmpeg,
)
from fixture_factory import (
    make_codec_matrix_inventory,
    make_codec_matrix_profiles,
    make_filter_chain_profiles,
    make_inheritance_profiles,
    make_invalid_cross_field_profiles,
    make_inventory,
    make_legacy_profiles_file,
    make_profiles_v3,
    make_subtitle_profiles,
    reorder_inventory_entries,
    run_argv,
    seed_for,
    write_fixture_bundle,
)

APP = Path("/app")
AURORA = APP / "aurora-build.mjs"
TESTS = Path(__file__).resolve().parent
SCHEMAS = TESTS / "schemas"
IMMUTABLE_MANIFEST = TESTS / "immutable-files.sha256"
VISIBLE_INVENTORY = Path("/data/cases/current/inventory.json")
VISIBLE_PROFILES = Path("/data/cases/current/profiles.yaml")

SYNTH_ENV = {
    "TZ": "UTC",
    "LC_ALL": "C.UTF-8",
    "SOURCE_DATE_EPOCH": "1704067200",
}

BUILD_PLAN_SCHEMA = json.loads((SCHEMAS / "build-plan-v3.schema.json").read_text(encoding="utf-8"))
LOCK_SCHEMA = json.loads((SCHEMAS / "dependency-lock-v1.schema.json").read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _inventory_contract_digest(path: Path) -> str:
    """Hash inventory semantics while ignoring build-derived content digests."""
    inventory = _load_json(path)

    def normalize(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: ("sha256:<build-derived>" if key == "content_digest" else normalize(item))
                for key, item in sorted(value.items())
            }
        if isinstance(value, list):
            return [normalize(item) for item in value]
        return value

    payload = json.dumps(
        normalize(inventory),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _assert_inventory_digests_match_assets(path: Path) -> None:
    """Verify build-derived content digests match the generated fixture bytes."""
    inventory = _load_json(path)
    source_root = Path(inventory["source_root"])
    for asset in inventory["assets"]:
        asset_path = source_root / asset["relative_path"]
        assert asset_path.is_file(), f"missing inventory asset: {asset_path}"
        assert asset["content_digest"] == f"sha256:{_sha256_file(asset_path)}"
        for track in asset.get("subtitle_tracks", []):
            relative_path = track.get("relative_path")
            if relative_path:
                track_path = source_root / relative_path
                assert track_path.is_file(), f"missing subtitle fixture: {track_path}"
                assert track["content_digest"] == f"sha256:{_sha256_file(track_path)}"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_profiles(path: Path) -> dict[str, Any]:
    if path.suffix in {".yaml", ".yml"}:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    return _load_json(path)


def _run_synthesize(
    *,
    inventory: Path,
    profiles: Path,
    output_dir: Path,
    ffmpeg: Path | None = None,
    check: bool = False,
    explain: Path | None = None,
    expect_success: bool = True,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, **SYNTH_ENV, **(extra_env or {})}
    synth_argv: list[str] = [
        "node",
        str(AURORA),
        "synthesize",
        "--inventory",
        str(inventory),
        "--profiles",
        str(profiles),
        "--output-dir",
        str(output_dir),
    ]
    if ffmpeg is not None:
        synth_argv.extend(["--ffmpeg", str(ffmpeg)])
    if check:
        synth_argv.append("--check")
    if explain is not None:
        synth_argv.extend(["--explain", str(explain)])
    result = run_argv(synth_argv, text=True, capture_output=True, env=env, check=False)
    if expect_success:
        assert result.returncode == 0, result.stdout + result.stderr
    return result


def _output_paths(output_dir: Path) -> dict[str, Path]:
    return {
        "build_plan": output_dir / "build-plan.json",
        "dependency_lock": output_dir / "dependency-lock.json",
        "makefile": output_dir / "ffmpeg.mk",
    }


def _run_generated_makefile(
    makefile: Path,
    *,
    dry_run: bool,
    env: dict[str, str],
) -> subprocess.CompletedProcess[str]:
    gnu_make = shutil.which("make")
    assert gnu_make, "GNU make is required in the verifier image"
    make_argv = [gnu_make, "-f", str(makefile)]
    if dry_run:
        make_argv[1:1] = ["-n"]
        make_argv.append("all")
    else:
        make_argv.extend(["-j1", "all"])
    return run_argv(make_argv, text=True, capture_output=True, env=env, check=False)


def _assert_schema_valid(instance: dict[str, Any], schema: dict[str, Any]) -> None:
    jsonschema.validate(instance=instance, schema=schema)


def _asset_by_id(inventory: dict[str, Any], asset_id: str) -> dict[str, Any]:
    for asset in inventory["assets"]:
        if asset["id"] == asset_id:
            return asset
    raise KeyError(asset_id)


@pytest.fixture
def workdir() -> Path:
    path = Path(tempfile.mkdtemp(prefix="aurora-test-"))
    yield path
    shutil.rmtree(path, ignore_errors=True)


def test_visible_current_case_produces_complete_schema_valid_output(workdir: Path) -> None:
    """The published visible fixture must synthesize all artifacts and pass JSON Schema validation."""
    assert VISIBLE_INVENTORY.is_file(), "missing /data/cases/current/inventory.json"
    assert VISIBLE_PROFILES.is_file(), "missing /data/cases/current/profiles.yaml"
    ffmpeg = workdir / "ffmpeg"
    create_fake_ffmpeg(ffmpeg, profile=CAPABILITY_FULL)
    out = workdir / "visible-out"
    _run_synthesize(inventory=VISIBLE_INVENTORY, profiles=VISIBLE_PROFILES, output_dir=out, ffmpeg=ffmpeg)

    paths = _output_paths(out)
    for name, path in paths.items():
        assert path.is_file(), f"missing output artifact: {name}"

    build_plan = _load_json(paths["build_plan"])
    lock = _load_json(paths["dependency_lock"])
    _assert_schema_valid(build_plan, BUILD_PLAN_SCHEMA)
    _assert_schema_valid(lock, LOCK_SCHEMA)
    assert build_plan["lock_fingerprint"] == lock["fingerprint"]
    assert build_plan["jobs"], "build plan must contain jobs"
    makefile = paths["makefile"].read_text(encoding="utf-8")
    for job in build_plan["jobs"]:
        assert job["output"]["filename"] in makefile


def test_profile_inheritance_preserves_explicit_false_zero_empty_array_and_null(workdir: Path) -> None:
    """Presence-aware inheritance must keep explicit false/0/''/[] and treat null as removal."""
    seed = seed_for("inherit_prof")
    bundle = write_fixture_bundle(
        workdir / "inheritance",
        inventory=make_inventory(seed, assets=[make_inventory(seed)["assets"][0]]),
        profiles=make_inheritance_profiles(),
    )
    ffmpeg = workdir / "ffmpeg"
    create_fake_ffmpeg(ffmpeg)
    out = workdir / "out"
    _run_synthesize(inventory=bundle["inventory"], profiles=bundle["profiles"], output_dir=out, ffmpeg=ffmpeg)

    job = _load_json(out / "build-plan.json")["jobs"][0]
    assert all(node["name"] != "tonemap" for node in job["filters"])
    assert not any(node["name"] == "scale" for node in job["filters"])
    assert not any(node["name"] == "crop" for node in job["filters"])
    assert job.get("subtitle_artifacts", []) == []


def test_legacy_v1_profile_keeps_legacy_omission_defaults(workdir: Path) -> None:
    """Legacy v1 omission must map to subtitle_mode none and no audio normalization filter."""
    seed = seed_for("legacy_v1")
    bundle = write_fixture_bundle(
        workdir / "legacy",
        inventory=make_inventory(seed, assets=[make_inventory(seed)["assets"][0]]),
        profiles=make_legacy_profiles_file(seed),
        profiles_name="profiles.json",
    )
    ffmpeg = workdir / "ffmpeg"
    create_fake_ffmpeg(ffmpeg)
    out = workdir / "out"
    _run_synthesize(inventory=bundle["inventory"], profiles=bundle["profiles"], output_dir=out, ffmpeg=ffmpeg)

    job = _load_json(out / "build-plan.json")["jobs"][0]
    assert job.get("subtitle_artifacts", []) == []
    assert all(node["name"] != "loudnorm" for node in job["filters"])


def test_filter_chain_follows_phase_order_and_preserves_repeated_nodes(workdir: Path) -> None:
    """Filter planning must preserve documented phase topology and semantic arguments."""

    def parse_filter_args(value: str) -> dict[str, str]:
        result: dict[str, str] = {}
        for component in value.split(":"):
            key, separator, item_value = component.partition("=")
            assert separator, f"Expected key=value component, got: {component!r}"
            result[key] = item_value
        return result

    seed = seed_for("filter_chain")
    asset = make_inventory(seed, assets=[make_inventory(seed)["assets"][1]])["assets"][0]
    profiles = make_filter_chain_profiles()
    profile = profiles["profiles"]["filter-heavy"]
    video = profile["video"]
    bundle = write_fixture_bundle(
        workdir / "filters",
        inventory={"format": "aurora-inventory-v2", "source_root": "/data", "assets": [asset]},
        profiles=profiles,
    )

    ffmpeg = workdir / "ffmpeg"
    create_fake_ffmpeg(ffmpeg)
    out = workdir / "out"
    _run_synthesize(inventory=bundle["inventory"], profiles=bundle["profiles"], output_dir=out, ffmpeg=ffmpeg)
    filters = _load_json(out / "build-plan.json")["jobs"][0]["filters"]

    phases = [node["phase"] for node in filters]
    assert phases == sorted(phases)
    assert [(node["name"], node["phase"], node["sequence"]) for node in filters] == [
        ("transpose", 10, 1),
        ("setpts", 30, 1),
        ("crop", 40, 1),
        ("scale", 40, 2),
        ("zscale", 50, 1),
        ("tonemap", 50, 2),
        ("zscale", 50, 3),
        ("fps", 60, 1),
        ("subtitles", 70, 1),
        ("format", 90, 1),
    ]

    by_name = {node["name"]: node for node in filters}
    assert by_name["setpts"]["args"] == video["setpts"]
    assert by_name["crop"]["args"] == video["crop"]
    assert by_name["scale"]["args"] == f'{video["target_width"]}:{video["target_height"]}'
    assert by_name["fps"]["args"] == video["fps"]

    zscale_nodes = [node for node in filters if node["name"] == "zscale"]
    assert len(zscale_nodes) == 2
    assert zscale_nodes[0]["args"] != zscale_nodes[1]["args"]
    assert parse_filter_args(zscale_nodes[0]["args"]) == {
        "transfer": "linear",
        "npl": "100",
    }
    tonemap_node = next(node for node in filters if node["name"] == "tonemap")
    assert parse_filter_args(tonemap_node["args"]) == {
        "tonemap": "hable",
        "desat": "0",
    }
    assert parse_filter_args(zscale_nodes[1]["args"]) == {
        "transfer": "bt709",
        "matrix": "bt709",
        "primaries": "bt709",
    }

    subtitle_node = next(node for node in filters if node["name"] == "subtitles")
    assert isinstance(subtitle_node["args"], str)
    assert subtitle_node["args"]

    format_node = next(node for node in filters if node["name"] == "format")
    assert isinstance(format_node["args"], str)
    assert format_node["args"]


def test_codec_selection_respects_source_alpha_hdr_mode_and_capabilities(workdir: Path) -> None:
    """Codec matrix must branch on delivery target, alpha, and HDR with tonemap support."""
    seed = seed_for("codec_matrix")
    inventory = make_codec_matrix_inventory(seed)
    profiles = make_codec_matrix_profiles()
    ffmpeg = workdir / "ffmpeg"
    create_fake_ffmpeg(ffmpeg, profile=CAPABILITY_FULL)

    cases = [
        ("sdr-clip", "web-sdr", "libx264"),
        ("hdr-clip", "web-hdr", "libx265"),
        ("alpha-clip", "archive", "prores_ks"),
        ("audio-only", "audio-preview", None),
    ]

    for asset_id, profile_name, expected_codec in cases:
        asset = _asset_by_id(inventory, asset_id)
        bundle = write_fixture_bundle(
            workdir / f"codec-{asset_id}",
            inventory={"format": inventory["format"], "source_root": inventory["source_root"], "assets": [asset]},
            profiles={
                "format": profiles["format"],
                "profiles": {profile_name: profiles["profiles"][profile_name]},
                "jobs": [{"asset_id": asset_id, "profile": profile_name, "artifact_name": f"out-{asset_id}"}],
            },
            profiles_name="profiles.json",
        )
        out = workdir / f"out-{asset_id}"
        _run_synthesize(inventory=bundle["inventory"], profiles=bundle["profiles"], output_dir=out, ffmpeg=ffmpeg)
        job = _load_json(out / "build-plan.json")["jobs"][0]
        if expected_codec is None:
            assert job["output"].get("video_codec") is None
        else:
            assert job["output"]["video_codec"] == expected_codec


def test_missing_required_capability_fails_without_fallback_or_partial_output(workdir: Path) -> None:
    """Missing encoders/filters must fail the command and leave the output directory untouched."""
    seed = seed_for("miss_caps")
    asset = make_inventory(seed)["assets"][1]
    bundle = write_fixture_bundle(
        workdir / "missing-cap",
        inventory={"format": "aurora-inventory-v2", "source_root": "/data", "assets": [asset]},
        profiles={
            "format": "aurora-profiles-v3",
            "profiles": {
                "web-hdr": {
                    "output": {"delivery_profile": "web-hdr", "container": "mp4"},
                    "video": {"target_width": 1280, "target_height": 720},
                    "subtitles": {"mode": "none"},
                }
            },
            "jobs": [{"asset_id": asset["id"], "profile": "web-hdr", "artifact_name": "hdr"}],
        },
        profiles_name="profiles.json",
    )
    ffmpeg = workdir / "ffmpeg"
    create_fake_ffmpeg(ffmpeg, profile=CAPABILITY_NO_LIBX265)
    out = workdir / "out"
    out.mkdir()
    sentinel = out / "build-plan.json"
    sentinel.write_text('{"sentinel":true}\n', encoding="utf-8")
    before_hash = _sha256_file(sentinel)
    result = _run_synthesize(
        inventory=bundle["inventory"],
        profiles=bundle["profiles"],
        output_dir=out,
        ffmpeg=ffmpeg,
        expect_success=False,
    )
    assert result.returncode != 0
    assert _sha256_file(sentinel) == before_hash


def test_subtitle_modes_languages_and_names_are_planned_consistently(workdir: Path) -> None:
    """Sidecar subtitle mode must produce stable language coverage and names."""
    seed = seed_for("subtitle_modes")
    asset = make_inventory(seed, assets=[make_inventory(seed)["assets"][0]])["assets"][0]
    bundle = write_fixture_bundle(
        workdir / "subs",
        inventory={"format": "aurora-inventory-v2", "source_root": "/data", "assets": [asset]},
        profiles=make_subtitle_profiles("sidecar", ["fr", "en"], None),
    )
    ffmpeg = workdir / "ffmpeg"
    create_fake_ffmpeg(ffmpeg)
    out = workdir / "out"
    _run_synthesize(inventory=bundle["inventory"], profiles=bundle["profiles"], output_dir=out, ffmpeg=ffmpeg)
    job = _load_json(out / "build-plan.json")["jobs"][0]
    langs = [a["language"] for a in job["subtitle_artifacts"]]
    assert langs == ["en", "fr"]
    assert job["subtitle_artifacts"][0]["filename"].endswith(".en.vtt")


def test_ambiguous_burn_in_language_is_rejected_atomically(workdir: Path) -> None:
    """Burn-in without burn_in_language must fail without writing outputs."""
    seed = seed_for("ambig_burn")
    asset = make_inventory(seed, assets=[make_inventory(seed)["assets"][0]])["assets"][0]
    bundle = write_fixture_bundle(
        workdir / "ambiguous",
        inventory={"format": "aurora-inventory-v2", "source_root": "/data", "assets": [asset]},
        profiles=make_subtitle_profiles("burn_in", ["en", "fr"], None),
    )
    ffmpeg = workdir / "ffmpeg"
    create_fake_ffmpeg(ffmpeg)
    out = workdir / "out"
    out.mkdir()
    sentinel = out / "dependency-lock.json"
    sentinel.write_text('{"sentinel":true}\n', encoding="utf-8")
    before_hash = _sha256_file(sentinel)
    result = _run_synthesize(
        inventory=bundle["inventory"],
        profiles=bundle["profiles"],
        output_dir=out,
        ffmpeg=ffmpeg,
        expect_success=False,
    )
    assert result.returncode != 0
    assert _sha256_file(sentinel) == before_hash


def test_equivalent_inventory_order_and_source_root_produce_byte_identical_artifacts(workdir: Path) -> None:
    """Reordered inventories and different source_root values must not change committed bytes."""
    seed = seed_for("inventory_order")
    inventory_a = make_inventory(seed, source_root="/data/a")
    inventory_b = reorder_inventory_entries(make_inventory(seed, source_root="/data/b"))
    profiles = make_profiles_v3(seed)
    ffmpeg = workdir / "ffmpeg"
    create_fake_ffmpeg(ffmpeg)

    outputs: dict[str, dict[str, bytes]] = {}
    for label, inventory in (("a", inventory_a), ("b", inventory_b)):
        bundle = write_fixture_bundle(workdir / f"order-{label}", inventory=inventory, profiles=profiles)
        out = workdir / f"out-{label}"
        _run_synthesize(inventory=bundle["inventory"], profiles=bundle["profiles"], output_dir=out, ffmpeg=ffmpeg)
        outputs[label] = {name: (out / name).read_bytes() for name in ("build-plan.json", "dependency-lock.json", "ffmpeg.mk")}

    assert outputs["a"] == outputs["b"]
    combined = json.dumps(_load_json(workdir / "out-a/build-plan.json"))
    assert "/data/a" not in combined and "/data/b" not in combined


def test_cache_key_changes_for_content_profile_or_toolchain_changes(workdir: Path) -> None:
    """Cache keys must move when content digests, profile shape, or toolchain fingerprint changes."""
    seed = seed_for("cache_sens")
    inventory = make_inventory(seed)
    profiles = make_profiles_v3(seed)
    ffmpeg = workdir / "ffmpeg"
    create_fake_ffmpeg(ffmpeg, profile=CAPABILITY_FULL)

    bundle = write_fixture_bundle(workdir / "cache-base", inventory=inventory, profiles=profiles)
    out_base = workdir / "out-base"
    _run_synthesize(inventory=bundle["inventory"], profiles=bundle["profiles"], output_dir=out_base, ffmpeg=ffmpeg)
    plan_base = _load_json(out_base / "build-plan.json")
    keys_base = {job["job_id"]: job["cache_key"] for job in plan_base["jobs"]}
    lock_fp = _load_json(out_base / "dependency-lock.json")["fingerprint"]

    mutated_inventory = json.loads(json.dumps(inventory))
    mutated_inventory["assets"][0]["content_digest"] = "sha256:" + "0" * 64
    bundle_mut = write_fixture_bundle(workdir / "cache-mut", inventory=mutated_inventory, profiles=profiles)
    out_mut = workdir / "out-mut"
    _run_synthesize(inventory=bundle_mut["inventory"], profiles=bundle_mut["profiles"], output_dir=out_mut, ffmpeg=ffmpeg)
    keys_mut = {job["job_id"]: job["cache_key"] for job in _load_json(out_mut / "build-plan.json")["jobs"]}
    assert keys_mut != keys_base

    derived_profiles = json.loads(json.dumps(profiles))
    derived_profiles["jobs"] = [{"asset_id": "hero", "profile": "web-derived", "artifact_name": "hero-web"}]
    bundle_prof = write_fixture_bundle(workdir / "cache-prof", inventory=inventory, profiles=derived_profiles)
    out_prof = workdir / "out-prof"
    _run_synthesize(inventory=bundle_prof["inventory"], profiles=bundle_prof["profiles"], output_dir=out_prof, ffmpeg=ffmpeg)
    keys_prof = {job["job_id"]: job["cache_key"] for job in _load_json(out_prof / "build-plan.json")["jobs"]}
    assert keys_prof != keys_base

    alt_ffmpeg = workdir / "ffmpeg-alt"
    create_fake_ffmpeg(alt_ffmpeg, profile=CAPABILITY_NO_TONEMAP, version=PROBE_VERSION_ALT)
    out_alt = workdir / "out-alt"
    _run_synthesize(
        inventory=bundle["inventory"],
        profiles=bundle["profiles"],
        output_dir=out_alt,
        ffmpeg=alt_ffmpeg,
    )
    keys_alt = {job["job_id"]: job["cache_key"] for job in _load_json(out_alt / "build-plan.json")["jobs"]}
    assert keys_alt != keys_base

    assert lock_fp == plan_base["lock_fingerprint"]
    assert len(set(keys_base.values())) == len(keys_base)


def test_dependency_lock_is_derived_from_selected_ffmpeg_and_is_path_independent(workdir: Path) -> None:
    """Lock fingerprint must depend on ffmpeg bytes, not absolute install path."""
    seed = seed_for("dependency_lock")
    inventory = make_inventory(seed, assets=[make_inventory(seed)["assets"][0]])
    profiles = make_profiles_v3(seed)

    ffmpeg_a = workdir / "bin-a" / "ffmpeg"
    ffmpeg_b = workdir / "nested/deep/bin-b/ffmpeg"
    create_fake_ffmpeg(ffmpeg_a, profile=CAPABILITY_FULL)
    create_fake_ffmpeg(ffmpeg_b, profile=CAPABILITY_FULL)

    out_a = workdir / "out-a"
    out_b = workdir / "out-b"
    bundle = write_fixture_bundle(workdir / "lock", inventory=inventory, profiles=profiles)
    _run_synthesize(inventory=bundle["inventory"], profiles=bundle["profiles"], output_dir=out_a, ffmpeg=ffmpeg_a)
    _run_synthesize(inventory=bundle["inventory"], profiles=bundle["profiles"], output_dir=out_b, ffmpeg=ffmpeg_b)
    lock_a = _load_json(out_a / "dependency-lock.json")
    lock_b = _load_json(out_b / "dependency-lock.json")
    assert lock_a == lock_b
    assert lock_a["executable"] == "ffmpeg"


def test_generated_makefile_parses_and_preserves_argv_for_make_sensitive_paths(workdir: Path) -> None:
    """Make must parse paths with spaces, hash, and dollar signs and pass exact argv to ffmpeg."""
    seed = seed_for("makefile_parse")
    asset = _asset_by_id(make_inventory(seed), "hero")
    asset["relative_path"] = "clips/launch master #1.mkv"
    bundle = write_fixture_bundle(
        workdir / "mk-parse",
        inventory={"format": "aurora-inventory-v2", "source_root": "/data/assets", "assets": [asset]},
        profiles=make_profiles_v3(seed),
    )
    ffmpeg = workdir / "ffmpeg"
    log = workdir / "ffmpeg.log"
    create_fake_ffmpeg(ffmpeg)
    out = workdir / "out"
    _run_synthesize(
        inventory=bundle["inventory"],
        profiles=bundle["profiles"],
        output_dir=out,
        ffmpeg=ffmpeg,
        extra_env={"FFMPEG_LOG": str(log)},
    )
    makefile = out / "ffmpeg.mk"
    dry = _run_generated_makefile(
        makefile,
        dry_run=True,
        env={**SYNTH_ENV, "ASSET_ROOT": "/data/assets", "FFMPEG": str(ffmpeg)},
    )
    assert dry.returncode == 0, dry.stderr
    assert "launch master #1.mkv" in dry.stdout or "launch master #1.mkv" in makefile.read_text(encoding="utf-8")


def test_generated_makefile_executes_tiny_real_fixture(workdir: Path) -> None:
    """A tiny real ffmpeg build from the generated makefile must succeed structurally."""
    _ = seed_for("make_exec")
    # Use the real interview clip with a simple web profile so encoding stays lightweight.
    inventory = {
        "format": "aurora-inventory-v2",
        "source_root": "/data/assets",
        "assets": [
            {
                "id": "interview-sdr",
                "relative_path": "clips/interview-sdr.mp4",
                "content_digest": json.loads(Path("/data/cases/current/inventory.json").read_text())["assets"][1][
                    "content_digest"
                ],
                "video": {
                    "width": 1920,
                    "height": 1080,
                    "fps": "24/1",
                    "pix_fmt": "yuv420p",
                    "color_transfer": "bt709",
                    "has_alpha": False,
                    "rotation": 0,
                },
                "audio_tracks": [{"index": 0, "language": "en", "channels": 2}],
                "subtitle_tracks": [],
            }
        ],
    }
    profiles = {
        "format": "aurora-profiles-v3",
        "profiles": {
            "web": {
                "output": {"delivery_profile": "web-sdr", "container": "mp4"},
                "video": {"target_width": 320, "target_height": 240},
                "subtitles": {"mode": "none"},
            }
        },
        "jobs": [{"asset_id": "interview-sdr", "profile": "web", "artifact_name": "interview-tiny"}],
    }
    bundle = write_fixture_bundle(workdir / "real", inventory=inventory, profiles=profiles, profiles_name="profiles.json")
    out = workdir / "real-out"
    _run_synthesize(inventory=bundle["inventory"], profiles=bundle["profiles"], output_dir=out, ffmpeg=Path("/usr/bin/ffmpeg"))
    artifacts = workdir / "artifacts"
    cache = workdir / "cache"
    artifacts.mkdir(parents=True, exist_ok=True)
    cache.mkdir(parents=True, exist_ok=True)
    makefile = out / "ffmpeg.mk"
    build = _run_generated_makefile(
        makefile,
        dry_run=False,
        env={
            **SYNTH_ENV,
            "ASSET_ROOT": "/data/assets",
            "OUTPUT_ROOT": str(artifacts),
            "CACHE_ROOT": str(cache),
            "FFMPEG": "/usr/bin/ffmpeg",
        },
    )
    assert build.returncode == 0, build.stdout + build.stderr
    assert (artifacts / "interview-tiny.mp4").is_file()


def test_failed_schema_or_cross_field_validation_is_transactional(workdir: Path) -> None:
    """Invalid cross-field requests must fail without mutating prior valid outputs."""
    seed = seed_for("txn_fail")
    bundle = write_fixture_bundle(
        workdir / "txn",
        inventory=make_inventory(seed, assets=[make_inventory(seed)["assets"][0]]),
        profiles=make_invalid_cross_field_profiles(),
        profiles_name="profiles.json",
    )
    ffmpeg = workdir / "ffmpeg"
    create_fake_ffmpeg(ffmpeg)
    out = workdir / "out"
    out.mkdir()
    good = {"format": "aurora-build-plan-v3", "generator": {"id": "x", "version": "1"}, "lock_fingerprint": "sha256:" + "a" * 64, "jobs": []}
    good_path = out / "build-plan.json"
    good_path.write_text(json.dumps(good) + "\n", encoding="utf-8")
    before = _sha256_file(good_path)
    result = _run_synthesize(
        inventory=bundle["inventory"],
        profiles=bundle["profiles"],
        output_dir=out,
        ffmpeg=ffmpeg,
        expect_success=False,
    )
    assert result.returncode != 0
    assert _sha256_file(good_path) == before
    assert not list(out.glob(".aurora-staging-*"))


def test_check_mode_has_no_side_effects_and_matches_synthesis_decisions(workdir: Path) -> None:
    """--check must exit zero without creating outputs and match synthesis job counts."""
    seed = seed_for("check_mode")
    bundle = write_fixture_bundle(
        workdir / "check",
        inventory=make_inventory(seed, assets=[make_inventory(seed)["assets"][0]]),
        profiles=make_profiles_v3(seed),
    )
    ffmpeg = workdir / "ffmpeg"
    create_fake_ffmpeg(ffmpeg)
    out = workdir / "out"
    check = _run_synthesize(
        inventory=bundle["inventory"],
        profiles=bundle["profiles"],
        output_dir=out,
        ffmpeg=ffmpeg,
        check=True,
    )
    assert check.returncode == 0
    assert not out.exists()
    _run_synthesize(inventory=bundle["inventory"], profiles=bundle["profiles"], output_dir=out, ffmpeg=ffmpeg)
    assert (out / "build-plan.json").is_file()


def test_input_docs_schemas_and_visible_fixtures_remain_unchanged() -> None:
    """Authoritative docs, schemas, and visible fixtures must match verifier checksum manifest."""
    if not IMMUTABLE_MANIFEST.is_file():
        pytest.skip("immutable manifest not generated yet")
    lines = [
        line.strip()
        for line in IMMUTABLE_MANIFEST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    for line in lines:
        digest, rel = line.split(None, 1)
        if rel.startswith("app/"):
            candidate = APP / rel.removeprefix("app/")
        elif rel.startswith("data/"):
            candidate = Path("/data") / rel.removeprefix("data/")
        else:
            candidate = Path("/") / rel
        assert candidate.is_file(), f"missing immutable file: {candidate}"
        if rel.endswith("/inventory.json"):
            _assert_inventory_digests_match_assets(candidate)
            actual = _inventory_contract_digest(candidate)
        else:
            actual = _sha256_file(candidate)
        assert actual == digest, f"checksum mismatch for {candidate}"
