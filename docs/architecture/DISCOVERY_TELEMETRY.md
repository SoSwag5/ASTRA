# Discovery funnel telemetry (`discovery-telemetry-v1`)

Issue #43. Implemented by `backend/discovery_telemetry.py`, instrumented from
`backend/main.py`'s existing `task('discover')` loop, and read through
`backend/search_workspace.py`'s `/api/search/telemetry*` endpoints.

## 1. Why this exists

Before #43 the headline discovery signal was "N/N sources healthy". That number
stays true while a run produces no useful jobs at all, because it says nothing
about where candidates were lost. This feature replaces it with a per-run and
per-source **monotonic funnel** plus explicitly separated failure, partial and
skipped states, so an operator can see the stage at which a source stopped
contributing.

This is instrumentation only. It does not change ranking, eligibility,
deduplication, provider transport or application lifecycle semantics. Every
stage value is read from the component that already owns that decision:

| Concern | Owner | Issue |
|---|---|---|
| Provider fetch, health, completion | `backend/job_providers/` | #38, #39 |
| Structural validity, identity, deduplication | `backend/services.add_job`, `backend/deduplication` | #40 |
| Geography, eligibility, relevance, ranking | `backend/assessment` via `backend/recall.evaluate` | #41 |
| Funnel accounting and reporting | `backend/discovery_telemetry` | #43 |

## 2. Schema version and persistence

- Schema version: **`discovery-telemetry-v1`** (`TELEMETRY_SCHEMA_VERSION`).
- Persistence: the payload is stored in the existing `AutomationRun.report`
  JSON under the key **`discovery_telemetry`** (`REPORT_KEY`).
- **No database migration.** `AutomationRun.report` already satisfies every
  requirement: per-run retrieval (by `AutomationRun.id`), per-source retrieval
  (the `sources` array inside the payload), 90-day retention (`created_at` is
  already indexed by primary key order and already drives the pre-existing
  verbose-decision cleanup), API serialization (the report is already JSON),
  future #47 consumption (through the API below), and atomic run finalization
  (the payload is written in the same `db.commit()` that finalizes the run).
  No `Job`/`JobObservation` identity field and no `Application` lifecycle field
  was changed for telemetry.

## 3. The monotonic funnel

```
FETCHED
  -> STRUCTURALLY_VALID
    -> CANONICAL_UNIQUE
      -> LOCATION_COMPATIBLE
        -> ELIGIBILITY_NOT_INCOMPATIBLE
          -> RELEVANT
            -> NEW
```

`DISPLAYED`, `SAVED` and `APPLIED` are **not** funnel stages. See §7.

### 3.1 Exact counter definitions

**`FETCHED`** — provider observations delivered by the provider/compatibility
boundary (`backend.adapters.discover`, i.e. `to_legacy_items(batch)`) to the
discovery orchestration loop for this source attempt. It is *not* network pages,
*not* HTTP requests, *not* raw JSON elements, and *not* the provider's own
pre-validation row count. Upstream provider metrics such as `records_received`
(rows the provider enumerated) and `records_rejected` (rows the provider's own
native-shape validation rejected before orchestration ever saw them) are
preserved separately under `provider_metrics` and are never mixed into the
funnel.

**`STRUCTURALLY_VALID`** — fetched observations that safely satisfied #40's
ingestion/persistence contract, i.e. `backend.services.add_job()` accepted them.
An observation `add_job()` rejects becomes an `INVALID_JOB` disposition and never
enters this stage. There is **no second structural validator**: `add_job()` and
the normalization/persistence seam behind it are the only authority.

**`CANONICAL_UNIQUE`** — distinct canonical `Job` identities represented by the
structurally valid observations of this source attempt, as resolved by #40's
deduplication. Repeated observations resolving to the same canonical job count
once. This is **not** "new database row": a canonical `Job` that already existed
is still a unique member of this attempt. Telemetry never reproduces identity
matching from fingerprints — it records the `Job.id` that `add_job()` returned.

**`LOCATION_COMPATIBLE`** — canonical-unique jobs whose authoritative #41
decision is *not* location-incompatible, read from `decision['location_compatible']`
(in mode `NEW`, `geography.compatibility != INCOMPATIBLE`). UNKNOWN geographic
evidence follows existing #41 semantics and stays compatible; it is never
silently converted into incompatible.

