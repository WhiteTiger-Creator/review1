use crate::a17::fold_a;
use crate::b29::gate_b;
use crate::types::{Checkpoint, FrameSet, RunMark, RulePack, SetBook};

pub fn load_pack(x0: &FrameSet, x1: &RulePack, x2: &SetBook, x3: &Checkpoint) -> Vec<RunMark> {
    let mid = fold_a(x0, x1, x3);
    gate_b(&mid, x2)
}

pub fn trim_label(input: &str) -> String {
    input.split_whitespace().collect::<Vec<_>>().join(" ")
}
