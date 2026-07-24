"""Behavior tests for constrained quorum recovery."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path

APP = Path('/app')
DB = APP / 'data/features.db'
FIXTURE = json.loads(Path('/tests/expected_state.json').read_text())


def sha256(path: Path) -> str:
    """Return the lowercase SHA-256 digest of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(query: str) -> list[list[object]]:
    """Read deterministic rows from SQLite."""
    connection = sqlite3.connect(DB)
    try:
        return [list(row) for row in connection.execute(query).fetchall()]
    finally:
        connection.close()


def test_protected_inputs_and_evidence_are_unchanged() -> None:
    """Protected files and source database evidence must remain unchanged."""
    for path, digest in FIXTURE['protected_file_sha256'].items():
        assert sha256(Path(path)) == digest
    assert rows(
        'SELECT signer_id,role,incident_id,public_key_sha256,status,priority,'
        'not_before,not_after,region,key_family,assurance_weight '
        'FROM recovery_candidates ORDER BY signer_id'
    ) == FIXTURE['recovery_candidates']
    assert rows(
        'SELECT frame_id,edge_density,skin_ratio,text_ratio,label '
        'FROM image_features ORDER BY frame_id'
    ) == FIXTURE['image_features']
    assert rows(
        'SELECT root_id,status FROM trust_roots ORDER BY root_id'
    ) == FIXTURE['trust_roots']
    assert rows(
        'SELECT parent_id,child_id,incident_id,not_before,not_after,status '
        'FROM delegation_edges ORDER BY parent_id,child_id,incident_id'
    ) == FIXTURE['delegation_edges']
    assert rows(
        'SELECT signer_id,custodian,risk_score '
        'FROM custody_controls ORDER BY signer_id'
    ) == FIXTURE['custody_controls']
    assert rows(
        'SELECT signer_a,signer_b,incident_id,active '
        'FROM pair_denials ORDER BY signer_a,signer_b,incident_id'
    ) == FIXTURE['pair_denials']


def test_selected_quorum_matches_held_out_optimum() -> None:
    """The delivered quorum must match the sealed global optimum."""
    lines = (APP / 'output/signer_quorum.tsv').read_text().splitlines()
    assert lines[0] == (
        'role\tsigner_id\tpriority\tregion\tkey_family\t'
        'assurance_weight\tpublic_key_sha256'
    )
    parsed = []
    for line in lines[1:]:
        role, signer, priority, region, family, weight, digest = line.split('\t')
        parsed.append([role, signer, int(priority), region, family, int(weight), digest])
    assert parsed == FIXTURE['expected_quorum_rows']


def test_quorum_summary_is_exact_and_grounded() -> None:
    """The quorum summary must report the selected constraints exactly."""
    summary = json.loads((APP / 'output/quorum_summary.json').read_text())
    assert list(summary) == [
        'assurance_weight',
        'delegation_roots',
        'regions',
        'signer_count',
        'signer_ids',
        'total_priority',
        'total_risk',
    ]
    assert summary == {
        'assurance_weight': FIXTURE['expected_assurance_weight'],
        'delegation_roots': FIXTURE['expected_delegation_roots'],
        'regions': FIXTURE['expected_regions'],
        'signer_count': len(FIXTURE['expected_signer_ids']),
        'signer_ids': FIXTURE['expected_signer_ids'],
        'total_priority': FIXTURE['expected_total_priority'],
        'total_risk': FIXTURE['expected_total_risk'],
    }


def test_delegation_paths_are_exact_and_grounded() -> None:
    """Every selected signer must use the sealed shortest valid trust path."""
    lines = (APP / 'output/delegation_paths.tsv').read_text().splitlines()
    assert lines[0] == (
        'role\tsigner_id\troot_id\thops\tdelegation_path\t'
        'custodian\trisk_score'
    )
    parsed = []
    for line in lines[1:]:
        role, signer, root, hops, path, custodian, risk = line.split('\t')
        parsed.append([role, signer, root, int(hops), path, custodian, int(risk)])
    assert parsed == FIXTURE['expected_delegation_rows']


