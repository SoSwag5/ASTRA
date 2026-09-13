# Architecture decision records

ADRs capture material decisions and their security and operational consequences.
Use [ADR_TEMPLATE.md](ADR_TEMPLATE.md). Number records sequentially and keep
superseded records; change their status and link the replacement.

## Status values

`Proposed`, `Accepted`, `Rejected`, `Deprecated`, or `Superseded by ADR-NNNN`.
A reconstructed record remains Proposed until the Owner confirms that it
accurately represents the intended decision. Implementation is evidence of the
current design, not proof of a historical approval conversation.

**`Accepted` means the Owner has approved the architecture decision — the
chosen design, options considered, and stated consequences — not that it has
been implemented or verified.** An ADR's own "Evidence and validation"
section tracks implementation evidence separately, using its own status
(e.g. `Pending`, `Partial`, `Complete`) independent of the ADR's `Accepted`
status. Do not treat an `Accepted` ADR as proof a control exists in code; the
release evidence pack and the linked risk-register entries are the
authoritative source for whether a described control has actually been
built and tested.

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
| [ADR-0001](0001-local-first-architecture.md) | Local-first single-user architecture | Accepted; Owner approved 2026-09-13 |
| [ADR-0002](0002-os-account-loopback-trust-boundary.md) | OS-account and localhost trust boundary | Accepted; existing Owner risk decision R-15 |
| [ADR-0003](0003-access-key-session-exchange.md) | Access key exchanged for expiring server-side session | Accepted; Owner approved 2026-09-13 |
| [ADR-0004](0004-build-once-verify-same-artifact.md) | Build once and verify the same artifact | Accepted; Owner approved 2026-09-13 |
| [ADR-0005](0005-cyclonedx-1-7-sbom.md) | CycloneDX 1.7 release SBOM | Accepted; Owner approved 2026-09-13 |
| [ADR-0006](0006-hosted-provenance.md) | Hosted provenance and independent verification | Accepted; Owner approved 2026-09-13 |
| [ADR-0007](0007-gmail-oauth-credential-storage.md) | Gmail OAuth and credential storage | Proposed; drafted for v1.1 Owner review |
| [ADR-0008](0008-gmail-read-only-mailbox-trust-boundary.md) | Gmail read-only mailbox trust boundary | Proposed; drafted for v1.1 Owner review |
| [ADR-0009](0009-external-job-provider-trust-boundary.md) | External job-provider trust boundary | Proposed; drafted for v1.1 Owner review |
