#[derive(Clone, Debug)]
pub struct ByteView<'a> {
    pub data: &'a [u8],
}

#[derive(Clone, Debug, Default)]
pub struct ChannelView {
    pub bytes: Vec<u8>,
    pub names: Vec<String>,
    /// Parallel present flags; false means slot still needs fill or is missing.
    pub present: Vec<bool>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PathKind {
    Off,
    On,
}

#[derive(Clone, Debug, Default)]
pub struct FillReport {
    pub filled: usize,
}

#[derive(Clone, Debug, Default)]
pub struct KitPolicy {
    pub forbid: Vec<String>,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum GateStatus {
    Accept,
    Reject,
}

#[derive(Clone, Debug, Default)]
pub struct PredBase {
    pub digest_u64: u64,
    pub gen: u32,
}

#[derive(Clone, Debug, Default)]
pub struct PredSeries {
    pub vals: Vec<(u64, f64)>,
}

#[derive(Clone, Debug, Default)]
pub struct AxCtx {
    /// gen -> list of (wire_name, canonical_name)
    pub maps: Vec<(u32, Vec<(String, String)>)>,
    pub canon0: Vec<String>,
    pub canon2: Vec<String>,
    /// Active wire pairs for this call (name, value).
    pub wire: Vec<(String, f32)>,
}

#[derive(Clone, Debug, Default)]
pub struct DvCtx {
    pub fills: Vec<(String, f32)>,
}

#[derive(Clone, Debug, Default)]
pub struct RjCtx {
    pub required0: Vec<String>,
    pub required2: Vec<String>,
}

#[derive(Clone, Debug, Default)]
pub struct ScCtx {
    pub k: u64,
}

pub fn fnv1a64(data: &[u8]) -> u64 {
    let mut h: u64 = 0xcbf29ce484222325;
    for &b in data {
        h ^= b as u64;
        h = h.wrapping_mul(0x100000001b3);
    }
    h
}

pub fn hex16(v: u64) -> String {
    format!("{:016x}", v)
}
