# Owner review packet — v1.1 Discovery & Application Intelligence

This packet is the governed handoff requested after v1.1 planning approval
with amendments (OD-011 through OD-017). It bundles the three drafted ADRs,
the threat-model delta, and the proposed risk-register additions for Owner
review. **No implementation begins until this packet is approved.**

Full context: `docs/planning/V1_1_DISCOVERY_AND_APPLICATION_INTELLIGENCE.md`;
decision records `docs/governance/OWNER_DECISIONS.md` OD-011 through OD-017.

## ADR-0007 — Gmail OAuth and credential storage

**Context:** v1.1 needs OAuth credentials for two user-owned Gmail accounts,
persisted locally, consistent with ASTRA's no-passwords-requested, local-first
posture.

**Options considered:** OAuth 2.0 authorization-code flow with PKCE and a
loopback redirect (installed-app client type); device-code flow; storing the
user's Gmail password/app-password directly (rejected outright — prohibited
by `AGENTS.md` and OD-012).

**Proposed decision:** Authorization-code + PKCE + loopback redirect,
requesting the narrowest read-only Gmail scope that supports confirmation
detection. Refresh tokens encrypted at rest via an OS-backed mechanism
(Windows DPAPI under the current user profile); access tokens held only in
memory per sync. Each account's credential, sync state, and detected records
are isolated from the other — never merged or shared. Primary account
activated and validated first; second account enabled only afterward
(OD-012).

**Security consequences:** New long-lived secret class (OAuth refresh
tokens). Token theft by an actor already inside the OS-account/host boundary
is a new instance of the existing R-15 residual, not a new trust boundary.
Tokens must never appear in logs, exports, or diagnostic bundles.

**Privacy consequences:** No new personal-data class beyond the credential
itself — the data it unlocks is scoped by ADR-0008. Per-account isolation
means disconnecting one account never exposes or deletes the other's data.

**Operational consequences:** One-time per-account browser consent flow; no
server-side component. Losing the encrypted local store requires
re-authorization, not loss of already-reconciled application records (stored
separately).

**Residual risk:** DPAPI-style protection does not protect against
compromise of the same OS user account (matches R-15's existing scope, not a
new limitation). Proposed as risk **R-16** (pending acceptance below).

**Evidence:** None yet — pre-implementation. Required before Accepted: a
working local PoC of the auth flow; confirmation of the exact scope
requested; a negative test proving tokens never reach logs/exports/the
database in plaintext.

**Recommendation:** APPROVE the design; mark Accepted once the evidence above
exists (at implementation, not before).

## ADR-0008 — Gmail read-only mailbox trust boundary

**Context:** Once authorized, ASTRA has the technical ability to read (and,
with a broader scope, mutate) Gmail. Product intent is strictly
observational.

**Options considered:** Read-only scope + read-only code path + minimized
extraction (chosen); a broader scope "for future flexibility" (rejected —
violates `AGENTS.md`/OD-012 minimization); full mailbox mirroring (rejected —
turns ASTRA into an email archive, contrary to OD-012's retention limit).

**Proposed decision:** ASTRA may read only the minimum data needed for
application tracking and may **never** send, delete, archive, trash, mark
read/unread, or otherwise modify Gmail messages or labels in v1.1 — enforced
at the integration layer (the Gmail client wrapper exposes no mutating
method), not only as policy. Retained fields are limited to: message ID,
account ID, sender, subject, received timestamp, detected company/role/
application state, confidence, evidence/parser identifier, and the relevant
URL. Full body content is used only transiently during parsing; any
exception (e.g., a Needs Review snippet) must be separately proposed, never
added silently.

**Security consequences:** Malicious HTML/links in message content must be
sanitized before any display and never auto-followed. Hard read-only
enforcement means a future bug cannot silently start mutating the mailbox
without a deliberate, reviewable change to the integration layer.

**Privacy consequences:** Directly implements the Owner's retention
requirement (OD-012) — no durable email archive. Reduces exposure if the
local database or a backup is ever compromised or exported.

**Operational consequences:** Users see derived evidence and, for MEDIUM
confidence, a minimal snippet — not a searchable email archive. If the user
later revokes access, ASTRA cannot have mutated their mailbox in the
meantime.

**Residual risk:** Narrow retention means a missed/low-confidence message
cannot be re-parsed later from ASTRA's own storage (the email itself remains
in Gmail, untouched). Read-only enforcement is a code-level control layered
on top of ADR-0007's scope selection — both are required. Proposed as risk
**R-17** (shared with ADR-0009, pending acceptance below).

**Evidence:** None yet — pre-implementation. Required before Accepted: the
actual granted scope confirmed read-only; a test asserting the Gmail client
wrapper exposes no mutating method; a test confirming no full message body
persists in the database after a sync/parse cycle.

**Recommendation:** APPROVE the design; mark Accepted once the evidence above
exists.

