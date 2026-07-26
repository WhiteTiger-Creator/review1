#![allow(dead_code)]
pub fn unused_seed_mix(x: u32) -> u32 {
    x.wrapping_mul(2654435761)
}
