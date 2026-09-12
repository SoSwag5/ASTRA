# ADR-0002: OS-account and localhost trust boundary

- **Status:** Accepted
- **Date:** 2026-09-12
- **Owner:** Ayham
- **Issue / pull request:** Existing R-15 decision; governance linkage added here
- **Target release:** v1.0
- **Supersedes / superseded by:** None

## Context and problem

ASTRA has no application identities, roles, or user-scoped objects. It needs an
honest authorization boundary for ASVS assessment and release communication.
Loopback binding does not prove which process or OS user made a request.

## Options considered

1. Trust the local OS account/localhost environment for the single-user product.
2. Require the optional access key for every installation while retaining no
   application-user model.
3. Add application identities and per-user authorization before v1.0.

## Decision

For v1.0, treat callers already inside the local OS-account/host boundary as in
scope for the single user. Retain loopback binding, Host/Origin/cross-site
checks, optional access-key sessions, data-directory guidance, and demo
isolation. Record ASVS 5.0.0 8.2.1 and 8.2.2 as N/A by this architecture because
there are no application consumers or user-owned objects to authorize.

## Rationale

Adding an identity and authorization subsystem would redefine the product and
delay the local single-user release. The selected boundary matches the intended
deployment while stating its limitation directly.

## Security and privacy impact

A malicious local process or sufficiently privileged user may read or modify
application data through the loopback service. Optional access-key mode reduces
casual local access but does not create multi-user isolation.

## Operational impact

Users should run ASTRA under a trusted OS account and secure the local machine
and data directory. There is no account provisioning or role administration.

## Tradeoffs and residual risk

R-15 records likelihood 2 and impact 2. The Owner accepted it for v1.0. Any
non-loopback binding, hosting, shared deployment, application accounts, roles,
multi-user use, or tenancy triggers reassessment and likely supersedes this ADR.
The risk record needs an expiry/reapproval date to match the Secure SDLC's
90-day exception rule.

## Evidence and validation

`docs/security/RISK_REGISTER.md`, `docs/security/L1_CLOSURE_REVIEW.md`,
`docs/security/THREAT_MODEL.md`, access/session tests, and repository commit
`a167e99c2bedd6f589c47516398a919893b261a9`.

## Framework impact

Defines ASVS 8.2.1/8.2.2 applicability for v1.0. It does not establish an ASVS
certification or make loopback equivalent to authentication.
