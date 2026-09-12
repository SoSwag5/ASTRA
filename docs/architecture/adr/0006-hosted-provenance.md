# ADR-0006: Hosted provenance with independent verification

- **Status:** Proposed
- **Date:** 2026-09-13
- **Owner:** Ayham
- **Issue / pull request:** Governance v1 branch
- **Target release:** v1.0
- **Supersedes / superseded by:** None

## Context and problem

Users and reviewers need evidence connecting an ASTRA artifact to its source and
hosted build identity without relying on a maintainer-held signing key or a prose
statement.

## Options considered

1. Publish checksums only.
2. Produce GitHub-hosted artifact and SBOM attestations, then verify them
   independently against repository, workflow, source, and subject digest.
3. Use a locally held signing key and self-reported build record.

## Decision

Use the SHA-pinned GitHub hosted release workflow to build and attest the artifact
and SBOM. A separate verification stage and release reviewer must validate the
attestations against the repository, signer workflow, source SHA, predicate type,
and artifact digest. This remains Proposed until Owner confirmation and actual
execution evidence exist.

## Rationale

Hosted identity and independent consumer verification strengthen traceability
and avoid a long-lived project signing key in the repository workflow.

## Security and privacy impact

Workflow permissions must remain least privilege. Pull requests must not receive
release credentials or attestation permissions. Published attestations and
metadata must pass privacy review.

## Operational impact

Release evidence includes immutable run URLs, downloaded verification output,
attestation identity, source SHA, artifact digest, and SBOM predicate result.
Platform or workflow changes require reassessment.

## Tradeoffs and residual risk

The design relies on the hosted platform, Actions supply chain, and correct
predicate interpretation. A valid signature does not prove the software is safe.

## Evidence and validation

`.github/workflows/release.yml`, `.github/workflows/review-candidate.yml`,
`docs/security/SLSA_V1.2_ASSESSMENT.md`, and future exact-run verification. A
prepared workflow is not executed provenance.

## Framework impact

Supports a conservative SLSA v1.2 assessment. Do not claim a SLSA Build level
until every requirement for that level is examined and evidenced for the exact
release.