**`ELIGIBILITY_NOT_INCOMPATIBLE`** — among location-compatible jobs, those whose
authoritative #41 eligibility result is not *confirmed* incompatible, read from
`decision['eligibility']['state']` and the hard-reject codes
`CONFIRMED_ELIGIBILITY_CONFLICT` / `EXPLICIT_NATIONALITY_RESTRICTION`. UNKNOWN
remains not-confirmed-incompatible. Work authorization, sponsorship, nationality
and residence are never inferred from missing evidence.

**`RELEVANT`** — among eligibility-not-incompatible jobs, those the existing #41
assessment did not hard-reject at all (`decision['excluded'] is False`). Since
geography and eligibility rejections have already been accounted for at earlier
stages, the exits recorded here are the remaining hard reasons —
`DOMAIN_INCOMPATIBLE`, `EXTREME_LEADERSHIP_MISMATCH`, `USER_BLOCKED`, and their
legacy-mode equivalents. There is no new relevance classifier. Experience gaps,
seniority uncertainty and imperfect fit are **ranking penalties** in #41, not
rejections, so such a job stays in `RELEVANT` and is merely ranked lower.

**`NEW`** — among relevant jobs, canonical jobs first created during this
discovery run, taken from #40's own answer (`add_job()` returned no duplicate
record). It excludes existing jobs merely re-observed, duplicate provider
observations, jobs that already dropped out before `RELEVANT`, and previously
known jobs whose timestamps were refreshed. A canonical row created for a
hard-rejected posting is genuinely created — it is reported as
`diagnostics.canonical_jobs_created_all_dispositions`, never as `NEW`.

### 3.2 Monotonicity

`FETCHED >= STRUCTURALLY_VALID >= CANONICAL_UNIQUE >= LOCATION_COMPATIBLE >=
ELIGIBILITY_NOT_INCOMPATIBLE >= RELEVANT >= NEW`, all non-negative integers.

This is **structural, never clamped**. `SourceAttempt` accumulates stage
membership as sets of stable identifiers (observation counters for the first two
stages, canonical `Job` ids for the rest), each derived with strict nesting from
the previous stage, and only serializes aggregate counts at finalization. A job
whose decision arrives without it having entered `CANONICAL_UNIQUE` is ignored
rather than counted.

`discovery_telemetry.validate()` then re-checks every invariant and raises
`TelemetryError`. It is called on every finalization and directly in tests, so an
impossible funnel cannot be published silently.

## 4. Observation versus canonical-job counting, and run aggregation

`funnel_basis` states the unit of every stage explicitly:

| Stages | Unit |
|---|---|
| `FETCHED`, `STRUCTURALLY_VALID` | `PROVIDER_OBSERVATIONS` |
| `CANONICAL_UNIQUE` … `NEW` | `CANONICAL_JOBS` |

The transition happens at `CANONICAL_UNIQUE`, where #40 resolves observations
into canonical identities.

Run-level aggregation (`funnel_aggregation.rule`):

- `FETCHED` and `STRUCTURALLY_VALID` are **sums** of the per-source observation
  counts. Two sources that each delivered the same posting genuinely made two
  observations.
- Every canonical stage is the size of the **union** of the per-source canonical
  id sets, so a job observed by more than one provider counts exactly once for
  the run. Per-source canonical counts are never summed, which would
  double-count cross-provider jobs.

`validate()` enforces the consequence: for every canonical stage,
`max(per-source) <= run <= sum(per-source)`.

## 5. Failure versus zero versus partial versus skipped

The all-zero funnel is never used to express a failure. Two independent fields
carry the outcome, alongside the provider's own `health` / `completion` /
`completion_reason` / bounded `error_code`:

- `fetch_outcome` describes the **provider boundary**: `SUCCEEDED`, `PARTIAL`,
  `FAILED`, `NOT_ATTEMPTED`.
- `attempt_outcome` describes the **whole attempt** (fetch plus ingestion and
  assessment): `OK`, `PARTIAL`, `FAILED`, `INGESTION_FAILED`, `SKIPPED`.

