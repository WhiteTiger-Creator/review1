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
    if stored == 0 && received == 0 {
        return CounterDecision::Accept {
            new_sign_count: 0,
            risk: None,
        };
    }
    if received > stored {
        return CounterDecision::Accept {
            new_sign_count: received,
            risk: None,
        };
    }
    // Non-increasing nonzero
    let backup_aware = backup_eligible && backup_counter_policy == "backup_aware";
    if backup_aware {
        CounterDecision::Accept {
            new_sign_count: stored.max(received),
            risk: Some("non_monotonic_backup_counter"),
        }
    } else {
        CounterDecision::RejectReplay
    }
}

pub fn credential_is_inactive(cred: &CredentialRow, user_status: &str) -> bool {
    cred.status == "quarantined" || cred.status == "revoked" || user_status == "disabled"
}
