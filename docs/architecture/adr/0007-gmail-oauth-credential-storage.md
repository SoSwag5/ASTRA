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

**Scope (explicitly selected, not left open):** request
`https://www.googleapis.com/auth/gmail.readonly` for v1.1.

This is a Google **Restricted** scope (Google's sensitive/restricted
scope classification), which carries additional obligations if ASTRA
is ever distributed beyond personal/local-first use — see
"Distribution scope" below. It is selected deliberately over the
narrower `gmail.metadata` scope: `gmail.metadata` does not grant
message-body access, which ASTRA's automatic body-based confirmation
parsing requires (§6.4 of the planning document), and `gmail.metadata`
does not support the Gmail `q` search parameter, which ASTRA needs to
narrow sync to a bounded, relevant query rather than pulling the
entire mailbox (ADR-0008). `gmail.readonly` is therefore the narrowest
scope that actually supports the required functionality, not merely
the narrowest scope in the abstract.

**Distribution scope:** this decision covers **personal/local-first
use** — a single user running their own installation with their own
Google OAuth client. Restricted scopes carry a Google OAuth
verification/security-assessment requirement for apps used by parties
beyond the developer's own accounts. **Wider public distribution of
ASTRA's Gmail integration requires a separate, explicit Owner decision
and a Google OAuth verification/readiness review before it ships** —
this ADR does not authorize that and must not be read as having
already cleared it.

**Flow:** OAuth 2.0 authorization-code flow with **PKCE using the S256
code-challenge method** (not `plain`), as an installed-app OAuth
client. Required elements:

- A **cryptographically random `state` parameter** is generated per
  authorization attempt and validated for an **exact match** on the
  callback; the callback is **consumed once** (single-use) — a replayed
  or reused callback is rejected.
- The redirect listens on a **random ephemeral loopback port, bound
  only to loopback** (`127.0.0.1`/`::1`), never `0.0.0.0` or any
  non-loopback interface.
- Authorization codes, access tokens, and refresh tokens are **never
  logged**, at any log level, including debug/diagnostic output.
- **After token exchange, ASTRA queries the authorized Gmail
  identity/profile and binds the resulting credential record to the
  actual authorized account** before persisting it — this closes the
  "account mix-up" case where a user intends to authorize one account
  but the consent flow completes against a different one (see the
  threat-model delta's new OAuth-callback abuse case).

**Storage:** per-account refresh tokens are stored locally, encrypted
at rest using an OS-backed mechanism (Windows DPAPI, using
**`CurrentUser` protection scope, never `LocalMachine`** — binding
decryption to the specific OS user, matching ASTRA's OS-account trust
boundary in ADR-0002) rather than plaintext in the SQLite database or
a config file. Access tokens are held only in memory for the duration
of a sync operation and are not persisted.

**Backup/export exclusion:** the OAuth credential store is **excluded
from ASTRA's normal backup, export, and diagnostic-bundle paths** —
those paths must not read, copy, or bundle it. This is a stricter rule
than "don't log it": it also is not swept up incidentally by a feature
that was not designed with credential handling in mind.

Each Gmail account is a **distinct, independently-scoped credential
record** — keyed by account identifier, never merged or shared between
the two accounts' token storage, sync state, or detected-application
records. Revocation is per-account: the user can disconnect one
account (deleting its stored refresh token and prompting Google-side
revocation) without affecting the other, and without deleting
already-reconciled application records (those stand on their own
evidence, per the application state model's provenance rules — see
ADR-0008's amended disconnect/retention rules for the exact scope of
what disconnect does and does not delete).

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
  conventions). Because the granted scope is `gmail.readonly`, theft
  of a refresh token exposes the **entire mailbox's read access**, not
  merely ASTRA's own minimized evidence records — this is reflected in
  risk R-16's rating (see `docs/security/RISK_REGISTER.md`), which
  rates inherent impact as severe (3) on that basis, not as material
  (2).
- **OAuth callback interception / CSRF / account mix-up:** covered as
  its own abuse case in the threat-model delta, with the state/PKCE/
  loopback/single-use-callback/identity-binding controls specified in
  the Decision section above as the mitigations.
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
with R-15's existing scope, not a new limitation). This is registered
as risk R-16 in `docs/security/RISK_REGISTER.md`, state **OPEN —
treatment planned for v1.1**: the Owner has approved recording this
risk, not accepted its residual — residual risk is reassessed only
after the controls above and their negative tests exist. Cross-platform
support (if ASTRA ever ships non-Windows) would need an equivalent
OS-backed store, not plaintext fallback.

## Evidence and validation

**Implementation evidence status: Pending.** This ADR's `Accepted`
status (if granted) reflects Owner approval of the architecture
decision above — it does not certify that any control described here
has been built. The following evidence is required before this ADR's
controls may be relied upon in the v1.1 release evidence pack, and is
tracked independently of the ADR's status field: a working local
proof-of-concept of the auth-code+PKCE(S256) flow against a real
Google OAuth client; confirmation that the exact granted scope is
`gmail.readonly`; a negative test proving tokens are never written to
logs, exports, backups, diagnostic bundles, or the SQLite database in
plaintext; negative tests for the OAuth-callback abuse case (incorrect
state rejected, missing state rejected, reused callback rejected,
invalid PKCE verifier rejected, credential cannot attach to the wrong
Gmail account record); and confirmation that DPAPI storage uses
`CurrentUser` scope. See issue #48 (v1.1 security/privacy assurance)
for where this evidence is assembled.

## Framework impact

Introduces newly-applicable ASVS areas for credential/token storage
and session-adjacent secret handling that were previously N/A under
the local-only, no-external-credential model (see the v1.1 threat-model
delta for the specific mapping). No SLSA/CycloneDX impact. SSDF
evidence expands to cover this new external-credential handling path.
