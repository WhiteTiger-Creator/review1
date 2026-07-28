from __future__ import annotations

import argparse
from pathlib import Path

from wtac.core.errband import wtac_uncertainty_budget
from wtac.core.loadcell import wtac_balance_coeffs
from wtac.core.mref import wtac_pitching_moment
from wtac.core.panel import wtac_integrate_forces
from wtac.core.qinf import wtac_dynamic_pressure
from wtac.core.tapcp import wtac_pair_stations, wtac_pressure_coefficients
from wtac.core.zeros import wtac_tare_stats
from wtac.emit.emit_artifacts import wtac_emit_artifacts
from wtac.feature.batch_stage import (
    wtac_build_feature_batch,
    wtac_bump_feature_epoch,
    wtac_load_feature_batch,
    wtac_write_feature_batch,
)
from wtac.io.load_campaign import wtac_load_campaign


def _cmd_feature(campaign_dir: Path, work_dir: Path) -> int:
    camp = wtac_load_campaign(campaign_dir)
    cond = camp["conditions"]
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    epoch = wtac_bump_feature_epoch(work, str(cond["campaign_id"]))
    q_inf = wtac_dynamic_pressure(cond)
    cps = wtac_pressure_coefficients(camp["pressures"], cond["p_inf_pa"], q_inf)
    pairs = wtac_pair_stations(camp["geometry"]["taps"], cps)
    batch = wtac_build_feature_batch(cond, q_inf, pairs, epoch)
    wtac_write_feature_batch(work, batch)
    return 0


def _cmd_eval(campaign_dir: Path, work_dir: Path) -> int:
    camp = wtac_load_campaign(campaign_dir)
    cond = camp["conditions"]
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    # Require staging file presence, but incomplete revision recomputes from raw campaign.
    _ = wtac_load_feature_batch(work)
    q_inf = wtac_dynamic_pressure(cond)
    cps = wtac_pressure_coefficients(camp["pressures"], cond["p_inf_pa"], q_inf)
    pairs = wtac_pair_stations(camp["geometry"]["taps"], cps)
    forces = wtac_integrate_forces(pairs, float(cond["alpha_deg"]))
    cm = wtac_pitching_moment(pairs, float(cond["xref_c"]))
    tare = wtac_tare_stats(camp["tare_runs"]["runs"])
    bal = wtac_balance_coeffs(
        camp["balance"], tare, q_inf, float(cond["chord_m"]), float(cond["span_m"])
    )
    unc = wtac_uncertainty_budget(cond, q_inf, pairs, forces, bal)
    wtac_emit_artifacts(work, cond, q_inf, forces, cm, bal, tare, unc)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wtac-validate")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("feature", "eval"):
        p = sub.add_parser(name)
        p.add_argument("--campaign-dir", required=True)
        p.add_argument("--work-dir", required=True)
    args = parser.parse_args(argv)
    camp = Path(args.campaign_dir)
    work = Path(args.work_dir)
    if args.cmd == "feature":
        return _cmd_feature(camp, work)
    if args.cmd == "eval":
        return _cmd_eval(camp, work)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
