# ADR-0004: Build once and verify the same release artifact

- **Status:** Proposed (reconstructed; Owner confirmation required)
- **Date:** 2026-09-13
- **Owner:** Ayham
- **Issue / pull request:** Governance v1 branch
- **Target release:** v1.0
- **Supersedes / superseded by:** None

## Context and problem

Rebuilding for later checks can produce a different artifact and break the chain
between reviewed source, tests, SBOM, installation, provenance, and publication.

## Options considered

1. Rebuild independently for each assurance stage.
2. Build once from a frozen source SHA and pass the same immutable artifact and
   digest through all release checks.
3. Build locally and upload without hosted identity or independent verification.

## Decision

Freeze the source, build one candidate on the approved hosted workflow, calculate
its digest, and reuse that artifact for manifest, SBOM association, clean-install,
attestation, independent verification, review, and publication. Any artifact or
source change invalidates the affected evidence. Owner confirmation is required.

## Rationale

This preserves traceability and prevents a reviewed artifact from being replaced
by an unreviewed rebuild.

## Security and privacy impact

The workflow must use least privilege, immutable action pins, hash-locked
dependencies, publication scanning, and trusted artifact transfer. Digests and
attestations must bind to the exact subject.

## Operational impact

Failed downstream verification requires a new candidate and new evidence rather
than an in-place artifact edit.

## Tradeoffs and residual risk

Hosted platform trust and dependency compromise remain. A digest proves identity,
not safety. The workflow must be executed and reviewed before any claim.

## Evidence and validation

`.github/workflows/release.yml`, `.github/workflows/review-candidate.yml`, build
scripts, and the exact hosted run/evidence pack. Execution evidence remains
release-specific.

## Framework impact

Supports SSDF release integrity and SLSA provenance requirements; no SLSA Build
level follows from workflow configuration alone.