| State | `attempt_state` | `fetch_outcome` | `attempt_outcome` | Funnel |
|---|---|---|---|---|
| 1. Fetch succeeded, zero observations | `ATTEMPTED` | `SUCCEEDED` (`health: EMPTY`) | `OK` | all zero, `counts_complete: true` |
| 2. Observations fetched, none survived a later stage | `ATTEMPTED` | `SUCCEEDED` | `OK` | `FETCHED > 0`, later stage 0 |
| 3. Explicit provider budget/completion condition | `ATTEMPTED` | `PARTIAL` | `PARTIAL` | counted, `counts_complete: false` |
| 4. Fetch failed before trustworthy results | `ATTEMPTED` | `FAILED` | `FAILED` | all zero, `error_code` set |
| 5. Skipped, not due (scheduled run) | `SKIPPED_NOT_DUE` | `NOT_ATTEMPTED` | `SKIPPED` | all zero |
| 6. Disabled, or outside a targeted run | `SKIPPED_DISABLED` / `SKIPPED_NOT_TARGETED` | `NOT_ATTEMPTED` | `SKIPPED` | all zero |
| 7. Valid results returned, ingestion then failed | `ATTEMPTED` | `SUCCEEDED`/`PARTIAL` | `INGESTION_FAILED` | observations kept, canonical stages cleared, `rolled_back: true` |

Notes:

- In state 7 the source's `completion`/`health` mirror what the existing
  per-source report records for a raised source (`FAILED`/`UNAVAILABLE`), while
  `fetch_outcome` keeps describing the fetch boundary itself. That pairing is
  precisely what distinguishes state 7 from state 4.
- `counts_complete` is only meaningful when `attempted` is true. For a skipped
  source it is `false` with `incomplete_reason` naming the skip, so an all-zero
  row is never mistaken for a scanned, empty source.
- `validate()` rejects any non-attempted source that carries a non-zero count.

### 5.1 Partial completion

A `PARTIAL` fetch (e.g. `DETAIL_BUDGET_EXHAUSTED`, `DETAIL_FETCH_INCOMPLETE`,
`PAGINATION_LIMIT_REACHED`) reports its real counts and marks them
`counts_complete: false` with `incomplete_reason` set to the provider's own
completion reason. The run-level `counts_complete` is false whenever any
attempted source is incomplete, and `sources_incomplete` counts them.

### 5.2 Telemetry's own failure

A telemetry defect must never corrupt persistence or fabricate counts:

- Each source's ingestion is already committed before finalization runs, so a
  telemetry error cannot roll back a valid source's jobs.
- `RunTelemetry.finalize()` catches every exception (including an invariant
  violation) and returns a bounded payload with `status: TELEMETRY_ERROR`,
  `telemetry_error_code: TELEMETRY_FINALIZATION_FAILED` and `funnel: null` —
  no counts at all rather than wrong ones.

## 6. Bounded error classification

External provider content is untrusted, so nothing is copied through verbatim:

- `error_code` must be a code from the closed transport/provider taxonomy
  (`ERROR_CODES`); anything else — including a code invented by a response —
  becomes `UNCLASSIFIED`.
- `error_class` is a local normalization of `health`: `POLICY_BLOCKED`,
  `RATE_LIMITED`, `AUTH_REQUIRED`, `MALFORMED_RESPONSE`, `SOURCE_UNAVAILABLE`,
  `PARTIAL_RESULT`, `INGESTION_ROLLED_BACK`, `UNCLASSIFIED`.
- Provider error **messages** are never carried. Source names are the user's own
  configured values and are bounded to 200 characters; provider families must
  match an identifier shape or become `unknown`.

## 7. Engagement outcomes

`DISPLAYED`, `SAVED` and `APPLIED` are asynchronous engagement outcomes reported
in a separate `engagement` object, at run level and per source. They are never
funnel filters, and `validate()` rejects a payload that places a funnel stage
inside `engagement` or vice versa.

Exactly one meaning is used, declared as `basis`:

> `RUN_OBSERVED_CANONICAL_JOBS_AT_RUN_FINALIZATION` — canonical jobs this run
> observed, whose authoritative persisted state carried the outcome at the moment
> the run was finalized.

It is **not** a during-run event count and **not** a current-state-at-query-time
count. These meanings are never mixed.

| Outcome | State | Authority |
|---|---|---|
| `DISPLAYED` | `UNAVAILABLE`, `count: null` | none |
| `SAVED` | `AVAILABLE` | `Job.analysis.saved` |
| `APPLIED` | `AVAILABLE` | `Application.applied_date` |

