# Owner review packet — v1.1 Discovery & Application Intelligence

This packet is the governed handoff requested after v1.1 planning approval
with amendments (OD-011 through OD-017). It bundles the three ADRs, the
threat-model delta, and the registered risk entries for Owner review.

**CLOSED — Owner approved 2026-09-13 (OD-018).** ADR-0007, ADR-0008, and
ADR-0009 are **Accepted** as architecture decisions. The threat-model delta
is **Approved**. R-16 (2/3=6, HIGH), R-17 (2/2), and R-18 (2/2) are
**registered as OPEN, treatment planned for v1.1** — registration, not
residual-risk acceptance. **Implementation evidence for all three ADRs
remains Pending** until built and independently reviewed (issue #48);
`Accepted` reflects architecture approval only, never proof of an
implemented control. This approval authorizes v1.1 implementation to begin,
starting with issue #37 (Discovery Query Planner).

**Revision 2 (2026-09-13):** amended per the Owner's security review to add
explicit OAuth scope/flow requirements, resolve retention/disconnect
wording, require multi-signal confidence gating, remove an architectural
dependency on the unmerged R-13 branch, distinguish UI sanitization from
LLM prompt-injection controls, add an OAuth-callback abuse case, correct
ADR status semantics (`Accepted` = architecture approved, not
implementation proof), and change R-16/R-17/R-18 from "proposed for
acceptance" to **registered as OPEN, with residual-risk acceptance
explicitly deferred**.

Full context: `docs/planning/V1_1_DISCOVERY_AND_APPLICATION_INTELLIGENCE.md`;
decision records `docs/governance/OWNER_DECISIONS.md` OD-011 through OD-018.

## ADR status semantics (governs how to read every ADR below)

Per `docs/architecture/adr/README.md`: **`Accepted` means the Owner has
approved the architecture decision** — the chosen design, options
considered, and stated consequences — **not that it has been implemented or
verified.** Each ADR's own "Evidence and validation" section tracks
implementation-evidence status (`Pending`/`Partial`/`Complete`)
independently of the ADR's status field. Approving an ADR in this packet is
an architecture decision, not a claim that any control described in it
already exists in code.

## ADR-0007 — Gmail OAuth and credential storage

**Context:** v1.1 needs OAuth credentials for two user-owned Gmail accounts,
persisted locally, consistent with ASTRA's no-passwords-requested, local-first
posture.

**Options considered:** OAuth 2.0 authorization-code flow with PKCE and a
loopback redirect (installed-app client type); device-code flow; storing the
user's Gmail password/app-password directly (rejected outright — prohibited
by `AGENTS.md` and OD-012).

**Proposed decision (amended):**

- **Scope, explicitly selected:** `https://www.googleapis.com/auth/gmail.readonly`
  — a Google **Restricted** scope. `gmail.metadata` was evaluated and
  rejected: it does not grant body access (needed for automatic body-based
  confirmation parsing) and does not support the Gmail `q` search parameter
  (needed to bound sync scope, ADR-0008).
- **Distribution scope:** this decision covers **personal/local-first use**
  only. Wider public distribution requires a separate Owner decision and a
  Google OAuth verification/readiness review — not authorized by this ADR.
- **Flow:** authorization-code + **PKCE with S256** (not `plain`);
  **cryptographically random `state`**, validated for exact match, callback
  **consumed once** (no replay); **random ephemeral loopback port bound only
  to loopback** (never `0.0.0.0`); authorization codes/access tokens/refresh
  tokens **never logged**; **after token exchange, ASTRA queries the
  authorized Gmail identity and binds the credential record to that actual
  account** before persisting (closes the account-mix-up case).
- **Storage:** refresh tokens encrypted at rest via Windows DPAPI using
  **`CurrentUser` protection scope, never `LocalMachine`**. Access tokens
  held only in memory per sync.
- **Backup/export exclusion:** the OAuth credential store is **excluded from
  ASTRA's normal backup, export, and diagnostic-bundle paths.**
- Each account's credential, sync state, and detected records are isolated
  from the other — never merged or shared. Primary account activated and
  validated first; second account enabled only afterward (OD-012).

