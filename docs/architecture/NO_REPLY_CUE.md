# "No reply for 90 days" (#47 follow-up C)

Implementation owner: Claude Code, on `feature/47-followup-no-response`,
stacked on the Gmail check-and-match follow-up; to be rebased onto the
reviewed #47 state before its pull request. Independent assurance: Codex.

## What it adds

A cue on applications that have gone 90 days with no employer reply, and an
optional user action to close one as "No response". Both are presentation of
facts ASTRA already records plus a decision the user makes; neither changes
the canonical application-state model (#46).

- **Never** asserts `REJECTED`, `CLOSED` or any other canonical state.
- **Never** counts a cue or a user close as a rejection, in any figure.
- **Never** closes anything automatically, on a timer or at start-up.
- No new table, column, migration, state, transition or endpoint.

## The rule

The cue applies to an application only when all of these hold
(`backend/progress.py::no_reply_status`):

1. **A dated submission is recorded.** The date is the canonical history's
   submission (`submission_of`, #47 §5.2): the first `APPLIED` transition, or
   an imported application's recorded applied date. An import without a date
   never gets the cue ("Submitted, date not recorded"), because its age is
   unknown.
2. **The canonical state is still `APPLIED`.** Any later recorded state
   (viewed, screening, interview, offer, rejected, withdrawn, closed) means
   something happened.
3. **No employer reply is recorded.** A user-recorded `MEANINGFUL_RESPONSE`
   event at any date suppresses the cue. Automated receipts
   (`AUTOMATED_CONFIRMATION`) and Gmail confirmations are not replies.
4. **At least 90 Asia/Dubai calendar days have passed.** Submitted on local
   day D, the cue appears on day D + 90 and not before. Time of day is
   ignored, so the cue does not flip at an arbitrary hour.

When the cue does not apply, the API returns why (`NOT_SUBMITTED`,
`SUBMISSION_DATE_NOT_RECORDED`, `LATER_STAGE_RECORDED`, `REPLY_RECORDED`,
`TOO_RECENT`), and the UI shows nothing.

90 days is fixed as specified by the Owner; it is returned by the API
(`no_reply_days`, `actions.no_reply.days`) so the UI never hard-codes it.

## Where it appears

- **Applications**: a callout with the count and a "Show them" filter; each
  cued row shows a warning badge, its submission date and elapsed days, and a
  "Close as No response" button. The filter view explains the rule in a
  disclosure.
- **Today**: one row under "Follow-ups & next actions" linking to
  Applications. It does not replace or hide the follow-ups themselves.
- **Progress › Outcomes**: "Closed by you as no response: N … not counted as
  rejections", shown only when N > 0, never as a rate.

## Closing as "No response"

The user's decision, confirmed in a dialog that states the consequences
before anything is saved:

- it is not recorded or counted as a rejection;
- the recorded stage stays Applied; nothing is asserted about the employer;
- follow-up reminders for it stop;
- a reply recorded later is pointed out; setting a new stage reopens it.

It is saved through the existing `POST /api/campaign/jobs/{id}/track` with
`stage: NO_RESPONSE` and a note recording the basis ("no employer reply
recorded N days after submission on D"). `canonical_for_legacy('NO_RESPONSE')`
is `None`, so `record_legacy_assertion` asserts nothing: canonical state and
the transition history are unchanged (tested). The campaign route records its
usual `NO_RESPONSE` application event, which gives the close date.

After closing:

- Progress and Today exclude its follow-ups and next actions.
- Its row shows "Closed by you: no response" with the close date.
- A `MEANINGFUL_RESPONSE` recorded after the close changes the badge to
  "Reply recorded after you closed it" and asks the user to set the new stage.
  "After" is the order ASTRA recorded the two events in, not the date the
  user gave the reply: a reply entered on the day of the close is dated
  midnight, and one logged late may carry an earlier date, yet both
  contradict the close. Nothing moves on its own.
- Setting any stage reopens it. A later stage moves the canonical state
  forward as usual; setting it back to Applied brings the cue back if there
  is still no reply (tested).

The same close can be chosen from the job's own stage menu at any stage,
which already existed. The wording therefore never claims a particular stage;
the row's canonical state is shown beside it.

## API additions (read-only)

- `GET /api/progress`: `actions.no_reply` =
  `{days, cue, closed_by_you, reply_after_close, items[≤25], truncated}`.
- `GET /api/progress/applications`: `no_reply_days`, and `no_reply` per item
  = `{status, reason, submitted_on, cue_from, days_since_submission,
  closed_on}`.

## Verification

- `tests/test_progress.py`: the day-90 boundary in Dubai time, including a
  late-evening submission; suppression by reply, later state, undated import
  and too-recent submission; closing through the real route leaves canonical
  state and history untouched, counts no rejection, drops the follow-up and
  surfaces a later reply; a reply recorded before the close does not reopen
  it, and one recorded after it but dated earlier is surfaced; closing from a
  later stage and reopening to Applied.
- `frontend/check-progress.cjs`: badge, line, rule and close-note wording.
- Browser QA on an isolated fictional workspace at 1280 px (ink and light),
  390 px and 320 px: Today's pointer, the callout, filter and rule, the
  confirm dialog (safe default focus, Tab containment, Escape changes nothing
  and restores focus), the close and its counts, the Progress note, a reply
  recorded afterwards through the job's detail view, reopening with a new
  stage, text contrast, target size, reflow and reduced motion.

## Architecture decision for the Owner (not implemented)

The user's close is recorded only in the legacy campaign stage and an
application event. The canonical model does not know about it, and the
legacy `/api/campaign` analytics still treat `NO_RESPONSE` as an active
application (as before this change; they never counted it as a rejection).
That is deliberate: every canonical option changes #46 and is the Owner's
call.

| Option | Consequence |
|---|---|
| **A. Keep it as a user annotation (this PR)** | No model change. Canonical figures are unaffected. The close is visible only where ASTRA reads the campaign stage. |
| B. Canonical `CLOSED` with a no-response reason | `CLOSED` is terminal: a later reply or interview could not be recorded without a new reopen transition, which the permitted-transition table forbids. |
| C. A new non-terminal canonical state or disposition flag | A transition-table and migration change, a #46-style review, and new rules for every metric that reads canonical state. |
| D. Automatic close or cue-driven state change | Asserts a fact no one observed. It conflicts with the #46 principle that state changes come from evidence or the user, and is not proposed. |

Recommendation: keep A unless a canonical record is needed for a specific
report. If it is, prefer C as a disposition flag outside the state machine
over B.
