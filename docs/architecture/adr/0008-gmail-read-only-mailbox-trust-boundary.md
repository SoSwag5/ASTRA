# ADR-0008: Gmail read-only mailbox trust boundary

- **Status:** Accepted (architecture decision only; Owner approved
  2026-09-13, OD-018). Implementation evidence remains **Pending** — see
  "Evidence and validation" below; do not treat this status as proof any
  control is implemented.
- **Date:** 2026-09-13
- **Owner:** Ayham
- **Issue / pull request:** v1.1 planning packet; see `docs/planning/V1_1_DISCOVERY_AND_APPLICATION_INTELLIGENCE.md` §6
- **Target release:** v1.1.0 (Phase B/C)
- **Supersedes / superseded by:** None

## Context and problem

Gaining Gmail access gives ASTRA the technical ability to read, and
(with a broader scope) send, delete, archive, or modify a user's email.
The product intent (OD-012, `AGENTS.md`) is strictly observational:
detect application-related signals, never act on the mailbox. Without
an explicit, enforced boundary, scope creep (a future feature quietly
requesting a broader scope, or a bug that calls a mutating API) is a
realistic risk given how permissive Gmail's API surface is once
authorized.

Decision questions:

- What is the maximum action set ASTRA may perform against Gmail in
  v1.1?
- What is the minimum data extracted and retained from each matched
  message?
- How long is any extracted or raw data retained, and what triggers
  deletion?

## Options considered

1. **Read-only scope, read-only code path, minimized extraction.**
   Request only a read-only Gmail scope; the integration code never
   calls a mutating Gmail API (send, delete, trash, modify labels,
   mark read/unread); extract only the fields needed for application
   tracking and discard the rest.
2. **Broader scope "for future flexibility."** Request a scope that
   also permits labeling or archiving, reasoning that a future feature
   might want it. Rejected: violates the Owner's explicit instruction
   (`AGENTS.md`, OD-012) and ASTRA's minimization principle; a broader
   granted scope is itself a bigger asset to protect and a bigger
   blast radius if the token is misused, whether or not the code
   currently calls the extra capability.
3. **Full mailbox mirroring for offline search/analytics.** Rejected:
   directly conflicts with "do not retain full email bodies
   indefinitely" (OD-012) and turns ASTRA into an email archive, which
   is a materially different privacy posture than a job-search
   assistant.

## Decision

ASTRA may read only the minimum mailbox data needed for application
tracking, and **may never send, delete, archive, trash, mark
read/unread, or otherwise modify Gmail messages or labels in v1.1.**
This is enforced at the integration layer (the Gmail client wrapper
exposes only read operations; no code path holds or calls a mutating
credential/scope), not merely as a policy statement.

**Retention:** for each detected application-related message, persist
only the minimized evidence record already specified in OD-012 —
message ID, account ID, sender, subject, received timestamp, detected
company, detected role, detected application state, confidence,
evidence/parser identifier, and the relevant job/application URL.

**Full message body or HTML is memory-only in v1.1.** It is used
transiently during parsing, held in process memory, and discarded once
parsing completes. **No implementation-defined disk cache of message
bodies/HTML is permitted** — this closes the ambiguity in the original
draft, which allowed "a short-lived cache" without specifying its
medium; that option is withdrawn. A specific, separately-approved
requirement may retain a minimal *snippet* (e.g., for the Needs Review
queue on a MEDIUM-confidence match) — never the full body — as the one
narrow exception, and that exception must be called out explicitly in
the implementing PR, not silently added.

