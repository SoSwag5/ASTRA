# Application state, transition history and Gmail reconciliation (#46)

Implementation owner: Claude Code, on `feature/46-application-reconciliation-state-model`
from `11a69b0921d55072aa4f552a0319320ab73d6741` (merged #45 / PR #67).
Revised across three independent review rounds; the reproduced defects and
their fixes are described in their sections below and summarised under
"Review remediation".
Independent review of the final candidate `006e9111a196e940d8d11163548ef642c2007e5c`
returned **APPROVE**, and the work merged to `master` via
[PR #68](https://github.com/SoSwag5/ASTRA/pull/68) as squash commit
`7ecd0b78277f67db0a44db176db467bcfb1f5a17`.
Review and testing were offline and deterministic: **no live mailbox
validation** has been performed, and **real-world reconciliation accuracy
remains unmeasured**.
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
| `DISCOVERED` | `SAVED`, `APPLIED`, `VIEWED`, `ASSESSMENT`, `INTERVIEW`, `OFFER`, `REJECTED`, `CLOSED` |
| `SAVED` | `APPLIED`, `VIEWED`, `ASSESSMENT`, `INTERVIEW`, `OFFER`, `REJECTED`, `CLOSED` |
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
- `OFFER` and `REJECTED` may only be closed. This is why the table stays
  explicit rather than being derived from the ordinal: `OFFER` and `REJECTED`
  are adjacent ordinals that must not reach each other.
- `CLOSED` is terminal with no outgoing transition, and is reachable from every
  other state (abandoning or archiving an application is always legitimate).
- A post-submission state **is** reachable from `DISCOVERED` and `SAVED`. The
  user is then recording a stage for an application they submitted outside
  ASTRA and never tracked here — they are correcting ASTRA's record, not
  claiming an impossible history. The transition carries
  `SUBMISSION_IMPLIED_BY_LATER_STATE` so the audit trail says the submission
  was implied by the user's assertion rather than observed by ASTRA.

  An earlier revision forbade these pairs. That was removed because it was
  **not** a security control — what actually bounds automated evidence is
  `AUTOMATED_TARGET_STATES`, the confidence gate and the manual-authority
  check, none of which the restriction participated in — while it did cause
  the canonical state and the legacy status columns to diverge whenever a user
  recorded an interview or rejection on a job they had not marked applied.

All 81 ordered state pairs — the 35 permitted and the 46 forbidden — are
covered by a fixture-driven regression in `tests/test_application_state.py`.

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

### Contradiction is not the same as absent agreement

Exactly one field can positively **contradict**: the application URL. When both
records resolve to a job-specific requisition identity and those identities
differ, the records name two different postings, and that outweighs every other
field. Employer, title, approximate date and source platform are exactly what
two genuinely separate applications to the same employer would share, so no
amount of agreement there can restore a strong match. A contradicted candidate
is never linked automatically.

Contradiction is deliberately narrow. `normalize_url_for_identity()` returns
`None` for a generic careers root, a tenant root, a login/portal page or a
search page, so such a URL establishes no identity and contradicts nothing.
Two spellings of the same posting — differing in scheme case, host case, a
trailing slash, or tracking parameters — normalize to the same key and agree.
Company, role, date and platform are never treated as contradictions, because
two applications to one employer routinely differ there without either record
being wrong.

A contradicted candidate is still **confirmable**: it is offered to the user as
a review item with the proposed target attached. Deciding whether two postings
are one application is precisely the judgement only the user can make, and a
review queue whose items cannot be resolved is the failure this distinction
exists to avoid.

| Situation | Outcome |
|---|---|
| Exactly one strong match, HIGH | Link the evidence and apply `APPLIED` |
| Exactly one strong match, MEDIUM | `NEEDS_REVIEW`; no mutation |
| More than one strong match | `NEEDS_REVIEW` (`AMBIGUOUS_MULTIPLE_STRONG_MATCHES`); no mutation, nothing created |
| Corroborated but contradictory requisition URL | `NEEDS_REVIEW` (`CONTRADICTORY_APPLICATION_URL_IDENTITY`), target proposed; never linked automatically |
| One agreeing field only | `NEEDS_REVIEW` (`SINGLE_FIELD_AGREEMENT_ONLY`), unattached |
| Some agreement, not strong | `NEEDS_REVIEW` (`NO_SUFFICIENTLY_STRONG_MATCH`), unattached |
| No candidate | `NEEDS_REVIEW` (`NO_CANDIDATE_APPLICATION`), unattached |
| LOW confidence | `NO_ACTION` (`LOW_CONFIDENCE_NEVER_MUTATES`) |
| Unsupported detected state | `NO_ACTION` (`DETECTED_STATE_NOT_SUPPORTED`) |

### Unlinkable evidence stays resolvable

HIGH and MEDIUM evidence that could not be linked becomes a **review item**,
not an unrecoverable `NO_ACTION`. The matching application very often simply
does not exist yet — the user saves or records it after the confirmation
arrives — and a decision taken before it existed must not be final.

Two mechanisms keep that deterministic:

- `confirm_review()` re-evaluates candidates at confirmation time, so an item
  becomes actionable as soon as a valid target exists, with no reconciliation
  run in between. When the item names no target and exactly one corroborating
  candidate exists, that one is used; otherwise the user names it explicitly.
  A target that does not corroborate is refused, leaving the item reviewable.
- `reconcile_pending()` also revisits review items that are **still awaiting
  review and not yet attached to an application**, through the same decision
  path as the first pass. HIGH with a now-unique uncontradicted match links;
  MEDIUM attaches the proposed target without mutating anything. An item
  already proposing a target is never revisited, so it cannot be swapped
  underneath a user who is looking at it, and a rejected or resolved item is
  never revisited at all.

Only the one existing link row is ever updated, so repeated runs cannot
duplicate links, transitions or review items.

LOW is unchanged: it never mutates state and never enters the queue, because
#45 caps the generic fallback at LOW precisely because it verified nothing.

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

### One budget for the whole run, and durable fairness

`reconcile_pending(limit=...)` bounds the **total** number of evidence rows a
run processes: `considered + revisited` never exceeds the requested limit, and
the request is itself clamped to `MAX_RUN_EVIDENCE`. The run reports `limit`
and `processed` alongside the counts so a caller can see the bound was kept.

Two earlier revisions got this wrong in different ways, and both are worth
recording because the second looked correct:

1. The limit was applied to each queue separately, so a run could process up
   to twice what was asked for.
2. The shared budget was correct, but the revisit queue was ordered by
   `gmail_application_links.id`. An unmatched item keeps its id, so the oldest
   unmatched items were re-selected on every run and later items were never
   reached — even after one of them became actionable. A non-zero `revisited`
   count looked like progress while the same rows were retried forever.

Fairness is now **durable**, held in the database rather than in any
process-local value, so it survives separate API requests, process restarts
and several workers sharing one local database.

**Within the revisit queue — rotation.** `gmail_application_links` carries
`revisit_sequence`, the value of a single monotonic counter
(`reconciliation_scheduler.attempt_sequence`) in force the last time a run
touched that row. The queue is ordered by `(revisit_sequence, id)`, and every
item a run touches is stamped with a fresh value, which moves it to the back.
An item can therefore never be re-selected ahead of one that has waited
longer.

*Why this terminates:* the counter is strictly increasing and allocated inside
the processing transaction, so no two rows ever share a stamp and the ordering
is total. With `U` eligible items and `r` revisit slots per run, every item is
attempted within `ceil(U / r)` runs — at worst `U` runs, when a run gives
revisits only one slot. A row that is selected but turns out ineligible is
stamped anyway before being skipped, so it cannot hold a slot run after run.

**Between queues — a durable pointer.** `reconciliation_scheduler.next_queue`
records which queue gets the next slot. It is advanced once per *processed*
item, inside that item's own transaction, so a crash leaves it exactly where
the last commit put it. Slots alternate from that pointer, and when the
preferred queue is empty the other takes the slot, so a single non-empty queue
still receives the whole budget.

This replaces an earlier documented exception which said that at `limit=1`
new confirmations would always win and the revisit queue could wait
indefinitely. **That exception no longer applies and the claim is withdrawn.**
At `limit=1` consecutive runs alternate, which
`test_limit_one_alternates_across_real_process_restarts` demonstrates across
six separate operating-system processes.

**Within the pending queue.** A confirmation leaves that queue permanently
once processed — it gains a link row — so ordering by `gmail_confirmations.id`
already gives eventual progress: the item at position `k` is reached within
`ceil(k / p)` runs for `p` pending slots per run.

**No duplicate processing.** Both snapshots are read before any processing and
the two sources are disjoint by construction — a confirmation either has a
link row or does not — so a review item a run creates is never also revisited
by that same run, and an explicit `seen` set makes that guarantee visible.

**Only eligible items are revisited.** The selection joins the evidence table
and filters to `decision = NEEDS_REVIEW` with a null `application_id`, and the
same conditions are re-checked inside the processing transaction. Linked,
no-action, user-confirmed, user-rejected, attached, deleted and concurrently
settled rows are all excluded, and a row that becomes ineligible between
planning and processing is counted as `skipped`, never as processed.

**Truthful counters.** `processed` equals `considered + revisited` and never
exceeds `limit`. `skipped` counts rows that were selected but not processed.
`revisits_changed` counts only revisits that actually changed the durable
decision, so repeated no-op retries cannot be read as queue progress.

## Schema and migration

Four additive tables, declared against the shared SQLAlchemy `Base` in their
own modules:

| Table | Purpose |
|---|---|
| `application_states` | Current-state projection, one row per application |
| `application_state_transitions` | Append-only history |
| `gmail_application_links` | One reconciliation decision per Gmail confirmation |
| `reconciliation_scheduler` | One row of durable scheduling state: a monotonic `attempt_sequence` counter and the `next_queue` pointer |

`backend/models.py`, `backend/policy.py` and `backend/services.py` are
SHA-256-pinned #42 evaluation-provenance inputs. **None of them was modified.**
The tables and their idempotent initializers live in
`backend/application_state.py` and `backend/application_reconciliation.py`,
the same convention #44 and #45 used. No existing table, column, index or row
is altered, so a pre-#46 database upgrades by gaining tables.

The scheduler arrived after `gmail_application_links` already existed on this
branch, so its upgrade is explicitly additive and idempotent:
`initialize_reconciliation_schema()` adds `revisit_sequence INTEGER NOT NULL
DEFAULT 0` when the column is absent, creates the
`(revisit_sequence, id)` rotation index, creates the scheduler table and seeds
its single row. Every pre-existing link therefore starts at 0 — "never touched
by the scheduler" — so the first run after the upgrade rotates through the
whole existing backlog in id order exactly as a fresh install would. Nothing
is rewritten and no decision changes.

The scheduler row holds no personal data: a counter and a two-value queue
token, both asserted by test. It follows `Base.metadata`, so it is included in
the private export and in SQLite backups like every other declared table.
`DELETE APPLICATION HISTORY` removes application-linked reconciliation records
and leaves the counter alone — it is operational state, not application
history. `DELETE ALL LOCAL DATA` removes the links and **resets** the
scheduler row to its initial values, so the counter never outlives the stamps
it produced.

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

Priming is not enough on its own when the legacy path **creates** the
application, which is what the job status route does for a job that was never
tracked. There is nothing to prime, `set_status()` creates the row already in
the requested state, and the bootstrap would then read the user's own edit back.
Those callers capture `pre_action_state()` *before* their edit — the
application's current canonical state, or, when no application exists, the
job's own workflow status — and pass it as `bootstrap_from`. The bootstrap then
records where the application actually was, tagged `LEGACY_PRE_ACTION_STATE`,
and the user's change is a genuine `USER_ACTION` transition on top of it with
manual authority set. Both the job status route and campaign tracking do this.

### Read-repair: complete, order-independent read models

An application that has never been touched has no projection row. Left alone,
that made the read models depend on browsing order: the summary counted only
applications something had previously opened, and an application's own history
was empty until its detail view was read.

`ensure_all_states()` is the read-repair. `state_summary()`,
`transition_history()` and `state_of()` all run it (or the single-application
equivalent) before answering, so every answer accounts for every application
regardless of what was read first. It is deterministic (each application
bootstraps from its own legacy columns by the same rules as any single
bootstrap), idempotent (an application that already has a projection is
skipped, and the unique index makes a concurrent double-bootstrap impossible),
auditable (each writes exactly one `LEGACY_MIGRATION` row) and bounded
(`MAX_BACKFILL`, with each application committed in its own transaction so a
partial failure leaves the completed ones intact). It never attributes a user
action to migration, because it only ever runs for applications no user action
has touched.

`state_summary()` reports `applications_total`, `pending_initialization` and
`complete` alongside the counts, so in the pathological case where more
applications exist than one call initializes the reader is told the breakdown
is partial instead of being quietly handed a short total.

A nonexistent application stays distinguishable from an existing but
uninitialized one: `transition_history()` and `state_of()` return `None` for an
identifier that does not exist (the API answers 404), while an existing
application returns its history, initializing it first if needed.

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
| `GET /api/applications/{id}/state/history` | Append-only history (bounded to 200); 404 when no such application |
| `GET /api/applications/state/summary` | Counts per state, plus the declared transition table |
| `GET /api/applications/state/reconciliation` | Fixed reconciliation parameters and decision counts |
| `GET /api/applications/state/needs-review` | Needs Review queue (bounded to 200) |
| `POST /api/applications/state/reconcile` | Explicit reconciliation run; `limit` bounds the total rows processed across both queues |
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
vocabulary plus `AMBIGUOUS_MATCH` and `URL_IDENTITY_CONFLICT`. No company name, role, subject, URL, email
address, message identifier or exception string can reach the log through this
path; unknown fields and out-of-vocabulary values are dropped, which is
asserted by test. The parked v1.2 tamper-evident logging work
(`hardening/l2-r13-r14`, OD-015) was **not** pulled forward.

## R-18 treatment evidence

R-18 is *reconciliation/duplicate manipulation or status-evidence spoofing
causing an incorrect application-state transition*. This change provides
treatment evidence for the two abuse cases the threat-model delta names:

- *Duplicate/reconciliation manipulation.* Matching requires at least three
  independent agreeing fields, never one guessable field; a contradictory
  requisition URL blocks automatic linking outright, so an attacker who knows
  the employer, role and approximate date still cannot force a merge onto a
  posting the evidence does not name; ambiguity produces a review item rather
  than a merge; nothing is ever created; and every decision carries a bounded
  reason code and field-agreement metadata.
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
- **No independent review of live behaviour.** Independent review of
  `006e911` returned APPROVE on the code and its offline evidence only.
- Only `APPLIED` can arrive automatically, because #45 parses nothing else.
  `VIEWED`, `ASSESSMENT`, `INTERVIEW`, `OFFER` and `REJECTED` are reachable only
  by the user's own action until a parser exists for them.
- Matching is exact-key, not fuzzy. An employer name or job title recorded
  differently in ASTRA than in the confirmation email will not agree, and the
  evidence stays unmatched rather than being guessed at. This favours precision
  over recall, deliberately.
- Because unlinkable HIGH/MEDIUM evidence is now queued rather than dropped, a
  mailbox containing many confirmations for applications ASTRA does not track
  produces a correspondingly long review queue. That is the honest state of
  affairs — the alternative was discarding them silently — but the queue's
  presentation and any bulk dismissal belong to #47, not here.
- Contradiction is detected only on the application URL. Two applications to
  one employer that differ only in title or date are not contradicted, and can
  still reach a strong match on employer, date and platform if their titles
  agree. Requisition-level identity is the only signal conservative enough to
  treat as decisive.
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

## Review remediation

An independent review of `150a45a` returned CHANGES REQUIRED with four
reproduced defects. All four were fixed on this branch:

1. **Conflicting requisition URLs auto-linked.** Excluding `APPLICATION_URL`
   from the agreeing fields let the remaining four satisfy the threshold.
   Contradiction is now modelled separately from absent agreement and blocks
   automatic linking; the item is offered to the user instead.
2. **The first manual status change was recorded as `LEGACY_MIGRATION`.** For a
   job with no application, priming was a no-op and the bootstrap read back the
   state the user's own action had just written. Callers now capture
   `pre_action_state()` before their edit and pass it as `bootstrap_from`, so
   the change is a `USER_ACTION` transition with manual authority.
3. **Unmatched MEDIUM evidence was consumed as `NO_ACTION`.** It never reached
   Needs Review, could not be confirmed, and was never revisited. HIGH and
   MEDIUM evidence that cannot be linked is now a resolvable review item, and
   `reconcile_pending()` revisits unresolved unattached items.

Two further review rounds each reproduced one more defect, both fixed on this
branch:

5. **A run could process twice the requested limit.** `reconcile_pending()`
   applied `limit` to the new-confirmation query and the unresolved-review
   query independently, so `limit=2` processed four rows. The two queues now
   share one budget, and `considered + revisited` never exceeds the requested
   limit.
6. **The revisit queue starved.** Ordering by `gmail_application_links.id`
   re-selected the same oldest unmatched items on every run, so a later item
   was never reached even once it became actionable. The queue is now rotated
   by a durable `revisit_sequence` stamp, and queue alternation is held in a
   durable pointer, so fairness survives restarts and `limit=1` alternates
   instead of favouring one side.
4. **Summaries and histories were order-dependent.** A legacy application was
   invisible until its detail view happened to be opened. `ensure_all_states()`
   read-repair makes every read complete and order-independent, and a
   nonexistent identifier stays distinguishable from an uninitialized one.

## Verification

Self-verification results, commands and exact counts are recorded on the pull
request and in `docs/governance/PROJECT_STATE.md`. Hosted results belong to the
PR's exact head; local results do not substitute for hosted CI or independent
review.
