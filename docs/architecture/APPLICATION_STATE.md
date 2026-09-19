# Application state, transition history and Gmail reconciliation (#46)

Implementation owner: Claude Code, on `feature/46-application-reconciliation-state-model`
from `11a69b0921d55072aa4f552a0319320ab73d6741` (merged #45 / PR #67).
This is **implementation and self-verification**, not an independent review.
**No live mailbox validation** has been performed. **No independent review yet.**
**R-18 remains OPEN.** **No residual-risk acceptance or release approval is
implied.** #46.2, #47 and #48 are not started.

## Why this exists

ASTRA could already say an application was `APPLIED`. It could not say *how it
knew*. Three overlapping vocabularies were written into three columns, each
overwritten in place:

| Vocabulary | Defined in | Written to |
|---|---|---|
| Job workflow status | `backend/policy.py::STATUSES` | `Job.status`, `Application.status` |
| Campaign stage | `backend/campaign.py::STAGES` | `Application.tracking['stage']` |
| Application status | `backend/models.py` | `Application.status` |

None carried who asserted the value, when, on what evidence, or what it
replaced. #46 adds one authoritative model beside them. It does **not** merge
or rewrite the three; they remain compatibility projections.

## Canonical authority

**`application_states.current_state` is the authoritative application state.**
`application_state_transitions` is the authoritative *history*, and is the
record of record: the current-state row is a projection of the latest accepted
transition, written in the same transaction, and never a substitute for it.

`Job.status`, `Application.status` and `Application.tracking['stage']` remain
**compatibility projections** for the existing frontend and API. They are not
authoritative, and a reader that needs a provable state reads the canonical
tables. See "Compatibility and divergence" below for what happens when the two
disagree.

## The state model

States, in progression order:

```
DISCOVERED -> SAVED -> APPLIED -> VIEWED -> ASSESSMENT -> INTERVIEW
                                              -> OFFER / REJECTED -> CLOSED
```

The permitted-transition table is declared once, in
`backend/application_state.py::PERMITTED`, and is complete: a target absent
from a state's row is forbidden.

| From | Permitted targets |
|---|---|
| `DISCOVERED` | `SAVED`, `APPLIED`, `CLOSED` |
| `SAVED` | `APPLIED`, `CLOSED` |
| `APPLIED` | `VIEWED`, `ASSESSMENT`, `INTERVIEW`, `OFFER`, `REJECTED`, `CLOSED` |
| `VIEWED` | `ASSESSMENT`, `INTERVIEW`, `OFFER`, `REJECTED`, `CLOSED` |
| `ASSESSMENT` | `INTERVIEW`, `OFFER`, `REJECTED`, `CLOSED` |
| `INTERVIEW` | `OFFER`, `REJECTED`, `CLOSED` |
| `OFFER` | `CLOSED` |
| `REJECTED` | `CLOSED` |
| `CLOSED` | *(none)* |

Properties this table encodes, each covered by its own test:

- Normal progress `DISCOVERED → SAVED → APPLIED`.
- Legitimate forward skips: `DISCOVERED → APPLIED`, `APPLIED → INTERVIEW`,
  `APPLIED → OFFER`, `VIEWED → INTERVIEW`.
- **No regression.** Every permitted target has a strictly higher ordinal than
  its source, so an earlier state is unreachable.
- A self-transition is not a transition and is never recorded.
- `OFFER` and `REJECTED` may only be closed.
- `CLOSED` is terminal with no outgoing transition, and is reachable from every
  other state (abandoning or archiving an application is always legitimate).
- `VIEWED`, `ASSESSMENT`, `INTERVIEW`, `OFFER` and `REJECTED` are unreachable
  from `DISCOVERED` and `SAVED`: an employer cannot act on an application that
  was never submitted.

All 81 ordered state pairs — permitted and forbidden — are covered by a
fixture-driven regression in `tests/test_application_state.py`.

Every state change in the codebase goes through
`application_state.assert_state()`. API handlers, reconciliation and the
migration path do not implement transition logic of their own.

## Provenance

Every accepted transition appends one immutable row carrying:

| Field | Meaning |
|---|---|
| `application_id`, `sequence` | Application identity and its per-application monotonic position |
| `previous_state`, `new_state` | What changed (`previous_state` is empty only for the bootstrap row) |
| `source_category` | `USER_ACTION`, `USER_CONFIRMED_GMAIL_EVIDENCE`, `GMAIL_PARSER`, `LEGACY_MIGRATION`, `BROWSER_CONFIRMATION`, `FUTURE_INTEGRATION` |
| `asserted_by` | Bounded actor token (`USER`, `GMAIL_SYNC`, `BROWSER`, `LEGACY_BOOTSTRAP`) |
| `confidence` | `HIGH`/`MEDIUM`/`LOW` for an automated source, empty for a manual one |
| `gmail_account_id` | #45's opaque connection identity — a digest of local random credential material, never an address or token |
| `gmail_message_id` | Gmail message identifier |
| `gmail_confirmation_id` | The `gmail_confirmations` row the assertion rests on |
| `parser_id` | Parser identifier/version, validated against the parser list |
| `evidence_tokens` | Bounded tokens only (see below) |
| `field_agreement` | Which reconciliation fields agreed, as field names only |
| `occurred_at`, `recorded_at` | When it happened; when ASTRA wrote it |
| `reason_code` | Bounded decision code |

The history is **append-only during ordinary application operation**. Nothing
updates or deletes a row; rows leave only with the application itself, through
the privacy controls' explicit deletion scopes.

### What is never stored

No column can hold an email body, HTML, a MIME structure, a snippet, an
authentication header, a secret, a URL with a query string, exception text or
any other unbounded external content. The table's complete column list is
asserted by test, so adding one is a deliberate, reviewed act.

`evidence_tokens` accepts only members of a closed vocabulary derived from
`gmail_confirmations` and `gmail_content` (the five corroboration signals, the
authentication verdict tokens, the parsing-limit tokens, and this module's own
legacy/timestamp tokens). Anything else — which is what a leaked company name
or subject line would look like — is dropped, not truncated. `parser_id` is
validated against the known parser list. `asserted_by`, `gmail_account_id` and
`gmail_message_id` are length- and charset-bounded, and a value containing
control characters is dropped entirely.

Timestamps are parsed strictly. A malformed, absent or non-string
`occurred_at` falls back to the recording time with an explicit
`OCCURRED_AT_INVALID` token; a value more than five minutes in the future is
clamped with `OCCURRED_AT_CLAMPED_NOT_FUTURE`. Neither raises.

## Confidence policy

| Confidence | Effect |
|---|---|
| **HIGH** | May automatically apply `APPLIED`, and only when reconciliation produced **one** unique strong multi-field match and the transition is permitted |
| **MEDIUM** | Creates or retains a Needs Review decision. Application state is not mutated until the user confirms |
| **LOW** | Never mutates application state, and never enters the review queue |

Additional bounds, all enforced in `assert_state()`:

- **`APPLIED` is the only state an automated source may set**
  (`AUTOMATED_TARGET_STATES`). #45 detects `APPLICATION_CONFIRMED` and
  explicitly defers viewed, assessment, interview, rejection and offer, so no
  automated evidence for a later state exists — at any confidence. This is
  structural, not conventional: widening it requires a parser that actually
  produces the evidence, and `DETECTED_STATE_TO_CANONICAL` has no entry for any
  deferred state.
- **A weaker automated signal never supersedes a manually confirmed state.**
  The projection caches `manual_ordinal`, the highest ordinal any manual source
  asserted; an automated transition at or below it is refused with
  `AUTOMATED_WEAKER_THAN_MANUAL`. This sits beside the no-regression property
  of the transition table, not instead of it.
- **User confirmation of a MEDIUM item is a manual transition.** Its
  `source_category` is `USER_CONFIRMED_GMAIL_EVIDENCE`, it carries the user's
  authority, and its history row still references the original Gmail account,
  message, parser and evidence tokens — the provenance chain back to the
  message stays intact.
- Evidence that is stale, ambiguous, contradictory, duplicated or incompatible
  with the current state produces a bounded review or refusal outcome and
  changes nothing.

## Reconciliation

`backend/application_reconciliation.py` decides which existing application a
piece of Gmail evidence is about. It is deterministic: normalized-key equality,
a fixed date window and URL identity, reusing `backend/normalization.py`'s
existing keys so ASTRA has one definition of "the same employer". **There is no
AI, no embedding similarity, no web lookup and no mailbox search.**

Fields compared:

| Field | Comparison |
|---|---|
| `COMPANY` | `normalization.employer_key()` equality |
| `ROLE` | `normalization.title_key()` equality (never strips seniority words) |
| `DATE_PROXIMITY` | Received timestamp within 14 days of the recorded application date, or the job's discovery date |
| `APPLICATION_URL` | `normalization.normalize_url_for_identity()` equality against the job's apply/job/canonical URLs |
| `SOURCE_PLATFORM` | The #45 parser platform against `Job.source` and every #40 `JobObservation.provider_family` |

A field whose value is missing or unusable on either side contributes nothing.
It never counts as agreement, and never as disagreement — absent information
cannot manufacture a match.

**A strong match requires the employer to agree *and* at least two further
independent corroborations**, so it always rests on at least three independent
fields. A single agreeing field never merges records; two are not enough either.

| Situation | Outcome |
|---|---|
| Exactly one strong match, HIGH | Link the evidence and apply `APPLIED` |
| Exactly one strong match, MEDIUM | `NEEDS_REVIEW`; no mutation |
| More than one strong match | `NEEDS_REVIEW` (`AMBIGUOUS_MULTIPLE_STRONG_MATCHES`); no mutation, nothing created |
| One agreeing field only | `NO_ACTION` (`SINGLE_FIELD_AGREEMENT_ONLY`) |
| Some agreement, not strong | `NO_ACTION` (`NO_SUFFICIENTLY_STRONG_MATCH`) |
| No candidate | `NO_ACTION` (`NO_CANDIDATE_APPLICATION`); evidence retained and reviewable |
| LOW confidence | `NO_ACTION` (`LOW_CONFIDENCE_NEVER_MUTATES`) |
| Unsupported detected state | `NO_ACTION` (`DETECTED_STATE_NOT_SUPPORTED`) |

**Reconciliation never creates a `Job` or an `Application`.** Unmatched
evidence stays unmatched. An existing manually recorded application is
therefore never duplicated by an incoming Gmail signal.

Every decision is explainable from its bounded `reason_code`, its
`matched_fields`, and the candidate counts — without naming any candidate.

### Idempotency and concurrency

`gmail_application_links.gmail_confirmation_id` is unique. A reconciliation run
**claims** a confirmation by inserting that row *before* any matching or state
change; a writer that loses the claim never asks the state service for a
transition at all. Replaying the same evidence returns the original decision
unchanged — no second link, no second transition, no re-evaluation.

`application_state_transitions` carries a unique `(application_id, sequence)`
index, so a lost append race is a bounded `CONCURRENT_HISTORY_APPEND` refusal
rather than a gap, a duplicate or an overwrite. The refusal leaves the caller's
transaction usable.

The claim, the transition, the projection update and the decision all happen in
one unit of work, so a failure can neither leave a new current state without
its history nor consume the evidence without a durable decision.

Reconciliation is **explicitly invoked**, exactly like #45's sync. There is no
scheduler and no background reconciliation. It shares the existing
cross-process task lock with discovery, export, deletion and Gmail sync.

## Schema and migration

Three additive tables, declared against the shared SQLAlchemy `Base` in their
own modules:

| Table | Purpose |
|---|---|
| `application_states` | Current-state projection, one row per application |
| `application_state_transitions` | Append-only history |
| `gmail_application_links` | One reconciliation decision per Gmail confirmation |

`backend/models.py`, `backend/policy.py` and `backend/services.py` are
SHA-256-pinned #42 evaluation-provenance inputs. **None of them was modified.**
The tables and their idempotent initializers live in
`backend/application_state.py` and `backend/application_reconciliation.py`,
the same convention #44 and #45 used. No existing table, column, index or row
is altered, so a pre-#46 database upgrades by gaining tables.

### Legacy bootstrap

Existing applications are bootstrapped **lazily, on first contact** — by the
first reader or writer that touches them — never by a bulk rewrite at startup.
The bootstrap derives the canonical state only from what the record already
supports, in decreasing order of specificity: the campaign stage, then
`Application.status`, then `Job.status`. A legacy value with no canonical
meaning (`NO_RESPONSE`, `SKIP`, `FAILED`) asserts nothing and is skipped rather
than being read as `DISCOVERED`.

It writes exactly one history row, `source_category = LEGACY_MIGRATION`, reason
`LEGACY_BOOTSTRAP`, with an empty `previous_state`. **No date, Gmail evidence,
confidence or intermediate transition is invented.** An `applied_date` the
record already carries dates the bootstrap only when the derived state is
`APPLIED` or later, and is tagged `LEGACY_APPLIED_DATE_PRESENT`; otherwise the
row's own creation time is used, which is an honest "this is when ASTRA first
knew", not a claim about when the application happened. A bootstrap carries no
manual authority, so it can never be mistaken for the user's own assertion.

Bootstrapping is idempotent and safe against a concurrent bootstrap: the unique
index on `application_id` turns a lost race into a re-read of the winner's row.
It preserves every existing application, campaign, job, event, document and
follow-up record.

Before a legacy path edits the columns the bootstrap reads, it calls
`prime_state()`. Order matters: a first-ever bootstrap taken *after* the user's
edit would derive the state from the value that edit had just written, record
the user's change as `LEGACY_MIGRATION`, and leave `manual_ordinal` unset so a
later automated signal could re-assert it.

### Rollback

Rolling back to pre-#46 code is supported: the older paths never referenced
these tables, and no pre-#46 row depends on them. The tables may be left in
place or dropped; a regression test asserts that dropping all three leaves
every application, job and legacy status field intact.

**Rollback limitation, stated honestly:** the canonical history is the only
place the provenance of a state change lives. Dropping the tables discards it
permanently — the legacy columns retain the *value* but never the evidence.
Rolling forward again re-bootstraps from the legacy columns and produces a new
`LEGACY_MIGRATION` row; it does not reconstruct the discarded history. Exported
archives and SQLite backups taken while #46 was active retain the history and
require their existing separate user-managed deletion.

**No live-data migration was performed during development.** Every test and
probe ran against isolated synthetic storage with both `DATABASE_URL` and
`HUNTER_DATA_DIR` pointed away from any real database.

## Integration points

| Path | Treatment |
|---|---|
| Campaign tracking (`POST /api/campaign/jobs/{id}/track`) | Primes, then records the user's assertion as `USER_ACTION` |
| Job status action (`POST /api/jobs/{id}/status`) | Primes, then records the user's assertion as `USER_ACTION` |
| Browser confirmation (`backend/browser.py`) | Records `BROWSER_CONFIRMATION` with manual authority. External browser submission remains disabled in this release; the path is routed rather than left as a future bypass |
| Gmail reconciliation | `GMAIL_PARSER`, or `USER_CONFIRMED_GMAIL_EVIDENCE` after review |
| Tracker import (`backend/services.py::import_tracker`) | Unchanged — it is a pinned file. Imported applications are bootstrapped truthfully on first contact, which is the same path every other pre-#46 application takes |
| Existing applications after upgrade | Lazy bootstrap on first contact |

### Compatibility and divergence

The legacy columns keep their existing behaviour exactly, so the current
frontend and API are unaffected (#46 has no UI scope). When a legacy path
asserts a move the canonical table does not permit — a user editing a campaign
stage backwards, for example — the legacy column still moves as before, and the
canonical model records a bounded `TRANSITION_NOT_PERMITTED` decision instead
of following it. **The divergence is recorded, never hidden, and the canonical
state never regresses.** The projections cannot bypass the history because they
are not the authority: nothing reads them to establish canonical state.

## API surface

Bounded reads for #47 to consume later, plus the user's own confirm/reject,
which the backend workflow cannot be completed without. **No route sets a state
directly** — a caller cannot name a target state over the API.

| Route | Purpose |
|---|---|
| `GET /api/applications/{id}/state` | Canonical state, history, legacy compatibility view |
| `GET /api/applications/{id}/state/history` | Append-only history (bounded to 200) |
| `GET /api/applications/state/summary` | Counts per state, plus the declared transition table |
| `GET /api/applications/state/reconciliation` | Fixed reconciliation parameters and decision counts |
| `GET /api/applications/state/needs-review` | Needs Review queue (bounded to 200) |
| `POST /api/applications/state/reconcile` | Explicit bounded reconciliation run |
| `POST /api/applications/state/needs-review/{id}/confirm` | User confirms a review item |
| `POST /api/applications/state/needs-review/{id}/reject` | User rejects a review item |

Every route is mounted on the same FastAPI app as the rest of the private API
and inherits the existing boundary controls unchanged: loopback-only peers, the
TrustedHost allowlist, the Origin allowlist, `Sec-Fetch-Site: cross-site`
rejection, the `Sec-Fetch-Dest` browser-navigation block, the optional
access-key session, bounded request size, the mutation lock on non-GET
requests, `ASTRA_DEMO_ONLY` denial, and `Cache-Control: no-store`. No control
is weakened for this router, and each of these is covered by a test.

## Privacy, export, deletion and backup

- **Export and backup.** The three tables are declared on `Base.metadata`, so
  the private export and SQLite backups include them. Their rows hold only
  bounded tokens, identifiers and timestamps.
- **`DELETE APPLICATION HISTORY`.** Removes canonical state, transition history
  and application-linked reconciliation records, in a foreign-key-safe order
  (children before the `applications` rows they reference). Gmail evidence
  itself is **not** removed: #45's lifecycle is unchanged, and reconciliation
  records that were never linked to an application are not application history
  and are left alone. Deleting an application relationship therefore never
  deletes unrelated Gmail evidence.
- **`DELETE CV`.** Leaves canonical state and reconciliation untouched.
- **`DELETE ALL LOCAL DATA`.** Removes canonical state, history, links and
  Gmail evidence. Links are released before the evidence they reference,
  because SQLite enforces foreign keys.
- **Disconnect.** Unchanged from ADR-0008: it removes the account's token and
  cursor and preserves evidence. #46's records survive alongside it, and the
  history keeps its reference to the originating message.
- **No raw email content** reaches SQLite, WAL/SHM sidecars, backups, exports,
  logs, security events, exceptions or API responses through any #46 path.
  Non-retention sentinels planted in the two fields #46 copies from an evidence
  row are asserted absent from #46's rows, read models, API shapes, export
  contents and every file under the data directory.

## Security events

Two bounded event types extend `backend/security_events.py`:

| Event | When |
|---|---|
| `APPLICATION_RECONCILIATION_CONFLICT` | Evidence matched ambiguously; no state changed |
| `APPLICATION_STATE_TRANSITION_REJECTED` | An automated transition was refused by the state rules |

Both use fixed reason text and a `result` field bounded to the refusal-reason
vocabulary plus `AMBIGUOUS_MATCH`. No company name, role, subject, URL, email
address, message identifier or exception string can reach the log through this
path; unknown fields and out-of-vocabulary values are dropped, which is
asserted by test. The parked v1.2 tamper-evident logging work
(`hardening/l2-r13-r14`, OD-015) was **not** pulled forward.

## R-18 treatment evidence

R-18 is *reconciliation/duplicate manipulation or status-evidence spoofing
causing an incorrect application-state transition*. This change provides
treatment evidence for the two abuse cases the threat-model delta names:

- *Duplicate/reconciliation manipulation.* Matching requires at least three
  independent agreeing fields, never one guessable field; ambiguity produces a
  review item rather than a merge; nothing is ever created; and every decision
  carries a bounded reason code and field-agreement metadata.
- *Status-evidence spoofing.* `APPLIED` is the only state an automated source
  may set, at HIGH confidence only, and only on a unique strong match; a weaker
  automated signal can neither downgrade nor upgrade past a manually confirmed
  state.

**R-18 remains OPEN.** The residual the delta identified is unchanged: an
attacker who already knows the user's real application details — employer,
role, approximate date and application URL — could still force a false merge,
and a spoof that satisfies #45's HIGH-confidence signals could still be
accepted. Multi-field matching raises the cost; it does not eliminate the
abuse case. Only later independent review and an Owner decision can change
R-18's residual-risk state. **No residual-risk acceptance or release approval
is implied.**

## Known limitations

- **No live mailbox validation.** Every test uses fictional evidence rows
  constructed directly in an isolated database. Nothing here measures
  real-world reconciliation accuracy, and no such claim is made.
- **No independent review yet.** This is implementation and self-verification.
- Only `APPLIED` can arrive automatically, because #45 parses nothing else.
  `VIEWED`, `ASSESSMENT`, `INTERVIEW`, `OFFER` and `REJECTED` are reachable only
  by the user's own action until a parser exists for them.
- Matching is exact-key, not fuzzy. An employer name or job title recorded
  differently in ASTRA than in the confirmation email will not agree, and the
  evidence stays unmatched rather than being guessed at. This favours precision
  over recall, deliberately.
- The 14-day date window and the "employer plus two corroborations" threshold
  are engineering judgements, not calibrated values. No dataset supports them.
- Cross-grant reconciliation is not claimed: #45 starts a new evidence
  namespace on reconnect, so evidence created under a previous grant cannot be
  matched to evidence under the new one.
- The legacy bootstrap cannot reconstruct history that was never recorded. A
  pre-#46 application starts with exactly one truthful row.
- Historical duplicate `Job` rows from before #40 remain unconsolidated
  (Owner Decision 2), so an evidence row could in principle match the
  "wrong one" of two pre-#40 duplicates. It would then be ambiguous and go to
  review, not be merged.

## Verification

Self-verification results, commands and exact counts are recorded on the pull
request and in `docs/governance/PROJECT_STATE.md`. Hosted results belong to the
PR's exact head; local results do not substitute for hosted CI or independent
review.
