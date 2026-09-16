# ADR-0007: Gmail OAuth and credential storage

- **Status:** Accepted (architecture decision only; Owner approved
  2026-09-13, OD-018). Implementation evidence remains **Pending** — see
  "Evidence and validation" below; do not treat this status as proof any
  control is implemented.
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

**Implementation evidence status: COMPLETE for this ADR's controls —
implemented and live-validated (self-verified; independent review waived
by the Owner for issue #44).** This ADR's `Accepted` status reflects
Owner approval of the architecture decision; the evidence below is what
certifies the controls were actually built and exercised, and it is
tracked independently of the status field.

**Final live validation: `PASS`** (issue #44, PR #66). Recorded
machine-verified evidence, fully redacted:

- Requested scope was exactly
  `https://www.googleapis.com/auth/gmail.readonly`, and the scope Google
  itself returned in the token response — and again on refresh — was
  exactly the same. Google's published definition of that scope is
  **"View your email messages and settings"**. No send, compose, modify,
  delete, label-management, broader settings, Calendar, Contacts or Drive
  authorization was requested or granted.
- PKCE `S256` with the challenge equal to SHA-256 of the verifier; 256-bit
  single-use `state` bound to the attempt; numeric `127.0.0.1` loopback on
  an ephemeral port; strict callback validation (wrong path 404, wrong
  method 405, wrong state 400 leaving the account disconnected).
- Authorized identity taken from the authenticated `users/me/profile` and
  matched to the connected account.
- Refresh token stored only in the DPAPI-backed Windows credential store
  under the current user, in a namespace separate from both the OpenAI
  credential and the OAuth client secret; refresh through
  `refresh_access_token` proved the stored credential usable.
- One metadata-only Gmail call (`users/me/profile`); no message listed, no
  content requested, no mailbox counts persisted.
- Disconnect removed the refresh token, the client secret, the identity
  keys and the sync state; remote revocation **succeeded**; reuse of the
  revoked token was **rejected by Google**; repeated disconnect was
  idempotent.
- Identity remanence `PURGED` — the authorized address absent from the
  database, `-wal`, `-shm` and the event log.
- Credential and privacy leak scan: **zero findings** across the isolated
  database and sidecars, the security-event log and 287 repository files.

**Manual consent-screen pixels were not preserved** — no screenshot or
transcription exists. The authoritative evidence for the granted
authorization is therefore the machine-verified authorization request, the
granted scope Google returned (twice), the successful metadata-only call
that scope permits, and Google's official definition of the scope. This
ADR does not claim a human-attested consent screen.

**Not claimed:** Google OAuth verification, public restricted-scope
distribution approval, certification, or production rollout approval —
see "Distribution scope" above. Issue #45 remains unstarted.

**Process note, recorded honestly:** Governance v1 normally requires
independent review before an Owner-authorized merge. For issue #44 the
Owner explicitly accepted the self-verification and waived an additional
independent review. No second party reviewed this implementation, and it
must not be described as independently reviewed.

Implemented and covered by automated tests on
`feature/44-gmail-oauth` (issue #44, **not merged**) — see
`docs/architecture/GMAIL_OAUTH.md`:

- The auth-code + PKCE(S256) + loopback-redirect flow, with a
  256-bit single-use `state` compared in constant time, atomic
  consume-before-exchange, 5-minute attempt expiry, per-slot
  supersession, and a memory-only attempt store that a restart clears.
- Granted-scope validation that inspects what Google actually granted
  and rejects a token that is **missing** `gmail.readonly` *or* carries
  anything beyond it, before any credential is stored.
- Authorized-identity binding from Gmail's authenticated
  `users/me/profile`, never from user intent or a login hint, with
  identity and credential-key uniqueness among connected records.
- Refresh-token storage in the native OS credential store only, under a
  dedicated namespace, with no plaintext/environment/SQLite/file/cache
  fallback, and a Windows check that the backend is the native
  DPAPI-backed Credential Manager (`CurrentUser`, never
  `LocalMachine`).
- **Amendment (Owner-authorized, live-verified): DPAPI-backed client-secret
  support.** This ADR's Options and Rationale sections assumed PKCE would
  remove the need for a client secret ("no client secret needed to be kept
  confidential"). Live validation proved that assumption incomplete for this
  client type: the Desktop OAuth client enforces client authentication at
  Google's token endpoint before evaluating the grant — `400
  invalid_request` naming the missing secret without one, `401
  invalid_client` with a deliberately wrong one. The Owner authorized
  narrow support on that evidence. The ADR's *intent* is preserved rather
  than reversed: a Desktop client secret is **not** treated as a globally
  confidential credential (anyone who distributes the app distributes it,
  and Google says as much), PKCE is unchanged and still required as proof
  of possession, and the secret is protected locally by exactly the
  mechanism this ADR already mandates for refresh tokens — DPAPI under
  `CurrentUser`, no plaintext fallback. It is entered only through a hidden
  console prompt (`python -m backend.gmail_setup`), never a command-line
  argument, a file, or the web UI; stored in its own keyring namespace
  separate from the per-account refresh tokens; sent only to the token
  endpoint, enforced at the single transport chokepoint; and removed when
  the last account disconnects or on full local deletion. See
  `docs/architecture/GMAIL_OAUTH.md` "Client secret".
- Negative tests proving high-entropy sentinel tokens are absent from
  application logs, captured stdout/stderr, the security-event file,
  the SQLite database bytes (including `-wal`/`-shm`), the private
  export archive, a daily backup snapshot, diagnostic output, every API
  response body, and exception strings and tracebacks.
- OAuth-callback abuse-case negative tests: incorrect `state` rejected,
  missing `state` rejected, duplicate `state` rejected, replayed
  callback rejected, expired/cancelled/superseded attempts rejected,
  concurrent callbacks yielding exactly one terminal result, and a
  credential that cannot attach to a conflicting Gmail account record.
- Per-account disconnect that removes local access even when Google is
  unreachable, times out, errors or answers malformed, and reports the
  local and remote results separately without ever presenting a failed
  revocation as a success.

**Previously outstanding, now satisfied or consciously accepted:**

- A live proof-of-concept against a real Google OAuth client in a
  dedicated ASTRA Google Cloud project — **done**, final run `PASS`.
- Confirmation on a real installation that the DPAPI-protected entry is
  present in Windows Credential Manager and that no plaintext token
  exists on disk — **done**; the entry was observed present in
  `keyring.backends.Windows` while connected and absent after disconnect,
  and the leak scan found no token in the database, its sidecars, the
  event log or the repository.
- **Manual consent-screen evidence of the exact permissions requested —
  NOT captured.** This requirement is recorded as unmet rather than
  quietly reinterpreted. The granted authorization is established instead
  by the machine-verified request, Google's own returned granted scope
  (twice), the metadata-only call that scope permits, and Google's
  official scope definition. A mocked test was never treated as
  consent-screen evidence.
- **Independent review of the implementation — NOT performed.** The Owner
  explicitly waived it for issue #44 and accepted the self-verification.

See issue #48 (v1.1 security/privacy assurance) for where this evidence
is assembled, and `docs/security/RISK_REGISTER.md` R-16, which remains
**OPEN** — the existence of this code is not closure.

## Framework impact

Introduces newly-applicable ASVS areas for credential/token storage
and session-adjacent secret handling that were previously N/A under
the local-only, no-external-credential model (see the v1.1 threat-model
delta for the specific mapping). No SLSA/CycloneDX impact. SSDF
evidence expands to cover this new external-credential handling path.
