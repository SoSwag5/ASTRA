# ASTRA v1.1 — Discovery & Application Intelligence

**Status:** Owner-approved with amendments (2026-09-13; OD-011 through
OD-017). Requirements and architecture planning only — implementation has
still not started. The mission, Discovery v2 architecture, and application
state model are approved as proposed (OD-011). The Gmail architecture is
approved with the amendments in §6 (OD-012). The release-scope recommendation
in the original draft of §12 was **not** approved and has been replaced with
the Owner's mandated scope (OD-013). The backlog in §11 is trimmed to the
Owner-approved 12 items (OD-014). Three ADRs (§13) and a threat-model delta
are drafted and awaiting Owner approval before any code is written
(OD-016, OD-017) — see `docs/governance/V1_1_OWNER_REVIEW_PACKET.md`.

**Origin:** Owner reprioritization on 2026-09-13, recorded in
`docs/governance/OWNER_DECISIONS.md` OD-010 and `docs/ROADMAP.md`. Real-world
use of `v1.0.0` showed the discovery/tracking loop under-delivers and the
dashboard under-reports real progress.

## 1. Problem statement

Observed after real v1.0 usage:

- Discovery frequently reports healthy sources but produces zero new useful
  jobs.
- Search does not behave like a real user searching for a role, e.g. "SOC
  Analyst Level 1" does not also surface adjacent titles a human would try.
- The user manually discovers and applies to significantly more jobs than
  ASTRA records, so ASTRA's application count is not trustworthy.
- Gmail contains application confirmations and status emails ASTRA does not
  reconcile, compounding the under-reporting.
- Net effect: the dashboard creates a false impression that little job-search
  activity is happening, undermining the product's core value proposition.

## 2. Product mission

Intended user loop:

```
DISCOVER -> REVIEW -> APPLY EXTERNALLY -> DETECT APPLICATION CONFIRMATION
  -> TRACK -> FOLLOW UP -> OUTCOME
```

ASTRA's role in this loop:

- Find jobs across legitimate structured sources.
- Rank them with an explainable score.
- Explain each match in evidence terms, not an opaque percentage.
- Link to legitimate external application destinations.
- Observe application confirmation/status signals (initially via Gmail).
- Maintain accurate application progress derived from real, verifiable events.

**Explicit non-goal:** autonomous job submission. The human remains
responsible for final application submission. This preserves ASTRA's existing
local-first, no-autonomous-action product boundary (ADR-0001) — v1.1 adds
observation and intelligence, not action-taking.

## 3. Discovery Engine v2 — requirements and architecture (planning only)

### 3.1 Target experience

A user query such as "SOC Analyst Level 1" should intelligently expand to
related titles — SOC Analyst, SOC Analyst Tier 1, Junior SOC Analyst, Security
Operations Analyst, Junior Cybersecurity Analyst, Cybersecurity Analyst — while
exact-query relevance remains weighted strongest.

**Excluded by Owner instruction:** no LinkedIn scraper or browser bot; no
automation of LinkedIn search/activity in violation of platform terms.

### 3.2 Sources to evaluate (provider-adapter model, not one scraper)

- Employer career pages (site-specific adapters where structure is stable).
- Greenhouse job board API.
- Lever postings API.
- Ashby postings API.
- Workable/public career endpoints where permitted by terms.
- Reputable job-search APIs (commercial aggregators with a public API/ToS that
  permits this use).
- Manually imported LinkedIn jobs (user pastes a URL/JD; no automated access).
- Manually imported employer jobs (same manual-import pattern).

Each source is an independent provider adapter behind a common interface, so
adding/removing/disabling a source never requires touching the pipeline.

### 3.3 Pipeline

```
QUERY PLANNER -> PROVIDER RETRIEVAL -> NORMALIZATION -> DEDUPLICATION
  -> ELIGIBILITY FILTERING -> RANKING -> EXPLANATION -> USER REVIEW
```

- **Query planner:** expands one user query into a bounded set of related
  title variants (synonym/seniority expansion), plus the original exact query
  weighted highest. Deterministic and inspectable — no opaque LLM-only query
  rewriting without a visible expansion list.
- **Provider retrieval:** each adapter fetches with its own pagination/rate
  limits; failures are isolated per-provider (one dead source does not block
  others).
- **Normalization:** map each provider's schema to one canonical job record
  (title, company, location, seniority signal, description, URL, posted date,
  source).
- **Deduplication:** cross-provider identity resolution (same job posted on an
  employer page and a board) using normalized title+company+location+content
  fingerprint, not just URL.
