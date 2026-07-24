use crate::harness::{read_json, run_cli, snapshot_catalog, with_store, TestCase};
use crate::reachability::{expected_reachability, inventory_blob_reachable};
use crate::store_builder::temp_file;
use anyhow::{bail, Context, Result};

fn check_clean_inspect() -> Result<()> {
    with_store(1, |root| {
        let out = run_cli(&["inspect", "--root", root.to_str().unwrap()])?;
        if !out.status.success() {
            bail!("inspect failed: {}", String::from_utf8_lossy(&out.stderr));
        }
        let stdout = String::from_utf8_lossy(&out.stdout);
        if !stdout.contains("demo") {
            bail!("expected demo image in inspect output");
        }
        Ok(())
    })
}

fn check_run_image() -> Result<()> {
    with_store(1, |root| {
        let result = temp_file("run-image")?;
        let out = run_cli(&[
            "run-image",
            "--root",
            root.to_str().unwrap(),
            "--image",
            "demo",
            "--result",
            result.to_str().unwrap(),
        ])?;
        if !out.status.success() {
            bail!("run-image failed: {}", String::from_utf8_lossy(&out.stderr));
        }
        let json = read_json(&result)?;
        if json["status"] != "ok" {
            bail!("run status not ok");
        }
        if json["rootfs_probe"]["stdout"] != "probe-ok:demo" {
            bail!("unexpected probe output");
        }
        let inv = temp_file("run-image-inv")?;
        run_cli(&[
            "recover",
            "--root",
            root.to_str().unwrap(),
            "--output",
            inv.to_str().unwrap(),
        ])?;
        let report = read_json(&inv)?;
        let snap_base = report["snapshots"]
            .as_array()
            .unwrap()
            .iter()
            .find(|s| s["id"] == "snap-base")
            .context("snap-base inventory row")?;
        if snap_base["reachable"] != true {
            bail!("parent snapshot snap-base must be reachable in inventory");
        }
        Ok(())
    })
}

fn check_recover_after_mark() -> Result<()> {
    with_store(2, |root| {
        let inv = temp_file("recover-mark")?;
        let out = run_cli(&[
            "recover",
            "--root",
            root.to_str().unwrap(),
            "--output",
            inv.to_str().unwrap(),
        ])?;
        if !out.status.success() {
            bail!("recover failed");
        }
        let report = read_json(&inv)?;
        if report["status"] != "ok" {
            bail!("expected ok status");
        }
        let gc = run_cli(&["gc", "--root", root.to_str().unwrap()])?;
        if !gc.status.success() {
            bail!("gc failed");
        }
        if report["schema_version"] != 1 {
            bail!("schema mismatch");
        }
        Ok(())
    })
}

fn check_gc_reclaim() -> Result<()> {
    with_store(3, |root| {
        let inv = temp_file("gc-reclaim")?;
        run_cli(&[
            "recover",
            "--root",
            root.to_str().unwrap(),
            "--output",
            inv.to_str().unwrap(),
        ])?;
        let before_blobs = std::fs::read_dir(root.join("blobs/sha256"))?.count();
        run_cli(&["gc", "--root", root.to_str().unwrap()])?;
        let after_blobs = std::fs::read_dir(root.join("blobs/sha256"))?.count();
        if after_blobs >= before_blobs {
            bail!("gc did not reclaim orphan blob");
        }
        Ok(())
    })
}

fn check_lease_journal_ahead() -> Result<()> {
    with_store(4, |root| {
        let inv = temp_file("lease-ahead")?;
        run_cli(&[
            "recover",
            "--root",
            root.to_str().unwrap(),
            "--output",
            inv.to_str().unwrap(),
        ])?;
        let report = read_json(&inv)?;
        let leases = report["leases"].as_array().context("leases")?;
        let active = leases.iter().filter(|l| l["active"] == true).count();
        if active == 0 {
            bail!("expected active lease from journal ahead of watermark");
        }
        Ok(())
    })
}