`DISPLAYED` stays explicitly unavailable in v1.1. ASTRA records no discovery
display/impression event. `Job.analysis['seen_at']` is a user-triggered
acknowledgement of a single job, not a display event and not run-scoped, so it is
**not** counted as `DISPLAYED`; no invasive UI event tracking was added to make
the value non-null. `DISPLAYED` is never inferred from `RELEVANT`, API retrieval
or database existence; `SAVED` is never inferred from ranking; `APPLIED` is never
inferred from preparation or readiness. Reads are read-only — no telemetry field
was added to `Application` lifecycle authority.

## 8. Version metadata

Every run identifies the production decision contract that produced it, under
`versions`: `telemetry_schema_version`, `assessment_schema_version`,
`assessment_ruleset_version`, `assessment_mode`, `recall_version`,
`taxonomy_version`, `experience_parser_version`, `normalization_version`,
`dedupe_version`, `provider_contract_version`. All are read from the central
constants the owning production modules already define; none comes from a
mutable documentation file.

`versions.evaluation_reference` carries #42 **evidence** metadata and states so
explicitly:

- `authority: OFFLINE_EVALUATION_EVIDENCE_ONLY` — it is never runtime authority.
- The production algorithm/version is the `assessment_*` fields above.
- The evaluation corpus/report versions are `corpus_schema_version`,
  `report_schema_version`, `human_label_version`.
- The evaluation result/status is `quality_gate_status: INSUFFICIENT_DATA` with
  `quality_gate_approval_state: PROPOSED / NOT OWNER-APPROVED`. **No quality
  gate is claimed to have passed.**

Production discovery does **not** import or rerun `backend/evaluation.py`, so
these are declared as stable literals in `backend/discovery_telemetry.py`.
`tests/test_discovery_telemetry.py` cross-checks them against #42's own
constants and its committed report, so they cannot drift silently.

## 9. Retention — exactly 90 days

`RETENTION_DAYS = 90`. `discovery_telemetry.prune_expired(db, clock=None,
limit=500)` runs at the end of every discovery run and replaces the pre-#43
verbose-decision cleanup.

- **Boundary:** *strictly* older than the UTC cutoff. A run whose `created_at`
  equals the cutoff is **kept**; a run one second older is pruned. Tests cover
  just-before, exact-boundary and just-after.
- **What is removed:** the `discovery_telemetry` payload and the verbose
  `decisions` list, from `AutomationRun` rows with `task == 'discover'`.
- **What is preserved:** every other operational field in the report (e.g.
  `discovered`, `sources`), and every `Job`, `JobObservation`, `Application`,
  user decision and application-history row. Nothing outside discovery
  reporting is scanned or rewritten.
- **No longer-lived aggregates** are retained. Aggregate values do not earn a
  longer retention. Longer trend retention may only be reconsidered in #47 if
  the dashboard demonstrates a genuine requirement.
- **Idempotent:** a second run prunes nothing and writes nothing.
- **Bounded:** at most `limit` runs per invocation, ordered by id.
- **Safe under malformed legacy reports:** a non-dict report is left untouched
  rather than rewritten.

An expired run and a pre-#43 legacy run are both reported by the API as
`TELEMETRY_UNAVAILABLE`. Historical reports are never rewritten to simulate
telemetry that was never captured.

## 10. API contract

Local, read-only, under the existing discovery/search area. Every `/api` route
is already gated by the application's loopback-peer, origin, `Sec-Fetch` and
optional access-key guards; nothing here is exposed externally and no analytics
service was added.

| Endpoint | Purpose |
|---|---|
| `GET /api/search/telemetry` | Latest completed or partial discovery run's telemetry |
| `GET /api/search/telemetry/runs?limit=&offset=` | Bounded history inside the 90-day window, newest first |
| `GET /api/search/telemetry/runs/{run_id}` | One run by local integer id |

- `limit` defaults to 5 and is clamped to a maximum of 20 runs
  (`MAX_TELEMETRY_RUNS`); a non-positive `limit` or negative `offset` is a 400.
  A non-integer `run_id` is a 422 (path validation), and an unknown, non-discover
  or out-of-retention `run_id` is a 404 carrying only a fixed message — never an
  internal path or SQL error.