- **Eligibility filtering:** hard exclusions only (e.g., wrong country/region
  when location is a hard constraint, blatant seniority mismatch). Design rule
  from the Owner: **retrieve broadly, rank second** — do not silently destroy
  most results through aggressive pre-filtering.
- **Ranking:** see §4.
- **Explanation:** every ranked result carries the evidence used, not just a
  score.
- **User review:** the human decides what to save/pursue; ASTRA does not act
  further on their behalf.

### 3.4 Evaluation plan (required before declaring v1.1 Discovery a success)

- Build a small manually labeled evaluation set (real or representative
  queries with human relevance judgments) before/alongside implementation.
- Track: Precision@10, Recall@K, nDCG@10, duplicate rate, stale-link rate, new
  relevant jobs/day.
- No ranking change ships as "improved" without a before/after measurement
  against this set.

## 4. Explainable job ranking (planning only)

Interpretable signals, not an opaque ML score:

- Job-title relevance (including query-expansion match strength).
- Seniority match.
- Cybersecurity domain relevance.
- Skill overlap against the user's stored facts/CV.
- UAE/location relevance.
- Experience requirement fit.
- Recency.
- Source quality/reliability.
- Exclusions/hard mismatches (surfaced, not silently dropped where retrieval
  was broad).

Every recommendation explains itself, e.g.:

```
92% match
✓ SOC/SIEM role
✓ Abu Dhabi
✓ junior / 0-2 years
✓ Python relevant
✓ networking/security overlap
△ Splunk requested; user has MSSGard SIEM background
```

The percentage is a transparent weighted combination of the signals above,
each traceable to the evidence shown — never an unexplained AI-generated
number.

## 5. Discovery observability (planning only)

Replace "12/12 sources healthy" as the headline metric with a per-source
funnel:

```
FETCHED -> UNIQUE -> UAE/LOCATION MATCH -> JUNIOR-ELIGIBLE -> RELEVANT
  -> NEW -> DISPLAYED -> SAVED -> APPLIED
```

Example:

```
Greenhouse
238 fetched
193 unique
44 UAE
18 junior relevant
7 new today
```

Every filtering stage must be explainable/debuggable — an operator (the Owner)
can see exactly where candidates were lost, not just a pass/fail source count.

## 6. Gmail application capture — requirements only (amended by OD-012)

### 6.1 Scope and constraints

- Architect for **two** user-owned Gmail accounts from the start, but roll
  out in order: activate and validate the **primary** account first
  (OAuth, sync, parsing, reconciliation, and duplicate-prevention all
  proven), then enable the **second** account. Do not debug two live
  mailboxes simultaneously on the first implementation pass (OD-012).
- Official Gmail API via OAuth only. No passwords requested, no HTML
  scraping.
- **Read-only** in this phase: no send, delete, archive, or modify (see
  ADR-0008).
- Local OAuth/token handling consistent with ASTRA's local-first security
  architecture — refresh tokens encrypted at rest via an OS-backed mechanism
  (e.g. Windows DPAPI), under the same OS-account trust boundary as the rest
  of ASTRA's data (see §8 and ADR-0007).

### 6.2 Target signals (priority order)

v1.1 priority: **application confirmation / "applied" only.**

- "Thank you for applying" / "Application received" / "Your application was
  sent to…"
- Deferred to a later evaluated phase: viewed, assessment invitation,
  interview invitation, rejection, offer.

### 6.3 Extraction fields and retention (amended by OD-012)

- Store only: message ID, account ID, sender, subject, received timestamp,
  detected company, detected role, detected application state, confidence,
  evidence/parser identifier, and the relevant job/application URL.
- **Do not retain full email bodies indefinitely.** If body content is
  temporarily needed for parsing, it is used transiently (in memory, or a
  short-lived cache) and discarded once parsing completes — not persisted as
  a durable record. A specific, separately-approved requirement (e.g. a
  snippet for the Needs Review queue) may retain a minimal excerpt, never the
  full body, and must be called out explicitly when proposed, not added
  silently. See ADR-0008.

### 6.4 Parsing strategy (amended by OD-012: deterministic-first)

- **Deterministic-first, not AI-first.** Initial detection is source-specific
  deterministic parsers matching known platforms, senders, subjects, and body
  patterns (Greenhouse/Lever/Workday-style confirmation templates are highly
  regular).
- A controlled generic fallback (pattern/heuristic-based) only for messages no
  deterministic parser matches, always tagged with lower confidence.
- **Cloud AI is not part of the initial classifier.** AI may only be
  evaluated later as a controlled fallback if deterministic/source-specific
  approaches prove insufficient in practice — that is a future, separately
  proposed decision, not part of this milestone's initial scope.

