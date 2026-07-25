//! Confidence classification (starter incomplete).

use crate::optimize::bounds::BoundState;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum OverallConfidence {
    BoundActive,
    Weak,
    Identifiable,
}

impl OverallConfidence {
    pub fn as_str(self) -> &'static str {
        match self {
            OverallConfidence::BoundActive => "BOUND_ACTIVE",
            OverallConfidence::Weak => "WEAK",
            OverallConfidence::Identifiable => "IDENTIFIABLE",
        }
    }
}

pub fn overall(_bounds: &[BoundState], _numerical_rank: usize, _group_count: usize) -> OverallConfidence {
    OverallConfidence::Weak
}

pub fn group_confidence(_bound: BoundState, _score: f64, _rank_tol: f64) -> String {
    "FREE_WEAK".into()
}
