# Beta 1 evidence and publication boundary

This source record accompanies release preparation on 2026-10-02. It does not
claim that a workflow has executed merely because it is configured. The release
page and its attached reports are authoritative for the final source SHA, artifact
digest, hosted outcomes and publication state; those cannot be embedded in their
own source commit without changing the candidate.

## Inherited, dated evidence

- #47 visual/motion candidate: `772fe7e87586720d9db6bed06cb1a12d3af14649`;
  [browser and interaction record](../architecture/VISUAL_MOTION_VALIDATION.md).
  Its prior browser review is inherited evidence, not a fresh beta artifact test.
- Corrected #48 record: `25d91e774915867d94db07de26b622f29e842791`.
  At its code snapshot `90e48ea76620ff1d876fb2907bb194b4c219916d`, 2,118
  Python tests passed and one existing test was intentionally skipped. That
  snapshot remained blocked by six pypdf 6.18.0 advisories.

## Beta preparation evidence

- Python lock changed pypdf to 6.19.0; all 47 exact product versions were
  hash-installed into a fresh environment. Strict pip-audit returned no known
  vulnerabilities on the updated lock, without suppressions, on 2026-10-02.
- Eleven frontend test scripts, TypeScript and production build passed. npm
  audit returned zero advisories. Vite reported that an access module also
  imported statically cannot be split into a separate dynamic chunk.
- New cross-major checks use fictional text PDFs, isolated databases and data
  directories, blocked outbound network helpers and no live Gmail/AI/discovery.
- An initial targeted run failed on denied default temporary-folder access.
  A second run exposed a test assertion using `text` instead of the planner's
  actual `query` field. Both failures are retained in Owner-local QA; the corrected
  run uses a dedicated temporary directory: **64 passed in 30.71 seconds**.
  No failed run is relabelled as PASS.
- The first complete beta-content run returned 2,159 passes, one existing skip,
  three failures and twelve errors. One failure correctly rejected unpublished
  personal commit metadata; a separate public candidate now uses no-reply identity.
  The other failures/errors caught the public fictional #42 evaluation manifest's
  stale dependency-lock hash after pypdf remediation. Only that lock hash was
  refreshed; the other 17 inputs, labels, policies and recipe remained unchanged.
  The report was regenerated and provenance-verified, with all substantive
  results unchanged. The private #46.2-C evaluation is untouched. A fresh complete
  run and hosted checks are required for the corrected candidate.

Fresh complete tests, packaged installation, CodeQL triage, dependency review,
repository controls, SBOM validation and hosted attestation verification are
required before publication. The pipeline builds a candidate once, then reviews
that same digest through Review Existing Candidate. It must fail closed if the
source/artifact-bound maintainer review or a required result is missing.

Codex owns this release integration by explicit Owner instruction. Self-verification
of new changes is not independent assurance. The post-release cloud review is
requested separately and remains pending until actually performed.

## Scope that remains open

The beta permission in OD-013 does not make final v1.1 requirements complete.
Two-account Gmail validation, live matching accuracy, R-16/17/18 Owner decisions,
a brother-PC test and broad career-quality evaluation remain open. Do not close
issue #48's final-release scope based solely on publishing this prerelease.

The ZIP contains no virtual environment, private records, credentials or Git
history. Installation fetches hash-checked dependencies; Python itself is not
bundled. Recommend the patched Python 3.13.16 interpreter. Local reference tests
use Python 3.13.2; hosted runtime versions must be read from actual job logs.
