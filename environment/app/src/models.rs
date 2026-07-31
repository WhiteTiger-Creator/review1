use serde::Serialize;

#[derive(Debug, Clone)]
pub struct RpPolicy {
    pub rp_id: String,
    pub require_user_verification: bool,
    pub backup_counter_policy: String,
}

#[derive(Debug, Clone)]
pub struct UserRow {
    pub user_id: String,
    pub status: String,
}

#[derive(Debug, Clone)]
pub struct CredentialRow {
    pub credential_id: String,
    pub user_id: String,
    pub rp_id: String,
    pub public_key_sec1: Vec<u8>,
    pub sign_count: u32,
    pub backup_eligible: bool,
    pub backup_state: bool,
    pub status: String,
    pub last_used_at: Option<String>,
}

#[derive(Debug, Clone)]
pub struct ChallengeRow {
    pub challenge_id: String,
    pub rp_id: String,
    pub challenge_bytes: Vec<u8>,
    pub issued_at: String,
    pub expires_at: String,
    pub consumed_at: Option<String>,
    pub consumed_by_assertion_id: Option<String>,
}

#[derive(Debug, Clone)]
pub struct AssertionJob {
    pub assertion_id: String,
    pub received_at: String,
    pub event_seq: i64,
    pub credential_id: String,
    pub challenge_id: String,
    pub client_data_json: Vec<u8>,
    pub authenticator_data: Vec<u8>,
    pub signature_der: Vec<u8>,
    pub status: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct AssertionResultRow {
    pub assertion_id: String,
    pub status: String,
    pub reason_or_null: Option<String>,
    pub risk_or_null: Option<String>,
    pub credential_id: String,
    pub challenge_id: String,
    pub received_at: String,
    pub user_present_or_null: Option<i64>,
    pub user_verified_or_null: Option<i64>,
    pub backup_eligible_or_null: Option<i64>,
    pub backup_state_or_null: Option<i64>,
    pub sign_count_or_null: Option<i64>,
    pub sign_count_before_or_null: Option<i64>,
    pub sign_count_after_or_null: Option<i64>,
    pub challenge_consumed: i64,
    pub credential_mutated: i64,
}

#[derive(Debug, Clone, Serialize)]
pub struct AssertionReportRow {
    pub assertion_id: String,
    pub credential_id: String,
    pub challenge_id: String,
    pub received_at: String,
    pub status: String,
    pub reason_or_null: Option<String>,
    pub risk_or_null: Option<String>,
    pub user_present_or_null: Option<i64>,
    pub user_verified_or_null: Option<i64>,
    pub backup_eligible_or_null: Option<i64>,
    pub backup_state_or_null: Option<i64>,
    pub sign_count_or_null: Option<i64>,
    pub sign_count_before_or_null: Option<i64>,
    pub sign_count_after_or_null: Option<i64>,
    pub challenge_consumed: i64,
    pub credential_mutated: i64,
}

#[derive(Debug, Clone, Serialize)]
pub struct CredentialReportRow {
    pub credential_id: String,
    pub user_id: String,
    pub rp_id: String,
    pub status: String,
    pub sign_count: i64,
    pub backup_eligible: i64,
    pub backup_state: i64,
    pub last_used_at_or_null: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct ChallengeReportRow {
    pub challenge_id: String,
    pub rp_id: String,
    pub status: String,
    pub issued_at: String,
    pub expires_at: String,
    pub consumed_at_or_null: Option<String>,
    pub consumed_by_assertion_id_or_null: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct Summary {
    pub processed_assertion_count: i64,
    pub accepted_assertion_count: i64,
    pub rejected_assertion_count: i64,
    pub risk_assertion_count: i64,
    pub consumed_challenge_count: i64,
    pub active_credential_count: i64,
    pub quarantined_credential_count: i64,
    pub revoked_credential_count: i64,
    pub pending_future_job_count: i64,
}

#[derive(Debug, Clone, Serialize)]
pub struct Report {
    pub assertion_rows: Vec<AssertionReportRow>,
    pub credential_rows: Vec<CredentialReportRow>,
    pub challenge_rows: Vec<ChallengeReportRow>,
    pub summary: Summary,
}

#[derive(Debug, Clone)]
pub struct ParsedAuthData {
    pub rp_id_hash: [u8; 32],
    pub flags: u8,
    pub sign_count: u32,
    pub user_present: bool,
    pub user_verified: bool,
    pub backup_eligible: bool,
    pub backup_state: bool,
}

#[derive(Debug, Clone)]
pub struct ParsedClientData {
    pub type_value: String,
    pub challenge: String,
    pub origin: String,
    pub cross_origin: Option<bool>,
}