### 6.5 Confidence policy

- **HIGH** — safe auto-reconciliation into the application state model.
- **MEDIUM** — routed to a "Needs Review" queue; the user confirms/rejects.
- **LOW** — never mutates application state.

### 6.6 Duplicate prevention

- Existing manually recorded applications must never be duplicated by an
  incoming Gmail signal. Reconciliation matches on (company, role,
  approximate date, and, where available, application URL/source platform)
  before creating a new record; a match updates the existing record's
  provenance instead of creating a second one.

## 7. Application state model (planning only)

Proposed states:

```
DISCOVERED -> SAVED -> APPLIED -> VIEWED -> ASSESSMENT -> INTERVIEW
  -> OFFER / REJECTED -> CLOSED
```

Required design elements:

- **Permitted transitions:** an explicit table (e.g., DISCOVERED→SAVED→APPLIED
  is normal; APPLIED→INTERVIEW skipping VIEWED is allowed; REJECTED/OFFER are
  terminal but reopenable to CLOSED only).
- **Manual vs. automated evidence:** every transition records who/what asserted
  it (user action vs. Gmail parser vs. future integration).
- **Confidence requirements:** automated transitions require at least MEDIUM
  confidence (§6.5); LOW confidence never transitions state.
- **Provenance/source of status:** each state carries its evidence trail
  (message ID, timestamp, parser version).
- **Conflict resolution:** a weaker automated signal must never silently
  overwrite a stronger manually confirmed state (e.g., a MEDIUM-confidence
  "viewed" email must not downgrade a user-confirmed INTERVIEW back to
  VIEWED).
- **History/audit trail:** append-only transition history per application
  record, not just a current-state field.
- **Duplicate reconciliation:** ties into §6.6.

## 8. Progress/dashboard experience (planning only)

Redesign around verified events, not gamification:

```
THIS WEEK
67 new relevant jobs discovered
18 strong matches
12 applications submitted
3 applications viewed
1 assessment
5 follow-ups due

GMAIL DETECTED
✓ Gruve — application received
✓ BlackStone eIT — application received
👁 PureCS — application viewed
⚠ 2 messages need review
```

Every number must trace to a real recorded discovery/application/Gmail event;
no synthetic streaks, badges, or unearned progress indicators.

## 9. Security and privacy impact (planning-stage threat-model review)

This milestone materially changes ASTRA's data flows: it introduces OAuth
tokens, restricted mailbox access for two identities, and parsing of
externally-sourced job and email content. The existing threat model (built for
a purely local, no-external-mailbox-access product) does not fully cover this.
A threat-model delta and likely new ADRs are required before implementation,
covering:

- **OAuth tokens (two Gmail identities):** local storage, scoping (narrowest
  Gmail read scope that satisfies §6), rotation/revocation, and what happens
  on token compromise within the existing OS-account trust boundary (R-15).
- **Restricted mailbox data / email content parsing:** treat all email content
  as untrusted input; malicious email content and malicious links must never
  be auto-followed or rendered as trusted; HTML in emails must be sanitized
  before any display, never executed.
- **Privacy/minimization:** store only the fields in §6.3, not full message
  bodies beyond what's needed for parsing/audit; define retention.
- **Local storage:** mailbox-derived data follows the same local-first
  storage/ACL posture as existing application data.
- **Duplicate/reconciliation attacks:** a malicious or spoofed email should not
  be able to overwrite a legitimate application's state (ties to §7 conflict
  resolution) — HIGH-confidence auto-reconciliation must be conservative.
- **External job-provider data:** treat all fetched job content as untrusted;
  apply the same sanitization discipline as email content before display.
- **SSRF:** any provider adapter or link-following behavior must reuse
  ASTRA's existing outbound-fetch policy controls (loopback/private-range
  blocking, redirect checks — see R-01, `policy.py`).
- **Parser/resource exhaustion:** bound message/job-body sizes read into
  memory, matching the pattern already used for AI provider responses (R-13).
- **AI use, if any:** if ranking/explanation uses the existing AI provider
  path, it inherits R-04/R-05 controls and must not receive raw email content
  without the same untrusted-data framing used for job/CV comparison today.
- **Audit/security events:** new event types for OAuth grant/revoke, parser
  failures, and reconciliation conflicts, extending `security_events.py`
  (relevant to R-14, §10).

**Framework impact to determine before implementation:**

