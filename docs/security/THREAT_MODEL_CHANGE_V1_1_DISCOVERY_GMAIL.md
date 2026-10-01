# Threat-model change — v1.1 Discovery v2 and Gmail application capture

- **Release / source SHA:** Planning-stage; targets v1.1.0. Written against
  `master` at the v1.1 planning-packet commit. No implementation exists yet.
- **Owner / reviewer / date:** Ayham (Owner review requested) / Claude Code
  (drafted) / 2026-09-13.
- **Related issue, PR, ADR, finding, or risk:** OD-010 through OD-017;
  `docs/planning/V1_1_DISCOVERY_AND_APPLICATION_INTELLIGENCE.md`; ADR-0007,
  ADR-0008, ADR-0009; risk-register additions R-16, R-17, R-18 below
  (registered OPEN, not residual-accepted).

## Change summary

v1.1 adds two materially new data flows to a product whose threat model
(`docs/THREAT_MODEL.md`) was built for a purely local, single-external-AI-call
architecture:

1. **Discovery v2**: fetching job postings from multiple external providers
   (employer pages, Greenhouse, Lever, Ashby, Workable, possibly job-search
   APIs, manual imports) instead of the current narrower discovery source set.
2. **Gmail application capture**: read-only OAuth access to two user-owned
   Gmail accounts to detect application-confirmation signals.

Both introduce untrusted external content into ASTRA's pipeline and, for
Gmail, a new class of long-lived secret (OAuth refresh tokens) that did not
exist before. This document is the planning-stage delta required before
implementation (OD-017); it does not claim the existing threat model already
covers these flows.

## Delta

| Area | Before | After | Evidence / action |
|---|---|---|---|
| Assets and sensitivity | Local job/application/CV/profile data; per-request AI credentials (`backend/providers.py`) | Adds: two Gmail OAuth refresh tokens; minimized per-message application-evidence records (ADR-0008); normalized external job records from multiple providers | ADR-0007 (token storage), ADR-0008 (data minimization) |
| Actors and privileges | Local OS user (trusted, ADR-0002); malicious local/shared-host actor (R-15) | Adds: external job-provider operators (untrusted, ADR-0009); malicious/spoofed email senders (new); Google OAuth infrastructure (trusted third party for the auth flow only) | ADR-0009 §"Actors"; this document's abuse cases below |
| Entry points and interfaces | Loopback HTTP API; existing AI provider calls; existing job-import paths | Adds: Gmail API read calls (per account); provider-adapter HTTP fetches (per source); OAuth authorization-code/loopback-redirect exchange during account setup | ADR-0007, ADR-0009 |
| Data flows and storage | SQLite local DB; local AI-usage ledger; local security-event log | Adds: encrypted-at-rest OAuth refresh tokens (OS-backed, e.g. DPAPI, `CurrentUser` scope), **excluded from normal backup/export/diagnostic-bundle paths**; minimized Gmail-evidence rows in the local DB (survive account disconnect; deleted only by a separate explicit user action, not by disconnect); normalized job-provider rows in the local DB | ADR-0007, ADR-0008 |
| Trust boundaries | OS-account/localhost boundary (ADR-0002, R-15) | Unchanged as the primary boundary; token theft by an actor already inside that boundary is a new *instance* of R-15's existing residual, not a new boundary | ADR-0007 "Security and privacy impact" |
| Deployment/network exposure | Outbound calls to a fixed AI provider only, policy-checked (`policy.py`) | Adds outbound calls to Gmail's API and to N job-provider endpoints/URLs, all routed through the same validated-fetch policy (ADR-0009) | `policy.py` reuse, not a new fetch path |
| Dependencies/build/update path | Existing AI SDK/HTTP client dependencies | Adds a Gmail API client library dependency (exact package TBD at implementation; subject to R-04 dependency-substitution controls: lockfile hashes, SBOM update) | R-04; SBOM/lockfile update required at implementation |

## Abuse cases

