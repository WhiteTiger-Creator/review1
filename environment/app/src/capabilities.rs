//! Capability loading and visibility.
//! Propagation across applied runbooks and completed batches is intentionally incomplete.

#![allow(dead_code)]

use std::collections::HashSet;

use crate::model::Deployment;

/// Loads only the deployment's static database capabilities.
pub fn static_capabilities(dep: &Deployment) -> HashSet<String> {
    dep.capabilities.clone()
}
