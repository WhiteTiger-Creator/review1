use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};
use std::process;

mod cargo_exec;
mod cli;
mod probe;
mod environment;
mod error;
mod include_graph;
mod input;
mod verify_sources;
mod lock_sync;
mod coalesce;
mod overrides;
mod paths;
mod report;
mod replace_graph;

use crate::error::{AuditorError, RequestFailure};
use crate::input::{CliOverride, EnvProfile, Request, SolverConfig, SourceProfiles};
use crate::coalesce::{ConfigValue, MergeLayer, Provenance};
use crate::report::*;

fn main() {
    let args = match cli::parse_args(std::env::args().skip(1).collect()) {
        Ok(a) => a,
        Err(e) => {
            eprintln!("fatal: {e}");
            process::exit(1);
        }
    };

    if let Err(e) = run(args) {
        eprintln!("fatal: {e}");
        process::exit(1);
    }
}

pub struct Args {
    pub fixture_root: PathBuf,
    pub requests: PathBuf,
    pub environment_overrides: PathBuf,
    pub cli_overrides: PathBuf,
    pub source_profiles: PathBuf,
    pub solver_config: PathBuf,
    pub output: PathBuf,
}

fn run(args: Args) -> Result<(), AuditorError> {
    // Atomic output prelude: remove stale final and exact temporary sibling.
    let tmp_sibling = PathBuf::from(format!("{}.tmp", args.output.display()));
    if args.output.exists() {
        fs::remove_file(&args.output).map_err(|e| AuditorError::Io(args.output.clone(), e))?;
    }
    if tmp_sibling.exists() {
        fs::remove_file(&tmp_sibling).map_err(|e| AuditorError::Io(tmp_sibling.clone(), e))?;
    }

    let fixture_root = paths::normalize_abs(&args.fixture_root)?;
    if !fixture_root.is_dir() {
        return Err(AuditorError::Fatal(format!(
            "fixture root missing: {}",
            fixture_root.display()
        )));
    }

    let requests = input::load_requests(&args.requests)?;
    let env_doc = input::load_environment_overrides(&args.environment_overrides)?;
    let cli_rows = input::load_cli_overrides(&args.cli_overrides)?;
    let source_profiles = input::load_source_profiles(&args.source_profiles)?;
    let solver = input::load_solver_config(&args.solver_config)?;

    let mut report = Report::default();
    let mut sorted_reqs = requests;
    sorted_reqs.sort_by(|a, b| a.request_id.cmp(&b.request_id));

    for req in &sorted_reqs {
        match process_request(
            &fixture_root,
            req,
            &env_doc,
            &cli_rows,
            &source_profiles,
            &solver,
        ) {
            Ok(partial) => report.merge_partial(partial),
            Err(AuditorError::Request(failure)) => {
                report.rejection_rows.push(RejectionRow {
                    request_id: failure.request_id.clone(),
                    stage: failure.stage,
                    reason: failure.reason,
                    path_or_source_or_null: failure.path_or_source,
                    details: failure.details,
                });
                report.request_rows.push(RequestRow {
                    request_id: failure.request_id.clone(),
                    invocation_directory: req.invocation_directory.clone(),
                    status: "rejected".into(),
                    reason_or_null: Some(report.rejection_rows.last().unwrap().reason.clone()),
                    discovered_config_count: 0,
                    include_count: 0,
                    effective_value_count: 0,
                    terminal_source_count: 0,
                    build_status: "not_run".into(),
                });
            }
            Err(e) => return Err(e),
        }
    }

    report.finalize_summary();
    report.sort_all();
    report::write_atomic(&args.output, &report)?;
    Ok(())
}

struct PartialReport {
    request_row: RequestRow,
    discovered_config_rows: Vec<DiscoveredConfigRow>,
    include_rows: Vec<IncludeRow>,
    effective_value_rows: Vec<EffectiveValueRow>,
    path_resolution_rows: Vec<PathResolutionRow>,
    source_rows: Vec<SourceRow>,
    replacement_edge_rows: Vec<ReplacementEdgeRow>,
    package_source_rows: Vec<PackageSourceRow>,
    lock_reconciliation_rows: Vec<LockReconciliationRow>,
    integrity_rows: Vec<IntegrityRow>,
    build_rows: Vec<BuildRow>,
    rejection_rows: Vec<RejectionRow>,
}