| Abuse case | STRIDE / CWE if confirmed | Preconditions | Controls | Residual risk | Test/evidence |
|---|---|---|---|---|---|
| OAuth refresh token exfiltration via logs, exports, or diagnostic bundles | Information Disclosure / CWE-532 (insertion of sensitive information into log file) | A code path logs, exports, or bundles the token | Tokens never logged; encrypted-at-rest storage (ADR-0007); privacy/export review (`docs/PRIVACY_DATA_FLOW.md` conventions extended) | Local actor with OS-account access could still read the store under that same user context (matches R-15's existing scope) | Negative test: token absent from log output, export bundles, and diagnostics after a sync cycle |
| OAuth refresh token theft by a local/shared-host actor | Information Disclosure / Spoofing | Actor already inside the OS-account boundary (R-15 precondition) | OS-backed encryption at rest (DPAPI); per-account isolation (ADR-0007) | Same actor could still act as the user generally (R-15's existing acceptance); not a new boundary | Manual review of storage mechanism; no plaintext-on-disk test |
| OAuth callback interception / CSRF / authorization-code substitution / account mix-up: an attacker intercepts or forges the OAuth redirect callback, substitutes their own authorization code, or the user's consent completes against an unintended Gmail account | Spoofing / CSRF / CWE-352 (cross-site request forgery), CWE-346 (origin validation error) | Attacker can reach the local loopback listener during the auth window, predict/observe the callback, or the user has multiple Google sessions active in-browser | PKCE with S256 code-challenge method; cryptographically random `state` parameter validated for exact match; random ephemeral loopback port bound only to loopback (never `0.0.0.0`); one-shot callback consumption (no replay); post-exchange identity binding — ASTRA queries the authorized Gmail profile and binds the credential to that actual account before persisting (ADR-0007) | Residual limited to an attacker who already has local-loopback access during the narrow auth window (overlaps R-15's local-actor precondition); PKCE+state closes remote CSRF-style substitution | Negative tests: incorrect `state` rejected; missing `state` rejected; reused/replayed callback rejected; invalid PKCE verifier rejected; credential cannot be attached to the wrong Gmail account record (identity-binding check fails closed) |
| Malicious/phishing email crafted to look like a real application-confirmation, causing a false HIGH-confidence auto-reconciliation | Spoofing / CWE-345 (insufficient verification of data authenticity) | Attacker knows or guesses the user is job-hunting and sends a spoofed confirmation | Deterministic parsers matched to known platform sender/domain/template patterns (OD-012); **HIGH confidence requires multiple independent corroborating signals** (sender identity, structural template match, and consistent extracted fields), not a single matched element; **message authentication evidence (SPF/DKIM/DMARC alignment, where Gmail exposes it) is incorporated as one required signal — missing/contradictory authentication evidence caps the result at MEDIUM regardless of content match** (ADR-0008); conflict-resolution rule (a weak signal can never downgrade a stronger manually confirmed state) | A well-crafted spoof matching a known template's exact sender/format *and* passing authentication checks (e.g. from a genuinely compromised sending account) could still pass as HIGH confidence | Requires: parser test corpus including at least one deliberately spoofed message per supported platform template; confirm it does NOT reach HIGH confidence; a separate test confirming a message with missing/contradictory authentication evidence is capped at MEDIUM even with a strong template match |
| Malicious HTML/links in email body rendered as trusted, or auto-followed | Tampering / CWE-79-adjacent (untrusted content), CWE-601 (open redirect if links followed) | Email body reaches a display or link-following code path unsanitized | Sanitization before any display (ADR-0008); no automatic link-following; URL validation via `policy.py` if any link is ever fetched server-side | None identified if controls hold; residual is a sanitization-library gap | Test: known malicious-pattern fixture (script tag, javascript: URI) rendered with no execution |
| Malformed or oversized email/job-provider payload causing parser resource exhaustion | Denial of Service / CWE-400 | Attacker or misbehaving provider sends an oversized or deeply nested payload | Size/time-capped reading, implemented/reused independently on current `master` as part of v1.1 (R-13's parked branch is a design reference only, not a code dependency — ADR-0009); defensive/strict parsing that rejects unexpected shapes (ADR-0009) | A parser bug could still hang on a crafted-but-under-cap payload | Test: oversized and deeply-nested fixture inputs handled without unbounded memory/time growth |
| SSRF via a job-provider URL or a link embedded in a job posting/email pointing at an internal/loopback/private-range address | Elevation of Privilege via SSRF / CWE-918 | ASTRA's backend fetches a URL sourced from external content | Reuse of `policy.py`'s existing validated-fetch (loopback/private-range/redirect rejection) for every new URL source (ADR-0009) | None identified beyond `policy.py`'s existing known limitations (R-01) | Test: loopback/private-range/link-local URL from a provider or email rejected before fetch |
| Duplicate/reconciliation manipulation: a crafted email or re-imported job causes a false merge with, or false split from, an existing application record | Tampering / CWE-354-adjacent (data integrity) | Attacker controls or predicts identifying fields (company/role/date) used for reconciliation matching | Reconciliation matches on multiple fields (company, role, approximate date, source URL where available), not a single guessable field; provenance/audit trail records every transition's source | A sufficiently well-informed spoof (attacker knows the user's real application details) could still force a false merge | Test: reconciliation matcher requires multi-field agreement; a single-field match alone does not merge |
| Status-evidence spoofing: a forged or manipulated signal claims a stronger application state than actually occurred (e.g., fake "interview" confirmation) | Spoofing / Repudiation | Same precondition as the phishing case above, escalated to a later-stage state | Confidence gating; the conflict-resolution rule (weak signal never downgrades a stronger manually-confirmed state) also implies a weak signal should not be allowed to *upgrade* past what its confidence supports; state-machine transition rules bound which states an automated signal of a given confidence may set | Deterministic-parser template spoofing remains the limiting factor, same as the first abuse case | Test: a MEDIUM/LOW-confidence signal attempting to set INTERVIEW/OFFER is routed to Needs Review, never auto-applied |
| Future AI-based email classification (if ever added as a fallback per OD-012) treats attacker-controlled email content as instructions rather than data | Tampering / prompt-injection-style | Only applies if/when AI fallback classification is implemented (explicitly out of scope for the initial v1.1 pass) | Must reuse the existing untrusted-data framing pattern (`backend/providers.py`) if and when built, with UI sanitization and AI-bound untrusted-data framing kept as distinct controls (ADR-0009); AI-derived output must never itself authorize an action, invoke a tool, or mutate application state; this document flags it now so it is not forgotten later | Not yet applicable; tracked as a future-work note, not a current control gap | N/A until that feature is proposed; requires its own threat-model delta at that time |

## Privacy and operational impact

- **Personal data collected, transmitted, retained, exported, or deleted
  (resolved wording — see ADR-0008):** New personal data classes: (1)
  Gmail-derived minimized evidence records (ADR-0008 field list) —
  **retained independent of account connection state**; disconnecting the
  originating Gmail account (ADR-0007) deletes that account's token and
  sync/integration state but does **not** delete these evidence records.
  Removing the evidence records themselves requires a separate, explicit
  user action (e.g. deleting the specific application record), consistent
  with the application state model's provenance/history rules. (2)
  transient full email content during parsing only — memory-only, no
  implementation-defined disk cache, not persisted absent a specific
  approved exception (ADR-0008). (3) normalized external job postings —
  not personal data, but sourced from third parties and subject to the
  same export/privacy review as any other displayed content. Export/
  deletion paths (`privacy.py`, R-07) must be extended to cover the new
  Gmail-evidence table(s) so a full data export/delete actually includes
  them; the OAuth token store is handled separately (see below), not
  through the normal export/deletion path.
- **Secrets/credentials/session impact:** Adds two OAuth refresh tokens per
  installation (one per Gmail account) as a new secret class, protected per
  ADR-0007. **The OAuth credential store is excluded from ASTRA's normal
  backup, export, and diagnostic-bundle paths** — those paths must not
  read, copy, or bundle it; account disconnect (not export) is the
  mechanism for removing a token. Existing session/access-key model
  (ADR-0003) is unaffected — Gmail tokens are a separate credential, not a
  replacement for or extension of ASTRA's own session mechanism.
- **Logging/telemetry impact:** New security-event types are needed for
  OAuth grant, OAuth revoke/disconnect, parser failure, and reconciliation
  conflict, extending `backend/security_events.py`'s taxonomy (relevant to
  R-14, which is deliberately on hold for v1.2 per OD-015 — these new event
  types should be added as part of v1.1's own implementation, not by pulling
  the parked `hardening/l2-r13-r14` branch forward).
