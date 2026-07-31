use crate::models::CredentialRow;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CounterDecision {
    Accept {
        new_sign_count: u32,
        risk: Option<&'static str>,
    },
    RejectReplay,
}

pub fn evaluate_counter(
    stored: u32,
    received: u32,
    backup_eligible: bool,
    backup_counter_policy: &str,
) -> CounterDecision {
    if received >= stored {
        return CounterDecision::Accept {
            new_sign_count: received,
            risk: None,
        };
    }
    if backup_eligible && backup_counter_policy == "disabled" {
        return CounterDecision::Accept {
            new_sign_count: stored,
            risk: None,
        };
    }
    CounterDecision::RejectReplay
}

pub fn credential_is_inactive(cred: &CredentialRow, user_status: &str) -> bool {
    cred.status == "quarantined" || cred.status == "revoked" || user_status == "disabled"
}
