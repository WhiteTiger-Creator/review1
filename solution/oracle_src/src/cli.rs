use std::path::PathBuf;

use anyhow::{bail, Result};
use clap::Parser;

#[derive(Debug, Clone)]
pub struct CliArgs {
    pub database: PathBuf,
    pub as_of: String,
    pub output: PathBuf,
}

#[derive(Parser, Debug)]
#[command(name = "webauthn-assertion-worker")]
#[command(about = "Bounded WebAuthn assertion audit worker")]
struct RawCli {
    #[arg(long)]
    database: PathBuf,
    #[arg(long)]
    as_of: String,
    #[arg(long)]
    output: PathBuf,
}

pub fn parse_args<I, S>(args: I) -> Result<CliArgs>
where
    I: IntoIterator<Item = S>,
    S: Into<std::ffi::OsString> + Clone,
{
    let raw = RawCli::try_parse_from(args).map_err(|e| anyhow::anyhow!("{e}"))?;
    if !raw.database.is_absolute() {
        bail!("--database must be an absolute path");
    }
    if !raw.output.is_absolute() {
        bail!("--output must be an absolute path");
    }
    Ok(CliArgs {
        database: raw.database,
        as_of: raw.as_of,
        output: raw.output,
    })
}

pub fn parse_as_of(raw: &str) -> Result<String> {
    let bytes = raw.as_bytes();
    if bytes.len() != 20 {
        bail!("invalid as-of timestamp");
    }
    // YYYY-MM-DDTHH:MM:SSZ
    let re_ok = bytes[4] == b'-'
        && bytes[7] == b'-'
        && bytes[10] == b'T'
        && bytes[13] == b':'
        && bytes[16] == b':'
        && bytes[19] == b'Z';
    if !re_ok {
        bail!("invalid as-of timestamp");
    }
    let year: i32 = std::str::from_utf8(&bytes[0..4])?.parse()?;
    let month: u32 = std::str::from_utf8(&bytes[5..7])?.parse()?;
    let day: u32 = std::str::from_utf8(&bytes[8..10])?.parse()?;
    let hour: u32 = std::str::from_utf8(&bytes[11..13])?.parse()?;
    let minute: u32 = std::str::from_utf8(&bytes[14..16])?.parse()?;
    let second: u32 = std::str::from_utf8(&bytes[17..19])?.parse()?;
    if !(1..=12).contains(&month) || hour > 23 || minute > 59 || second > 59 {
        bail!("invalid as-of timestamp");
    }
    if !valid_calendar_date(year, month, day) {
        bail!("invalid as-of timestamp");
    }
    Ok(raw.to_string())
}

fn valid_calendar_date(year: i32, month: u32, day: u32) -> bool {
    let dim = days_in_month(year, month);
    day >= 1 && day <= dim
}

fn days_in_month(year: i32, month: u32) -> u32 {
    match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 => {
            if is_leap(year) {
                29
            } else {
                28
            }
        }
        _ => 0,
    }
}

fn is_leap(year: i32) -> bool {
    (year % 4 == 0 && year % 100 != 0) || (year % 400 == 0)
}

/// Lexicographic compare is valid for the published UTC profile.
pub fn ts_cmp(a: &str, b: &str) -> std::cmp::Ordering {
    a.cmp(b)
}
