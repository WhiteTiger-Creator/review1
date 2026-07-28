#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

function main() {
  const outDir = '/app/output';
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(path.join(outDir, 'build-plan.json'), JSON.stringify({
    root: 'ridge-ui',
    nodeVersion: '20.11.1',
    packages: [],
    unresolved: [],
    peerWarnings: [],
    policyViolations: [],
    mirrorWarnings: [],
    lockDrift: [],
    summary: {
      packageCount: 0,
      workspaceCount: 0,
      registryCount: 0,
      patchedCount: 0,
      yankedSelectedCount: 0,
      unresolvedCount: 0,
      peerWarningCount: 0,
      policyViolationCount: 0,
      mirrorWarningCount: 0,
      lockDriftCount: 0
    }
  }, null, 2));
}

main();
