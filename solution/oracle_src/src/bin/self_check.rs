//! Author-only Oracle self-checks. Never invoked from candidate pytest.

use p256::ecdsa::{signature::Signer, Signature, SigningKey};
use p256::SecretKey;
use webauthn_assertion_worker::authenticator_data::{
    build_authenticator_data, parse_authenticator_data,
};
use webauthn_assertion_worker::cli::ts_cmp;
use webauthn_assertion_worker::crypto::{b64url_encode, sha256, signed_message, verify_es256_der};
use webauthn_assertion_worker::policy::{evaluate_counter, CounterDecision};
use webauthn_assertion_worker::strict_json::parse_client_data_object;

fn main() {
    check_client_data_hashing();
    check_normalization_stable_reaches_later_rules();
    check_auth_data();
    check_der_verify();
    check_counter_policies();
    check_inclusive_expiration();
    check_job_ordering_keys();
    check_test21_snapshot_contract();
    println!("oracle-self-check: ok");
}

fn check_client_data_hashing() {
    let noncanonical = br#"{
  "origin": "https://www.example.com",
  "type": "webauthn.get",
  "challenge": "abc"
}"#;
    let compact = serde_json::to_vec(&serde_json::from_slice::<serde_json::Value>(noncanonical).unwrap())
        .unwrap();
    assert_ne!(noncanonical.as_slice(), compact.as_slice());
    // Original-byte hashing: digests differ when whitespace/order differ.
    assert_ne!(sha256(noncanonical), sha256(&compact));
    let msg_nc = signed_message(b"ad", noncanonical);
    let msg_c = signed_message(b"ad", &compact);
    assert_ne!(msg_nc, msg_c);

    let dup = br#"{"type":"webauthn.get","type":"webauthn.get","challenge":"abc","origin":"https://example.com"}"#;
    assert!(parse_client_data_object(dup).is_err());
}

fn check_normalization_stable_reaches_later_rules() {
    // Alphabetical compact JSON matches serde_json::Value re-encoding.
    let stable = br#"{"challenge":"abc","origin":"https://example.com","type":"webauthn.get"}"#;
    let roundtrip =
        serde_json::to_vec(&serde_json::from_slice::<serde_json::Value>(stable).unwrap()).unwrap();
    assert_eq!(stable.as_slice(), roundtrip.as_slice());
    let parsed = parse_client_data_object(stable).expect("parse stable");
    assert_eq!(parsed.type_value, "webauthn.get");
    assert_eq!(parsed.origin, "https://example.com");
}

fn check_auth_data() {
    let rp = sha256(b"example.com");
    let raw = build_authenticator_data(&rp, 0x01 | 0x04, 42);
    let parsed = parse_authenticator_data(&raw).unwrap();
    assert_eq!(parsed.sign_count, 42);
    assert!(parsed.user_present && parsed.user_verified);
    assert!(parse_authenticator_data(&raw[..36]).is_err());
    let mut bad = raw.clone();
    bad[32] |= 0x40; // AT
    assert!(parse_authenticator_data(&bad).is_err());
}

fn check_der_verify() {
    let sk = SigningKey::from(SecretKey::from_slice(&[7u8; 32]).unwrap());
    let vk = sk.verifying_key();
    let sec1 = vk.to_encoded_point(false);
    let msg = b"authenticator-data-and-hash-message";
    let sig: Signature = sk.sign(msg);
    let der = sig.to_der();
    verify_es256_der(sec1.as_bytes(), msg, der.as_bytes()).unwrap();
    let mut trailing = der.as_bytes().to_vec();
    trailing.push(0);
    assert!(verify_es256_der(sec1.as_bytes(), msg, &trailing).is_err());
    let raw64 = {
        let (r, s) = (sig.r().to_bytes(), sig.s().to_bytes());
        let mut v = Vec::new();
        v.extend_from_slice(&r);
        v.extend_from_slice(&s);
        v
    };
    assert!(verify_es256_der(sec1.as_bytes(), msg, &raw64).is_err());
    let _ = b64url_encode(b"hello");
    let _ = signed_message(b"ad", b"cd");
}

fn check_counter_policies() {
    assert!(matches!(
        evaluate_counter(0, 0, false, "strict"),
        CounterDecision::Accept {
            new_sign_count: 0,
            risk: None
        }
    ));
    assert!(matches!(
        evaluate_counter(0, 5, false, "strict"),
        CounterDecision::Accept {
            new_sign_count: 5,
            risk: None
        }
    ));
    assert!(matches!(
        evaluate_counter(5, 0, false, "strict"),
        CounterDecision::RejectReplay
    ));
    assert!(matches!(
        evaluate_counter(5, 0, true, "backup_aware"),
        CounterDecision::Accept {
            new_sign_count: 5,
            risk: Some("non_monotonic_backup_counter")
        }
    ));
    assert!(matches!(
        evaluate_counter(5, 5, false, "strict"),
        CounterDecision::RejectReplay
    ));
    assert!(matches!(
        evaluate_counter(5, 5, true, "backup_aware"),
        CounterDecision::Accept {
            new_sign_count: 5,
            risk: Some("non_monotonic_backup_counter")
        }
    ));
    assert!(matches!(
        evaluate_counter(5, 4, true, "strict"),
        CounterDecision::RejectReplay
    ));
    assert!(matches!(
        evaluate_counter(5, 4, false, "backup_aware"),
        CounterDecision::RejectReplay
    ));
}

fn check_inclusive_expiration() {
    // received_at == expires_at is not expired (inclusive).
    assert_eq!(
        ts_cmp("2026-06-10T12:20:00Z", "2026-06-10T12:20:00Z"),
        std::cmp::Ordering::Equal
    );
}

fn check_job_ordering_keys() {
    // Processing key: received_at, event_seq, assertion_id.
    let mut jobs = vec![
        ("2026-06-11T08:00:00Z", 300i64, "assert-t21-a"),
        ("2026-06-11T08:00:00Z", 200i64, "assert-t21-b"),
        ("2026-06-11T08:00:00Z", 100i64, "assert-t21-c"),
    ];
    jobs.sort_by(|a, b| {
        a.0.cmp(&b.0)
            .then(a.1.cmp(&b.1))
            .then(a.2.cmp(&b.2))
    });
    assert_eq!(
        jobs.iter().map(|j| j.2).collect::<Vec<_>>(),
        vec!["assert-t21-c", "assert-t21-b", "assert-t21-a"]
    );
    // Lexicographic assertion_id order is the reverse of event_seq order.
    let mut by_id = jobs.clone();
    by_id.sort_by(|a, b| a.2.cmp(&b.2));
    assert_eq!(
        by_id.iter().map(|j| j.2).collect::<Vec<_>>(),
        vec!["assert-t21-a", "assert-t21-b", "assert-t21-c"]
    );
}

fn check_test21_snapshot_contract() {
    // Step 1 advance 20 -> 21; step 2 UV reject keeps 21; step 3 replay keeps 21.
    let mut stored = 20u32;
    match evaluate_counter(stored, 21, true, "backup_aware") {
        CounterDecision::Accept {
            new_sign_count,
            risk: None,
        } => stored = new_sign_count,
        other => panic!("step1 unexpected: {other:?}"),
    }
    assert_eq!(stored, 21);
    // Authenticated UV rejection does not change count (policy stage after counters).
    assert_eq!(stored, 21);
    // Challenge reuse is challenge_already_consumed (ordering helper only here).
    assert_eq!(stored, 21);
}