## ADR-0009 — External job-provider trust boundary

**Context:** Discovery v2's provider-adapter architecture fetches job
postings from multiple external, ASTRA-uncontrolled sources feeding
normalization, ranking, and display (and potentially the AI-comparison
path).

**Options considered:** Treat every provider identically as untrusted, with a
common adapter contract enforcing validation/caps/sanitization (chosen);
trust "reputable" providers more than manual imports (rejected — reputation
is not a technical control); no common adapter contract (rejected —
inconsistent enforcement across sources).

**Proposed decision:** Every adapter is bound by the same rules regardless of
source: URL validation reusing ASTRA's existing outbound-fetch policy
(`policy.py`, closing SSRF for the new URL set); size/time-capped response
reading (same pattern as the existing AI-response cap); strict/defensive
parsing that rejects unexpected shapes rather than coercing them;
sanitization before any display or AI use, with provider content framed as
untrusted data exactly like job/CV text is today; per-provider failure
isolation; and source/URL provenance retained on every normalized record.

**Security consequences:** Closes SSRF exposure for the new external-URL
surface by reusing an already-reviewed control rather than inventing a
second one. Guards the AI-comparison path against provider-sourced content
being treated as instructions.

**Privacy consequences:** No new personal-data class — job postings are not
personal data — but provider content is still subject to the same
display/export sanitization review as any other rendered content.

**Operational consequences:** Per-source failure isolation plus the funnel
telemetry (planning doc §5) gives visibility into which sources are healthy,
directly targeting the "12/12 healthy, zero results" failure mode that
motivated this milestone.

**Residual risk:** A provider that changes its response shape without notice
fails closed for that source (intentional, favors correctness over
availability). A user-pasted malicious manual-import URL is contained the
same way a bad provider response would be, but the user remains responsible
for what they choose to import. Proposed as risk **R-17** (shared with
ADR-0008) and **R-18** (reconciliation/status-evidence spoofing — see the
threat-model delta), pending acceptance below.

**Evidence:** None yet — pre-implementation. Required before Accepted: a test
proving loopback/private-range provider or job URLs are rejected before
fetch; a test proving an oversized response is capped without blocking other
providers; a test proving provider HTML is sanitized before any display
path.

**Recommendation:** APPROVE the design; mark Accepted once the evidence above
exists.

## Threat-model delta summary

Full document: `docs/security/THREAT_MODEL_CHANGE_V1_1_DISCOVERY_GMAIL.md`.

Covers, at minimum, every area the Owner specified: OAuth authorization and
refresh tokens; two Gmail identities; token theft; mailbox-data minimization;
malicious email HTML/text/URLs; parser/resource exhaustion; job-provider
content; malicious job links; SSRF; duplicate/reconciliation manipulation;
status-evidence spoofing; local storage; logs/audit events; and optional
future AI parsing (flagged as explicitly out of scope for the initial pass
and requiring its own future threat-model delta if ever proposed).

Nine abuse cases are enumerated with STRIDE/CWE classification, preconditions,
controls, residual risk, and the specific negative test required before each
is considered mitigated. No test evidence exists yet — this is the
pre-implementation delta.

**Proposed risk-register additions (not yet accepted):**

| ID | Risk | L/I | Covers |
|---|---|---|---|
| R-16 | Gmail OAuth refresh-token theft or misuse | 2/2 | ADR-0007 |
| R-17 | Malicious/spoofed email or job-provider content reaching the user, parser, or AI-comparison path | 2/2 | ADR-0008, ADR-0009 |
| R-18 | Reconciliation/duplicate manipulation or status-evidence spoofing | 2/2 | Application state model (planning doc §7) |

**Framework impact:** ASVS credential/token-storage and input-validation/
SSRF-prevention requirements become newly applicable where previously N/A
under the local-only model; exact clause mapping is deferred to when these
ADRs are Accepted and implementation begins, so it is written against real
code rather than a still-changing design. SSDF evidence expands to cover the
new external-credential and external-data paths. No SLSA/CycloneDX impact
beyond a routine SBOM/lockfile update for the Gmail API client dependency
(R-04 applies).

## Owner decisions required to close this packet

- [ ] Approve ADR-0007 (Gmail OAuth and credential storage) — or request
      changes.
- [ ] Approve ADR-0008 (Gmail read-only mailbox trust boundary) — or request
      changes.
- [ ] Approve ADR-0009 (external job-provider trust boundary) — or request
      changes.
- [ ] Approve the threat-model delta
      (`THREAT_MODEL_CHANGE_V1_1_DISCOVERY_GMAIL.md`).
- [ ] Accept, reject, or amend proposed risks R-16, R-17, R-18.

Once all five are approved, the three ADRs move from Proposed to Accepted,
the 12-item backlog (planning doc §11) is filed under the "v1.1 — Discovery &
Application Intelligence" milestone, and the first implementation branch is
the Discovery Query Planner (Phase A).
