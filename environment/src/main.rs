use eta_risk_provenance::m18::load_pack;
use eta_risk_provenance::n21::{cli_note, finish_pack};
use eta_risk_provenance::p34::{compact_count, markdown_from_doc};
use eta_risk_provenance::types::{
    AliasBook, Checkpoint, EventRow, FrameSet, LedgerRow, PackView, RulePack, SetBook,
};
use std::env;
use std::error::Error;
use std::fs;
use std::path::{Path, PathBuf};

fn main() -> Result<(), Box<dyn Error>> {
    let out_dir = parse_out_dir()?;
    fs::create_dir_all(&out_dir)?;
    let base = PathBuf::from("/app/environment/local");
    let frames = read_frames(&base.join("events_b.jsonl"))?;
    let pack = read_rules(&base.join("rev_a.json"))?;
    let set_book = read_set(&base.join("holdout_map.json"))?;
    let _aliases = read_aliases(&base.join("alias_map.json"))?;
    let ledger = read_ledger(&base.join("catalog.tsv"))?;
    let checkpoint = read_checkpoint(&base.join("checkpoint.json"))?;
    let rows = load_pack(&frames, &pack, &set_book, &checkpoint);
    let view = PackView {
        run_id: pack.name.clone(),
        pinned: set_book.pinned.clone(),
        held_out: set_book.holdout.clone(),
        review_order: set_book.review.clone(),
        ledger,
    };
    let doc = finish_pack(&rows, &view);
    let json = serde_json::to_string_pretty(&doc)?;
    fs::write(out_dir.join("risk_trace.json"), json)?;
    fs::write(out_dir.join("residual_risk.md"), markdown_from_doc(&doc))?;
    eprintln!("{}; {} review items", cli_note(doc.records.len()), compact_count(&doc));
    Ok(())
}

fn parse_out_dir() -> Result<PathBuf, Box<dyn Error>> {
    let mut args = env::args().skip(1);
    while let Some(arg) = args.next() {
        if arg == "--out" {
            if let Some(value) = args.next() {
                return Ok(PathBuf::from(value));
            }
        }
    }
    Ok(PathBuf::from("/app/output"))
}

fn read_frames(path: &Path) -> Result<FrameSet, Box<dyn Error>> {
    let raw = fs::read_to_string(path)?;
    let mut rows = Vec::new();
    for line in raw.lines().filter(|line| !line.trim().is_empty()) {
        rows.push(serde_json::from_str::<EventRow>(line)?);
    }
    Ok(FrameSet { rows })
}

fn read_rules(path: &Path) -> Result<RulePack, Box<dyn Error>> {
    let raw = fs::read_to_string(path)?;
    Ok(serde_json::from_str(&raw)?)
}

fn read_set(path: &Path) -> Result<SetBook, Box<dyn Error>> {
    let raw = fs::read_to_string(path)?;
    Ok(serde_json::from_str(&raw)?)
}

fn read_aliases(path: &Path) -> Result<AliasBook, Box<dyn Error>> {
    let raw = fs::read_to_string(path)?;
    Ok(serde_json::from_str(&raw)?)
}

fn read_checkpoint(path: &Path) -> Result<Checkpoint, Box<dyn Error>> {
    let raw = fs::read_to_string(path)?;
    Ok(serde_json::from_str(&raw)?)
}

fn read_ledger(path: &Path) -> Result<Vec<LedgerRow>, Box<dyn Error>> {
    let raw = fs::read_to_string(path)?;
    let mut rows = Vec::new();
    for line in raw.lines().skip(1).filter(|line| !line.trim().is_empty()) {
        let parts: Vec<_> = line.split('\t').collect();
        if parts.len() == 3 {
            rows.push(LedgerRow {
                id: parts[0].to_string(),
                label: parts[1].to_string(),
                owner: parts[2].to_string(),
            });
        }
    }
    Ok(rows)
}
