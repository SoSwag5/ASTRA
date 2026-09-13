# ADR-0004: Build once and verify the same release artifact

- **Status:** Accepted
- **Date:** 2026-09-13
- **Owner:** Ayham
- **Issue / pull request:** [PR #28](https://github.com/SoSwag5/ASTRA/pull/28)
- **Owner approval:** Approved 2026-09-13
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
source change invalidates the affected evidence. The Owner approved this
decision on 2026-09-13.

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

`.github/workflows/release.yml`, `.github/workflows/review-candidate.yml`, and the
build/verification scripts implemented the design. Run 34722561421 built and
attested the candidate from released source `81ad2d3`; run 34732173819 reviewed
the same artifact with SHA-256 `a5842744…b4399f` and produced the final successful
gate. Execution evidence remains release-specific. The Owner confirmed this ADR
on 2026-09-13.

## Framework impact

Supports SSDF release integrity and SLSA provenance requirements; no SLSA Build
level follows from workflow configuration alone.
