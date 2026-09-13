# ADR-0001: Local-first single-user architecture

- **Status:** Accepted
- **Date:** 2026-09-13
- **Owner:** Ayham
- **Issue / pull request:** [PR #28](https://github.com/SoSwag5/ASTRA/pull/28)
- **Owner approval:** Approved 2026-09-13
- **Target release:** v1.0
- **Supersedes / superseded by:** None

## Context and problem

ASTRA manages sensitive job, application, CV, and profile data. Existing code
and documentation implement a personal application served on loopback with local
storage and manual control over final application submission.

## Options considered

1. Local-first single-user application with optional, per-request cloud AI.
2. Hosted multi-user service with application identities and tenant isolation.
3. Desktop client backed by a managed remote data service.

## Decision

For v1.x, retain a local-first, single-user product. Store user data locally,
bind the service to loopback, keep final application submission manual, and
require explicit consent for each cloud-AI request. The Owner approved this
reconstructed decision on 2026-09-13.

## Rationale

The design minimizes remote exposure and operational burden while supporting a
personal workflow. Hosted or multi-user operation would require identity,
authorization, tenant isolation, new privacy controls, and a different threat
model.

## Security and privacy impact

The local OS account is the primary trust boundary. Loopback reduces network
exposure but does not authenticate the caller. Cloud AI may receive only the
data authorized for a specific request. Automated discovery must not become
automated application submission.

## Operational impact

Users manage the local runtime, data directory, backups, and prerequisites.
Distribution and upgrade hardening is planned for v1.2.

## Tradeoffs and residual risk

Local malware or another process within the trusted host boundary may reach
local resources. R-15 documents this accepted v1.0 risk. The design does not
provide remote access, shared tenancy, or hostile-user isolation.

## Evidence and validation

The architecture shipped in immutable v1.0.0 source `81ad2d3`. Evidence includes
the README, architecture inventory, threat model, privacy flow, local-access
guide, demo isolation, hosted clean-install verification, and application/security
tests. The Owner confirmed this reconstructed ADR on 2026-09-13.

## Framework impact

Sets ASVS applicability and the scope of SSDF/SAMM evidence. Any hosted or
multi-user change reopens authorization controls and requires new assessments.