def test_policy_binds_all_recovery_evidence() -> None:
    """The release policy must bind the model, candidate snapshot, ledger, and chain."""
    policy_path = APP / 'trust/release-policy.json'
    policy = json.loads(policy_path.read_text())
    assert list(policy) == [
        'allowed_model_kind',
        'assurance_weight',
        'candidate_snapshot_sha256',
        'compromise_ledger_sha256',
        'delegation_state_sha256',
        'incident_id',
        'maximum_threshold',
        'minimum_threshold',
        'model_sha256',
        'previous_policy_sha256',
        'regions',
        'release_sequence',
        'signer_id',
        'signer_ids',
        'trust_roots',
    ]
    request = json.loads((APP / 'recovery/recovery-request.json').read_text())
    config = json.loads((APP / 'config/screening.json').read_text())
    assert policy['allowed_model_kind'] == 'logistic_regression'
    assert policy['assurance_weight'] == FIXTURE['expected_assurance_weight']
    assert policy['candidate_snapshot_sha256'] == sha256(APP / 'recovery/candidate-snapshot.tsv')
    assert policy['compromise_ledger_sha256'] == sha256(APP / 'recovery/compromise-ledger.jsonl')
    assert policy['delegation_state_sha256'] == sha256(APP / 'recovery/delegation-state.tsv')
    assert policy['incident_id'] == request['incident_id']
    assert policy['minimum_threshold'] == config['minimum_threshold']
    assert policy['maximum_threshold'] == config['maximum_threshold']
    assert policy['model_sha256'] == sha256(APP / 'model/metadata.json')
    assert policy['regions'] == FIXTURE['expected_regions']
    assert policy['signer_ids'] == FIXTURE['expected_signer_ids']
    assert policy['signer_id'] == FIXTURE['expected_signer_ids'][0]
    assert policy['trust_roots'] == FIXTURE['expected_delegation_roots']
    baseline = FIXTURE['initial_release_history'][-1]
    assert policy['previous_policy_sha256'] == baseline[1]
    request_minimum = request['minimum_release_sequence']
    assert policy['release_sequence'] == max(baseline[0] + 1, request_minimum)


