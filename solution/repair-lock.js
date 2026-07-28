#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const { URL } = require('url');

const ROOT = '/app';
const workspaceDir = path.join(ROOT, 'workspace');

function readJson(p) {
  return JSON.parse(fs.readFileSync(p, 'utf8'));
}

function sortedEntries(obj) {
  return Object.entries(obj || {}).sort(([a], [b]) => a.localeCompare(b));
}

function splitVersion(v) {
  const s = String(v);
  const hyphen = s.indexOf('-');
  const core = hyphen === -1 ? s : s.slice(0, hyphen);
  const pre = hyphen === -1 ? null : s.slice(hyphen + 1);
  const parts = core.split('.').map((n) => parseInt(n, 10));
  while (parts.length < 3) parts.push(0);
  return { parts, pre, raw: s };
}

function cmpVer(a, b) {
  const aa = splitVersion(a);
  const bb = splitVersion(b);
  for (let i = 0; i < 3; i += 1) {
    if (aa.parts[i] !== bb.parts[i]) return aa.parts[i] - bb.parts[i];
  }
  if (aa.pre === null && bb.pre === null) return 0;
  if (aa.pre === null) return 1;
  if (bb.pre === null) return -1;
  return aa.pre < bb.pre ? -1 : aa.pre > bb.pre ? 1 : 0;
}

function checkComparator(version, op, rhs) {
  const c = cmpVer(version, rhs);
  if (op === '>=') return c >= 0;
  if (op === '>') return c > 0;
  if (op === '<=') return c <= 0;
  if (op === '<') return c < 0;
  if (op === '=') return c === 0;
  return false;
}

function prereleaseAllowed(version, comparatorVersion) {
  const v = splitVersion(version);
  if (v.pre === null) return true;
  if (!comparatorVersion) return false;
  const c = splitVersion(comparatorVersion);
  if (c.pre === null) return false;
  return v.parts[0] === c.parts[0] && v.parts[1] === c.parts[1] && v.parts[2] === c.parts[2];
}

function expandXRange(range) {
  if (/^\d+\.x$/i.test(range)) {
    const maj = parseInt(range.split('.')[0], 10);
    return [`>=${maj}.0.0`, `<${maj + 1}.0.0`];
  }
  if (/^\d+\.\d+\.x$/i.test(range)) {
    const [maj, min] = range.split('.').map((n) => parseInt(n, 10));
    return [`>=${maj}.${min}.0`, `<${maj}.${min + 1}.0`];
  }
  return null;
}

function satisfiesSingle(version, range) {
  range = String(range).trim();
  if (!range || range === '*') return true;
  if (range.startsWith('workspace:')) return true;
  if (/^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$/.test(range)) return version === range;

  const x = expandXRange(range);
  if (x) {
    return x.every((c) => {
      const m = c.match(/^(>=|>|<=|<)(\d+\.\d+\.\d+)$/);
      return m && checkComparator(version, m[1], m[2]) && prereleaseAllowed(version, m[2]);
    });
  }

  if (range.startsWith('^')) {
    const base = range.slice(1);
    const [maj, min, patch] = splitVersion(base).parts;
    let upper;
    if (maj > 0) upper = `${maj + 1}.0.0`;
    else if (min > 0) upper = `0.${min + 1}.0`;
    else upper = `0.0.${patch + 1}`;
    return checkComparator(version, '>=', base) && checkComparator(version, '<', upper) && prereleaseAllowed(version, base);
  }

  if (range.startsWith('~')) {
    const base = range.slice(1);
    const [maj, min] = splitVersion(base).parts;
    return checkComparator(version, '>=', base) && checkComparator(version, '<', `${maj}.${min + 1}.0`) && prereleaseAllowed(version, base);
  }

  if (range.includes(' - ')) {
    const [left, right] = range.split(' - ').map((s) => s.trim());
    return checkComparator(version, '>=', left) && checkComparator(version, '<=', right) && prereleaseAllowed(version, left);
  }

  const comps = range.split(/\s+/).filter(Boolean);
  if (comps.length && comps.every((c) => /^(>=|>|<=|<|=)\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$/.test(c))) {
    return comps.every((c) => {
      const m = c.match(/^(>=|>|<=|<|=)(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)$/);
      return m && checkComparator(version, m[1], m[2]) && prereleaseAllowed(version, m[2]);
    });
  }

  return false;
}

function satisfies(version, range) {
  if (!range || range === '*') return true;
  range = String(range).trim();
  if (range.startsWith('workspace:')) return true;
  return range.split('||').map((s) => s.trim()).filter(Boolean).some((alt) => satisfiesSingle(version, alt));
}