fn check_missing_snapshot_reconstruction() -> Result<()> {
    with_store(6, |root| {
        let inv = temp_file("missing-snap")?;
        run_cli(&[
            "recover",
            "--root",
            root.to_str().unwrap(),
            "--output",
            inv.to_str().unwrap(),
        ])?;
        let report = read_json(&inv)?;
        let snaps: Vec<_> = report["snapshots"]
            .as_array()
            .unwrap()
            .iter()
            .map(|s| s["id"].as_str().unwrap())
            .collect();
        if !snaps.contains(&"snap-base") {
            bail!("missing reconstructed snap-base");
        }
        let result = temp_file("missing-snap-run")?;
        let out = run_cli(&[
            "run-image",
            "--root",
            root.to_str().unwrap(),
            "--image",
            "demo",
            "--result",
            result.to_str().unwrap(),
        ])?;
        if !out.status.success() {
            bail!("demo image must remain runnable after snapshot reconstruction");
        }
        Ok(())
    })
}

fn check_isolated_marker_rejected() -> Result<()> {
    with_store(7, |root| {
        let out = run_cli(&["verify-store", "--root", root.to_str().unwrap()])?;
        if out.status.success() {
            bail!("isolated marker must be rejected");
        }
        Ok(())
    })
}

fn check_tamper_no_mutation() -> Result<()> {
    with_store(8, |root| {
        let before = snapshot_catalog(root)?;
        let inv = temp_file("tamper")?;
        let out = run_cli(&[
            "recover",
            "--root",
            root.to_str().unwrap(),
            "--output",
            inv.to_str().unwrap(),
        ])?;
        if !out.status.success() {
            bail!("recover should write rejected inventory without error");
        }
        let after = snapshot_catalog(root)?;
        if before != after {
            bail!("catalog mutated on tamper");
        }
        let report = read_json(&inv)?;
        if report["status"] != "rejected" {
            bail!("expected rejected inventory");
        }
        Ok(())
    })
}

fn check_recover_gc_idempotent() -> Result<()> {
    with_store(1, |root| {
        let inv1 = temp_file("idem-1")?;
        let inv2 = temp_file("idem-2")?;
        for path in [&inv1, &inv2] {
            run_cli(&[
                "recover",
                "--root",
                root.to_str().unwrap(),
                "--output",
                path.to_str().unwrap(),
            ])?;
            run_cli(&["gc", "--root", root.to_str().unwrap()])?;
        }
        let a = read_json(&inv1)?;
        let b = read_json(&inv2)?;
        if a["blobs"] != b["blobs"] {
            bail!("inventory not idempotent");
        }
        Ok(())
    })
}

fn check_recover_interrupt_resume() -> Result<()> {
    with_store(9, |root| {
        let partial = temp_file("partial")?;
        let final_inv = temp_file("final")?;
        run_cli(&[
            "recover",
            "--root",
            root.to_str().unwrap(),
            "--output",
            partial.to_str().unwrap(),
            "--interrupt-after",
            "validation",
        ])?;
        let p = read_json(&partial)?;
        if p["status"] != "partial" {
            bail!("expected partial status");
        }
        run_cli(&[
            "recover",
            "--root",
            root.to_str().unwrap(),
            "--output",
            final_inv.to_str().unwrap(),
        ])?;
        let f = read_json(&final_inv)?;
        if f["status"] != "ok" {
            bail!("expected final ok");
        }
        Ok(())
    })
}

fn check_gc_interrupt_resume() -> Result<()> {
    with_store(10, |root| {
        let inv = temp_file("gc-interrupt")?;
        run_cli(&[
            "recover",
            "--root",
            root.to_str().unwrap(),
            "--output",
            inv.to_str().unwrap(),
        ])?;
        run_cli(&[
            "gc",
            "--root",
            root.to_str().unwrap(),
            "--interrupt-after",
            "intent",
        ])?;
        let mid = std::fs::read_dir(root.join("blobs/sha256"))?.count();
        run_cli(&["gc", "--root", root.to_str().unwrap()])?;
        let end = std::fs::read_dir(root.join("blobs/sha256"))?.count();
        if end >= mid {
            bail!("gc resume did not reclaim");
        }
        Ok(())
    })
}

fn check_verify_store_clean() -> Result<()> {
    with_store(1, |root| {
        let out = run_cli(&["verify-store", "--root", root.to_str().unwrap()])?;
        if !out.status.success() {
            bail!("verify-store failed on clean store");
        }
        Ok(())
    })
}

