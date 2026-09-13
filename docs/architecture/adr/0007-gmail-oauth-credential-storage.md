# ADR-0007: Gmail OAuth and credential storage

- **Status:** Proposed
- **Date:** 2026-09-13
- **Owner:** Ayham
- **Issue / pull request:** v1.1 planning packet; see `docs/planning/V1_1_DISCOVERY_AND_APPLICATION_INTELLIGENCE.md` §6
- **Target release:** v1.1.0 (Phase B)
- **Supersedes / superseded by:** None

## Context and problem

v1.1 adds read-only Gmail application-confirmation capture for two
user-owned Gmail accounts (OD-012). This requires obtaining and
persisting OAuth credentials for each account on the user's own
machine, consistent with ASTRA's local-first, no-passwords-requested
security posture (`AGENTS.md`; ADR-0001; ADR-0002). No design for
acquiring, storing, using, or revoking these credentials exists yet.

Decision questions this ADR must answer:

- Which OAuth flow is appropriate for a local installed desktop
  application (no server-side redirect endpoint under ASTRA's control)?
- What is the minimum Gmail permission scope for read-only application
  tracking?
- How and where are refresh tokens stored at rest on Windows?
- How is a token revoked (by the user, or automatically on suspected
  compromise)?
- How are the two Gmail account identities kept separable so a
  detection or reconciliation bug in one account cannot silently
  affect the other?

## Options considered

1. **OAuth 2.0 authorization-code flow with PKCE, loopback redirect,
   installed-app client type.** ASTRA opens the system browser to
   Google's consent screen, receives the redirect on a locally bound
   ephemeral loopback port it briefly listens on, and exchanges the
   code for tokens using PKCE (no client secret needed to be kept
   confidential, consistent with Google's guidance for installed
   apps). Standard, well-supported flow for CLI/desktop apps; matches
   ASTRA's local-first, no-hosted-backend architecture.
2. **Device-code flow.** Simpler UI (a code the user types into a
   browser on any device) but designed for input-constrained devices;
   adds unnecessary friction for a desktop app that already has a
   browser available, and still requires the same token-storage
   problem.
3. **Store the user's Gmail password and use IMAP with app-specific
   passwords or account credentials directly.** Rejected outright:
   `AGENTS.md` and OD-012 explicitly prohibit requesting Gmail
   passwords; this would also require the user to weaken their Google
   account security (enabling less-secure access) and is exactly the
   pattern ASTRA's existing consent/credential model avoids elsewhere
   (`backend/providers.py` credential handling for AI providers).

## Decision

Use the OAuth 2.0 authorization-code flow with PKCE and a loopback
redirect, as an installed-app OAuth client, requesting the **narrowest
read-only Gmail scope that supports the confirmation-detection use
case** (`gmail.readonly` or a more restrictive label/query-scoped
alternative if Google offers one suitable for this use — to be
confirmed during implementation against current Google API scope
documentation, not assumed here).

Store per-account refresh tokens locally, encrypted at rest using an
OS-backed mechanism appropriate to ASTRA's supported platform (Windows
DPAPI via the current user's profile, matching the protection model
already implied by ASTRA's OS-account trust boundary in ADR-0002)
rather than plaintext in the SQLite database or a config file. Access
tokens are held only in memory for the duration of a sync operation
and are not persisted.

Each Gmail account is a **distinct, independently-scoped credential
record** — keyed by account identifier, never merged or shared between
the two accounts' token storage, sync state, or detected-application
records. Revocation is per-account: the user can disconnect one
account (deleting its stored refresh token and prompting Google-side
revocation) without affecting the other, and without deleting
already-reconciled application records (those stand on their own
evidence, per the application state model's provenance rules).

Implementation activates and validates the **primary account only**
first (OD-012); the second account's credential flow reuses the same
mechanism but is not enabled until the first account's OAuth, sync,
parsing, reconciliation, and duplicate-prevention behavior are
validated.

## Rationale

The authorization-code-with-PKCE/loopback pattern is Google's
documented recommendation for installed applications and avoids
embedding a confidential client secret, which an installed app cannot
keep confidential. It requires no ASTRA-operated server component,
consistent with the local-first architecture. OS-backed encryption at
rest (DPAPI) matches how a local-first Windows application should
protect long-lived secrets without inventing a bespoke encryption
scheme, and keeps token protection tied to the same OS-account trust
boundary ASTRA already relies on (ADR-0002) rather than a weaker
in-repo secret.

Per-account isolation directly serves OD-012's "validate one account
before adding a second" requirement: if account isolation were weak,
validating the primary account would not actually de-risk enabling the
second.

## Security and privacy impact

- **Assets:** Gmail OAuth refresh tokens (two, one per account);
  transient access tokens; the minimum extracted application-tracking
  data (see ADR-0008).
- **Actors:** the local OS user (trusted, per ADR-0002); a malicious
  local process or another OS user on a shared/compromised host
  (R-15's existing threat actor); Google's OAuth infrastructure
  (trusted third party for the flow itself).
- **Trust boundary:** unchanged from ADR-0002 — a caller already inside
  the local OS-account/host boundary is in ASTRA's trusted scope.
  Token theft by such an actor is a new instance of R-15's existing
  residual, not a new trust boundary; DPAPI-style protection raises
  the bar (requires the same user context to decrypt) but does not
  eliminate it.
- **New risk:** OAuth refresh-token theft or misuse if local storage
  protection is weaker than assumed, or if a token is logged,
  exported, or included in a diagnostic bundle. Structured logging
  and diagnostics must treat tokens as secrets (never logged, never
  included in exports — see `docs/security/PRIVACY_DATA_FLOW.md`
  conventions).
- **Revocation:** must be user-initiated and effective immediately
  (local deletion) with a best-effort server-side revocation call;
  a failed server-side revocation must not block local deletion or be
  reported as success if it did not happen.

## Operational impact

Users authorize each Gmail account through a one-time browser consent
flow per account. Losing the machine or profile (no backup of the
DPAPI-protected token) requires re-authorization, not data loss of
already-reconciled applications (those are stored separately from the
credential). No server-side component to operate, monitor, or scale.

## Tradeoffs and residual risk

DPAPI-style protection is tied to the Windows user profile; it does
not protect against a compromise of that same user account (consistent
with R-15's existing scope, not a new limitation). A new risk-register
entry is proposed in the v1.1 threat-model delta for Owner acceptance
before implementation. Cross-platform support (if ASTRA ever ships
non-Windows) would need an equivalent OS-backed store, not plaintext
fallback.

## Evidence and validation

None yet — this is a pre-implementation draft. Required before
Accepted: a working local proof-of-concept of the auth-code+PKCE flow
against a real Google OAuth client, confirmation of the exact scope
requested, and a negative test proving tokens are never written to
logs, exports, or the SQLite database in plaintext.

## Framework impact

Introduces newly-applicable ASVS areas for credential/token storage
and session-adjacent secret handling that were previously N/A under
the local-only, no-external-credential model (see the v1.1 threat-model
delta for the specific mapping). No SLSA/CycloneDX impact. SSDF
evidence expands to cover this new external-credential handling path.