- **ASVS:** new requirements become applicable around token storage, input
  validation of external content, and session/credential handling for the
  OAuth flow (previously N/A under a purely local, single-external-integration
  model).
- **SSDF:** evidence expands to cover the new external data ingestion paths.
- **New risks:** a new risk register entries are needed for OAuth token
  handling, malicious email/job content, and reconciliation/duplicate attacks
  (do not silently fold these into an unrelated existing risk).
- **ADRs required (see §12):** OAuth/credential handling, Gmail read-only
  integration boundary, and provider-adapter external-data trust boundary.

No claim is made that the current threat model already covers Gmail
integration; this section was the planning input for the dedicated
threat-model delta now drafted at
`docs/security/THREAT_MODEL_CHANGE_V1_1_DISCOVERY_GMAIL.md`, submitted for
Owner approval alongside the three ADRs in §13.

## 10. R-13/R-14 WIP recommendation

A local branch `hardening/l2-r13-r14` (commit `e679a27`, isolated, marked
`[WIP do-not-merge]`) contains unmerged pre-Governance work:

- **R-13:** a 1&nbsp;MB streaming byte cap on AI provider responses
  (`backend/providers.py`, `_read_capped`), closing the "unbounded body from a
  compromised/faulty endpoint" gap.
- **R-14:** a tamper-evident hash-chain for the security-event log
  (`backend/security_events.py`) — each entry carries
  `chain = SHA-256(prev_chain + core_fields)`, with a `verify()` function that
  detects modified, reordered, or deleted lines; explicitly documented as
  tamper-*evident*, not tamper-*proof* (a local actor with code access could
  recompute the chain — consistent with the R-15 trust boundary, not a new
  claim beyond it).
- Five new security event types (`SESSION_INVALID`, `REQUEST_REJECTED`,
  `AI_QUOTA_EXCEEDED`, `AI_RESPONSE_OVERSIZED`, `UNHANDLED_ERROR`) wired into
  `main.py` and `ai_usage.py`.
- 12 focused tests in `tests/security/test_l2_hardening.py` covering the byte
  cap, chain construction, tamper detection (modified line, deleted line), and
  fail-open telemetry behavior (`record` must never raise).

**Independent review of the diff in this session** found the implementation
narrowly scoped, consistent with the existing `security_events.py` fail-open
design ("Telemetry must never break or delay a security control"), and
well-tested, including negative cases. The large deletion count in a
branch-vs-master diff is an artifact of the branch predating the Governance v1
docs merge, not a real change — the actual code diff is four small, scoped
edits plus one new test file.

**Recommendation:** retain it. Roadmap reprioritization moves Operational
Security & Resilience to **v1.2**, and R-13/R-14 are exactly that class of
work, so this WIP maps to **v1.2**, not v1.1. Rebased onto current `master`
(commit `f4b8f6f`) and tracked by issue #33.

**Owner decision (OD-015): on hold for the duration of v1.1.** Do not merge
it and do not spend further implementation or independent-review time on it
during v1.1, unless a genuine v1.1 dependency requires it. v1.1 may itself
alter logging/security events (e.g. new OAuth-grant/revoke and
parser-failure event types, §9), which would otherwise create unnecessary
rebase churn on this branch — review it properly when the v1.2 milestone
opens.

## 11. Approved v1.1 issue backlog (OD-014 — trimmed to 12)

The Owner trimmed the originally proposed 15 items to 12, combining the
ranking/eligibility split and folding Workable evaluation into the
Lever/Ashby issue. Each issue, when filed, states scope, explicit non-goals,
acceptance criteria, security/privacy considerations, dependencies, and
testing/evaluation requirements, with the "v1.1 — Discovery & Application
Intelligence" milestone and appropriate labels.

1. Discovery query planner (exact queries, synonym/title expansion,
   seniority interpretation).
2. Job provider adapter framework + Greenhouse (adapter contract, first real
   provider).
3. Lever + Ashby providers (Workable evaluated inside this issue before any
   implementation decision).
4. Normalization + cross-provider deduplication.
5. Eligibility filtering + explainable ranking (combined: title, seniority,
   skills, location, experience, recency signals, plus explanation evidence).
6. Discovery evaluation harness (manually labeled dataset; Precision@10,
   Recall@K, nDCG@10, duplicate rate, stale-link rate).
7. Discovery funnel telemetry (fetched → unique → eligible → relevant → new
   → displayed → saved/applied).
8. Gmail OAuth + two-account architecture (primary account activated first;
   second enabled only after validation; secure local token storage per
   ADR-0007).
9. Gmail incremental read-only sync + confirmation parsing (deterministic
   source parsers first, generic fallback, confidence scoring — §6.4).
