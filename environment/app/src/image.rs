//! KXF1 container parsing.
//!
//! `parse` returns the shadowed body together with the header fields the rest of the
//! workbench reports, or the contract's error code and a human-readable detail.

pub const IO_BASE: u16 = 0xFF00;
pub const IO_TOP: u16 = 0xFF1F;

pub struct Firmware {
    pub load: u16,
    pub body: Vec<u8>,
    pub checksum: u16,
}

pub fn parse(raw: &[u8]) -> Result<Firmware, (&'static str, String)> {
    let _ = raw;
    Err(("io_error", "container validation is not implemented".to_string()))
}

/// True for addresses inside the peripheral window.
pub fn is_io(addr: u16) -> bool {
    let _ = addr;
    false
}
