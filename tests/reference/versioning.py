"""Version parsing and matching per cmake_dependency_profile.md."""

from __future__ import annotations

import re

VersionTuple = tuple[int, int, int]

_VERSION_RE = re.compile(r"^(\d+)(?:\.(\d+))?(?:\.(\d+))?$")


class InvalidVersionError(ValueError):
    """Raised when a version string is not N / N.N / N.N.N."""


def parse_version(version: str) -> VersionTuple:
    """Parse a version string to (major, minor, patch), padding missing parts with zero."""
    match = _VERSION_RE.fullmatch(version.strip())
    if not match:
        raise InvalidVersionError(version)
    major = int(match.group(1))
    minor = int(match.group(2) or 0)
    patch = int(match.group(3) or 0)
    return major, minor, patch


def version_to_string(version: VersionTuple) -> str:
    """Normalize a version tuple back to its canonical dotted form."""
    major, minor, patch = version
    if minor == 0 and patch == 0:
        return str(major)
    if patch == 0:
        return f"{major}.{minor}"
    return f"{major}.{minor}.{patch}"


def compare_versions(left: VersionTuple, right: VersionTuple) -> int:
    """Lexicographic compare by (major, minor, patch)."""
    if left < right:
        return -1
    if left > right:
        return 1
    return 0


def versions_equal(left: VersionTuple, right: VersionTuple) -> bool:
    return left == right


def version_gte(candidate: VersionTuple, requested: VersionTuple) -> bool:
    return compare_versions(candidate, requested) >= 0


def candidate_matches(
    candidate_version: str,
    compatibility: str,
    request_version: str | None,
    exact: bool,
) -> bool:
    """Return whether a package candidate satisfies the request version constraints."""
    cand = parse_version(candidate_version)
    if request_version is None:
        return True
    req = parse_version(request_version)
    if exact:
        return versions_equal(cand, req)
    if compatibility == "exact":
        return versions_equal(cand, req)
    if compatibility == "same_major":
        return cand[0] == req[0] and version_gte(cand, req)
    if compatibility == "same_minor_or_newer":
        return cand[0] == req[0] and cand[1] == req[1] and version_gte(cand, req)
    return False


def source_version_matches(
    source_version: str | None,
    request_version: str | None,
    exact: bool,
) -> bool:
    """Version check for override, provider, and fetchcontent sources (no compatibility label)."""
    if request_version is None:
        return True
    if source_version is None:
        return False
    cand = parse_version(source_version)
    req = parse_version(request_version)
    if exact:
        return versions_equal(cand, req)
    return version_gte(cand, req)
