# Progress and dashboard redesign (#47)

Implementation owner: Claude Code, on `feature/47-progress-dashboard` from
`master` `22642e88f516f827c1dc4250bc72eb259306fafd`. Independent assurance:
Codex, after the draft PR. This document is the implementation plan and the
metric/source contract. It was written before any #47 code and is updated
where implementation changed a detail.

No discovery, Gmail parsing, matching or application-transition policy is
changed by #47. It reads what #43, #45 and #46 already record, adds one
bounded read-only reporting projection, and routes the user's confirm/reject
through the existing #46 endpoints.

## 1. What each page is for

| Page | Question it answers | Authority |
|---|---|---|
| **Today** | What should I do now? | Needs Review count, follow-ups and next actions, highest-ranked unseen jobs, saved jobs, portal pack |
| **Progress** | What verifiably happened in a period, what needs my decision, what supports each figure, and what is incomplete? | Recorded transitions, Gmail evidence and links, discovery telemetry |
| **Applications** | Where does each application stand now? | `application_states.current_state` |

## 2. Audit of the current surfaces

| Surface | Finding | Decision |
|---|---|---|
| Legacy `Dashboard` block in `main.tsx` | Unreachable: no navigation item sets `page === 'Dashboard'`. It still costs a `/api/dashboard` request on every reload. Its figures read `Application.status` (legacy), average a heuristic score, and chart raw job counts by location/source. | Remove the block and stop requesting `/api/dashboard` from the UI. The backend route stays for existing clients and tools. |
| Today goal: "N / 5 quality applications this week" | Numerator counts `tracking.fit_at_application in (EXCELLENT, STRONG)`, a ranking snapshot. #46.2-C failed its relevance criterion, so a ranking band is not a validated quality measure. It is a progress meter without an event-traceable numerator. | Remove from Today. The stored `weekly_target` preference is preserved, not deleted, and is no longer shown as a meter. |
| Today "Strong new matches" | A ranking suggestion labelled as a validated match. | Rename to "Highest-ranked new jobs" with the index shown as a heuristic priority, not a fit claim. |
| Today "N/N sources healthy" line | #43 exists precisely because this stays true while a scan finds nothing useful. | Replace with the latest telemetry run's status (complete / incomplete / failed sources / unavailable). |
| Today footer "submitted · active · reached interview" | Legacy `applied_date` and `tracking.stage`. | Remove; verified figures live on Progress. |
| Visible `Progress` page (`/api/campaign` metrics) | KPIs from legacy `applied_date`/`tracking.stage`; rates without small-sample handling beyond a null; "Fit at application", role-family and emirate breakdowns are heuristics; "Last seven days" counts legacy `ApplicationEvent` stage labels; coverage paragraph counts ranking-derived holdings. | Replace with the verified Progress page below. Keep outcome rates, recomputed from canonical history with explicit denominators. Keep source and CV-version breakdowns (recorded values). Drop fit, emirate and role-family breakdowns, the legacy seven-day review and the coverage paragraph. |
| Applications page | Lists and filters by legacy `tracking.stage`. | List and filter by canonical `current_state`; show the legacy stage only when it diverges, labelled as such. |
| Discovery page | Already consumes the scan controls; out of scope. | Unchanged. |

## 3. Implementation plan

1. **Backend projection** — `backend/progress.py`, router `/api/progress`,
   mounted like every other router so the existing loopback, origin,
   `Sec-Fetch`, access-key, demo-only and `no-store` guards apply unchanged.
   - `GET /api/progress?period=` — period figures, current state, follow-ups,
     discovery period tally, Gmail coverage and review counts.
   - `GET /api/progress/needs-review?limit=&offset=` — the Needs Review queue
     with a bounded **candidate projection** per item.
   - `GET /api/progress/applications` — bounded canonical pipeline rows.
   All three are read-only apart from the existing #46 read-repair
   (`application_state.ensure_all_states()`), which `state_summary()` already
   runs on every read and which writes only truthful `LEGACY_MIGRATION`
   bootstrap rows. No state logic, matching rule, confidence rule or
   transition rule is added or copied.
2. **Candidates** — the review payload today carries no candidate list, yet
   an ambiguous item needs an `application_id` to confirm. The projection
   calls `application_reconciliation.find_candidates()` and keeps exactly the
   candidates for which `Candidate.confirmable` is true — the same call and the
   same filter `confirm_review()` applies. The UI never chooses or ranks a
   candidate itself; it pre-selects only the target the backend already
   proposed (`link.application_id`).
