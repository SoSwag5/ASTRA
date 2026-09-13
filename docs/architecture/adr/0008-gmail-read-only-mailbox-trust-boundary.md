# ADR-0008: Gmail read-only mailbox trust boundary

- **Status:** Proposed
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

Retention: for each detected application-related message, persist only
the minimized evidence record already specified in OD-012 — message
ID, account ID, sender, subject, received timestamp, detected
company, detected role, detected application state, confidence,
evidence/parser identifier, and the relevant job/application URL.
Full message body or HTML is used only transiently during parsing (in
memory, or in a short-lived cache with a defined maximum lifetime to
be set during implementation) and is not persisted once parsing
completes, unless a specific, separately-approved requirement
demonstrates an actual need (e.g., surfacing a snippet in the "needs
review" queue for a MEDIUM-confidence match) — in which case only the
minimal snippet needed for that UI, not the full body, is retained,
and that exception must be called out explicitly in the implementing
PR, not silently added.

Sync scope is narrowed at the query level where Gmail's search syntax
allows it (e.g., restricting to a bounded time window or label/query
filter relevant to job applications) rather than pulling the entire
mailbox, both for minimization and to bound processing cost.

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

## Evidence and validation

None yet — pre-implementation draft. Required before Accepted: the
actual Gmail scope requested by ADR-0007's implementation confirmed as
read-only; a code-level test asserting the Gmail client wrapper
exposes no mutating method; a test confirming full message bodies are
not present in the SQLite database after a sync/parse cycle completes.

## Framework impact

Establishes the privacy-minimization boundary the v1.1 threat-model
delta's data-flow section depends on. No SLSA/CycloneDX impact.
Contributes to newly-applicable ASVS data-protection/privacy
requirements alongside ADR-0007 (see the threat-model delta).
