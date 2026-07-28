#!/usr/bin/python3
"""Offline SQLite registry bridge for the orbital model release task."""
from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote


def finite(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("catalog contains a non-finite value")
    return value


def row_dict(columns: list[str], row: tuple[Any, ...]) -> dict[str, Any]:
    return {name: finite(value) for name, value in zip(columns, row, strict=True)}


def read_only_connection(path: str) -> sqlite3.Connection:
    uri = "file:" + quote(str(Path(path).resolve()), safe="/") + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def export_catalog(db_path: str) -> int:
    con = read_only_connection(db_path)
    try:
        campaign_columns = [
            "campaign_id", "model_revision", "feature_revision", "expected_sample_count",
            "feature_count", "decision_threshold", "abstain_spread", "bootstrap_replicates",
            "ece_bins", "min_coverage", "min_balanced_accuracy_lower", "max_brier",
            "max_ece", "max_fpr_gap", "max_feature_drift",
        ]
        rows = con.execute("""
            SELECT campaign_id, model_revision, feature_revision, expected_sample_count,
                   feature_count, decision_threshold, abstain_spread, bootstrap_replicates,
                   ece_bins, min_coverage, min_balanced_accuracy_lower, max_brier,
                   max_ece, max_fpr_gap, max_feature_drift
              FROM campaigns WHERE published = TRUE ORDER BY campaign_id
        """).fetchall()
        campaigns: list[dict[str, Any]] = []
        for row in rows:
            campaign = row_dict(campaign_columns, row)
            sample_columns = ["sample_index", "sample_id", "site_id", "device_family", "label", "tile_path", "roi_x", "roi_y", "roi_size", "intensity_gain", "intensity_offset"]
            campaign["samples"] = [row_dict(sample_columns, item) for item in con.execute("""
                SELECT sample_index, sample_id, site_id, device_family, label, tile_path,
                       roi_x, roi_y, roi_size, intensity_gain, intensity_offset
                  FROM samples WHERE campaign_id = ? ORDER BY sample_index
            """, [campaign["campaign_id"]]).fetchall()]
            head_columns = ["head_id", "head_order", "intercept", "temperature", "vote_weight"]
            heads = [row_dict(head_columns, item) for item in con.execute("""
                SELECT head_id, head_order, intercept, temperature, vote_weight
                  FROM model_heads WHERE campaign_id = ? ORDER BY head_order
            """, [campaign["campaign_id"]]).fetchall()]
            for head in heads:
                weight_rows = con.execute("""
                    SELECT feature_index, weight FROM model_weights
                     WHERE campaign_id = ? AND head_id = ? ORDER BY feature_index
                """, [campaign["campaign_id"], head["head_id"]]).fetchall()
                head["weights"] = [finite(item[1]) for item in weight_rows]
                head["weight_indices"] = [item[0] for item in weight_rows]
            campaign["heads"] = heads
            ref_columns = ["feature_index", "feature_name", "mean", "scale"]
            campaign["feature_references"] = [row_dict(ref_columns, item) for item in con.execute("""
                SELECT feature_index, feature_name, reference_mean, reference_scale
                  FROM feature_references WHERE campaign_id = ? ORDER BY feature_index
            """, [campaign["campaign_id"]]).fetchall()]
            campaigns.append(campaign)
        json.dump({"campaigns": campaigns}, sys.stdout, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        sys.stdout.write("\n")
        return 0
    finally:
        con.close()


def seed_database(schema_path: str, manifest_path: str, db_path: str) -> int:
    schema = Path(schema_path).read_text(encoding="utf-8")
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    campaigns = manifest.get("campaigns")
    if not isinstance(campaigns, list) or not campaigns:
        raise ValueError("manifest requires campaigns")
    destination = Path(db_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    os.close(fd)
    temporary = Path(name)
    temporary.unlink(missing_ok=True)
    con = sqlite3.connect(str(temporary), isolation_level=None)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(schema)
        con.execute("BEGIN IMMEDIATE")
        for campaign in campaigns:
            con.execute("""
                INSERT INTO campaigns VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [campaign["campaign_id"], campaign["model_revision"], campaign["feature_revision"], campaign["expected_sample_count"], campaign["feature_count"], campaign["decision_threshold"], campaign["abstain_spread"], campaign["bootstrap_replicates"], campaign["ece_bins"], campaign["min_coverage"], campaign["min_balanced_accuracy_lower"], campaign["max_brier"], campaign["max_ece"], campaign["max_fpr_gap"], campaign["max_feature_drift"], campaign["published"]])
            for sample in campaign["samples"]:
                con.execute("""
                    INSERT INTO samples VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, [campaign["campaign_id"], sample["sample_index"], sample["sample_id"], sample["site_id"], sample["device_family"], sample["label"], sample["tile_path"], sample["roi_x"], sample["roi_y"], sample["roi_size"], sample["intensity_gain"], sample["intensity_offset"]])
            for head in campaign["heads"]:
                con.execute("INSERT INTO model_heads VALUES (?, ?, ?, ?, ?, ?)", [campaign["campaign_id"], head["head_id"], head["head_order"], head["intercept"], head["temperature"], head["vote_weight"]])
                for index, weight in enumerate(head["weights"]):
                    con.execute("INSERT INTO model_weights VALUES (?, ?, ?, ?)", [campaign["campaign_id"], head["head_id"], index, weight])
            for ref in campaign["feature_references"]:
                con.execute("INSERT INTO feature_references VALUES (?, ?, ?, ?, ?)", [campaign["campaign_id"], ref["feature_index"], ref["feature_name"], ref["mean"], ref["scale"]])
        con.execute("COMMIT")
        con.close()
        os.replace(temporary, destination)
        return 0
    except Exception:
        try:
            con.execute("ROLLBACK")
        except Exception:
            pass
        con.close()
        temporary.unlink(missing_ok=True)
        raise


def main() -> int:
    try:
        if Path(sys.argv[0]).name == "orbit-seed":
            parser = argparse.ArgumentParser(prog="orbit-seed")
            parser.add_argument("--schema", required=True)
            parser.add_argument("--manifest", required=True)
            parser.add_argument("--db", required=True)
            args = parser.parse_args()
            return seed_database(args.schema, args.manifest, args.db)
        parser = argparse.ArgumentParser(prog="orbit-registry")
        subcommands = parser.add_subparsers(dest="command", required=True)
        export_parser = subcommands.add_parser("export")
        export_parser.add_argument("--db", required=True)
        args = parser.parse_args()
        return export_catalog(args.db)
    except SystemExit:
        raise
    except Exception as error:
        print(error, file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