function parseAlias(spec) {
  const m = /^npm:([^@]+(?:\/[^@]+)?|@[^/]+\/[^@]+)@(.+)$/.exec(spec);
  return m ? { real: m[1], range: m[2] } : null;
}

function engineOk(expr, node) {
  if (!expr) return true;
  return expr.split(/\s+/).filter(Boolean).every((part) => {
    if (part.startsWith('>=')) return cmpVer(node, part.slice(2)) >= 0;
    if (part.startsWith('<')) return cmpVer(node, part.slice(1)) < 0;
    return true;
  });
}

function hostOf(url) {
  try {
    return new URL(url).host;
  } catch {
    return '';
  }
}

function preferenceClass(meta) {
  const dep = !!meta.deprecated;
  const yank = !!meta.yanked;
  if (!dep && !yank) return 0;
  if (dep && !yank) return 1;
  if (!dep && yank) return 2;
  return 3;
}

function pickVersion(versionsMap, range, preferStable, nodeVersion) {
  const satisfying = Object.entries(versionsMap).filter(
    ([v, meta]) => satisfies(v, range) && !meta.deprecated && engineOk(meta.engines && meta.engines.node, nodeVersion)
  );
  if (!satisfying.length) return null;
  satisfying.sort(([a, ma], [b, mb]) => {
    const ca = preferenceClass(ma);
    const cb = preferenceClass(mb);
    if (ca !== cb) return ca - cb;
    if (preferStable) {
      const pa = splitVersion(a).pre === null ? 0 : 1;
      const pb = splitVersion(b).pre === null ? 0 : 1;
      if (pa !== pb) return pa - pb;
    }
    return cmpVer(b, a);
  });
  return satisfying[0];
}

function workspaceRangeToReal(range, localVersion) {
  if (!range.startsWith('workspace:')) return range;
  const token = range.slice('workspace:'.length);
  if (token === '*' || token === '') return '*';
  if (token === '^') return `^${localVersion}`;
  if (token === '~') return `~${localVersion}`;
  return token;
}

function shouldSkipOs(registry, depName, buildHost) {
  const depMeta = registry[depName] || {};
  const versions = Object.values(depMeta);
  if (!versions.length) return false;
  return versions.every((m) => Array.isArray(m.os) && m.os.length > 0 && !m.os.includes(buildHost));
}

function loadWorkspaces() {
  const out = new Map();
  const base = path.join(workspaceDir, 'packages');
  if (!fs.existsSync(base)) return out;
  for (const dir of fs.readdirSync(base).sort()) {
    const p = path.join(base, dir, 'package.json');
    if (fs.existsSync(p)) {
      const pkg = readJson(p);
      out.set(pkg.name, { ...pkg, dir, peerDependenciesMeta: pkg.peerDependenciesMeta || {} });
    }
  }
  return out;
}

function lockDriftEntries(lock, selectedByName) {
  const drift = [];
  for (const [key, meta] of Object.entries(lock.packages || {})) {
    if (!key.startsWith('node_modules/')) continue;
    const rel = key.slice('node_modules/'.length);
    if (!rel || rel.includes('node_modules/')) continue;
    const lockName = rel.startsWith('@') ? rel : rel.includes('/') ? null : rel;
    if (!lockName || !meta.version) continue;
    const planned = selectedByName.get(lockName);
    if (!planned || planned.source !== 'registry') continue;
    if (planned.version === meta.version) continue;
    drift.push({
      package: lockName,
      lockVersion: meta.version,
      plannedVersion: planned.version,
      lockIntegrity: meta.integrity || null,
      plannedIntegrity: planned.integrity,
    });
  }
  drift.sort((a, b) => a.package.localeCompare(b.package));
  return drift;
}

