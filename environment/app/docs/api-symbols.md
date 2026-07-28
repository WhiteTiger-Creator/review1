# API symbols

The package wtac must expose these callables (importable after PYTHONPATH=/app):

| Symbol | Module | Role |
|--------|--------|------|
| wtac_load_campaign | wtac.io.load_campaign | Load campaign directory |
| wtac_dynamic_pressure | wtac.core.qinf | Freestream dynamic pressure |
| wtac_pressure_coefficients | wtac.core.tapcp | Tap Cp map |
| wtac_pair_stations | wtac.core.tapcp | Paired upper/lower rows |
| wtac_integrate_forces | wtac.core.panel | Cn, Ca, Cl, Cd |
| wtac_pitching_moment | wtac.core.mref | Cm about xref |
| wtac_tare_stats | wtac.core.zeros | Tare means/sigmas |
| wtac_balance_coeffs | wtac.core.loadcell | Balance Cl/Cd/Cm |
| wtac_uncertainty_budget | wtac.core.errband | RSS budget dict |
| wtac_build_feature_batch | wtac.feature.batch_stage | Build staging dict |
| wtac_write_feature_batch | wtac.feature.batch_stage | Persist feature_batch.json |
| wtac_load_feature_batch | wtac.feature.batch_stage | Load staging batch |
| wtac_bump_feature_epoch | wtac.feature.batch_stage | Bump feature_ledger epoch |
| wtac_record_eval_success | wtac.feature.batch_stage | Increment eval_count |
| wtac_emit_artifacts | wtac.emit.emit_artifacts | Write four outputs |
| wtac_report_seal | wtac.emit.emit_artifacts | FNV-1a seal |
| wtac_decoy_prandtl_q | wtac.decoy.decoy_prandtl | Decoy only |
| wtac_decoy_pitot_blend | wtac.decoy.decoy_pitot_blend | Decoy only |

CLI entry: wtac.cli:main installed as /usr/local/bin/wtac-validate with subcommands `feature` and `eval`.