def test_every_quorum_signature_verifies() -> None:
    """Every selected signer must provide a valid detached policy signature."""
    policy = APP / 'trust/release-policy.json'
    primary = FIXTURE['expected_signer_ids'][0]
    assert (APP / 'trust/release.pub').read_bytes() == (
        APP / f'recovery/candidates/{primary}-verification.material'
    ).read_bytes()
    for signer in FIXTURE['expected_signer_ids']:
        signature = (
            APP / 'trust/release-policy.sig'
            if signer == primary
            else APP / f'trust/approvals/{signer}.sig'
        )
        result = subprocess.run(
            [
                'openssl',
                'dgst',
                '-sha256',
                '-verify',
                str(APP / f'recovery/candidates/{signer}-verification.material'),
                '-signature',
                str(signature),
                str(policy),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0


def test_database_preserves_history_and_records_one_release() -> None:
    """The transaction must preserve baseline rows and append one exact release."""
    history = rows(
        'SELECT release_sequence,policy_sha256,incident_id,signer_quorum '
        'FROM release_history ORDER BY release_sequence'
    )
    assert history[:-1] == FIXTURE['initial_release_history']
    assert len(history) == len(FIXTURE['initial_release_history']) + 1
    policy = json.loads((APP / 'trust/release-policy.json').read_text())
    assert history[-1] == [
        policy['release_sequence'],
        sha256(APP / 'trust/release-policy.json'),
        policy['incident_id'],
        ','.join(FIXTURE['expected_signer_ids']),
    ]
    compromised = json.loads((APP / 'recovery/recovery-request.json').read_text())['revoked_signer']
    states = dict(
        (row[0], row[2])
        for row in rows('SELECT signer_id,public_key_sha256,status FROM trusted_signers')
    )
    assert states[compromised] == 'revoked'
    for signer in FIXTURE['expected_signer_ids']:
        assert states[signer] == 'trusted'


def test_audit_is_exact_and_grounded() -> None:
    """The recovery audit must be grounded in the published policy and inputs."""
    audit = json.loads((APP / 'output/recovery_audit.json').read_text())
    assert list(audit) == [
        'candidate_snapshot_sha256',
        'compromise_ledger_sha256',
        'delegation_state_sha256',
        'incident_id',
        'policy_sha256',
        'previous_policy_sha256',
        'release_sequence',
        'signature_count',
        'signer_ids',
    ]
    policy = json.loads((APP / 'trust/release-policy.json').read_text())
    assert audit == {
        'candidate_snapshot_sha256': sha256(APP / 'recovery/candidate-snapshot.tsv'),
        'compromise_ledger_sha256': sha256(APP / 'recovery/compromise-ledger.jsonl'),
        'delegation_state_sha256': sha256(APP / 'recovery/delegation-state.tsv'),
        'incident_id': policy['incident_id'],
        'policy_sha256': sha256(APP / 'trust/release-policy.json'),
        'previous_policy_sha256': policy['previous_policy_sha256'],
        'release_sequence': policy['release_sequence'],
        'signature_count': len(FIXTURE['expected_signer_ids']),
        'signer_ids': FIXTURE['expected_signer_ids'],
    }


def test_gate_deliverable_is_admitted_and_deterministic(tmp_path: Path) -> None:
    """The required gate output must be admitted, grounded, and reproducible."""
    delivered = APP / 'output/gate.json'
    assert delivered.exists()
    assert json.loads(delivered.read_text()) == FIXTURE['expected_gate']
    rerun = tmp_path / 'gate.json'
    result = subprocess.run(
        [str(APP / 'bin/screening-gate'), '--output', str(rerun)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert rerun.read_bytes() == delivered.read_bytes()


def run_gate(output: Path) -> subprocess.CompletedProcess[str]:
    """Run the admission gate against the recovered release."""
    return subprocess.run(
        [str(APP / 'bin/screening-gate'), '--output', str(output)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_gate_fails_closed_when_primary_trust_is_revoked(tmp_path: Path) -> None:
    """Revoking the installed primary signer must make the gate fail closed."""
    primary = FIXTURE['expected_signer_ids'][0]
    connection = sqlite3.connect(DB)
    connection.execute(
        "UPDATE trusted_signers SET status='revoked' WHERE signer_id=?",
        (primary,),
    )
    connection.commit()
    try:
        output = tmp_path / 'rejected.json'
        result = run_gate(output)
        assert result.returncode != 0
        assert json.loads(output.read_text()) == {'error': 'signer_revoked'}
    finally:
        connection.execute(
            "UPDATE trusted_signers SET status='trusted' WHERE signer_id=?",
            (primary,),
        )
        connection.commit()
        connection.close()


def test_gate_fails_closed_when_a_trust_root_is_revoked(tmp_path: Path) -> None:
    """A selected delegation root becoming revoked must block admission."""
    root = FIXTURE['expected_delegation_roots'][0]
    connection = sqlite3.connect(DB)
    connection.execute("UPDATE trust_roots SET status='revoked' WHERE root_id=?", (root,))
    connection.commit()
    try:
        output = tmp_path / 'root-rejected.json'
        result = run_gate(output)
        assert result.returncode != 0
        assert json.loads(output.read_text()) == {'error': 'trust_root_revoked'}
    finally:
        connection.execute("UPDATE trust_roots SET status='trusted' WHERE root_id=?", (root,))
        connection.commit()
        connection.close()


def test_gate_fails_closed_when_pair_denial_becomes_active(tmp_path: Path) -> None:
    """A new active denial between selected signers must block admission."""
    first, second = FIXTURE['expected_signer_ids'][:2]
    connection = sqlite3.connect(DB)
    connection.execute(
        'INSERT OR REPLACE INTO pair_denials(signer_a,signer_b,incident_id,active) '
        'VALUES(?,?,?,1)',
        (first, second, 'INC-2026-0721-SCREENING'),
    )
    connection.commit()
    try:
        output = tmp_path / 'pair-rejected.json'
        result = run_gate(output)
        assert result.returncode != 0
        assert json.loads(output.read_text()) == {'error': 'pair_denied'}
    finally:
        connection.execute(
            'DELETE FROM pair_denials WHERE signer_a=? AND signer_b=? '
            'AND incident_id=?',
            (first, second, 'INC-2026-0721-SCREENING'),
        )
        connection.commit()
        connection.close()
