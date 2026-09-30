# In-app Gmail check and match (#47 follow-up B)

Implementation owner: Claude Code, on `feature/47-followup-gmail-operations`,
stacked on the interaction/Settings follow-up and the #47 candidate; to be
rebased onto the reviewed #47 state before its pull request. Independent
assurance: Codex.

## What it adds

Explicit controls for two operations that already existed only as API routes:

1. **Read Gmail** — `POST /api/gmail/accounts/primary/sync` (#45): the primary
   account only, read-only scope, bounded window and budget, minimal evidence.
2. **Match to applications** — `POST /api/applications/state/reconcile` (#46):
   links high-confidence evidence with one clear match, queues anything
   uncertain for the user's decision, never creates an application.

They are shown on Progress (collapsible, directly above Needs Review) and in
Settings › Gmail & permissions. Neither step runs on its own, after the other,
on a timer or at start-up. There is no background or scheduled check, and the
secondary account stays disabled (`SECONDARY_NOT_ENABLED`, OD-012).

No sync, parsing, matching, confidence or transition logic changed. The only
backend addition is a read-only status route.

## `GET /api/progress/gmail`

Returns what the controls need to be truthful, and nothing that identifies the
mailbox:

| Field | Source |
|---|---|
| `connection` | The same fail-closed status `/api/gmail/status` reports (`gmail_accounts._account_status`): a record that says CONNECTED without its stored credential is `DISCONNECTED_INCONSISTENT`. Only the status token is returned. |
| `coverage` | #47's `gmail_coverage()`: whether the last check completed, and the time it covered |
| `unmatched_total`, `unmatched_reviewable` | Exact counts of saved evidence with no reconciliation decision (all confidences; HIGH/MEDIUM) |
| `review` | #47's exact Needs Review totals |
| `limits` | The constants the sync and reconciliation code enforce |

No address, token, message or account identifier, subject, sender or snippet
is returned. The route writes nothing (tested against table snapshots).

## Truthfulness rules

- The read step reports only what the sync summary says: messages read, new
  confirmations saved by confidence, already-recorded and non-confirmation
  counts, unreadable messages, and any limit it stopped at. It always says the
  new evidence is **not linked** until the match step runs.
- The match step reports its own summary. Every count is scoped to the items
  that run looked at, so a re-checked item that was already waiting is never
  presented as new.
- A busy task lock (409) is reported as "nothing was read/changed". A broken
  or expired connection asks the user to reconnect. Other failures show the
  server's authored message; raw errors are never displayed.
- "Check Gmail now" is unavailable until the connection is genuinely usable,
  and says why.

## Verification

- `tests/test_progress.py`: exact counts, fixed limits, fail-closed connection
  status, no identity data, read-only route.
- `frontend/check-gmail-ops.cjs`: every outcome — disconnected, reconnect
  needed, busy, failed, partial, repeated, successful, matched, capped and
  revisit-only runs — plus the initial render.
- Browser QA against an isolated fictional workspace, desktop and mobile:
  the real fail-closed state; fictional sync responses for success, repeated,
  busy, partial and failed reads (the Gmail API is never contacted); the real
  match step on fictional evidence, with the Needs Review queue updating and
  focus moving to it.

## Known limits

- Progress while reading is indeterminate (the sync API reports only when it
  finishes); the control states the message and time budget instead.
- The primary account only. Enabling the secondary account remains an Owner
  decision.