**Security consequences:** New long-lived secret class (OAuth refresh
tokens). Because the scope is `gmail.readonly`, token theft exposes the
**entire mailbox's read access**, not merely ASTRA's own minimized evidence
records — this is why R-16's impact is rated severe (3), not material (2).
Token theft by an actor already inside the OS-account/host boundary is a new
instance of the existing R-15 residual, not a new trust boundary. Tokens
must never appear in logs, exports, backups, or diagnostic bundles. A new
OAuth-callback abuse case (interception/CSRF/authorization-code
substitution/account mix-up) is covered by the state/PKCE/loopback/
single-use-callback/identity-binding controls above.

**Privacy consequences:** No new personal-data class beyond the credential
itself — the data it unlocks is scoped by ADR-0008. Per-account isolation
means disconnecting one account never exposes or deletes the other's data.

**Operational consequences:** One-time per-account browser consent flow; no
server-side component. Losing the encrypted local store requires
re-authorization, not loss of already-reconciled application records (stored
separately).

**Residual risk:** DPAPI-style protection does not protect against
compromise of the same OS user account (matches R-15's existing scope, not a
new limitation). Registered as risk **R-16**, rating **2/3 = 6, HIGH**, state
**OPEN — treatment planned for v1.1**. This is a registration, not a
residual-risk acceptance — the Owner approves recording the risk; residual
risk is reassessed only after the controls above and their negative tests
exist.

**Evidence (implementation, independent of ADR status):** Pending. Required
before these controls may be relied upon in the release evidence pack: a
working local PoC of the auth-code+PKCE(S256) flow; confirmation the granted
scope is exactly `gmail.readonly`; a negative test proving tokens never
reach logs/exports/backups/the database in plaintext; negative tests for
the OAuth-callback abuse case (incorrect state rejected, missing state
rejected, reused callback rejected, invalid PKCE verifier rejected,
credential cannot attach to the wrong account); confirmation DPAPI uses
`CurrentUser` scope.

**Recommendation:** APPROVE the architecture decision. Approving `Accepted`
here does not certify any control is implemented — see "ADR status
semantics" above.

## ADR-0008 — Gmail read-only mailbox trust boundary

**Context:** Once authorized, ASTRA has the technical ability to read (and,
with a broader scope, mutate) Gmail. Product intent is strictly
observational.

