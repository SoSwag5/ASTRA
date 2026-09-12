# ASTRA product and assurance roadmap

The roadmap communicates direction rather than a release promise. Scope and
timing remain Owner decisions. Open 8-15 meaningful issues when a milestone
starts; do not pre-create a large speculative backlog.

## v1.0 — secure local-first release

- Complete the local-first product baseline and preserve manual final submission.
- Close the evidence-backed Secure SDLC, AppSec, privacy, dependency, SBOM,
  provenance, clean-install, and release assurance gates.
- Publish only after the exact candidate passes the fail-closed gate and the
  Owner approves the exact source and artifact.

## v1.1 — operational security and resilience

- Improve recovery, backup validation, diagnostics, resource controls, and
  security-event coverage.
- Exercise incident response and recovery paths using synthetic data.
- Reassess open ASVS L2 and SAMM roadmap items affected by the work.

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