3. **Confirm/reject** — the UI posts to the existing
   `POST /api/applications/state/needs-review/{id}/confirm` (with the
   user-selected `application_id`) and `/reject`. It renders the returned
   `ok`, `applied`, `state.previous_state`/`current_state` and `reason_code`
   truthfully, including a confirmation that resolves the item without
   advancing an application already at an equal or later state.
4. **Frontend** — design tokens (`tokens.css`), a new `Progress.tsx`, a pure
   `progressModel.ts` for labels/formatting/result messages, and focused edits
   to `Campaign.tsx` (Today, Applications) and `main.tsx` (legacy block).
5. **Tests** — pytest comparisons of every figure against fictional records,
   an SSR render check of the Progress components, and the existing suites.
6. **Visual QA** — the built app against an isolated fictional database at
   320/390/768/1280 px, light and dark, keyboard-only and reduced motion.

## 4. Time and period rules

- Timezone: **Asia/Dubai** (UTC+4, no daylight saving) via `zoneinfo`.
- Periods: `this_week` (Monday 00:00 Dubai of the current ISO week to the next
  Monday 00:00), `last_week` (the previous such week), `last_30_days` and
  `last_90_days` (Dubai midnight 29 or 89 days before today, to the next
  Dubai midnight). Every window is half-open: `start <= t < end`.
- `last_90_days` starts after the 90-day telemetry retention cutoff by
  construction (a calendar window of 90 days includes today), so no requested
  window reaches pruned telemetry.
- Timestamps are parsed with `application_state.parse_timestamp()`; a naive
  value is UTC, exactly as #46 stores it. A value that does not parse is never
  placed in any window; it is counted as "date not recorded".

## 5. Metric and source contract

Each entry: **label** · source · event or current state · time field and
window · deduplication key · missing/partial/failed treatment · how to inspect
the basis. "Event" means something that happened inside the period;
"current" means the state now, regardless of the period.

### 5.1 Needs your decision

**Gmail messages that need your decision**
- Source: `gmail_application_links` where `decision = NEEDS_REVIEW`, joined to
  `gmail_confirmations`; only `confidence ∈ {HIGH, MEDIUM}`.
- Current state (the queue now). Not windowed; each item shows its
  `received_at` in Dubai time.