- **Backup/recovery/incident impact:** The OAuth token store is excluded
  from ASTRA's normal backup/export paths (ADR-0007), so a standard ASTRA
  backup does not carry the token — losing or restoring a backup means
  re-authorizing Gmail, not a token-exposure event via the backup itself.
  Gmail-derived evidence records (not the token) do follow normal
  backup/export, per the resolved retention rule above. An incident (e.g.,
  suspected token compromise) response is: disconnect the affected account
  (ADR-0007 revocation), which the user can do without ASTRA "knowing" the
  token was compromised — no automatic compromise detection is proposed
  for v1.1.

## Decisions and verification

- **Required ADR or risk registration:** ADR-0007, ADR-0008, ADR-0009 (all
  Proposed, pending Owner approval — OD-016). Registration (not
  acceptance) of R-16, R-17, R-18 below is requested from the Owner
  (OD-017); registering a risk records it as tracked and OPEN with
  planned treatment — it is explicitly **not** the Owner accepting its
  residual risk. Residual-risk acceptance is a separate, later decision
  made only after the controls in the abuse-case table above are
  implemented and their negative tests pass.
- **ASVS/SSDF/SAMM/SBOM/SLSA impact:**
  - **ASVS:** requirements in the credential/token-storage and
    session-secret-handling areas, and in input-validation/SSRF-prevention
    for the new external-data surface, become newly applicable where they
    were previously N/A under the local-only, single-AI-call model. The
    exact clause-level mapping (extending
    `docs/security/OWASP_ASVS_5.0.0_MAPPING.md`) is deferred to when
    ADR-0007/0009 are Accepted and implementation begins, so the mapping is
    written against real code rather than a still-changing design — this
    document does not claim a specific clause result now.
  - **SSDF:** evidence expands to cover the new external-credential
    (Gmail OAuth) and external-data (job providers) handling paths.
  - **SAMM:** no claimed change; not currently tracked with dated evidence
    for this project.
  - **SBOM:** anticipated that a Gmail API client library dependency would
    need lockfile hashes and an SBOM update at implementation (R-04
    applies). **Outcome at issue #44: no dependency was added.** The
    authorization flow is implemented against already-pinned `httpx`/
    `httpcore` plus the Python standard library, so the lockfile, SBOM
    inputs and dependency-review evidence are unchanged. Re-evaluate if
    issue #45 introduces a Gmail client library.
  - **SLSA:** no build/provenance impact — no new build/release artifact
    type is introduced.
