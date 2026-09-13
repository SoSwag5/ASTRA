# ADR-0003: Access key exchanged for an expiring server-side session

- **Status:** Proposed (reconstructed; Owner confirmation required)
- **Date:** 2026-09-13
- **Owner:** Ayham
- **Issue / pull request:** Governance v1 branch
- **Target release:** v1.0
- **Supersedes / superseded by:** None

## Context and problem

When optional access-key mode is enabled, repeatedly sending a long-lived key to
the API increases exposure and complicates logout and lockout behavior.

## Options considered

1. Send the access key with every request.
2. Exchange the access key for a random, expiring, server-side session and clear
   it on logout or teardown.
3. Add full application identities and persistent user sessions.

## Decision

Use the access key only at the session exchange boundary. Issue a random
server-side session with expiry, idle timeout, invalidation/logout, and bounded
failed-attempt lockout. Keep keyless mode available within the accepted local
trust boundary. This record requires Owner confirmation.

## Rationale

The exchange limits repeated exposure of the long-lived secret and supports
session lifecycle controls without introducing a multi-user identity model.

## Security and privacy impact

Session tokens are sensitive and must not appear in logs, URLs, exports, or
persistent browser storage. Cross-site, Origin, Host, and local-peer controls
remain required. Logout and application teardown must clear client state.

## Operational impact

Access-key provisioning and recovery remain local configuration concerns.
Sessions expire and may require the user to unlock again.

## Tradeoffs and residual risk

A compromised local process/browser context may steal an active token. R-15
still applies; this design is not multi-user authorization.

## Evidence and validation

`backend/access.py`, `docs/security/LOCAL_ACCESS.md`, and focused session/security
tests are present in released source `81ad2d3`. The v1.0 candidate's Python
3.13/3.14 test and security-verification jobs passed. Owner confirmation of the
reconstructed architecture decision remains pending.

## Framework impact

Supports relevant ASVS authentication/session controls. It does not change the
architectural N/A determination for per-consumer authorization.