**Options considered:** Read-only scope + read-only code path + minimized
extraction (chosen); a broader scope "for future flexibility" (rejected —
violates `AGENTS.md`/OD-012 minimization); full mailbox mirroring (rejected —
turns ASTRA into an email archive, contrary to OD-012's retention limit).

**Proposed decision (amended):** ASTRA may read only the minimum data needed
for application tracking and may **never** send, delete, archive, trash,
mark read/unread, or otherwise modify Gmail messages or labels in v1.1 —
enforced at the integration layer, not only as policy. Retained fields:
message ID, account ID, sender, subject, received timestamp, detected
company/role/application state, confidence, evidence/parser identifier, and
the relevant URL.

- **Full body/HTML is memory-only** — used transiently during parsing, held
  in process memory, discarded once parsing completes. **No
  implementation-defined disk cache is permitted** (the original draft's
  "short-lived cache" option is withdrawn). A separately-approved minimal
  snippet exception (e.g. for Needs Review) is the only carve-out, and must
  be called out explicitly when proposed.
- **Disconnect/retention (resolved):** disconnecting an account (ADR-0007)
  deletes that account's refresh token **and its sync/account-integration
  state**. Disconnect does **not** delete already-created Gmail-derived
  evidence records — those persist on their own evidence, independent of
  connection state. Removing that evidence is a **separate, explicit user
  action** (e.g. deleting the specific application record). This is the
  authoritative resolution of a wording contradiction the original delta
  had between "retained until ... disconnects the account" and "disconnect
  does not delete evidence" — the latter is correct and now stated
  consistently everywhere.
- **HIGH confidence requires multiple independent corroborating signals**
  (sender identity, structural template match, and consistent extracted
  fields) — a single matched element is not sufficient. **Where Gmail
  exposes message authentication evidence (SPF/DKIM/DMARC alignment), it is
  incorporated as one required signal; missing/contradictory authentication
  evidence caps the result at MEDIUM** regardless of how well the content
  otherwise matches a known template.

**Security consequences:** Malicious HTML/links in message content must be
sanitized before any display and never auto-followed. Hard read-only
enforcement means a future bug cannot silently start mutating the mailbox
without a deliberate, reviewable change to the integration layer.
Multi-signal + authentication-evidence gating directly narrows the
spoofed-confirmation abuse case in the threat-model delta.

**Privacy consequences:** Directly implements the Owner's retention
requirement (OD-012) — no durable email archive, memory-only body handling.
Evidence-record retention is now explicitly decoupled from account
connection state (see above), removing the prior ambiguity about what
disconnect does.

**Operational consequences:** Users see derived evidence and, for MEDIUM
confidence, a minimal snippet — not a searchable email archive. Disconnect
stops sync without silently erasing tracked application history.

**Residual risk:** Narrow retention means a missed/low-confidence message
cannot be re-parsed later from ASTRA's own storage. Read-only enforcement is
a code-level control layered on ADR-0007's scope selection — both required.
Registered as risk **R-17** (shared with ADR-0009), rating 2/2, Moderate,
state **OPEN — treatment planned for v1.1** — registered, not
residual-accepted.

**Evidence (implementation, independent of ADR status):** Pending. Required:
the actual granted scope confirmed read-only; a test asserting the Gmail
client wrapper exposes no mutating method; a test confirming no full body/
HTML persists in the database or any on-disk cache after a sync/parse
cycle; a test proving a single-signal match cannot reach HIGH confidence; a
test proving missing/contradictory authentication evidence caps a message
at MEDIUM.

**Recommendation:** APPROVE the architecture decision (see "ADR status
semantics" above for what Accepted does and does not certify).

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

**Proposed decision (amended):** Every adapter is bound by the same rules
regardless of source: URL validation reusing ASTRA's existing outbound-fetch
policy (`policy.py`); size/time-capped response reading, **implemented/
reused independently on current `master` as part of v1.1** — this
architecturally does **not** depend on the unmerged `hardening/l2-r13-r14`
branch, which stays parked per OD-015 and may change independently; that
branch is a **design reference only**, not a code dependency; strict/
defensive parsing rejecting unexpected shapes; per-provider failure
isolation; source/URL provenance retained on every normalized record.

- **UI sanitization and AI-bound untrusted-data framing are distinct
  controls, not one:** UI sanitization escapes/sanitizes provider-sourced
  text/HTML before display (targets the browser as execution context).
  AI-bound framing separately normalizes and delimits the same class of
  content as untrusted *data* when passed to the AI-comparison path
  (targets the model as execution context) — satisfying one does not
  satisfy the other. **Provider-sourced content passed to the AI path must
  never authorize an action, invoke a tool, or mutate application state**;
  that path remains advisory/explanatory output only (ADR-0001).

**Security consequences:** Closes SSRF exposure for the new external-URL
surface by reusing an already-reviewed control. Guards both the UI (via
sanitization) and the AI-comparison path (via untrusted-data framing and a
no-action-authorization rule) against provider-sourced content, as two
separate controls.

**Privacy consequences:** No new personal-data class — job postings are not
personal data — but provider content is still subject to the same
display/export sanitization review as any other rendered content.

**Operational consequences:** Per-source failure isolation plus the funnel
telemetry (planning doc §5) gives visibility into which sources are healthy,
directly targeting the "12/12 healthy, zero results" failure mode that
motivated this milestone.

**Residual risk:** A provider that changes its response shape without notice
fails closed for that source (intentional). A user-pasted malicious
manual-import URL is contained the same way a bad provider response would
be. Registered as risk **R-17** (shared with ADR-0008) and **R-18**
(reconciliation/status-evidence spoofing), both rating 2/2, Moderate, state
**OPEN — treatment planned for v1.1** — registered, not residual-accepted.

**Evidence (implementation, independent of ADR status):** Pending. Required:
tests proving the SSRF policy rejects loopback/private-range provider or
job URLs; a test proving an oversized response is capped by v1.1's own
independent implementation and does not block other providers; a test
proving provider HTML is sanitized before any display path; a test proving
provider-sourced content passed to the AI path cannot trigger a tool call,
action, or state mutation.

**Recommendation:** APPROVE the architecture decision (see "ADR status
semantics" above).

## Threat-model delta summary

Full document: `docs/security/THREAT_MODEL_CHANGE_V1_1_DISCOVERY_GMAIL.md`.

Covers every area the Owner specified, **plus one added this revision**:
OAuth authorization and refresh tokens; two Gmail identities; token theft;
**OAuth callback interception/CSRF/authorization-code substitution/account
mix-up (new abuse case)**; mailbox-data minimization; malicious email
HTML/text/URLs; parser/resource exhaustion; job-provider content; malicious
job links; SSRF; duplicate/reconciliation manipulation; status-evidence
spoofing; local storage; logs/audit events; optional future AI parsing
(explicitly out of scope for the initial pass).

Ten abuse cases are now enumerated (nine plus the new OAuth-callback case)
with STRIDE/CWE classification, preconditions, controls, residual risk, and
required negative tests. The new case's controls: PKCE S256, random state,
ephemeral loopback listener, loopback-only binding, exact state validation,
one-shot callback, post-exchange Gmail identity binding. Its required
negative tests: incorrect state rejected; missing state rejected; reused
callback rejected; invalid PKCE verifier rejected; credential cannot attach
to the wrong Gmail account record.

The retention/disconnect wording contradiction in the prior revision
(evidence records described as both "retained until disconnect" and
"not deleted by disconnect") is resolved: disconnect deletes the token and
sync state only; evidence records require a separate explicit deletion
action. OAuth credentials are now explicitly excluded from backup/export in
the delta's data-flow table and privacy-impact section.

No test evidence exists yet — this remains the pre-implementation delta.

**Risk-register entries — registered, not residual-accepted:**

| ID | Risk | L/I | State |
|---|---|---|---|
| R-16 | Gmail OAuth refresh-token theft or misuse (incl. OAuth-callback abuse case) | **2/3 = 6, HIGH** | OPEN — treatment planned for v1.1 |
| R-17 | Malicious/spoofed email or job-provider content reaching the user, parser, or AI-comparison path | 2/2, Moderate | OPEN — treatment planned for v1.1 |
| R-18 | Reconciliation/duplicate manipulation or status-evidence spoofing | 2/2, Moderate | OPEN — treatment planned for v1.1 |

R-16's rating changed from 2/2 to **2/3 = 6, HIGH** this revision: impact is
severe (3), not material (2), because a `gmail.readonly` token exposes the
entire mailbox's read access, not merely ASTRA's own minimized records.

**Framework impact:** ASVS credential/token-storage and input-validation/
SSRF-prevention requirements become newly applicable where previously N/A
under the local-only model; exact clause mapping is deferred to when these
ADRs are Accepted and implementation begins, so it is written against real
code rather than a still-changing design. SSDF evidence expands to cover the
new external-credential and external-data paths. No SLSA/CycloneDX impact
beyond a routine SBOM/lockfile update for the Gmail API client dependency
(R-04 applies).

## Owner decisions to close this packet — ALL APPROVED 2026-09-13 (OD-018)

- [x] Approve ADR-0007 (Gmail OAuth and credential storage) as an
      architecture decision. **Status: Accepted.** Approval does not certify
      implementation — implementation evidence remains Pending (see "ADR
      status semantics").
- [x] Approve ADR-0008 (Gmail read-only mailbox trust boundary) as an
      architecture decision. **Status: Accepted.** Implementation evidence
      Pending.
- [x] Approve ADR-0009 (external job-provider trust boundary) as an
      architecture decision. **Status: Accepted.** Implementation evidence
      Pending.
- [x] Approve the threat-model delta
      (`THREAT_MODEL_CHANGE_V1_1_DISCOVERY_GMAIL.md`), including the new
      OAuth-callback abuse case. **Status: Approved.**
- [x] Approve **registering** R-16 (2/3=6 HIGH), R-17 (2/2), and R-18 (2/2)
      as OPEN risks with treatment planned for v1.1. **Status: Registered —
      this is registration, not residual-risk acceptance.** Residual-risk
      acceptance is a separate, later decision made only after the controls
      above and their negative tests exist and are independently reviewed.

All five are approved. The three ADRs are `Accepted` (architecture approval
only — implementation evidence stays `Pending` until built and verified per
issue #48). Implementation authorized to begin: the first branch is the
Discovery Query Planner (Phase A, issue #37).