10. Application reconciliation + application-state model (dedupe, manual vs.
    automatic provenance, transition rules, evidence history — §7).
11. Progress/dashboard redesign (weekly progress, confirmed applications,
    Gmail-detected events, Needs Review queue — §8).
12. v1.1 security/privacy assurance (threat-model delta, Gmail/data/provider
    risks, ASVS/SSDF delta, regression/security tests, release evidence).

Do not create unnecessary micro-issues beyond this list.

## 12. Release scope (amended — OD-013)

**The Owner did not approve the originally proposed staged release split**
(Discovery-only v1.1.0, Gmail deferred to a later v1.1.x/v1.2.0). The
rationale for rejecting it: the reprioritization exists precisely because
ASTRA currently fails at *both* ends — it doesn't find enough useful jobs,
and it doesn't know about the applications actually being submitted.
Shipping Discovery alone would only solve half the problem.

**Approved scope:** final `v1.1.0` must deliver the complete minimum product
loop in one release — Discovery v2 + Gmail application-confirmation capture
+ application reconciliation/state + a basic progress dashboard.

Development is staged **internally**, not as separate public releases:

- **Phase A — Discovery:** query planner, providers, normalization, ranking,
  evaluation harness (backlog items 1-7).
- **Phase B — Application Intelligence:** Gmail OAuth, one-account sync,
  confirmation parser, reconciliation (backlog items 8-9, primary account
  only).
- **Phase C — Complete loop:** second Gmail account, application state
  model, progress/dashboard (backlog items 8 completion, 10-11).
- **Phase D — Release assurance:** security/privacy assurance, full
  regression, release evidence pack (backlog item 12).

If intermediate public builds are wanted, use prereleases rather than
treating a major new capability as a patch release:

```
v1.1.0-alpha.1   Discovery working
v1.1.0-beta.1    Gmail + reconciliation working
v1.1.0-rc.1      complete candidate
v1.1.0           final
```

## 13. ADRs required before implementation (drafted — OD-016)

Three ADRs are drafted (status: Proposed, not yet Accepted) and included in
the Owner Review Packet:

- [ADR-0007](../architecture/adr/0007-gmail-oauth-credential-storage.md) —
  Gmail OAuth and credential storage (local token storage, scope, revocation,
  two-account isolation).
- [ADR-0008](../architecture/adr/0008-gmail-read-only-mailbox-trust-boundary.md)
  — Gmail read-only mailbox trust boundary (no send/delete/archive/modify;
  minimized retention per §6.3).
- [ADR-0009](../architecture/adr/0009-external-job-provider-trust-boundary.md)
  — external job-provider trust boundary (untrusted-by-default providers,
  URL validation, size/time caps, sanitization).

Each follows the ADR triggers in `docs/architecture/adr/README.md`
(persistence/privacy boundaries; secrets/credentials; data-flow change).

## 14. Owner decisions recorded this round (OD-011 through OD-017)

- **OD-011:** mission, Discovery v2 architecture, and application state
  model approved as proposed.
- **OD-012:** Gmail architecture approved with amendments — single-account
  rollout first, deterministic-first classification, minimized retention
  (§6).
- **OD-013:** release-scope split rejected; single complete-loop v1.1.0
  with internal phases and prerelease tags approved (§12).
- **OD-014:** backlog approved and trimmed to 12 issues (§11).
- **OD-015:** R-13/R-14 mapping to v1.2 approved; on hold during v1.1 (§10).
- **OD-016:** ADR-0007/0008/0009 required; drafted, not yet Accepted (§13).
- **OD-017:** v1.1 threat-model delta required; drafted, not yet approved
  (`docs/security/THREAT_MODEL_CHANGE_V1_1_DISCOVERY_GMAIL.md`).

**Still pending Owner approval:** the three ADR drafts and the threat-model
delta itself (including the three proposed risk-register additions R-16,
R-17, R-18) — submitted together as
`docs/governance/V1_1_OWNER_REVIEW_PACKET.md`.

## 15. Next implementation step

1. Owner reviews and approves (or amends) the Owner Review Packet — the
   three ADR drafts and the threat-model delta, including the proposed
   risk-register additions.
2. Once approved, file the 12 backlog issues (§11) under the "v1.1 —
   Discovery & Application Intelligence" milestone with full scope/non-goals/
   acceptance-criteria/security/dependency/testing detail.
3. Mark ADR-0007/0008/0009 Accepted.
4. Begin Phase A: the first implementation branch is the **Discovery Query
   Planner** (backlog item 1).
