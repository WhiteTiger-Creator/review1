//! Journal packing helpers.

pub fn stamp(seed: u64) -> u64 {
    seed.wrapping_mul(0x9E3779B97F4A7C15).wrapping_add(1)
}
