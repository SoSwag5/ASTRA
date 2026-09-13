# ASTRA v1.1 — Discovery & Application Intelligence

**Status:** Proposed. Requirements and architecture planning only. No
implementation has started. The Owner must approve the mission, architecture
direction, and backlog before any v1.1 branch opens.

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

## 6. Gmail application capture — requirements only

### 6.1 Scope and constraints

- Two user-owned Gmail accounts.
- Official Gmail API via OAuth only. No passwords requested, no HTML
  scraping.
- **Read-only** in this phase: no send, delete, archive, or modify.
- Local OAuth/token handling consistent with ASTRA's local-first security
  architecture (tokens stay on the local host, under the same OS-account trust
  boundary as the rest of ASTRA's data — see §8).

### 6.2 Target signals (priority order)

v1.1 priority: **application confirmation / "applied" only.**

- "Thank you for applying" / "Application received" / "Your application was
  sent to…"
- Deferred to a later evaluated phase: viewed, assessment invitation,
  interview invitation, rejection, offer.

### 6.3 Extraction fields

- Company, role, application date/time, source platform, Gmail account,
  confirmation message ID, related job/application URL (if present),
  confidence, parser/source identifier.

### 6.4 Parsing strategy

- Source-specific deterministic parsers first (Greenhouse/Lever/Workday-style
  confirmation templates are highly regular).
- A controlled generic fallback (pattern/heuristic-based) only for messages no
  deterministic parser matches, always tagged with lower confidence.

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
integration; this section is the planning input for a dedicated threat-model
change document (`docs/security/THREAT_MODEL_CHANGE_TEMPLATE.md`) to be
completed before implementation begins.

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
work, so this WIP maps to **v1.2**, not v1.1. Do not merge as-is per the
Owner's instruction and the governance model: the branch should be rebased
onto current `master`, tracked by a GitHub issue mapping it into v1.2, and
independently reviewed (Codex, per `RELEASE_GOVERNANCE.md` roles) before a PR
is opened — this session performs the mapping and rebase, not the independent
review or merge.

## 11. Proposed v1.1 issue backlog (for Owner approval — not yet created)

1. Discovery v2: query planner (title/seniority expansion, exact-match
   weighting).
2. Discovery v2: provider-adapter interface + first adapter (Greenhouse).
3. Discovery v2: additional provider adapters (Lever, Ashby; evaluate
   Workable).
4. Discovery v2: retrieval normalization and cross-provider deduplication.
5. Discovery v2: eligibility filtering per the "retrieve broadly, rank second"
   rule.
6. Explainable ranking model + per-result evidence rendering.
7. Discovery evaluation dataset + Precision@10/Recall@K/nDCG@10 harness.
8. Discovery funnel telemetry (per-source funnel metrics, §5).
9. Gmail OAuth and two-account management (local token handling).
10. Gmail incremental sync (read-only, scoped to relevant label/query).
11. Application-confirmation parsing (deterministic parsers + generic
    fallback + confidence policy).
12. Application reconciliation/deduplication against existing records.
13. Application state model implementation (transitions, provenance,
    conflict resolution, audit trail).
14. Progress/dashboard redesign around verified events.
15. Gmail/external-data threat-model update and risk-register additions.

This is 15 items; the Owner may combine or drop items to land closer to 8-12
for the initial milestone slice.

## 12. Proposed release scope

Recommendation: **stage rather than ship v1.1.0 as one large release.**

- **v1.1.0 — Discovery v2 core:** query planner, provider adapters (at least
  Greenhouse), normalization/deduplication, explainable ranking, evaluation
  harness, funnel telemetry. This alone directly addresses "discovery reports
  healthy but finds nothing" and is independently valuable and testable.
- **v1.1.1 (or v1.2.0, Owner's call on versioning) — Gmail application
  capture + reconciliation + dashboard redesign:** depends on its own OAuth
  threat-model work and is a distinct trust-boundary change (ADR-triggering)
  from discovery. Shipping it separately avoids coupling a data-flow/privacy
  review to a ranking-algorithm release, and lets the discovery half ship
  sooner.

Rationale: Discovery v2 and Gmail capture have different risk profiles (pure
retrieval/ranking vs. OAuth/external-mailbox trust boundary) and different
validation needs (an evaluation dataset vs. a threat-model review). Coupling
them into one release gates the lower-risk, higher-certainty work behind the
higher-risk, higher-review-burden work.

## 13. ADRs likely required before implementation

- OAuth/credential handling for Gmail (local storage, scope, revocation).
- Gmail read-only integration trust boundary (what ASTRA can and cannot do
  with mailbox access — explicitly no send/delete/modify).
- External job-provider data trust boundary (provider adapters as an untrusted
  external data source, distinct from the existing AI-provider trust
  boundary).

Each follows the ADR triggers in `docs/architecture/adr/README.md`
(persistence/privacy boundaries; secrets/credentials; and, for the mailbox
integration, arguably a data-flow/deployment-topology change).

## 14. Owner decisions required before implementation

- Approve or amend the v1.1 mission (§2) and the discovery/Gmail architecture
  direction (§3, §6).
- Approve, trim, or reorder the proposed backlog (§11).
- Approve the staged release recommendation (§12) or direct a different
  scope split.
- Approve the R-13/R-14 mapping to v1.2 (§10) and authorize opening the
  tracking issue and rebasing the branch (implementation/merge still requires
  independent review first).
- Decide which Gmail read scope and which of the two accounts is in scope for
  the first increment, if not both simultaneously.

## 15. Next implementation step (after Owner approval)

1. Owner approves this document (in whole or with amendments).
2. Open the approved subset of the backlog (§11) as GitHub issues with
   acceptance criteria.
3. Write the Gmail/external-data threat-model delta and the ADRs in §13
   before any OAuth or provider-adapter code is written.
4. Begin Discovery v2 core (query planner + first provider adapter) as the
   first implementation branch, per the staged release plan (§12).
