use crate::models::ParsedAuthData;

const DISALLOWED_MASK: u8 = 0xE2;

pub fn parse_authenticator_data(bytes: &[u8]) -> Result<ParsedAuthData, &'static str> {
    if bytes.len() != 37 {
        return Err("authenticator_data_malformed");
    }
    let flags = bytes[32];
    if flags & DISALLOWED_MASK != 0 {
        return Err("authenticator_data_malformed");
    }
    let mut rp_id_hash = [0u8; 32];
    rp_id_hash.copy_from_slice(&bytes[0..32]);
    let sign_count = u32::from_be_bytes([bytes[33], bytes[34], bytes[35], bytes[36]]);
    Ok(ParsedAuthData {
        rp_id_hash,
        flags,
        sign_count,
        user_present: flags & 0x01 != 0,
        user_verified: flags & 0x04 != 0,
        backup_eligible: flags & 0x08 != 0,
        backup_state: flags & 0x10 != 0,
    })
}

pub fn build_authenticator_data(rp_id_hash: &[u8; 32], flags: u8, sign_count: u32) -> Vec<u8> {
    let mut out = Vec::with_capacity(37);
    out.extend_from_slice(rp_id_hash);
    out.push(flags);
    out.extend_from_slice(&sign_count.to_be_bytes());
    out
}
