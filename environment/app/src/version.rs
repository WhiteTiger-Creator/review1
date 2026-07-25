//! Bounded version parsing and matching.

use crate::error::{FatalError, INVALID_VERSION};
use std::cmp::Ordering;

pub type VersionTuple = (i64, i64, i64);

#[derive(Debug, Clone)]
pub struct InvalidVersionError(pub String);

impl std::fmt::Display for InvalidVersionError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "invalid version: {}", self.0)
    }
}

impl std::error::Error for InvalidVersionError {}

pub fn parse_version(version: &str) -> Result<VersionTuple, InvalidVersionError> {
    let trimmed = version.trim();
    let parts: Vec<&str> = trimmed.split('.').collect();
    if parts.is_empty() || parts.len() > 3 {
        return Err(InvalidVersionError(version.to_string()));
    }
    if parts.iter().any(|part| part.is_empty()) {
        return Err(InvalidVersionError(version.to_string()));
    }
    let mut nums = Vec::with_capacity(3);
    for part in parts {
        let value: i64 = part
            .parse()
            .map_err(|_| InvalidVersionError(version.to_string()))?;
        if value < 0 {
            return Err(InvalidVersionError(version.to_string()));
        }
        nums.push(value);
    }
    while nums.len() < 3 {
        nums.push(0);
    }
    Ok((nums[0], nums[1], nums[2]))
}

pub fn validate_version_or_null(value: Option<&str>) -> Result<(), FatalError> {
    if let Some(version) = value {
        parse_version(version).map_err(|_| FatalError::new(INVALID_VERSION, version.to_string()))?;
    }
    Ok(())
}

fn compare_versions(left: VersionTuple, right: VersionTuple) -> Ordering {
    left.cmp(&right)
}

fn versions_equal(left: VersionTuple, right: VersionTuple) -> bool {
    left == right
}

fn version_gte(candidate: VersionTuple, requested: VersionTuple) -> bool {
    compare_versions(candidate, requested) != Ordering::Less
}

pub fn candidate_matches(
    candidate_version: &str,
    compatibility: &str,
    request_version: Option<&str>,
    exact: bool,
) -> Result<bool, FatalError> {
    let cand = parse_version(candidate_version)
        .map_err(|_| FatalError::new(INVALID_VERSION, candidate_version.to_string()))?;
    if request_version.is_none() {
        return Ok(true);
    }
    let req = parse_version(request_version.unwrap())
        .map_err(|_| FatalError::new(INVALID_VERSION, request_version.unwrap().to_string()))?;
    if exact {
        return Ok(versions_equal(cand, req));
    }
    match compatibility {
        "exact" => Ok(versions_equal(cand, req)),
        "same_major" => Ok(cand.0 == req.0 && version_gte(cand, req)),
        "same_minor_or_newer" => Ok(cand.0 == req.0 && cand.1 == req.1 && version_gte(cand, req)),
        _ => Ok(false),
    }
}

pub fn source_version_matches(
    source_version: Option<&str>,
    request_version: Option<&str>,
    exact: bool,
) -> Result<bool, FatalError> {
    if request_version.is_none() {
        return Ok(true);
    }
    let Some(source_version) = source_version else {
        return Ok(false);
    };
    let cand = parse_version(source_version)
        .map_err(|_| FatalError::new(INVALID_VERSION, source_version.to_string()))?;
    let req = parse_version(request_version.unwrap())
        .map_err(|_| FatalError::new(INVALID_VERSION, request_version.unwrap().to_string()))?;
    if exact {
        Ok(versions_equal(cand, req))
    } else {
        Ok(version_gte(cand, req))
    }
}
