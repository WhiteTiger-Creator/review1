mod drive_a;
mod drive_b;
mod drive_c;
mod drive_d;
mod engine;
mod jrn_u;

use std::env;
use std::path::PathBuf;

fn main() {
    let args: Vec<String> = env::args().collect();
    let mut catalog = PathBuf::from("/app/environment/cfgs/join_policy.toml");
    let mut journal_out = PathBuf::from("/app/output/skew_journal.json");
    let mut suite_full = false;
    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--suite" => {
                i += 1;
                if i < args.len() && args[i] == "full" {
                    suite_full = true;
                }
            }
            "--catalog" => {
                i += 1;
                if i < args.len() {
                    catalog = PathBuf::from(&args[i]);
                }
            }
            "--journal-out" => {
                i += 1;
                if i < args.len() {
                    journal_out = PathBuf::from(&args[i]);
                }
            }
            _ => {}
        }
        i += 1;
    }
    let _ = (suite_full, jrn_u::stamp(1));
    let root = PathBuf::from("/app/environment");
    engine::run_all(&root, &catalog, &journal_out);
}
