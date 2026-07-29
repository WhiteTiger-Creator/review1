pub mod canonical_cbor;
pub mod decision;
pub mod edge;
pub mod node;

pub use canonical_cbor::{encode_value, validate_cbor};
pub use decision::{build_decision, build_evidence, DecisionDocument, EvidenceGraph};
pub use edge::{dedupe_edges, merge_paths, sort_edges, EvidenceEdge};
pub use node::{node_id, EvidenceNode};
