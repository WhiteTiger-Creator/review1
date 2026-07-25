import hashlib
import json
import subprocess
from pathlib import Path

APP = Path('/app')
OUT = APP / 'output' / 'build-plan.json'
CMD = ['node', '/app/bin/repair-lock.js']

BASE_POLICY = {
    'nodeVersion': '20.11.1',
    'buildHost': 'linux',
    'includeDevDependencies': False,
    'includeOptionalDependencies': False,
    'preferStable': True,
    'licenseAllowlist': ['MIT'],
    'blockedPackages': [],
    'expectedIntegrityHost': 'mirror.local',
    'overrides': {},
    'resolutions': {},
    'patches': {},
}


def run_tool():
    if OUT.exists():
        OUT.unlink()
    result = subprocess.run(
        CMD, cwd='/app', text=True, capture_output=True, timeout=30, check=False
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert OUT.exists(), 'build-plan.json was not created'
    raw = OUT.read_text()
    return raw, json.loads(raw)


def by_name(plan):
    return {pkg['name']: pkg for pkg in plan['packages']}


def input_fingerprints(app_root=APP):
    fingerprints = {}
    for directory in ('workspace', 'registry', 'config', 'docs'):
        root = app_root / directory
        if not root.exists():
            continue
        for path in sorted(root.rglob('*')):
            if path.is_file():
                rel = path.relative_to(app_root).as_posix()
                fingerprints[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return fingerprints


EXPECTED_INPUT_FINGERPRINTS = {
    'workspace/package-lock.json': '83d758b7f6688af47c17c90945a19cbb6c79ea31ea6efc8ff78a3a4748cc3f12',
    'workspace/package.json': 'e26b5b2f48c772b9d4cfc05397a06df53364710e1f59003de38c92a55c2d9545',
    'workspace/packages/core/package.json': 'a34997a7c8f9e64f62a5e65f16600f79e96600b995b7a2d0140b47453e547156',
    'workspace/packages/plugin-auth/package.json': 'ffbb4f5fb65aa591f968d79c763facf78a61c87930a7d9cf0d2502344edb37f7',
    'workspace/packages/telemetry/package.json': '0cb4980f40a359404fe7b6a42e2a1b0033306cdd88722f42199f467f92d52e64',
    'registry/packages.json': '6b6e4bc17dee211eb445a6671afde81abe4b2d6dfb564b1fa5ebca59dffa4b77',
    'config/archive_policy.json': 'd5ffa1bf3361173802e3c49718c331727f3971df0bac3df133782d2108dae58d',
    'config/policy.json': '4a29473c3e523781038e86eb41f950e1a7aec764b6372b4fe2e89d8698401c27',
    'docs/mirror_contract.md': '2b516caa41bd18f700e0590afd14500e3126a895dc46c2508eb5d8346c775d0c',
}


def test_bundled_inputs_remain_unchanged():
    before = input_fingerprints()
    assert before == EXPECTED_INPUT_FINGERPRINTS
    run_tool()
    after = input_fingerprints()
    assert after == EXPECTED_INPUT_FINGERPRINTS


def test_top_level_schema_formatting_and_determinism():
    raw1, plan1 = run_tool()
    raw2, _ = run_tool()
    assert raw1 == raw2
    assert raw1 == json.dumps(plan1, indent=2)
    assert '\t' not in raw1
    assert list(plan1.keys()) == [
        'root', 'nodeVersion', 'packages', 'unresolved', 'peerWarnings',
        'policyViolations', 'mirrorWarnings', 'lockDrift', 'summary'
    ]
    assert plan1['root'] == 'ridge-ui'
    assert plan1['nodeVersion'] == '20.11.1'
    assert [p['name'] for p in plan1['packages']] == sorted(p['name'] for p in plan1['packages'])


def test_package_entry_key_order_and_requested_by():
    _, plan = run_tool()
    for pkg in plan['packages']:
        assert list(pkg.keys()) == [
            'name', 'package', 'version', 'source', 'requestedBy',
            'license', 'integrity', 'tarball', 'patched', 'yanked'
        ]
        assert pkg['requestedBy'] == sorted(set(pkg['requestedBy']))


def test_resolution_overrides_aliases_workspaces_and_shared_versions():
    _, plan = run_tool()
    pkgs = by_name(plan)
    expected_names = {
        '@ridge/core', '@ridge/plugin-auth', '@types/node', 'ansi-regex', 'debug',
        'jsonwebtoken', 'jwa', 'jws', 'left-pad', 'left-pad-safe',
        'ms', 'rollup', 'undici-types'
    }
    assert set(pkgs) == expected_names
    assert '@ridge/telemetry' not in pkgs
    assert 'source-map' not in pkgs
    assert pkgs['@ridge/core']['source'] == 'workspace'
    assert pkgs['debug']['version'] == '4.3.5'
    assert pkgs['debug']['integrity'] == 'sha512-debug435-patched'
    assert pkgs['ansi-regex']['version'] == '6.1.0'
    assert pkgs['left-pad-safe']['package'] == 'left-pad'
    assert pkgs['left-pad']['integrity'] == 'sha512-left130-patched'
    assert pkgs['ms']['version'] == '2.1.3'
    assert pkgs['ms']['requestedBy'] == ['@ridge/core', 'debug', 'root']


def test_resolutions_pins_and_transitive_chain():
    _, plan = run_tool()
    pkgs = by_name(plan)
    assert pkgs['jsonwebtoken']['version'] == '9.0.0'
    assert pkgs['jsonwebtoken']['integrity'] == 'sha512-jwt900'
    assert pkgs['jws']['version'] == '3.2.2'
    assert pkgs['jwa']['requestedBy'] == ['jws']
    assert pkgs['undici-types']['requestedBy'] == ['@types/node']


def test_transitive_dev_engine_blocked_and_patch_behavior():
    _, plan = run_tool()
    pkgs = by_name(plan)
    assert pkgs['rollup']['version'] == '3.29.5'
    assert 'fsevents' not in pkgs
    assert pkgs['jwa']['version'] == '1.4.1'
    assert pkgs['debug']['patched'] is True
    assert pkgs['left-pad-safe']['patched'] is True
    assert plan['unresolved'] == [{
        'name': 'event-stream',
        'range': '^4.0.0',
        'requestedBy': 'root',
        'reason': 'blocked by policy'
    }]


def test_peer_optional_meta_and_mirror_warnings():
    _, plan = run_tool()
    peers = {(w['package'], w['peer']) for w in plan['peerWarnings']}
    assert ('@ridge/plugin-auth', 'legacy-shim') not in peers
    assert ('jsonwebtoken', 'crypto-helper') in peers
    assert plan['policyViolations'] == []
    assert plan['mirrorWarnings'] == [{
        'package': 'ansi-regex',
        'version': '6.1.0',
        'tarball': 'https://cdn.badmirror.test/ansi-regex-6.1.0.tgz',
        'expectedHost': 'mirror.local'
    }]


def test_lock_drift_matches_stale_snapshot():
    _, plan = run_tool()
    assert plan['lockDrift'] == [
        {
            'package': 'ansi-regex',
            'lockVersion': '5.0.1',
            'plannedVersion': '6.1.0',
            'lockIntegrity': 'sha512-oldansi',
            'plannedIntegrity': 'sha512-ansi610'
        },
        {
            'package': 'debug',
            'lockVersion': '3.2.7',
            'plannedVersion': '4.3.5',
            'lockIntegrity': 'sha512-olddebug',
            'plannedIntegrity': 'sha512-debug435-patched'
        },
        {
            'package': 'left-pad',
            'lockVersion': '1.1.3',
            'plannedVersion': '1.3.0',
            'lockIntegrity': 'sha512-oldleft',
            'plannedIntegrity': 'sha512-left130-patched'
        },
        {
            'package': 'ms',
            'lockVersion': '2.1.1',
            'plannedVersion': '2.1.3',
            'lockIntegrity': 'sha512-oldms',
            'plannedIntegrity': 'sha512-ms213'
        }
    ]


def test_warning_section_sort_orders():
    _, plan = run_tool()
    assert plan['unresolved'] == sorted(
        plan['unresolved'], key=lambda e: (e['name'], e['requestedBy'], e['range'])
    )
    assert plan['peerWarnings'] == sorted(
        plan['peerWarnings'], key=lambda e: (e['package'], e['peer'], e['requested'])
    )
    assert plan['mirrorWarnings'] == sorted(
        plan['mirrorWarnings'], key=lambda e: (e['package'], e['version'])
    )
    assert plan['lockDrift'] == sorted(plan['lockDrift'], key=lambda e: e['package'])


def test_summary_matches_report_sections():
    _, plan = run_tool()
    packages = plan['packages']
    summary = plan['summary']
    assert summary == {
        'packageCount': len(packages),
        'workspaceCount': sum(1 for p in packages if p['source'] == 'workspace'),
        'registryCount': sum(1 for p in packages if p['source'] == 'registry'),
        'patchedCount': sum(1 for p in packages if p['patched']),
        'yankedSelectedCount': sum(1 for p in packages if p['yanked']),
        'unresolvedCount': len(plan['unresolved']),
        'peerWarningCount': len(plan['peerWarnings']),
        'policyViolationCount': len(plan['policyViolations']),
        'mirrorWarningCount': len(plan['mirrorWarnings']),
        'lockDriftCount': len(plan['lockDrift'])
    }
    assert summary['packageCount'] == 13
    assert summary['patchedCount'] == 3
    assert summary['lockDriftCount'] == 4
    assert summary['yankedSelectedCount'] == 0


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n')


def _swap_app_files(overrides):
    backups = {}
    for rel, content in overrides.items():
        target = APP / rel
        backups[target] = target.read_text() if target.exists() else None
        if content is None:
            if target.exists():
                target.unlink()
        elif rel.endswith('.json'):
            _write_json(target, content)
        else:
            target.write_text(content)
    return backups


def _restore_app_files(backups):
    for target, original in backups.items():
        if original is None:
            if target.exists():
                target.unlink()
        else:
            target.write_text(original)


def _minimal_workspace(deps=None, dev_deps=None, optional_deps=None):
    pkg = {
        'name': 'ridge-ui',
        'version': '1.0.0',
        'private': True,
        'workspaces': ['packages/*'],
        'dependencies': deps or {}
    }
    if dev_deps is not None:
        pkg['devDependencies'] = dev_deps
    if optional_deps is not None:
        pkg['optionalDependencies'] = optional_deps
    return pkg


def test_license_violation_synthetic():
    policy = dict(BASE_POLICY)
    overrides = {
        'workspace/package.json': _minimal_workspace({'bad-license-lib': '1.0.0'}),
        'workspace/packages/core/package.json': {'name': '@ridge/core', 'version': '1.0.0', 'dependencies': {}},
        'registry/packages.json': {
            'packages': {
                'bad-license-lib': {
                    '1.0.0': {
                        'license': 'GPL-3.0',
                        'integrity': 'sha512-gpl',
                        'tarball': 'https://mirror.local/bad-license-lib-1.0.0.tgz',
                        'dependencies': {}
                    }
                }
            }
        },
        'config/policy.json': policy
    }
    backups = _swap_app_files(overrides)
    try:
        _, plan = run_tool()
        assert plan['policyViolations'] == [{
            'package': 'bad-license-lib',
            'version': '1.0.0',
            'rule': 'license',
            'message': 'license GPL-3.0 is not allowed'
        }]
    finally:
        _restore_app_files(backups)


def test_deprecated_only_unresolved_synthetic():
    overrides = {
        'workspace/package.json': _minimal_workspace({'legacy-only': '^1.0.0'}),
        'workspace/packages/core/package.json': {'name': '@ridge/core', 'version': '1.0.0', 'dependencies': {}},
        'registry/packages.json': {
            'packages': {
                'legacy-only': {
                    '1.0.0': {'license': 'MIT', 'integrity': 'a', 'tarball': 'https://mirror.local/a.tgz', 'deprecated': True, 'dependencies': {}},
                    '1.1.0': {'license': 'MIT', 'integrity': 'b', 'tarball': 'https://mirror.local/b.tgz', 'deprecated': True, 'dependencies': {}}
                }
            }
        },
        'config/policy.json': dict(BASE_POLICY)
    }
    backups = _swap_app_files(overrides)
    try:
        _, plan = run_tool()
        assert plan['packages'] == []
        assert plan['unresolved'][0]['reason'] == 'no compatible version'
    finally:
        _restore_app_files(backups)


def test_resolution_out_of_range_synthetic():
    policy = dict(BASE_POLICY, resolutions={'widget': '2.0.0'})
    overrides = {
        'workspace/package.json': _minimal_workspace({'widget': '^1.0.0'}),
        'workspace/packages/core/package.json': {'name': '@ridge/core', 'version': '1.0.0', 'dependencies': {}},
        'registry/packages.json': {
            'packages': {
                'widget': {
                    '1.0.0': {'license': 'MIT', 'integrity': 'w100', 'tarball': 'https://mirror.local/w100.tgz', 'dependencies': {}},
                    '2.0.0': {'license': 'MIT', 'integrity': 'w200', 'tarball': 'https://mirror.local/w200.tgz', 'dependencies': {}}
                }
            }
        },
        'config/policy.json': policy
    }
    backups = _swap_app_files(overrides)
    try:
        _, plan = run_tool()
        assert plan['unresolved'] == [{
            'name': 'widget',
            'range': '^1.0.0',
            'requestedBy': 'root',
            'reason': 'resolution out of range'
        }]
    finally:
        _restore_app_files(backups)


def test_version_conflict_suffix_synthetic():
    overrides = {
        'workspace/package.json': _minimal_workspace({
            'widget': '^1.0.0',
            'widget-alt': 'npm:widget@^2.0.0'
        }),
        'workspace/packages/core/package.json': {'name': '@ridge/core', 'version': '1.0.0', 'dependencies': {}},
        'registry/packages.json': {
            'packages': {
                'widget': {
                    '1.0.0': {'license': 'MIT', 'integrity': 'w100', 'tarball': 'https://mirror.local/w100.tgz', 'dependencies': {}},
                    '2.0.0': {'license': 'MIT', 'integrity': 'w200', 'tarball': 'https://mirror.local/w200.tgz', 'dependencies': {}}
                }
            }
        },
        'config/policy.json': dict(BASE_POLICY)
    }
    backups = _swap_app_files(overrides)
    try:
        _, plan = run_tool()
        pkgs = by_name(plan)
        assert pkgs['widget']['version'] == '1.0.0'
        assert pkgs['widget-alt']['version'] == '2.0.0'
    finally:
        _restore_app_files(backups)


def test_version_conflict_hash_suffix_synthetic():
    overrides = {
        'workspace/package.json': _minimal_workspace({
            '@ridge/core': 'workspace:*',
            'widget': '^1.0.0'
        }),
        'workspace/packages/core/package.json': {
            'name': '@ridge/core',
            'version': '1.0.0',
            'dependencies': {'widget': '^2.0.0'}
        },
        'registry/packages.json': {
            'packages': {
                'widget': {
                    '1.0.0': {'license': 'MIT', 'integrity': 'w100', 'tarball': 'https://mirror.local/w100.tgz', 'dependencies': {}},
                    '2.0.0': {'license': 'MIT', 'integrity': 'w200', 'tarball': 'https://mirror.local/w200.tgz', 'dependencies': {}}
                }
            }
        },
        'config/policy.json': dict(BASE_POLICY)
    }
    backups = _swap_app_files(overrides)
    try:
        _, plan = run_tool()
        pkgs = by_name(plan)
        assert pkgs['widget']['version'] == '1.0.0'
        assert pkgs['widget#2']['version'] == '2.0.0'
        assert pkgs['widget#2']['package'] == 'widget'
    finally:
        _restore_app_files(backups)


def test_workspace_missing_synthetic():
    overrides = {
        'workspace/package.json': _minimal_workspace({'@ridge/missing': 'workspace:*'}),
        'workspace/packages/core/package.json': {'name': '@ridge/core', 'version': '1.0.0', 'dependencies': {}},
        'registry/packages.json': {'packages': {}},
        'config/policy.json': dict(BASE_POLICY)
    }
    backups = _swap_app_files(overrides)
    try:
        _, plan = run_tool()
        assert plan['unresolved'][0]['reason'] == 'workspace package missing'
    finally:
        _restore_app_files(backups)


def test_peer_range_mismatch_synthetic():
    overrides = {
        'workspace/package.json': _minimal_workspace({'host': '1.0.0', 'peer-lib': '1.0.0'}),
        'workspace/packages/core/package.json': {'name': '@ridge/core', 'version': '1.0.0', 'dependencies': {}},
        'registry/packages.json': {
            'packages': {
                'host': {
                    '1.0.0': {
                        'license': 'MIT',
                        'integrity': 'host',
                        'tarball': 'https://mirror.local/host.tgz',
                        'peerDependencies': {'peer-lib': '^2.0.0'},
                        'dependencies': {}
                    }
                },
                'peer-lib': {
                    '1.0.0': {'license': 'MIT', 'integrity': 'peer', 'tarball': 'https://mirror.local/peer.tgz', 'dependencies': {}}
                }
            }
        },
        'config/policy.json': dict(BASE_POLICY)
    }
    backups = _swap_app_files(overrides)
    try:
        _, plan = run_tool()
        assert plan['peerWarnings'][0]['reason'] == 'peer range mismatch'
    finally:
        _restore_app_files(backups)


def test_patch_integrity_only_on_matching_version():
    policy = dict(BASE_POLICY, patches={'widget': {'version': '1.0.0', 'file': 'p.patch', 'integrity': 'sha512-patched'}})
    overrides = {
        'workspace/package.json': _minimal_workspace({'widget': '^1.0.0'}),
        'workspace/packages/core/package.json': {'name': '@ridge/core', 'version': '1.0.0', 'dependencies': {}},
        'registry/packages.json': {
            'packages': {
                'widget': {
                    '1.0.0': {'license': 'MIT', 'integrity': 'w100', 'tarball': 'https://mirror.local/w100.tgz', 'dependencies': {}},
                    '1.1.0': {'license': 'MIT', 'integrity': 'w110', 'tarball': 'https://mirror.local/w110.tgz', 'dependencies': {}}
                }
            }
        },
        'config/policy.json': policy
    }
    backups = _swap_app_files(overrides)
    try:
        _, plan = run_tool()
        pkgs = by_name(plan)
        assert pkgs['widget']['version'] == '1.1.0'
        assert pkgs['widget']['patched'] is False
        assert pkgs['widget']['integrity'] == 'w110'
    finally:
        _restore_app_files(backups)


def test_prefer_stable_skips_prerelease_synthetic():
    overrides = {
        'workspace/package.json': _minimal_workspace({'widget': '^1.0.0'}),
        'workspace/packages/core/package.json': {'name': '@ridge/core', 'version': '1.0.0', 'dependencies': {}},
        'registry/packages.json': {
            'packages': {
                'widget': {
                    '1.0.0': {'license': 'MIT', 'integrity': 'w100', 'tarball': 'https://mirror.local/w100.tgz', 'dependencies': {}},
                    '1.1.0-rc.1': {'license': 'MIT', 'integrity': 'w110rc', 'tarball': 'https://mirror.local/w110rc.tgz', 'dependencies': {}},
                    '1.1.0': {'license': 'MIT', 'integrity': 'w110', 'tarball': 'https://mirror.local/w110.tgz', 'dependencies': {}}
                }
            }
        },
        'config/policy.json': dict(BASE_POLICY, preferStable=True)
    }
    backups = _swap_app_files(overrides)
    try:
        _, plan = run_tool()
        assert by_name(plan)['widget']['version'] == '1.1.0'
    finally:
        _restore_app_files(backups)


def test_yanked_fallback_when_only_option_synthetic():
    overrides = {
        'workspace/package.json': _minimal_workspace({'widget': '^1.0.0'}),
        'workspace/packages/core/package.json': {'name': '@ridge/core', 'version': '1.0.0', 'dependencies': {}},
        'registry/packages.json': {
            'packages': {
                'widget': {
                    '1.0.0': {'license': 'MIT', 'integrity': 'w100', 'tarball': 'https://mirror.local/w100.tgz', 'yanked': True, 'dependencies': {}}
                }
            }
        },
        'config/policy.json': dict(BASE_POLICY)
    }
    backups = _swap_app_files(overrides)
    try:
        _, plan = run_tool()
        pkgs = by_name(plan)
        assert pkgs['widget']['yanked'] is True
        assert plan['summary']['yankedSelectedCount'] == 1
    finally:
        _restore_app_files(backups)


def test_yanked_deprioritized_when_stable_exists_synthetic():
    overrides = {
        'workspace/package.json': _minimal_workspace({'widget': '^1.0.0'}),
        'workspace/packages/core/package.json': {'name': '@ridge/core', 'version': '1.0.0', 'dependencies': {}},
        'registry/packages.json': {
            'packages': {
                'widget': {
                    '1.0.0': {'license': 'MIT', 'integrity': 'w100', 'tarball': 'https://mirror.local/w100.tgz', 'dependencies': {}},
                    '1.1.0': {'license': 'MIT', 'integrity': 'w110', 'tarball': 'https://mirror.local/w110.tgz', 'yanked': True, 'dependencies': {}}
                }
            }
        },
        'config/policy.json': dict(BASE_POLICY)
    }
    backups = _swap_app_files(overrides)
    try:
        _, plan = run_tool()
        assert by_name(plan)['widget']['version'] == '1.0.0'
        assert plan['summary']['yankedSelectedCount'] == 0
    finally:
        _restore_app_files(backups)


def test_optional_dependencies_respect_policy_flag():
    overrides = {
        'workspace/package.json': _minimal_workspace(
            {},
            optional_deps={'opt-root': '^1.0.0'}
        ),
        'workspace/packages/core/package.json': {
            'name': '@ridge/core',
            'version': '1.0.0',
            'dependencies': {},
            'optionalDependencies': {'opt-ws': '^1.0.0'}
        },
        'registry/packages.json': {
            'packages': {
                'opt-root': {'1.0.0': {'license': 'MIT', 'integrity': 'or', 'tarball': 'https://mirror.local/or.tgz', 'dependencies': {}}},
                'opt-ws': {'1.0.0': {'license': 'MIT', 'integrity': 'ow', 'tarball': 'https://mirror.local/ow.tgz', 'dependencies': {}}},
                'host': {
                    '1.0.0': {
                        'license': 'MIT',
                        'integrity': 'host',
                        'tarball': 'https://mirror.local/host.tgz',
                        'dependencies': {},
                        'optionalDependencies': {'opt-reg': '^1.0.0'}
                    }
                }
            }
        },
        'config/policy.json': dict(BASE_POLICY, includeOptionalDependencies=False)
    }
    overrides['workspace/package.json']['dependencies'] = {'host': '1.0.0'}
    backups = _swap_app_files(overrides)
    try:
        _, plan = run_tool()
        names = set(by_name(plan))
        assert names == {'host'}
    finally:
        _restore_app_files(backups)


def test_optional_dependencies_install_when_enabled():
    policy = dict(BASE_POLICY, includeOptionalDependencies=True)
    overrides = {
        'workspace/package.json': _minimal_workspace({'host': '1.0.0'}),
        'workspace/packages/core/package.json': {'name': '@ridge/core', 'version': '1.0.0', 'dependencies': {}},
        'registry/packages.json': {
            'packages': {
                'host': {
                    '1.0.0': {
                        'license': 'MIT',
                        'integrity': 'host',
                        'tarball': 'https://mirror.local/host.tgz',
                        'dependencies': {},
                        'optionalDependencies': {'opt-reg': '1.0.0'}
                    }
                },
                'opt-reg': {'1.0.0': {'license': 'MIT', 'integrity': 'or', 'tarball': 'https://mirror.local/or.tgz', 'dependencies': {}}}
            }
        },
        'config/policy.json': policy
    }
    backups = _swap_app_files(overrides)
    try:
        _, plan = run_tool()
        assert 'opt-reg' in by_name(plan)
    finally:
        _restore_app_files(backups)


def test_workspace_semver_prefers_local_package():
    overrides = {
        'workspace/package.json': _minimal_workspace({'@ridge/lib': '^1.2.0'}),
        'workspace/packages/core/package.json': {'name': '@ridge/core', 'version': '1.0.0', 'dependencies': {}},
        'workspace/packages/lib/package.json': {'name': '@ridge/lib', 'version': '1.4.0', 'dependencies': {}},
        'registry/packages.json': {
            'packages': {
                '@ridge/lib': {
                    '1.9.0': {'license': 'MIT', 'integrity': 'lib190', 'tarball': 'https://mirror.local/lib190.tgz', 'dependencies': {}}
                }
            }
        },
        'config/policy.json': dict(BASE_POLICY)
    }
    backups = _swap_app_files(overrides)
    try:
        _, plan = run_tool()
        pkgs = by_name(plan)
        assert pkgs['@ridge/lib']['source'] == 'workspace'
        assert pkgs['@ridge/lib']['version'] == '1.4.0'
    finally:
        _restore_app_files(backups)


def test_x_range_hyphen_and_union_synthetic():
    overrides = {
        'workspace/package.json': _minimal_workspace({
            'x-lib': '1.2.x',
            'range-lib': '1.0.0 - 1.2.0',
            'union-lib': '^1.0.0 || ^2.0.0'
        }),
        'workspace/packages/core/package.json': {'name': '@ridge/core', 'version': '1.0.0', 'dependencies': {}},
        'registry/packages.json': {
            'packages': {
                'x-lib': {
                    '1.1.0': {'license': 'MIT', 'integrity': 'x110', 'tarball': 'https://mirror.local/x110.tgz', 'dependencies': {}},
                    '1.2.7': {'license': 'MIT', 'integrity': 'x127', 'tarball': 'https://mirror.local/x127.tgz', 'dependencies': {}},
                    '1.3.0': {'license': 'MIT', 'integrity': 'x130', 'tarball': 'https://mirror.local/x130.tgz', 'dependencies': {}}
                },
                'range-lib': {
                    '1.0.0': {'license': 'MIT', 'integrity': 'r100', 'tarball': 'https://mirror.local/r100.tgz', 'dependencies': {}},
                    '1.2.0': {'license': 'MIT', 'integrity': 'r120', 'tarball': 'https://mirror.local/r120.tgz', 'dependencies': {}},
                    '1.3.0': {'license': 'MIT', 'integrity': 'r130', 'tarball': 'https://mirror.local/r130.tgz', 'dependencies': {}}
                },
                'union-lib': {
                    '1.5.0': {'license': 'MIT', 'integrity': 'u150', 'tarball': 'https://mirror.local/u150.tgz', 'dependencies': {}},
                    '2.1.0': {'license': 'MIT', 'integrity': 'u210', 'tarball': 'https://mirror.local/u210.tgz', 'dependencies': {}}
                }
            }
        },
        'config/policy.json': dict(BASE_POLICY)
    }
    backups = _swap_app_files(overrides)
    try:
        _, plan = run_tool()
        pkgs = by_name(plan)
        assert pkgs['x-lib']['version'] == '1.2.7'
        assert pkgs['range-lib']['version'] == '1.2.0'
        assert pkgs['union-lib']['version'] == '2.1.0'
    finally:
        _restore_app_files(backups)


def test_lock_drift_ignores_workspace_and_missing_entries():
    overrides = {
        'workspace/package.json': _minimal_workspace({'widget': '1.0.0'}),
        'workspace/packages/core/package.json': {'name': '@ridge/core', 'version': '1.0.0', 'dependencies': {}},
        'workspace/package-lock.json': {
            'name': 'ridge-ui',
            'lockfileVersion': 3,
            'packages': {
                '': {'dependencies': {'widget': '1.0.0'}},
                'node_modules/widget': {'version': '0.9.0', 'integrity': 'old'},
                'node_modules/@ridge/core': {'version': '1.0.0', 'integrity': 'ws'}
            }
        },
        'registry/packages.json': {
            'packages': {
                'widget': {'1.0.0': {'license': 'MIT', 'integrity': 'w100', 'tarball': 'https://mirror.local/w100.tgz', 'dependencies': {}}}
            }
        },
        'config/policy.json': dict(BASE_POLICY)
    }
    backups = _swap_app_files(overrides)
    try:
        _, plan = run_tool()
        assert plan['lockDrift'] == [{
            'package': 'widget',
            'lockVersion': '0.9.0',
            'plannedVersion': '1.0.0',
            'lockIntegrity': 'old',
            'plannedIntegrity': 'w100'
        }]
    finally:
        _restore_app_files(backups)


def test_lock_drift_includes_scoped_registry_entries():
    policy = dict(BASE_POLICY, includeDevDependencies=True)
    overrides = {
        'workspace/package.json': _minimal_workspace({}, dev_deps={'@types/node': '^20.0.0'}),
        'workspace/packages/core/package.json': {'name': '@ridge/core', 'version': '1.0.0', 'dependencies': {}},
        'workspace/package-lock.json': {
            'name': 'ridge-ui',
            'lockfileVersion': 3,
            'packages': {
                '': {'devDependencies': {'@types/node': '^20.0.0'}},
                'node_modules/@types/node': {'version': '20.0.0', 'integrity': 'old-types'}
            }
        },
        'registry/packages.json': {
            'packages': {
                '@types/node': {
                    '20.11.30': {
                        'license': 'MIT',
                        'integrity': 'sha512-types201130',
                        'tarball': 'https://mirror.local/@types/node/-/node-20.11.30.tgz',
                        'dependencies': {}
                    }
                }
            }
        },
        'config/policy.json': policy
    }
    backups = _swap_app_files(overrides)
    try:
        _, plan = run_tool()
        assert plan['lockDrift'] == [{
            'package': '@types/node',
            'lockVersion': '20.0.0',
            'plannedVersion': '20.11.30',
            'lockIntegrity': 'old-types',
            'plannedIntegrity': 'sha512-types201130'
        }]
    finally:
        _restore_app_files(backups)