- Deduplication: link id (unique per `gmail_confirmation_id` by #46's index).
- The total is an exact `COUNT` over the whole queue, never the size of the
  returned page; the page states "showing X–Y of N". An item with any other
  confidence is excluded and its count reported (`excluded_other_confidence`,
  expected 0 because #46 never queues LOW). Schema not initialized → queue
  "unavailable", never "0".
- Basis: each item shows detected employer and role, platform, confidence,
  the bounded reason code in plain language, which fields agreed, and the
  confirmable candidates.
- MEDIUM items are always actionable. HIGH evidence that could not be linked
  (#46 queues it rather than dropping it) is shown too, not filtered away.
- Displayed Gmail fields (minimized): detected company, detected role,
  received time, platform (from `parser_id`), confidence, reason code,
  matched field names. **Not displayed or returned by the projection:**
  subject, sender, Gmail message/account identifiers, the evidence URL, or
  any snippet — no approved snippet exception exists (ADR-0008), and the
  listed fields are sufficient for the decision. All text renders as React
  text nodes; nothing is rendered as HTML.

**Gmail evidence not yet matched**
- Source: HIGH/MEDIUM `gmail_confirmations` rows with no link row.
- Current state. Deduplication: confirmation id.
- Shown as a count with the explanation that reconciliation has not run for
  them; never merged into the review total.

**Follow-ups due**
- Source: `followups` (`done = false`) for applications whose canonical
  `current_state` is not `REJECTED` or `CLOSED`.
- Current state. `due_date` converted to a Dubai calendar date; "due now" is
  on or before today (overdue flagged); "next 7 days" is up to today + 7.
- Deduplication: one follow-up per application (unique index).
- A follow-up whose date does not parse is listed as "date not recorded",
  never as due.
- Basis: the listed follow-ups with their application.

### 5.2 Period figures (events)

**Applications submitted** — applications that *reached* `APPLIED` in the
period. Distinct from "currently at Applied" (§5.3).
- Source: `application_state_transitions`.
- Event. Time field: `occurred_at` (the asserted occurrence: the date the user
  entered, the moment the user recorded it when they gave none, or the Gmail
  message's received time). Window per §4.
- Counted rows: an accepted transition with `new_state = APPLIED`; or a
  `LEGACY_MIGRATION` bootstrap row at `APPLIED` or later that carries
  `LEGACY_APPLIED_DATE_PRESENT` (its `occurred_at` is the recorded applied
  date).
- Not counted, reported as "submission date not recorded": a bootstrap row
  without `LEGACY_APPLIED_DATE_PRESENT` (its time is when ASTRA first knew,
  not when anything happened); a transition carrying
  `SUBMISSION_IMPLIED_BY_LATER_STATE` (the user recorded a later stage without
  a submission date); a row carrying `OCCURRED_AT_INVALID`.
- Deduplication: `application_id`. The transition table forbids re-entering
  `APPLIED`, so a user record plus a later HIGH Gmail confirmation for the
  same application is one submission (the second is refused by #46).
- Breakdown by `source_category`: you recorded, Gmail (high confidence),
  Gmail confirmed by you, imported record, browser confirmation.
- Basis: the bounded list of counted applications with date and source, plus
  the excluded counts.

**Other stage changes** — transitions into `SAVED`, `VIEWED`,
`ASSESSMENT`, `INTERVIEW`, `OFFER`, `REJECTED`, `CLOSED` in the period.
- Source: `application_state_transitions`, excluding bootstrap rows (a
  bootstrap's time is not the stage's occurrence).
- Event; `occurred_at`; per §4. Deduplication: (`application_id`,
  `new_state`), unique by the no-regression rule.
- Only the user can currently record these; the UI says so. **No Gmail
  "viewed" or later capability is shown**, because #45 parses only initial
  confirmations.
- Basis: the bounded event list.

**Gmail confirmations received**
- Source: `gmail_confirmations` with `confidence ∈ {HIGH, MEDIUM}`, left-joined
  to `gmail_application_links`.
- Event; `received_at`; per §4.
- Deduplication: messages by `gmail_message_id` (a reconnect starts a new
  evidence namespace, so the same mailbox message can be stored twice);
  applications by linked `application_id`.
- Outcome breakdown: linked automatically, confirmed by you, awaiting your
  decision, rejected by you, not used (`NO_ACTION`), not yet matched. LOW
  evidence in the window is reported separately as "low confidence, not used".
- Coverage: the Gmail connection status and the date the last *completed*
  sync covered (`completed_through`), or "sync incomplete". When no account
  is connected and no evidence exists the figure is "Gmail not connected",
  never 0. Evidence received after the covered date cannot be present, and
  the UI says so.
- Basis: the bounded list of linked/confirmed confirmations, shown with the
  ASTRA application they were linked to.

**New relevant jobs found by scans**
- Source: discovery telemetry (`discovery-telemetry-v1`), read with the same
  bounded retention query and whitelist projection as
  `GET /api/search/telemetry/runs` (`search_workspace._telemetry_runs()` and
  `discovery_telemetry.public_view()`).
- Event. Time field: `AutomationRun.created_at` (scan start) — the field
  retention uses. Per §4.
- Value: the sum over runs in the window of the **run-level** `NEW` stage.
  Run-level canonical stages are already deduplicated across sources (union
  of canonical job ids), and `NEW` jobs are created in exactly one run, so
  runs are disjoint. Per-source values are never summed.
- Partial: if any counted run has `counts_complete: false`, the figure is
  labelled "at least N" with the number of incomplete runs.
  `TELEMETRY_UNAVAILABLE` (legacy or expired) and `RUN_IN_PROGRESS` runs, and
  runs whose telemetry is a `TELEMETRY_ERROR` with a null funnel, contribute
  nothing and are counted separately; a period whose runs are all unavailable
  is "Not recorded", never 0. No scans in the period → "No scans in this
  period". The history read is bounded (at most 10 pages of 20 runs); if the
  bound is reached before the window start the result says so.
- Manually added jobs are not discovery events and are not counted.
- Never presented as market coverage: fetched counts measure what configured
  sources returned.
- Basis: the per-run list (time, status, completeness, `NEW`).

### 5.3 Current state

**Where applications stand** (journey)
- Source: `GET /api/applications/state/summary` data
  (`application_state.state_summary()`), i.e. counts of
  `application_states.current_state`.
- Current state. `complete` / `pending_initialization` shown when the
  read-repair did not reach every application.
- Shown beside the period's stage events so "currently at Applied" and
  "reached Applied this period" are never confused.
- Basis: the Applications page, filterable by canonical state.

**Applications page rows**
- Source: `application_states` joined to `applications` and `jobs`; bounded
  to 500 rows with a truncation flag.
- Current state, plus the submission date from §5.2's rule (or "Not
  recorded"), the user-recorded CV version, and the follow-up date.
- The legacy `tracking.stage` is shown only when its canonical mapping
  differs from `current_state`, labelled "legacy stage".

### 5.4 Discovery health (latest run)

- Source: `GET /api/search/telemetry` directly.
- Current state of the latest finished run (or in-progress).
- Stages are rendered in `FUNNEL_STAGES` order from the payload keys, with
  `funnel_basis` (provider observations vs canonical jobs) shown beside the
  run-level numbers. Per-source rows render `attempt_state`,
  `fetch_outcome`/`attempt_outcome`, `counts_complete` and
  `incomplete_reason`; a failed, skipped, cancelled or partial source is shown
  as that state, never as "0 jobs". `DISPLAYED` is shown as unavailable.
  `NO_DATA`, `TELEMETRY_UNAVAILABLE`, `RUN_IN_PROGRESS` and a null funnel each
  have a designed state.

### 5.5 All-time outcomes (details section)

- **Submitted applications**: applications whose history contains `APPLIED`
  or a post-submission state (`VIEWED` … `REJECTED`).
- **Reached interview / offer / rejected**: history contains that state.
- **Replies you recorded**: distinct applications with a user-recorded
  `MEANINGFUL_RESPONSE` `ApplicationEvent` (automated receipts excluded).
- Rates are shown as "n of N"; a percentage is shown only when N ≥ 10,
  otherwise "Not enough data". Never a probability or a benchmark.
- **Submissions by week** (last 12 Dubai weeks, from §5.2's rule), with direct
  labels, a text summary and a data table.
- **By source** (`jobs.source`) and **by CV version** (user-recorded
  `tracking.cv_version`, "Not recorded" when blank).

### 5.6 Omitted or shown as unavailable

| Desired figure | Why |
|---|---|
| "Strong matches" | #46.2-C did not validate relevance ranking; a ranking band is not a verified match. |
| "Applications viewed" / assessment from Gmail | #45 parses initial confirmations only. Later stages appear only as user-recorded events. |
| `DISPLAYED` | No display event exists (#43). Shown as unavailable. |
| Market coverage | Fetched listings measure configured sources only. |
| Quality-applications goal | See §2. |
| Fit, emirate and role-family breakdowns | Heuristic labels, not recorded facts. |

## 6. UX and accessibility decisions

- First screen of Progress: a one-line next action, then Needs Review, then
  four verified period figures, then the journey, then discovery health.
  Rates and breakdowns follow.
- Every figure has an "evidence" disclosure naming its source, rule,
  exclusions and the counted records.
- States are written out: "Not recorded", "Not enough data", "Run
  incomplete", "No scans in this period", "Gmail not connected". Null is never
  rendered as 0.
- Confirm and reject announce their outcome through a polite live region and
  return focus to the next item (or the queue heading when empty). Errors are
  announced assertively and keep the item in place.
- Motion is limited to hover/focus, disclosure and item resolution (≤ 200 ms);
  `prefers-reduced-motion` removes it with identical static feedback. No
  count-ups and no perpetual motion. Controls are never delayed for motion.
- Targets are at least 24 × 24 CSS px (WCAG 2.2 2.5.8), focus is always
  visible, and core tasks reflow at 320 px without horizontal scrolling.
- Icons: Lucide only. No external assets, fonts or images are imported.

## 7. Known limits (planned)

- No in-app control runs Gmail sync or reconciliation (unchanged from
  #45/#46); Progress reports evidence as of the last completed sync and counts
  unmatched evidence. Adding such a control is a separate scope decision.
- A reconnect creates a new evidence namespace; message-level deduplication by
  `gmail_message_id` compensates in the counts, but a duplicate review item
  from a reconnect is still shown as its own item.
- Discovery figures cover at most 90 days (retention) and at most 200 runs
  per request.
- The bootstrap cannot date history that was never recorded, so an imported
  application without an applied date has no submission date.
