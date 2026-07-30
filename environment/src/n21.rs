use crate::c31::render_c;
use crate::types::{OutputDoc, PackView, RunMark};

pub fn finish_pack(x0: &[RunMark], x1: &PackView) -> OutputDoc {
    render_c(x0, x1)
}

pub fn cli_note(count: usize) -> String {
    format!("processed {count} local rows")
}
