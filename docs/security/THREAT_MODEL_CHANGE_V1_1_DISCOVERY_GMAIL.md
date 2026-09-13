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
  - **SBOM:** a Gmail API client library dependency will need lockfile
    hashes and an SBOM update at implementation (R-04 applies).
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
- **Remaining assumptions and recheck triggers:** assumes Google's OAuth
  infrastructure and API behave as documented (not independently verified
  here); assumes Windows DPAPI (or the OS-backed equivalent chosen at
  implementation) provides the protection ADR-0007 describes — to be
  confirmed during implementation, not assumed permanently. Recheck this
  delta if: a broader Gmail scope than read-only is ever requested; AI-based
  email classification is added (see the abuse-case table); ASTRA adds a
  third external mailbox provider; or the provider-adapter list grows to
  include a source that cannot honor the size/time-cap or URL-validation
  controls.
- **Owner decision:** Pending. This document, together with ADR-0007,
  ADR-0008, ADR-0009, and the risk-register additions below, is submitted as
  part of the v1.1 Owner Review Packet (`docs/governance/V1_1_OWNER_REVIEW_PACKET.md`)
  for approval before any implementation begins.

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
