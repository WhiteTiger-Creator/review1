pub mod kern;
pub mod rowv;

pub use kern::{apply_point, idx_th, idx_v, mid_v, solve_reduced};
pub use rowv::{CaseSpec, LoadSpec, SpanObs, integrate_fine};