fn process_request(
    fixture_root: &Path,
    req: &Request,
    env_doc: &input::EnvironmentOverrides,
    cli_rows: &[CliOverride],
    source_profiles: &SourceProfiles,
    solver: &SolverConfig,
) -> Result<PartialReport, AuditorError> {
    let inv = fixture_root.join(&req.invocation_directory);
    let inv = paths::normalize_abs(&inv)?;
    if !inv.is_dir() {
        return Err(AuditorError::Request(RequestFailure {
            request_id: req.request_id.clone(),
            stage: "discovery".into(),
            reason: "invocation_directory_missing".into(),
            path_or_source: Some(req.invocation_directory.clone()),
            details: "invocation directory does not exist".into(),
        }));
    }
    if !paths::is_within(fixture_root, &inv) {
        return Err(AuditorError::Request(RequestFailure {
            request_id: req.request_id.clone(),
            stage: "path".into(),
            reason: "path_escape".into(),
            path_or_source: Some(req.invocation_directory.clone()),
            details: "invocation directory escapes fixture root".into(),
        }));
    }

    let discovered = probe::discover_configs(fixture_root, &inv)?;
    let mut include_rows = Vec::new();
    let mut merged = coalesce::MergedConfig::new();

    // Shallow → deep
    let mut ordered = discovered.clone();
    ordered.sort_by_key(|d| std::cmp::Reverse(d.discovery_depth)); // shallow first: higher depth is closer to root? 
    // discovery_depth 0 = invocation (deepest). Higher depth = closer to fixture root (shallower).
    // Load order: shallow first = highest discovery_depth first.
    ordered.sort_by_key(|d| std::cmp::Reverse(d.discovery_depth));

    // Separate 1-based include-event counter (not shared with discovery load_order).
    let mut include_load_order = 0u32;
    for disc in &ordered {
        let file_merge = include_graph::load_file_with_includes(
            fixture_root,
            &disc.absolute_path,
            &req.request_id,
            solver,
            &mut include_rows,
            0,
            &mut BTreeSet::new(),
            &mut include_load_order,
        )?;
        merged.merge_from(file_merge, MergeLayer::ConfigFile);
    }

    // Assign discovery load_order ascending shallow→deep
    let mut discovered_rows = Vec::new();
    for (idx, disc) in ordered.iter().enumerate() {
        discovered_rows.push(DiscoveredConfigRow {
            request_id: req.request_id.clone(),
            config_path: paths::rel_to(fixture_root, &disc.absolute_path),
            discovery_depth: disc.discovery_depth,
            load_order: (idx as u32) + 1,
        });
    }

    // Environment
    let profile = env_doc
        .profiles
        .iter()
        .find(|p| p.profile_id == req.environment_profile_id)
        .ok_or_else(|| {
            AuditorError::Request(RequestFailure {
                request_id: req.request_id.clone(),
                stage: "environment".into(),
                reason: "unknown_environment_profile".into(),
                path_or_source: Some(req.environment_profile_id.clone()),
                details: "environment profile not found".into(),
            })
        })?;
    environment::apply_env(&mut merged, profile, &inv)?;

    // CLI overrides LTR
    let mut cli_for_profile: Vec<&CliOverride> = cli_rows
        .iter()
        .filter(|c| c.profile_id == req.cli_override_profile_id)
        .collect();
    cli_for_profile.sort_by_key(|c| c.sequence);
    overrides::apply_cli(
        &mut merged,
        fixture_root,
        &inv,
        &cli_for_profile,
        &req.request_id,
    )?;

    let effective_rows = merged.effective_value_rows(&req.request_id);
    let path_rows = paths::resolve_path_keys(
        fixture_root,
        &inv,
        &merged,
        &req.request_id,
    )?;

    let (source_rows, edge_rows, terminal_map) =
        replace_graph::analyze(&req.request_id, fixture_root, &merged, &path_rows)?;

    let lock_path = fixture_root.join(&req.existing_lock);
    let packages = lock_sync::parse_registry_packages(&lock_path)?;

    let (pkg_rows, lock_rows, integ_rows, src_reject) = verify_sources::reconcile_and_verify(
        &req.request_id,
        fixture_root,
        &packages,
        &terminal_map,
        &source_rows,
        source_profiles,
    )?;

    if let Some(fail) = src_reject {
        let mut partial = PartialReport {
            request_row: RequestRow {
                request_id: req.request_id.clone(),
                invocation_directory: req.invocation_directory.clone(),
                status: "rejected".into(),
                reason_or_null: Some(fail.reason.clone()),
                discovered_config_count: discovered_rows.len() as u32,
                include_count: include_rows
                    .iter()
                    .filter(|r| r.request_id == req.request_id)
                    .count() as u32,
                effective_value_count: effective_rows.len() as u32,
                terminal_source_count: source_rows
                    .iter()
                    .filter(|s| s.replace_with_or_null.is_none())
                    .count() as u32,
                build_status: "not_run".into(),
            },
            discovered_config_rows: discovered_rows,
            include_rows,
            effective_value_rows: effective_rows,
            path_resolution_rows: path_rows,
            source_rows,
            replacement_edge_rows: edge_rows,
            package_source_rows: pkg_rows,
            lock_reconciliation_rows: lock_rows,
            integrity_rows: integ_rows,
            build_rows: vec![],
            rejection_rows: vec![RejectionRow {
                request_id: fail.request_id,
                stage: fail.stage,
                reason: fail.reason,
                path_or_source_or_null: fail.path_or_source,
                details: fail.details,
            }],
        };
        return Ok(partial);
    }

    let mut build_rows = Vec::new();
    let mut build_status = "skipped".to_string();
    if req.run_build {
        match cargo_exec::run_locked_offline(
            &req.request_id,
            fixture_root,
            &req.workspace_manifest,
            &req.existing_lock,
            &terminal_map,
            &merged,
        ) {
            Ok(row) => {
                build_status = row.status.clone();
                build_rows.push(row);
            }
            Err(AuditorError::Request(failure)) => {
                build_status = "failed".into();
                return Ok(PartialReport {
                    request_row: RequestRow {
                        request_id: req.request_id.clone(),
                        invocation_directory: req.invocation_directory.clone(),
                        status: "rejected".into(),
                        reason_or_null: Some(failure.reason.clone()),
                        discovered_config_count: discovered_rows.len() as u32,
                        include_count: include_rows.len() as u32,
                        effective_value_count: effective_rows.len() as u32,
                        terminal_source_count: source_rows
                            .iter()
                            .filter(|s| s.replace_with_or_null.is_none())
                            .count() as u32,
                        build_status: build_status.clone(),
                    },
                    discovered_config_rows: discovered_rows,
                    include_rows,
                    effective_value_rows: effective_rows,
                    path_resolution_rows: path_rows,
                    source_rows,
                    replacement_edge_rows: edge_rows,
                    package_source_rows: pkg_rows,
                    lock_reconciliation_rows: lock_rows,
                    integrity_rows: integ_rows,
                    build_rows,
                    rejection_rows: vec![RejectionRow {
                        request_id: failure.request_id,
                        stage: failure.stage,
                        reason: failure.reason,
                        path_or_source_or_null: failure.path_or_source,
                        details: failure.details,
                    }],
                });
            }
            Err(e) => return Err(e),
        }
    }

    Ok(PartialReport {
        request_row: RequestRow {
            request_id: req.request_id.clone(),
            invocation_directory: req.invocation_directory.clone(),
            status: "accepted".into(),
            reason_or_null: None,
            discovered_config_count: discovered_rows.len() as u32,
            include_count: include_rows.len() as u32,
            effective_value_count: effective_rows.len() as u32,
            terminal_source_count: source_rows
                .iter()
                .filter(|s| s.replace_with_or_null.is_none())
                .count() as u32,
            build_status,
        },
        discovered_config_rows: discovered_rows,
        include_rows,
        effective_value_rows: effective_rows,
        path_resolution_rows: path_rows,
        source_rows,
        replacement_edge_rows: edge_rows,
        package_source_rows: pkg_rows,
        lock_reconciliation_rows: lock_rows,
        integrity_rows: integ_rows,
        build_rows,
        rejection_rows: vec![],
    })
}

impl Report {
    fn merge_partial(&mut self, p: PartialReport) {
        self.request_rows.push(p.request_row);
        self.discovered_config_rows
            .extend(p.discovered_config_rows);
        self.include_rows.extend(p.include_rows);
        self.effective_value_rows.extend(p.effective_value_rows);
        self.path_resolution_rows.extend(p.path_resolution_rows);
        self.source_rows.extend(p.source_rows);
        self.replacement_edge_rows.extend(p.replacement_edge_rows);
        self.package_source_rows.extend(p.package_source_rows);
        self.lock_reconciliation_rows
            .extend(p.lock_reconciliation_rows);
        self.integrity_rows.extend(p.integrity_rows);
        self.build_rows.extend(p.build_rows);
        self.rejection_rows.extend(p.rejection_rows);
    }
}