**Disconnect and retention (resolved wording):** disconnecting a Gmail
account (ADR-0007) deletes that account's refresh token **and its
synchronization/account-integration state** (last-sync cursor, queued
work, per-account credential record). Disconnect does **not** delete
already-created Gmail-derived evidence records (the minimized rows
above) — those persist as part of the application state model's
history, on their own evidence, independent of whether the
originating account is still connected. **Removing that Gmail-derived
metadata is a separate, explicit user action** (e.g. deleting the
specific application record, or a distinct "also erase Gmail-derived
history" action if one is built) — disconnect alone does not imply it.
This is the authoritative resolution of the retention/disconnect
wording; the threat-model delta's data-flow row is corrected to match
(see `docs/security/THREAT_MODEL_CHANGE_V1_1_DISCOVERY_GMAIL.md`,
which previously stated evidence is "retained until ... disconnects
the account," implying disconnect deletes evidence — it does not).

Sync scope is narrowed at the query level where Gmail's search syntax
allows it (e.g., restricting to a bounded time window or label/query
filter relevant to job applications) rather than pulling the entire
mailbox, both for minimization and to bound processing cost.

**HIGH-confidence reconciliation requires multiple independent
evidence signals** — a single matched element (e.g. subject line
alone, or sender address alone) is not sufficient to reach HIGH
confidence; the deterministic parser must corroborate at least sender
identity, structural template match, and extracted field consistency
(company/role/date all present and mutually consistent) before a
detection is tagged HIGH. **Where Gmail exposes message authentication
evidence (e.g. SPF/DKIM/DMARC alignment information available via the
Gmail API), that evidence is incorporated into source-authenticity
assessment as one of the required independent signals.** Missing or
contradictory authentication evidence (the message fails or lacks
alignment information ASTRA can check) **must prevent automatic HIGH-
confidence treatment**, regardless of how well the content otherwise
matches a known template — such a message is capped at MEDIUM and
routed to Needs Review.

## Rationale

A hard read-only boundary enforced in code (not just policy) means a
future bug or feature addition cannot silently start mutating the
user's mailbox without a deliberate, reviewable change to the
integration layer itself. Minimizing retained fields keeps ASTRA's
data footprint aligned with its local-first, application-tracking
purpose rather than accumulating an email archive, which would be a
larger, more sensitive asset than anything ASTRA currently stores.

## Security and privacy impact

- **Assets:** the minimized per-message evidence records (see above);
  transient full message content during parsing only.
- **Actors:** same as ADR-0007 — the local OS user (trusted); a
  malicious local/shared-host actor (R-15); malicious or spoofed email
  senders (new actor class for this ADR — see the threat-model delta
  for phishing/malicious-link handling).
- **Data minimization:** directly implements OD-012's retention limit.
  Full bodies are not a durable asset ASTRA holds, shrinking exposure
  if the local database or backups are ever compromised or exported.
- **Malicious content:** any HTML or links from message content must
  be sanitized before any display and never auto-followed or rendered
  as trusted (ties to the existing untrusted-content handling pattern
  used for job/CV text passed to the AI provider path).

## Operational impact

Users see only the derived evidence and (for MEDIUM-confidence items)
a minimal snippet in the Needs Review queue — not a searchable email
archive. Reduces local storage growth compared to mirroring. No
mutation means a Gmail-side incident (e.g., the user later revokes
access) cannot result in ASTRA having altered their mailbox.

## Tradeoffs and residual risk

Narrow retention means ASTRA cannot later "look back" at a full
message if the parser missed something — a MEDIUM/LOW-confidence
message not reconciled at detection time cannot be re-parsed from
ASTRA's own storage later; the user would need to keep the email
in Gmail (which they already do, since ASTRA never deletes anything).
This is an accepted tradeoff favoring minimization. Read-only
enforcement is a code-level control, not a Google-side technical
guarantee beyond the granted OAuth scope itself; if implementation
mistakenly requests a broader scope, this ADR's intent is violated at
the authorization layer, not just the code layer — ADR-0007's scope
selection and this ADR's code-level enforcement are both required,
not either/or.

This is registered as risk R-17 (shared with ADR-0009) in
`docs/security/RISK_REGISTER.md`, state **OPEN — treatment planned for
v1.1** — the Owner has approved recording this risk, not accepted its
residual; residual risk is reassessed only after the controls above
and their negative tests exist.

## Evidence and validation

**Implementation evidence status: PARTIAL — only the authorization-layer
half exists.** This ADR's `Accepted` status reflects Owner approval of
the architecture decision above, not proof that any control has been
built.

Satisfied by issue #44 (`feature/44-gmail-oauth`, **not merged**) — see
`docs/architecture/GMAIL_OAUTH.md`:

- The actual Gmail scope ASTRA requests is confirmed read-only in code
  and by test: exactly `https://www.googleapis.com/auth/gmail.readonly`,
  with parametrized tests asserting no `mail.google.com`, Gmail
  modify/send/compose/insert/settings, Drive, Contacts or
  OpenID/profile/email scope is ever requested, and
  `include_granted_scopes=false` so a broader earlier grant is not
  silently inherited.
- A code-level test asserting the Gmail client wrapper exposes no
  mutating operation: the profile lookup is the **only** Gmail API URL
  anywhere in the feature, asserted by scanning the modules for any
  other `/gmail/v1/` path, so no code path can call a mutating
  operation.
- The granted scope is validated after exchange and a
  broader-than-requested grant stops the flow before any credential is
  stored — so the scope-layer intent of this ADR is enforced at the
  authorization layer, not only asserted in code.
- Disconnect semantics per this ADR's amended rules: disconnect deletes
  the account's refresh token **and** its sync state, and does not
  delete application records or history. Tests cover both halves.
- No message, thread, subject, sender, history or `threadId` value is
  persisted; mailbox counts returned by the profile lookup are dropped
  rather than stored.

**Not applicable yet, because the behaviour does not exist:** issue #44
implements no mailbox sync or parsing at all. The remaining evidence —
no full message body or HTML in the SQLite database or any on-disk cache
after a sync/parse cycle; a single-signal match cannot reach HIGH
confidence; a message with missing or contradictory authentication
evidence is capped at MEDIUM regardless of template match quality —
requires issue #45 and cannot be produced before it. See issue #48 for
where this evidence is assembled.

## Framework impact

Establishes the privacy-minimization boundary the v1.1 threat-model
delta's data-flow section depends on. No SLSA/CycloneDX impact.
Contributes to newly-applicable ASVS data-protection/privacy
requirements alongside ADR-0007 (see the threat-model delta).
