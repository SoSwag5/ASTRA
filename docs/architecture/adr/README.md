# Architecture decision records

ADRs capture material decisions and their security and operational consequences.
Use [ADR_TEMPLATE.md](ADR_TEMPLATE.md). Number records sequentially and keep
superseded records; change their status and link the replacement.

## Status values

`Proposed`, `Accepted`, `Rejected`, `Deprecated`, or `Superseded by ADR-NNNN`.
A reconstructed record remains Proposed until the Owner confirms that it
accurately represents the intended decision. Implementation is evidence of the
current design, not proof of a historical approval conversation.

## ADR triggers

Create or update an ADR for changes to:

- trust boundaries, identity, authentication, authorization, or tenancy;
- deployment topology, network exposure, hosting, or cloud providers;
- persistence, data formats, migration, backup, deletion, or privacy boundaries;
- secrets, credentials, encryption, signing, or key management;
- release integrity, build platform, update channel, provenance, or supply chain;
- material operational ownership, availability, observability, or incident
  response architecture.

## Initial register

| ID | Decision | Status |
|---|---|---|
| [ADR-0001](0001-local-first-architecture.md) | Local-first single-user architecture | Proposed, reconstructed; Owner confirmation required |
| [ADR-0002](0002-os-account-loopback-trust-boundary.md) | OS-account and localhost trust boundary | Accepted; existing Owner risk decision R-15 |
| [ADR-0003](0003-access-key-session-exchange.md) | Access key exchanged for expiring server-side session | Proposed, reconstructed; Owner confirmation required |
| [ADR-0004](0004-build-once-verify-same-artifact.md) | Build once and verify the same artifact | Proposed, reconstructed; Owner confirmation required |
| [ADR-0005](0005-cyclonedx-1-7-sbom.md) | CycloneDX 1.7 release SBOM | Proposed, reconstructed; Owner confirmation required |
| [ADR-0006](0006-hosted-provenance.md) | Hosted provenance and independent verification | Proposed; execution evidence required |