function main() {
  const rootPkg = readJson(path.join(workspaceDir, 'package.json'));
  const lock = readJson(path.join(workspaceDir, 'package-lock.json'));
  const policy = readJson(path.join(ROOT, 'config/policy.json'));
  const registry = readJson(path.join(ROOT, 'registry/packages.json')).packages;
  const workspaces = loadWorkspaces();
  const requests = [];
  const selected = [];
  const unresolved = [];
  const peerWarnings = [];
  const policyViolations = [];
  const mirrorWarnings = [];
  const peerMetaByPackage = new Map();

  function rememberPeerMeta(pkgName, meta) {
    if (!meta || !Object.keys(meta).length) return;
    const existing = peerMetaByPackage.get(pkgName) || {};
    peerMetaByPackage.set(pkgName, { ...existing, ...meta });
  }

  function effectiveRange(real, rawRange) {
    return policy.overrides && policy.overrides[real] ? policy.overrides[real] : rawRange;
  }

  function addRequest(outputName, spec, requestedBy) {
    const alias = parseAlias(spec);
    const real = alias ? alias.real : outputName;
    const rawRange = alias ? alias.range : spec;
    const range = effectiveRange(real, rawRange);
    requests.push({ outputName, real, range, rawRange, requestedBy, alias: !!alias, spec });
  }

  function walkDeps(manifest, requestedBy, includeOptional) {
    for (const [n, s] of sortedEntries(manifest.dependencies)) addRequest(n, s, requestedBy);
    if (includeOptional) {
      for (const [n, s] of sortedEntries(manifest.optionalDependencies)) addRequest(n, s, requestedBy);
    }
  }

  walkDeps(rootPkg, 'root', policy.includeOptionalDependencies);
  if (policy.includeDevDependencies) {
    for (const [n, s] of sortedEntries(rootPkg.devDependencies)) addRequest(n, s, 'root');
  }

  function findExisting(req) {
    if (req.alias) return null;
    return selected.find((p) => p.name === req.real && p.package === req.real && satisfies(p.version, req.range));
  }

  function nextConflictName(base) {
    if (!selected.some((p) => p.name === base)) return base;
    let i = 2;
    while (selected.some((p) => p.name === `${base}#${i}`)) i += 1;
    return `${base}#${i}`;
  }

  function selectRegistry(req) {
    if ((policy.blockedPackages || []).includes(req.real)) {
      unresolved.push({ name: req.outputName, range: req.rawRange, requestedBy: req.requestedBy, reason: 'blocked by policy' });
      return null;
    }

    const versions = registry[req.real] || {};
    let version;
    let meta;

    if (!(policy.overrides && policy.overrides[req.real]) && policy.resolutions && policy.resolutions[req.real] !== undefined) {
      const pin = policy.resolutions[req.real];
      meta = versions[pin];
      if (!meta || meta.deprecated || !satisfies(pin, req.range) || !engineOk(meta.engines && meta.engines.node, policy.nodeVersion)) {
        unresolved.push({ name: req.outputName, range: req.rawRange, requestedBy: req.requestedBy, reason: 'resolution out of range' });
        return null;
      }
      version = pin;
    } else {
      const picked = pickVersion(versions, req.range, !!policy.preferStable, policy.nodeVersion);
      if (!picked) {
        unresolved.push({ name: req.outputName, range: req.rawRange, requestedBy: req.requestedBy, reason: 'no compatible version' });
        return null;
      }
      [version, meta] = picked;
    }

    const outName = req.alias ? req.outputName : nextConflictName(req.real);
    const patch = policy.patches && policy.patches[req.real];
    const patched = !!(patch && patch.version === version);
    const pkg = {
      name: outName,
      package: req.real,
      version,
      source: 'registry',
      requestedBy: [req.requestedBy],
      license: meta.license ?? null,
      integrity: patched && patch.integrity ? patch.integrity : meta.integrity ?? null,
      tarball: meta.tarball ?? null,
      patched,
      yanked: !!meta.yanked,
      dependencies: meta.dependencies || {},
      optionalDependencies: meta.optionalDependencies || {},
      peerDependencies: meta.peerDependencies || {},
      peerDependenciesMeta: meta.peerDependenciesMeta || {},
    };
    selected.push(pkg);
    rememberPeerMeta(req.real, pkg.peerDependenciesMeta);

    if (meta.license && !(policy.licenseAllowlist || []).includes(meta.license)) {
      policyViolations.push({ package: req.real, version, rule: 'license', message: `license ${meta.license} is not allowed` });
    }
    if (meta.tarball && hostOf(meta.tarball) !== policy.expectedIntegrityHost) {
      mirrorWarnings.push({ package: req.real, version, tarball: meta.tarball, expectedHost: policy.expectedIntegrityHost });
    }

    for (const [dep, spec] of sortedEntries(meta.dependencies)) {
      if (shouldSkipOs(registry, dep, policy.buildHost)) continue;
      addRequest(dep, spec, outName);
    }
    if (policy.includeOptionalDependencies) {
      for (const [dep, spec] of sortedEntries(meta.optionalDependencies)) {
        if (shouldSkipOs(registry, dep, policy.buildHost)) continue;
        addRequest(dep, spec, outName);
      }
    }

    return pkg;
  }

  for (let idx = 0; idx < requests.length; idx += 1) {
    const req = requests[idx];

    if (req.spec.startsWith('workspace:') || (workspaces.has(req.real) && !req.alias && satisfies(workspaces.get(req.real).version, req.range))) {
      const wp = workspaces.get(req.real);
      if (!wp) {
        unresolved.push({ name: req.outputName, range: req.rawRange, requestedBy: req.requestedBy, reason: 'workspace package missing' });
        continue;
      }
      const expanded = req.spec.startsWith('workspace:') ? workspaceRangeToReal(req.spec, wp.version) : req.range;
      if (!satisfies(wp.version, expanded)) {
        unresolved.push({ name: req.outputName, range: req.rawRange, requestedBy: req.requestedBy, reason: 'no compatible version' });
        continue;
      }
      const existing = selected.find((p) => p.name === req.real && p.source === 'workspace');
      if (existing) {
        if (!existing.requestedBy.includes(req.requestedBy)) existing.requestedBy.push(req.requestedBy);
        continue;
      }
      const pkg = {
        name: req.real,
        package: req.real,
        version: wp.version,
        source: 'workspace',
        requestedBy: [req.requestedBy],
        license: wp.license ?? null,
        integrity: null,
        tarball: null,
        patched: false,
        yanked: false,
        dependencies: wp.dependencies || {},
        optionalDependencies: wp.optionalDependencies || {},
        peerDependencies: wp.peerDependencies || {},
        peerDependenciesMeta: wp.peerDependenciesMeta || {},
      };
      selected.push(pkg);
      rememberPeerMeta(req.real, pkg.peerDependenciesMeta);
      if (pkg.license && !(policy.licenseAllowlist || []).includes(pkg.license)) {
        policyViolations.push({ package: pkg.package, version: pkg.version, rule: 'license', message: `license ${pkg.license} is not allowed` });
      }
      walkDeps(wp, pkg.name, policy.includeOptionalDependencies);
      continue;
    }

    const existing = findExisting(req);
    if (existing) {
      if (!existing.requestedBy.includes(req.requestedBy)) existing.requestedBy.push(req.requestedBy);
      continue;
    }
    selectRegistry(req);
  }

  const foundByPkg = new Map();
  for (const p of selected) {
    if (!foundByPkg.has(p.package)) foundByPkg.set(p.package, p.version);
  }

  for (const p of selected) {
    const meta = peerMetaByPackage.get(p.package) || p.peerDependenciesMeta || {};
    for (const [peer, range] of sortedEntries(p.peerDependencies)) {
      if (meta[peer] && meta[peer].optional) continue;
      const found = foundByPkg.get(peer) || null;
      if (!found || !satisfies(found, range)) {
        peerWarnings.push({
          package: p.package,
          peer,
          requested: range,
          found,
          reason: found ? 'peer range mismatch' : 'missing peer dependency',
        });
      }
    }
  }

  for (const p of selected) p.requestedBy.sort();
  selected.sort((a, b) => a.name.localeCompare(b.name));
  unresolved.sort((a, b) => a.name.localeCompare(b.name) || a.requestedBy.localeCompare(b.requestedBy) || a.range.localeCompare(b.range));
  peerWarnings.sort((a, b) => a.package.localeCompare(b.package) || a.peer.localeCompare(b.peer) || a.requested.localeCompare(b.requested));
  policyViolations.sort((a, b) => a.package.localeCompare(b.package) || a.rule.localeCompare(b.rule));
  mirrorWarnings.sort((a, b) => a.package.localeCompare(b.package) || cmpVer(a.version, b.version));

  const packages = selected.map(({ dependencies, optionalDependencies, peerDependencies, peerDependenciesMeta, ...p }) => p);
  const selectedByName = new Map(packages.map((p) => [p.name, p]));
  const lockDrift = lockDriftEntries(lock, selectedByName);
  const summary = {
    packageCount: packages.length,
    workspaceCount: packages.filter((p) => p.source === 'workspace').length,
    registryCount: packages.filter((p) => p.source === 'registry').length,
    patchedCount: packages.filter((p) => p.patched).length,
    yankedSelectedCount: packages.filter((p) => p.yanked).length,
    unresolvedCount: unresolved.length,
    peerWarningCount: peerWarnings.length,
    policyViolationCount: policyViolations.length,
    mirrorWarningCount: mirrorWarnings.length,
    lockDriftCount: lockDrift.length,
  };

  const plan = {
    root: rootPkg.name,
    nodeVersion: policy.nodeVersion,
    packages,
    unresolved,
    peerWarnings,
    policyViolations,
    mirrorWarnings,
    lockDrift,
    summary,
  };

  fs.mkdirSync(path.join(ROOT, 'output'), { recursive: true });
  fs.writeFileSync(path.join(ROOT, 'output', 'build-plan.json'), JSON.stringify(plan, null, 2));
}

main();
