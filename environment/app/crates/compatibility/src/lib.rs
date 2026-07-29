pub mod legacy;
pub mod projection;

pub use legacy::{
    legacy_allows_predicate, legacy_namespace_allowed, load_legacy_receipt, verify_legacy_receipt,
    LegacyReceipt,
};
pub use projection::{project_legacy_evidence, LegacyProjection};
