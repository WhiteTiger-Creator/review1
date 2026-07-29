# Toolchain

Build with `/app/environment/ci/build.sh` (Make + gcc). Binary: `/app/bin/percctl`.

```bash
bash /app/environment/ci/build.sh
bash /app/environment/ci/rebuild.sh
/app/bin/percctl cycle /app/environment/fixtures/suite.json
/app/bin/percctl cycle /app/environment/fixtures/resume.json
/app/bin/percctl resume-probe
```

Manifest: `/app/environment/fixtures/manifest.json`
Cases: `/app/environment/fixtures/cases/examples.json`
Suite: `/app/environment/fixtures/suite.json`
Resume suite: `/app/environment/fixtures/resume.json`
Image snapshot: `/opt/verifier-fixtures/environment`
Verifier scratch suites may be written under `/app/output/`.

Scratch verifier suites: `/app/output/fold_only.json`, `/app/output/tear_only.json`.

Ledger emit lives in `/app/environment/drv/emit.c`; the verifier may temporarily
stub that path while checking that hand-written JSON cannot satisfy the suite.
Verifier poison generation value 7 appears only in anti-static checks.
