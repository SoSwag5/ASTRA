# ASTRA product and assurance roadmap

The roadmap communicates direction rather than a release promise. Scope and
timing remain Owner decisions. Open 8-15 meaningful issues when a milestone
starts; do not pre-create a large speculative backlog.

## v1.0 — secure local-first release — RELEASED

- Released as immutable `v1.0.0` from source `81ad2d3` on 2026-09-13.
- Preserves the local-first product boundary and manual final submission.
- Final gate: APPROVED WITH DOCUMENTED RESIDUAL RISK, zero blockers; hosted
  provenance and CycloneDX 1.7 SBOM attestations verified.
- Post-release documentation/governance debt is tracked in issues #24-#27 and
  does not change the frozen release.

## v1.1 — Operational Security & Resilience — NEXT, NOT STARTED

v1.1 begins only after Owner approval and merge of Release Governance v1. When
the milestone starts, select 8-15 meaningful issues with explicit owners and
acceptance criteria; do not treat existing local experiments as milestone work.

- Improve recovery, backup validation, diagnostics, resource controls, and
  security-event coverage.
- Exercise incident response and recovery paths using synthetic data.
- Reassess open ASVS L2 and SAMM roadmap items affected by the work.
- Triage R-12, R-13, R-14, scheduled-task migration, and post-release issues
  #24-#27 into the milestone or a preceding documentation patch as appropriate.

## v1.2 — professional distribution and upgrade lifecycle

- Design signed installation, upgrade, rollback, migration, and uninstall paths.
- Validate upgrades from supported versions on clean Windows environments.
- Define update-channel integrity and support boundaries before implementation.

## v1.5 — AWS reference architecture

- Produce an Owner-approved AWS reference architecture and Infrastructure as
  Code with explicit identity, secrets, network, logging, backup, cost, and
  observability boundaries.
- Keep the local-first edition supported; a reference architecture is not a
  production-hosting claim.

## v2.0 — identity, authorization, and multi-user operation

- Introduce application identities, authorization, tenant boundaries, and data
  isolation only through approved ADRs and a full threat-model update.
- Reopen R-15 and every ASVS control previously scoped N/A because v1.0 was
  single-user and local-only.
- Provide compatibility and data-migration guidance for the new trust model.

## v2.1 and later — production security maturity

- Strengthen operational monitoring, vulnerability response, resilience,
  independent assurance, and measurable SAMM practices using real evidence.
- Reassess SSDF, ASVS, SAMM, CycloneDX, and SLSA claims for each material change.