- Every response carries `schema_version` and a `status`: `OK`, `NO_DATA`,
  `TELEMETRY_UNAVAILABLE` or `RUN_IN_PROGRESS`.
- Per-source data is inside each run's `telemetry.sources`.
- The projection is **whitelist-based** (`public_view`): only known aggregate
  fields are copied out, so even a payload written by a different build can never
  leak a verbose decision record or private job content through this endpoint.

### Example (sanitized, synthetic)

```json
{
  "schema_version": "discovery-telemetry-v1",
  "status": "OK",
  "run": {
    "run_id": 1,
    "run_status": "PARTIAL",
    "telemetry_status": "OK",
    "telemetry": {
      "schema_version": "discovery-telemetry-v1",
      "status": "INCOMPLETE",
      "trigger": "MANUAL",
      "source_filter": null,
      "funnel": {"FETCHED": 5, "STRUCTURALLY_VALID": 4, "CANONICAL_UNIQUE": 3,
                 "LOCATION_COMPATIBLE": 2, "ELIGIBILITY_NOT_INCOMPATIBLE": 2,
                 "RELEVANT": 1, "NEW": 1},
      "counts_complete": false,
      "sources_total": 5, "sources_attempted": 4, "sources_succeeded": 3,
      "sources_partial": 0, "sources_failed": 1, "sources_skipped": 1,
      "engagement": {
        "basis": "RUN_OBSERVED_CANONICAL_JOBS_AT_RUN_FINALIZATION",
        "observed_canonical_jobs": 3,
        "DISPLAYED": {"state": "UNAVAILABLE", "count": null, "authority": null},
        "SAVED": {"state": "AVAILABLE", "count": 0, "authority": "Job.analysis.saved"},
        "APPLIED": {"state": "AVAILABLE", "count": 0, "authority": "Application.applied_date"}
      },
      "retention": {"retention_days": 90, "expires_at": "2026-12-15T04:23:37+00:00"},
      "sources": [
        {"source_id": 1, "source_name": "Acme Security", "provider_family": "greenhouse",
         "attempted": true, "attempt_state": "ATTEMPTED", "attempt_outcome": "OK",
         "fetch_outcome": "SUCCEEDED", "health": "HEALTHY", "completion": "COMPLETE",
         "error_code": null, "error_class": null, "counts_complete": true,
         "funnel": {"FETCHED": 4, "STRUCTURALLY_VALID": 3, "CANONICAL_UNIQUE": 3,
                    "LOCATION_COMPATIBLE": 2, "ELIGIBILITY_NOT_INCOMPATIBLE": 2,
                    "RELEVANT": 1, "NEW": 1},
         "stage_exits": {"LOCATION_COMPATIBLE": {"GEO_INCOMPATIBLE": 1},
                         "ELIGIBILITY_NOT_INCOMPATIBLE": {},
                         "RELEVANT": {"DOMAIN_INCOMPATIBLE": 1}},
         "diagnostics": {"invalid_observations": 1,
                         "duplicate_observations_same_source": 0,
                         "canonical_jobs_created_all_dispositions": 3}},
        {"source_id": 4, "source_name": "Broken Board", "provider_family": "greenhouse",
         "attempted": true, "attempt_state": "ATTEMPTED", "attempt_outcome": "FAILED",
         "fetch_outcome": "FAILED", "health": "UNAVAILABLE", "completion": "FAILED",
         "error_code": "SOURCE_REQUEST_FAILED", "error_class": "SOURCE_UNAVAILABLE",
         "counts_complete": false, "incomplete_reason": "FETCH_FAILED",
         "funnel": {"FETCHED": 0, "STRUCTURALLY_VALID": 0, "CANONICAL_UNIQUE": 0,
                    "LOCATION_COMPATIBLE": 0, "ELIGIBILITY_NOT_INCOMPATIBLE": 0,
                    "RELEVANT": 0, "NEW": 0}},
        {"source_id": 5, "source_name": "Paused Board", "provider_family": "lever",
         "attempted": false, "attempt_state": "SKIPPED_DISABLED",
         "attempt_outcome": "SKIPPED", "fetch_outcome": "NOT_ATTEMPTED",
         "incomplete_reason": "SKIPPED_DISABLED",
         "funnel": {"FETCHED": 0, "STRUCTURALLY_VALID": 0, "CANONICAL_UNIQUE": 0,
                    "LOCATION_COMPATIBLE": 0, "ELIGIBILITY_NOT_INCOMPATIBLE": 0,
                    "RELEVANT": 0, "NEW": 0}}
      ]
    }
  }
}
```