fn check_reachability_parent_closure() -> Result<()> {
    with_store(1, |root| {
        let inv = temp_file("reach")?;
        run_cli(&[
            "recover",
            "--root",
            root.to_str().unwrap(),
            "--output",
            inv.to_str().unwrap(),
        ])?;
        let report = read_json(&inv)?;
        let (expected_blobs, expected_snaps) = expected_reachability(root)?;
        for digest in &expected_blobs {
            if !inventory_blob_reachable(&report, digest) {
                bail!("blob {digest} should be reachable");
            }
        }
        for id in &expected_snaps {
            let found = report["snapshots"]
                .as_array()
                .unwrap()
                .iter()
                .any(|s| s["id"] == *id && s["reachable"] == true);
            if !found {
                bail!("snapshot {id} should be reachable");
            }
        }
        Ok(())
    })
}

fn check_lease_generation_not_cancelled() -> Result<()> {
    with_store(11, |root| {
        let inv = temp_file("lease-gen")?;
        run_cli(&[
            "recover",
            "--root",
            root.to_str().unwrap(),
            "--output",
            inv.to_str().unwrap(),
        ])?;
        let report = read_json(&inv)?;
        let lease = report["leases"]
            .as_array()
            .unwrap()
            .iter()
            .find(|l| l["lease_id"] == "lease-gen")
            .context("lease-gen")?;
        if lease["generation"] != 6 || lease["active"] != true {
            bail!("newer acquire must survive old release");
        }
        Ok(())
    })
}

fn check_import_bundle() -> Result<()> {
    with_store(5, |root| {
        let layer = crate::store_builder::put_blob_public(root, b"layer")?;
        let config = crate::store_builder::put_blob_public(root, b"cfg")?;
        let snap = crate::store_builder::put_blob_public(root, b"snap")?;
        crate::store_builder::write_snapshot_public(root, "snap-demo-root", None, &snap, "full")?;
        let bundle = temp_file("bundle")?;
        let manifest = serde_json::json!({
            "schema_version": 2,
            "name": "demo",
            "config_digest": config,
            "layers": [{"digest": layer, "size": 4, "media_type": "application/vnd.oci.image.layer.v1.tar+gzip"}],
            "root_snapshot_id": "snap-demo-root",
        });
        std::fs::write(&bundle, serde_json::to_string_pretty(&manifest)?)?;
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let _ = std::fs::set_permissions(&bundle, std::fs::Permissions::from_mode(0o666));
        }
        let out = run_cli(&[
            "import",
            "--root",
            root.to_str().unwrap(),
            "--bundle",
            bundle.to_str().unwrap(),
        ])?;
        if !out.status.success() {
            bail!("import failed: {}", String::from_utf8_lossy(&out.stderr));
        }
        Ok(())
    })
}

pub const ALL_CASES: &[TestCase] = &[
    TestCase { name: "clean_inspect", check: check_clean_inspect },
    TestCase { name: "run_image", check: check_run_image },
    TestCase { name: "recover_after_mark", check: check_recover_after_mark },
    TestCase { name: "gc_reclaim", check: check_gc_reclaim },
    TestCase { name: "lease_journal_ahead", check: check_lease_journal_ahead },
    TestCase {
        name: "missing_snapshot_reconstruction",
        check: check_missing_snapshot_reconstruction,
    },
    TestCase {
        name: "isolated_marker_rejected",
        check: check_isolated_marker_rejected,
    },
    TestCase { name: "tamper_no_mutation", check: check_tamper_no_mutation },
    TestCase {
        name: "recover_gc_idempotent",
        check: check_recover_gc_idempotent,
    },
    TestCase {
        name: "recover_interrupt_resume",
        check: check_recover_interrupt_resume,
    },
    TestCase { name: "gc_interrupt_resume", check: check_gc_interrupt_resume },
    TestCase { name: "verify_store_clean", check: check_verify_store_clean },
    TestCase {
        name: "reachability_parent_closure",
        check: check_reachability_parent_closure,
    },
    TestCase {
        name: "lease_generation_not_cancelled",
        check: check_lease_generation_not_cancelled,
    },
    TestCase { name: "import_bundle", check: check_import_bundle },
];
