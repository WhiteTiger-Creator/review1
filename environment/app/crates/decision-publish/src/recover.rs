use std::fs;
use std::path::Path;

pub fn recover_current_generation(output_dir: &Path) -> anyhow::Result<Option<std::path::PathBuf>> {
    let pointer = output_dir.join(".admission-generations/current");
    if !pointer.exists() {
        return Ok(None);
    }
    let target = fs::read_to_string(&pointer)?.trim().to_string();
    let generation = output_dir.join(".admission-generations").join(target);
    if generation.exists() {
        Ok(Some(generation))
    } else {
        Ok(None)
    }
}