- **Negative tests and review:** enumerated per abuse case above. Per
  `docs/architecture/adr/README.md`'s status semantics, an ADR's `Accepted`
  status reflects Owner approval of the architecture decision, not proof
  that these tests exist — each ADR's own "Evidence and validation"
  section tracks implementation-evidence status independently, and that
  evidence (including these negative tests) is required before the
  described controls may be relied upon in the v1.1 release evidence pack
  (issue #48), regardless of the ADR's status field.
- **Implementation status of the OAuth-callback abuse case (issue #44,
  `feature/44-gmail-oauth`, not merged):** the enumerated negative tests for
  that one abuse case now **exist and pass** — incorrect `state` rejected,
  missing `state` rejected, duplicate `state` rejected, replayed callback
  rejected, expired/cancelled/superseded attempts rejected, concurrent
  callbacks producing exactly one terminal result, and a credential that
  cannot be attached to a conflicting Gmail account record. PKCE S256, the
  loopback-only ephemeral listener, one-shot callback consumption and
  post-exchange identity binding are implemented as described. Two caveats:
  this covers the authorization/credential layer only, and **no live Google
  consent-screen run has been performed**, so the assumption below about
  Google's documented behaviour is still only documentation-verified. Every
  other abuse case in the table above remains **Pending** — issues #45-#47
  have not started. See `docs/architecture/GMAIL_OAUTH.md`.
- **Google documentation verified (2026-09-16), not live-verified:** the
  installed-app flow, Gmail scope classification, revocation endpoint and
  `users.getProfile` contract were each checked against Google's current
  published references during #44. One finding materially affects this
  delta's account-mix-up control: at the `gmail.readonly` scope,
  `users.getProfile` returns **no opaque immutable subject identifier** —
  only `emailAddress`. Identity binding therefore uses the authenticated
  address, which is authoritative but **not immutable**. Requesting an
  OpenID/`userinfo.email` scope purely to obtain one was rejected as
  contrary to minimization. Recorded as a residual limitation, not resolved.
- **Remaining assumptions and recheck triggers:** assumes Google's OAuth
  infrastructure and API behave as documented (verified against current
  published documentation during #44, but **not** independently verified
  against live behaviour); assumes Windows DPAPI (or the OS-backed
  equivalent chosen at implementation) provides the protection ADR-0007
  describes — #44 enforces that the selected keyring backend is the native
  DPAPI-backed Windows Credential Manager under `CurrentUser` and fails
  closed otherwise, but the protection property itself is Microsoft's, not
  independently verified here. Recheck this
  delta if: a broader Gmail scope than read-only is ever requested; AI-based
  email classification is added (see the abuse-case table); ASTRA adds a
  third external mailbox provider; or the provider-adapter list grows to
  include a source that cannot honor the size/time-cap or URL-validation
  controls.
- **Owner decision: APPROVED (2026-09-13, OD-018).** This delta, ADR-0007,
  ADR-0008, and ADR-0009 are approved as architecture decisions (each ADR's
  status moves to Accepted); R-16/R-17/R-18 below are registered as OPEN
  risks with treatment planned for v1.1 — registration, not residual-risk
  acceptance. Implementation evidence for all three ADRs and negative-test
  evidence for every abuse case above remain **Pending** until implemented
  and independently reviewed (issue #48). This approval authorizes
  implementation to begin on the approved backlog (starting with issue #37),
  not a claim that any control described here yet exists in code.

## Risk-register additions — registered, not residual-accepted

These are registered in `docs/security/RISK_REGISTER.md` at the Owner's
request. Per that document's own header, and per this round's explicit
Owner instruction: **registering a risk is not the Owner accepting its
residual risk.** State `OPEN — treatment planned for v1.1` means the risk
is tracked and treatment (the controls in the abuse-case table above) is
planned for this milestone; residual-risk acceptance is a distinct, later
decision made only once those controls and their negative tests exist.

| ID | Risk | L/I (inherent) | State | Rationale |
|---|---|---|---|---|
| R-16 | Gmail OAuth refresh-token theft or misuse (local/shared-host actor, or accidental logging/export) | **2/3 = 6, HIGH** | OPEN — treatment planned for v1.1 | New secret class introduced by ADR-0007. Impact rated **severe (3)**, not material (2): the granted scope is `gmail.readonly`, so theft of the refresh token exposes the **entire mailbox's read access**, not merely ASTRA's own minimized evidence records — broader than the impact of a typical local ASTRA-data compromise under R-15. Likelihood (2, plausible) matches R-15's existing local-actor precondition. |
| R-17 | Malicious/spoofed email or job-provider content (phishing links, malformed/oversized payloads, spoofed confirmation templates) reaching the user, the parser, or the AI-comparison path | 2/2, Moderate | OPEN — treatment planned for v1.1 | New untrusted-content surface from ADR-0008/ADR-0009; mitigated by sanitization, size/time caps, deterministic-parser template matching with multi-signal/authentication-evidence gating, and untrusted-data framing, but not eliminated |
| R-18 | Reconciliation/duplicate manipulation or status-evidence spoofing causing an incorrect application-state transition | 2/2, Moderate | OPEN — treatment planned for v1.1 | New integrity risk from the application state model's automated-evidence path; mitigated by multi-field reconciliation matching and confidence-gated state transitions, but a sufficiently well-informed spoof remains possible |

Also registers the new OAuth-callback abuse case (state/PKCE/loopback/
identity-binding) under **R-16** rather than as a separate risk ID — it is
a threat against the same asset (the OAuth credential) as the rest of
R-16, mitigated by the controls in ADR-0007's Decision section.

## Issue #45 implementation delta (2026-09-17)

The #44 foundation is merged via PR #66. The bounded mailbox read path now
exists, documented in [Gmail sync](../architecture/GMAIL_SYNC.md). It adds no
dependency and no Gmail mutation/AI/reconciliation path. Receiver-header trust,
per-grant evidence identity, capped query pagination, malformed input, public
URL minimization, body non-retention, disconnect retention and full erasure are
exercised with fictional fixtures. Transport deadlines now include bounded DNS,
pinned dialing and each TLS/read/write operation; private transport debug
traces are suppressed per context. No parked v1.2 code was merged.

These are implemented controls with self-verification, not an independent
review, live mailbox accuracy result, or residual-risk acceptance. Earlier
planning/pending statements above are historical. R-16/R-17/R-18 stay OPEN;
#46 reconciliation and #48 release assurance are not implemented by #45.

Framework delta: SSDF implementation/verification evidence expands through
adversarial input and privacy regressions. ASVS input validation, output
handling, sensitive-data storage/logging and API access boundaries are exercised
by the #45 suites; no clause or level claim is newly asserted. SAMM/SLSA claims
are unchanged. No dependency, lockfile, SBOM input or release artifact changed.

## Issue #46 implementation note (reconciliation and application state)

#46 implements the two abuse cases this delta registered under R-18 —
*duplicate/reconciliation manipulation* and *status-evidence spoofing*. See
[Application state](../architecture/APPLICATION_STATE.md) for the as-built
design.

Controls now implemented against those abuse cases:

- **Multi-field matching, not a single guessable field.** A merge requires the
  normalized employer to agree *and* at least two further independent
  corroborations among role, application-date proximity, application-URL
  identity and source platform — at least three independent fields. Comparison
  is deterministic normalized-key equality and a fixed 14-day window; a field
  with no usable value on either side contributes nothing rather than acting as
  a wildcard. No AI, embedding similarity, web lookup or mailbox search is
  used.
- **A contradictory requisition URL is decisive.** When both records resolve to
  a job-specific posting identity and those identities differ, the records name
  two different postings and automatic linking is blocked outright — agreement
  on employer, title, approximate date and platform cannot outweigh it, because
  those four are exactly what two genuinely separate applications to the same
  employer share. This closes the case where an attacker (or a coincidence)
  knows the guessable fields but not the posting. The contradiction test is
  deliberately narrow: a generic careers root, tenant root, login or search
  page establishes no identity and contradicts nothing, and two spellings of
  one posting normalize equal. Resolving a contradiction is offered to the user
  as a review decision, never taken by ASTRA.
- **Ambiguity never mutates.** More than one strong candidate produces a
  bounded Needs Review decision and a `APPLICATION_RECONCILIATION_CONFLICT`
  security event. No application is mutated and none is created.
- **Nothing is ever created from evidence.** Reconciliation links to an
  existing application or leaves the evidence unmatched and reviewable, so an
  unsolicited or spoofed message cannot conjure a record and an existing
  manually recorded application cannot be duplicated.
- **Confidence-bounded transitions.** `APPLIED` is the only canonical state an
  automated source may set — at HIGH confidence only, and only on a unique
  strong match — because #45 parses no later-stage message. MEDIUM produces a
  review item with no mutation; LOW never mutates. A later-stage state is
  unreachable from any automated path at any confidence.
- **Manual authority.** A weaker automated signal can neither downgrade nor
  re-assert a state a manual source established, enforced both by the
  forward-only transition table and by an explicit manual-authority check.
- **Provable transitions.** Every accepted change appends an immutable history
  row identifying who or what asserted it, the source category, confidence,
  Gmail account/message/parser identity, bounded evidence tokens, field
  agreement, both timestamps and a bounded reason code.
- **Bounded logging.** The two new security-event types use fixed reason text
  and a `result` field restricted to the refusal-reason vocabulary. No company
  name, role, subject, URL, email address, message identifier or exception
  string can reach the log through this path.

These are implemented controls with self-verification, not an independent
review, a live mailbox validation, a measured real-world reconciliation
accuracy result, or a residual-risk acceptance. **R-18 remains OPEN**, and the
residual identified in the abuse-case table above is unchanged: an attacker who
already knows the user's real application details could still force a false
merge, and a spoof satisfying #45's HIGH-confidence signals could still be
accepted. Multi-field matching raises the cost; it does not eliminate the abuse
case. R-16 and R-17 are unaffected by #46. The parked v1.2 tamper-evident
logging work (OD-015) was not pulled forward.

Framework delta: SSDF implementation/verification evidence expands through the
state-machine, reconciliation, migration and deletion regressions. ASVS input
validation, output handling, sensitive-data storage/logging and API access
boundaries are exercised by the #46 suites; no clause or level claim is newly
asserted. SAMM/SLSA claims are unchanged. No dependency, lockfile, SBOM input
or release artifact changed, and no evaluation-provenance-pinned file was
modified.

## Issue #48 as-built reconciliation (2026-10-01)

This section closes the gap between the planned delta above and the code on
`master` at `22642e88f516f827c1dc4250bc72eb259306fafd`. Claude Code wrote it
for issue #48. It is not yet independently reviewed or Owner-approved. The
earlier sections are dated records. Statements in them that a control is
"pending", that #44 or #46 is "not merged", or that a dependency would be
added are historical, and this section supersedes them.

### Abuse cases against the as-built controls

Each requirement ID points to an entry in
`tests/security/v1_1_assurance_inventory.py`, which names the exact tests.
The consolidated suite runs with `python -m pytest -m v1_1_assurance`.

| Abuse case | As-built control | Evidence (requirement IDs) | Status | Residual |
|---|---|---|---|---|
| TM-1 Token exfiltration via logs, exports or diagnostics | A secret wrapper redacts every representation. Tokens and the client secret never reach logs, events, SQLite bytes, export, backup, diagnostics, API bodies or exception text. The credential store is outside every export and backup path. | A7-NEVER-LOGGED, A7-EXCLUSION, A7-CLIENT-SECRET, TM-PRIVACY-PATHS, TM-AUDIT-EVENTS | Implemented and tested | A future code path could still log a value; the sentinel tests cover the paths that exist |
| TM-2 Token theft by a local or shared-host actor | Native Windows credential store (DPAPI, CurrentUser) only, with no plaintext fallback. Per-account opaque keys. Access tokens and attempts are memory-only. Disconnect removes local access even when Google fails. | A7-STORAGE, A7-ISOLATION, A7-REVOCATION | Implemented, tested, live-validated in #44 | Unchanged: an actor running as the same OS user can read the store (an R-15 instance). R-16 stays 2/3 |
| TM-3 Callback interception, CSRF, code substitution or account mix-up | PKCE S256, a 256-bit single-use state compared in constant time, a numeric-loopback ephemeral listener, five-minute attempts, fixed host-pinned Google endpoints, an exact scope check, and binding to the identity Google returns. | A7-SCOPE, A7-PKCE, A7-STATE, A7-LOOPBACK, A7-IDENTITY, A7-TRANSPORT, A7-API-BOUNDARY, A7-SECONDARY-GATE | Implemented, tested, live-validated in #44 | An actor with loopback access during the five-minute window. Identity binding uses the authenticated address, which is authoritative but not immutable |
| TM-4 Spoofed confirmation reaching HIGH | Deterministic Greenhouse, Lever and Workday templates. HIGH needs sender, structure, body and field consistency plus receiver authentication from the header Google adds. Missing, failed, foreign, misaligned or contradictory authentication caps the result at exactly MEDIUM, which goes to Needs Review. | A8-MULTI-SIGNAL, A8-AUTH-CAP | Implemented and tested with fictional fixtures | A genuinely authenticated, compromised sender using an exact template still reaches HIGH. Real-world parser accuracy is unmeasured; there was no live mailbox validation |
| TM-5 Malicious HTML or links rendered or followed | Email HTML becomes bounded plain text in memory and is never stored. Unsafe URLs are dropped and no link is fetched. Provider HTML is reduced to text. The UI renders all of it through React text expressions, and a test rejects any raw-HTML sink. | A8-HOSTILE-CONTENT, A8-NON-RETENTION, A9-UI-SANITIZATION | Implemented and tested | `adapters.clean` unescapes provider HTML twice (ASVS 1.1.1, an existing Level 2 FAIL). Display stays safe because React escapes text |
| TM-6 Parser or resource exhaustion | Provider responses are capped encoded and decoded, with deadline-bounded streaming and bounded redirects, retries and pagination. Gmail messages are capped by size, MIME parts and depth. Failures are isolated per source and per message. All of it is on `master`; the parked R-13 branch was not used. | A9-RESPONSE-CAPS, A9-OVERSIZED-ISOLATION, A9-STRICT-PARSING, A9-FAILURE-ISOLATION, A8-PARSER-BOUNDS, A8-BOUNDED-SYNC | Implemented and tested | A parser bug under the caps could still be slow; the caps bound the cost |
| TM-7 SSRF | Greenhouse, Lever and Ashby fetches go through `job_providers/transport.py`, which resolves once, refuses any private, loopback or link-local address, dials the validated address and revalidates every redirect. OAuth and Gmail calls go only to pinned Google hosts. Email links are never fetched. | A9-SSRF, A8-HOSTILE-CONTENT | Implemented and tested for the v1.1 paths | SmartRecruiters and generic `parse_url` sources still use the legacy `adapters.fetch`, which validates with `policy.py` and connects separately: the existing R-01 DNS race, unchanged by v1.1. Arbitrary URL import is disabled |
| TM-8 Reconciliation or duplicate manipulation | A merge needs the employer plus two further independent fields. A contradictory requisition URL blocks linking. Ambiguity creates a review item, never a merge. Evidence never creates a job or application. Fingerprint-only dedupe evidence never merges. | TM-RECONCILE, A9-PROVENANCE | Implemented and tested; #46 independently approved | Unchanged: an attacker who knows the real employer, role, date and requisition URL can still force a false link. Real-world accuracy is unmeasured |
| TM-9 Status-evidence spoofing | Automated evidence can set only APPLIED, only at HIGH, only on a unique strong match. Later states are unreachable from any automated path at any confidence. Manual states cannot be overridden or re-asserted, and no route accepts a target state. This is stricter than planned. | TM-STATUS-SPOOF | Implemented and tested; #46 independently approved | Inherits the TM-4 residual: a HIGH spoof can set APPLIED and nothing later |
| TM-10 AI email classification | Not built in the inspected implementation. The dependency guard checks declared known AI imports at every nesting level, supported positional literal import calls and modules loaded at import time. It does not prove complete runtime reachability or cover computed imports, keyword/indirect loader forms and transitive lazy dependencies; those require review. Provider text in the separate advice path travels as JSON data, with no tools, a strict output schema and tested absence of application-state mutation. | TM-AI-EMAIL-GUARD, A9-AI-FRAMING | Not applicable to mailbox classification; bounded dependency guard | An AI mailbox feature needs its own threat-model delta and runtime abuse tests. A passing dependency guard cannot replace that review |

### Surfaces added since the planning delta

- **#43 telemetry and #46.2-A Start Scan** add the read-only
  `/api/search/telemetry*` routes and the `/api/scan/*` preview, start and
  cancel routes. Neither changes a trust boundary. A new #48 test walks the
  live route table and proves that every private route, these included,
  keeps the Origin, cross-site, access-key and demo-mode guards.
- **No new dependency.** No product lockfile changed between `v1.0.0` and
  `22642e8`. The Gmail client library this delta anticipated was never
  added.
- **Second Gmail account.** The two-account design exists, but the secondary
  slot is disabled in code: it cannot start OAuth or sync. OD-012 allows it
  to be enabled only after the primary account's sync, parsing and
  reconciliation are validated, and that has not happened (#45 and #46 had
  no live mailbox validation). This delta therefore covers one-account
  operation. Enabling the second account is a recheck trigger.

### Gaps found by #48

| Gap | Disposition |
|---|---|
| The ASVS mapping still said ASTRA had no OAuth client | Corrected in this branch (documentation only) |
| R-16 and R-18 still described #44 and #46 as not merged | Corrected in this branch (documentation only) |
| ADR-0009 required four tests, two of which did not exist: an oversized response isolated from other providers, and provider text reaching a model unable to act. The exact MEDIUM cap, the absence of raw-HTML sinks and full route-guard coverage were also untested | Tests added in this branch (`tests/security/test_v1_1_assurance.py`). All pass on `22642e8`; no product code changed |
| Legacy `adapters.fetch` (SmartRecruiters, generic sources) is not on the pinned transport | Existing R-01 residual, not a v1.1 regression. Proposed as a follow-up for the Owner; not patched here |
| The secondary account is not enabled, but OD-013 says `v1.1.0` delivers two accounts | Owner decision required (see the v1.1 evidence pack) |
| #47 (progress dashboard) is not merged | Its routes, and any follow-up that triggers Gmail operations, need a delta check when merged. The route-guard test covers new routes automatically |

### Decision requested

- **Owner:** approve this as-built reconciliation, or ask for changes.
  Approval would confirm the controls are built as described. It would not
  accept any residual risk; R-16, R-17 and R-18 are decided separately.
- **Independent review:** Codex reviews this section and its evidence at the
  exact commit before the Owner decides.
