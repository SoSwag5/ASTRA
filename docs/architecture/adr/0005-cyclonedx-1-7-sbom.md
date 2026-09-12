# ADR-0005: CycloneDX 1.7 release SBOM

- **Status:** Proposed (reconstructed; Owner confirmation required)
- **Date:** 2026-09-13
- **Owner:** Ayham
- **Issue / pull request:** Governance v1 branch
- **Target release:** v1.0
- **Supersedes / superseded by:** None

## Context and problem

ASTRA needs a machine-readable inventory covering its locked Python environment
and npm dependency graph, with strict validation and a digest bound to a release.

## Options considered

1. Maintain a prose dependency list.
2. Generate and schema-validate a CycloneDX 1.7 JSON SBOM.
3. Generate another SBOM format or an unvalidated dependency export.

## Decision

Generate a CycloneDX 1.7 JSON SBOM from locked dependencies, validate its schema
and graph, record generator/validator versions and SHA-256, and bind the result to
the exact candidate artifact. Owner confirmation is required.

## Rationale

CycloneDX supplies a structured, versioned format that current ASTRA tooling
already generates and validates across both ecosystems.

## Security and privacy impact

The SBOM supports component review and vulnerability response. It must exclude
credentials and private paths. Completeness is limited to the generator's inputs
and must be checked rather than assumed.

## Operational impact

Dependency changes require regeneration, validation, digest update, and review
of licenses, advisories, and unexpected components.

## Tradeoffs and residual risk

Schema validity does not prove component completeness, absence of malicious
packages, or absence of vulnerabilities.

## Evidence and validation

`scripts/generate_sbom.py`, `scripts/validate_sbom.py`, `docs/security/SBOM.md`,
the release SBOM, validation output, component count, tool versions, and digest.

## Framework impact

Supports SSDF component/provenance practices and the qualified claim “release
SBOM generated and validated as CycloneDX 1.7” for the evidenced release.