## 11. Privacy boundaries

Telemetry is aggregate local operational data. It must never contain job
descriptions, titles, URLs, provider-native payloads, candidate profile or CV
content, application answers, email data, credentials, tokens, exception traces,
local filesystem paths, raw unbounded provider error messages, or unbounded
identifiers taken from external content.

This is enforced, not just intended: `validate()` walks the whole payload and
rejects any forbidden key (`FORBIDDEN_KEYS`), any string longer than 700
characters, any unsupported value type and excessive nesting. The API projection
is additionally whitelist-based. Provider metrics are filtered to a fixed list of
numeric/boolean fields.

User-configured **source names** are returned through the local API by design —
they are the operator's own labels and are what make the report readable. No
telemetry is sent to any external service; no tracking, analytics SDK or network
beacon was added; no per-job private content is logged.

## 12. Legacy runs and the pre-#43 funnel

- A run recorded before #43, or one whose telemetry has expired, is returned with
  `telemetry_status: TELEMETRY_UNAVAILABLE` and `telemetry: null`. Consumers must
  handle that state; they never crash on a missing schema.
- The pre-#43 `report['funnel']` produced by `backend.recall.funnel()` is
  retained **only** as derived compatibility output for the existing recall audit
  view and workspace UI. `backend/main.py`'s `_compat_funnel()` stamps
  `schema: legacy-discovery-funnel-compat-1`, `authoritative_funnel:
  discovery_telemetry (discovery-telemetry-v1)` and a `compatibility_note` into
  the persisted report, so there is exactly one source of truth and no consumer
  has to guess which shape is authoritative. `backend/recall.py` itself is a
  provenance-pinned #42 evaluation input and was deliberately left unmodified.

## 13. How issue #47 should consume this

The dashboard redesign should read `GET /api/search/telemetry` for "today" and
`GET /api/search/telemetry/runs` for a short recent history, and should:

1. Key every stage off `FUNNEL_STAGES` order rather than hardcoding labels.
2. Show `funnel_basis` wherever it presents a per-source and a run number side by
   side, because a run's canonical stages are deduplicated across sources while
   its observation stages are summed.
3. Render `attempt_state`/`fetch_outcome`/`attempt_outcome` instead of collapsing
   a failed, skipped or empty source into "0 jobs".
4. Surface `counts_complete` / `incomplete_reason` rather than presenting a
   partial source's numbers as final.
5. Render `DISPLAYED` as genuinely unavailable — not as zero.
6. Degrade gracefully on `TELEMETRY_UNAVAILABLE`, `RUN_IN_PROGRESS` and
   `NO_DATA`, and on a `TELEMETRY_ERROR` payload with a null funnel.
7. Not request more than `MAX_TELEMETRY_RUNS` runs, and not expect history older
   than 90 days.

## 14. Known limitations

- `DISPLAYED` is unavailable in v1.1; there is no display event to count.
- `SAVED`/`APPLIED` are measured once, at run finalization, for the jobs that run
  observed. A job saved or applied to later is not retroactively added to that
  run's numbers, and a run's numbers are not refreshed.
- A run whose source list exceeds 200 entries reports the surplus only as
  `sources_truncated`.
- Run-level `RELEVANT`/`NEW` deduplicate across sources, so per-source numbers do
  not sum to the run total for canonical stages. This is intended and is stated
  in `funnel_aggregation`.
- In an `INGESTION_FAILED` attempt, `STRUCTURALLY_VALID` reflects observations
  that satisfied the ingestion contract before the source's transaction was
  rolled back. The rows no longer exist; `rolled_back` and `incomplete_reason`
  say so.
- SmartRecruiters still uses the legacy `backend/adapters.py` transport and
  reports no `provider_metrics`, so its `provider_metrics` is `null`. Its funnel
  is unaffected.
- Telemetry is attached only when the discover task reaches finalization. A run
  that fails outright (`AutomationRun.status == 'FAILED'`) carries no telemetry
  payload and is reported as `TELEMETRY_UNAVAILABLE`.
- Retention prunes at most 500 runs per discovery run; a very large backlog
  converges over successive runs rather than in one pass.
