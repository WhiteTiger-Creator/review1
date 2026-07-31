use crate::models::ParsedClientData;
use crate::strict_json::parse_client_data_object;

pub fn parse_client_data(bytes: &[u8]) -> Result<ParsedClientData, &'static str> {
    parse_client_data_object(bytes).map_err(|_| "client_data_malformed")
}

pub fn validate_client_data_type(parsed: &ParsedClientData) -> Result<(), &'static str> {
    if parsed.type_value != "webauthn.get" {
        return Err("client_data_type_invalid");
    }
    Ok(())
}
