use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result};

pub fn temp_sibling(output: &Path) -> PathBuf {
    let mut tmp = output.as_os_str().to_os_string();
    tmp.push(".tmp");
    PathBuf::from(tmp)
}

pub fn cleanup_outputs(output: &Path) -> Result<()> {
    let tmp = temp_sibling(output);
    if output.exists() {
        fs::remove_file(output).with_context(|| format!("remove stale {}", output.display()))?;
    }
    if tmp.exists() {
        fs::remove_file(&tmp).with_context(|| format!("remove temp {}", tmp.display()))?;
    }
    Ok(())
}

pub fn write_report_atomic(output: &Path, bytes: &[u8]) -> Result<()> {
    let tmp = temp_sibling(output);
    {
        let mut f = fs::File::create(&tmp).with_context(|| format!("create {}", tmp.display()))?;
        f.write_all(bytes)?;
        f.sync_all()?;
    }
    fs::rename(&tmp, output).with_context(|| format!("rename to {}", output.display()))?;
    Ok(())
}
