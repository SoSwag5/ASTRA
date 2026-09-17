# Gmail read-only synchronization and confirmations (#45)

Implementation owner: Codex, continuing the Owner-authorized partial branch
`feature/45-gmail-sync-confirmation-parsing` from
`c53eb4e1f26f90087b1ca6522db9bbf71e63a463` (merged #44 / PR #66).
This is implementation and self-verification, not an independent review.
No live mailbox has been accessed for #45. No risk acceptance or release
approval is implied. #46 is not implemented.

## Flow and invocation

An explicit local `POST /api/gmail/accounts/primary/sync` refreshes the existing
read-only authorization, lists a narrow interval, fetches message content,
extracts bounded inert text, detects initial confirmations, and stores only
minimized evidence in `gmail_confirmations`. It never reads or changes
application records. There is no automatic sync scheduler or new frontend.

`GET /api/gmail/sync/status` reports capabilities and checkpoint presence.
`GET /api/gmail/confirmations?limit=50` returns minimized evidence (1–200 rows).
The existing loopback/Host/Origin/CSRF/session/demo/no-store guards apply.
Sync shares the existing cross-process task lock with discovery, export and
deletion, and has a per-slot in-process lock. Secondary sync returns
`SECONDARY_NOT_ENABLED` before authorization or network access.

Gmail operations: **messages.list and messages.get(format=full), GET only**.
The existing credential layer uses the Google token endpoint to refresh.
There is no history feed, thread enumeration, attachment download, Gmail write,
label operation, sending, draft creation, or URL/image fetching from email.

## Exact query and limits

The client accepts only this authored predicate, with validated epoch seconds:

```text
after:{after} before:{before} -in:chats {subject:"thank you for applying" subject:"thanks for applying" subject:"thank you for your application" subject:"application received" subject:"application submitted" subject:"application confirmation" subject:"we received your application" subject:"your application was sent" (subject:"your application" {from:greenhouse.io from:greenhouse-mail.io from:lever.co from:myworkday.com from:myworkdayjobs.com from:workday.com})}
```

No caller-provided search, broad query, or spam/trash inclusion is accepted.
The returned `internalDate` must also fall within the requested interval.

| Resource | Bound |
|---|---|
| First run / invalid checkpoint | Previous 30 days |
| Maximum interval / checkpoint age | 90 days; older checkpoints reset to 30 days |
| Incremental overlap | 24 hours before the completed interval end |
| Frozen interval end | Invocation time rounded down to seconds, plus 1 second |
| Pages per invocation | 5 |
| IDs per page | 25 |
| Total listed IDs / attempted message reads | 100 / 100, including failed reads |
| Mailbox network budget | 120 seconds, shared by list/get calls; bounded parsing/storage follows |
| Per list/get call | 20 seconds shared across retries |
| Retry | At most 2 retries, only HTTP 429/500/502/503/504; 0.5-second backoff clamped to remaining time |
| Authorization refresh | Existing 30-second budget, before the mailbox budget |
| List response | 256 KiB wire and decompressed bytes |
| Message response | 1 MiB wire and decompressed bytes |
| MIME traversal | Depth 8, at most 64 visited parts |
| Decoded body | 256 KiB across all parts |
| Template scan | First 20,000 text characters |
| Headers | First 128, 2,000 characters per relevant value |
| Subject / sender / company / role | 512 / 320 / 80 / 100 characters |
| URLs | At most 20, at most 2,048 characters per URL |
| Message ID / page token | 128 / 512 characters, restricted alphabet |

The transport reuses #44's credential protections, fixed Google hosts,
verified TLS, no redirects, no proxies and no connection retries. #45 repairs
the inherited timeout assumption by reusing only the provider transport's
bounded DNS resolver and deadline-aware stream primitives: DNS validates all
addresses before dialing a pinned public IP, while TLS checks the original
Google hostname. It does not reuse the provider HTTP fetch/redirect API.
The DNS pool has four workers and a bounded backlog; running OS resolutions
cannot be force-cancelled, but callers time out and admission stays bounded.
HTTPX/HTTPcore trace logging is suppressed in the credential request context
to prevent upstream response headers leaking at debug level.
The TLS context loads system trust explicitly without honoring `SSLKEYLOGFILE`;
HTTPX's `trust_env=False` alone does not disable Python's TLS key-log hook.
Unexpected sync/storage failures are converted to authored errors before they
can reach the application's general exception logger.

## Checkpoints, duplicates, and account isolation

`gmail_accounts.sync_state` contains only a version and either
`completed_through`, or a frozen `after`, `before`, and `page_token`.
The first-page interval is saved before listing, with a null page token; an
interrupted first page therefore replays that same interval on a later day.
After a fully processed page, the next token is saved. A count/time limit
returns `complete: false`; it never commits the interval as complete. The next
invocation resumes the same interval. The completed marker advances only when
pagination ends, including empty intervals. Already recorded IDs are skipped
before fetching; a unique database index independently prevents duplicate
`(gmail_account_id, gmail_message_id)` rows.

Malformed/expired pagination produces a typed failure and marks the checkpoint
for a conservative reset. A transport/auth failure leaves the last completed
page intact. Missing, oversized or malformed individual messages are counted
as unreadable; their contents are not retained and they do not stall every
later message. Unmatched non-confirmations are explicitly counted, not stored.
They may be re-read within the overlap because no extra mailbox ledger is kept.

Evidence uses an opaque connection identity: SHA-256 of the credential handle's
fresh local randomness, never an email hash, mailbox address or credential.
Connection identity is rechecked before reads and atomically with persistence.
A reconnect cannot apply old work or a cursor to the new grant. **A reconnect
starts a new evidence namespace**, including when reconnecting the same mailbox;
cross-grant duplicate reconciliation is not claimed. No old evidence is
reattributed to the new mailbox occupying the slot.

Gmail search pagination is not a transactional mailbox snapshot. An interval
stays fixed locally, but concurrent mailbox changes or messages imported with
an old internal date can still affect search membership. The 24-hour overlap
reduces delayed-visibility gaps; complete coverage of arbitrary backdated
imports or mailbox changes is not claimed.

## Parsers and confidence

Parsers: `greenhouse-confirmation-v1`, `lever-confirmation-v1`,
`workday-confirmation-v1`; fallback: `generic-confirmation-fallback-v1`.
All are deterministic English patterns. Only `APPLICATION_CONFIRMED` is stored.
Later-stage subjects and explicit rejection/negation do not create an initial
confirmation from quoted text. No AI, application reconciliation or state
transition exists in this change.

HIGH requires every one of: allowlisted sender domain; complete anchored
subject structure; body template with role/company; equal normalized company
in subject and body plus a relevant platform URL; and aligned Gmail
authentication evidence. A missing field, inconsistent repeated body template,
ambiguous header, invalid date, malformed/truncated content, or unsafe link
prevents HIGH. Workday subjects without a company remain below HIGH.

Authentication requires one unambiguous `Authentication-Results` header with
`mx.google.com` as authserv-id, explicit DMARC PASS aligned to the From domain,
and SPF or DKIM PASS. Absent remaining mechanisms are allowed; failed, neutral,
unknown or contradictory verdicts are not. ARC copies, foreign issuers,
duplicate mechanisms and duplicate relevant headers cannot establish HIGH.
Only normalized verdict tokens survive parsing. This trusts Google's receiving
path; it is **not independent DKIM verification** and cannot defeat a compromised
authenticated sending account or an attacker able to import arbitrary mail
with fabricated receiver headers into the user's mailbox.

A sender/subject/template alone never reaches HIGH. A message that lacks a
full deterministic match uses LOW generic fallback; if it has a confirmation
phrase, its minimized evidence is retained. Otherwise its non-confirmation
outcome is counted. Generic URLs are omitted rather than guessing relevance.

### Template provenance and known coverage limits

Vendor documentation establishes configurable application acknowledgements;
it does not promise universal sender addresses or exact text. The fixtures are
fictional template shapes, not captured customer emails. These parsers favor
precision over recall and have no measured real-world accuracy. Custom senders,
custom wording, languages other than English, and confirmations without the
required subject fields may fall back or not match the narrow query.

References checked during implementation:

- [Google list API](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list): query and page-token contract.
- [Google filtering](https://developers.google.com/workspace/gmail/api/guides/filtering): epoch seconds avoid the documented PST interpretation of date strings.
- [Google message resource](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages): MIME payload and internalDate; API-imported mail can supply an internal date, so it is not a cryptographic receipt guarantee.
- [Greenhouse template types](https://support.greenhouse.io/hc/en-us/articles/115002573326-Email-template-types) and [default emails](https://support.greenhouse.io/hc/en-us/articles/360020268211-Greenhouse-Recruiting-default-emails): configurable notifications.
- [Lever API](https://hire.lever.co/developer/documentation): application-confirmation email capability, not an exact universal template contract.
- [Lever Postings API](https://github.com/lever/postings-api): hosted posting and application links use a tenant plus posting UUID on `jobs.lever.co` or `jobs.eu.lever.co`; the fictional fixtures follow that shape.
- [Workday candidate notifications](https://stage.doc.workday.com/admin-guide/en-us/human-capital-management/recruiting/candidates/notifications-for-candidates/pzg1486073761924.html): configurable notification templates.
- [RFC 8601](https://www.rfc-editor.org/rfc/rfc8601.html): Authentication-Results trust-boundary limitations.

## Retention, hostile content, upgrade and rollback

Retained content is limited to the governed message ID, opaque account ID,
sender, subject, received timestamp, company, role, detected state, confidence,
parser/evidence tokens, and relevant public application URL. Local row ID,
slot and creation/update timestamps provide normal record bookkeeping.
No body, HTML, MIME object, attachment, snippet, raw response, authentication
header, token, code, or secret column is added.

HTML passes through a bounded inert HTML parser, never a browser. Active
elements and their contents are ignored. Display fields contain no markup
delimiters or control/bidirectional characters. URLs allow HTTPS public-domain
paths only; unsafe schemes, userinfo, IP literals, private host forms, punycode,
nonstandard ports and deceptive visible anchor destinations are rejected.
Queries/fragments are removed to avoid retaining tracking/address/token data.
No extracted URL or remote image is requested.

`initialize_sync_schema()` creates the evidence table and indexes additively,
without altering the evaluation-pinned `models.py` or #44 account schema.
Startup registers it; exports and SQLite backups include minimized evidence.
Disconnect clears credentials/cursor but keeps evidence. **Delete All Local
Data** explicitly removes evidence; ordinary CV/history deletion does not.
Rollback to #44 can leave the inert table in place, but #44's export/delete
code does not manage it: erase evidence on #45 before rollback if needed.
Backups/exported copies require their existing separate user-managed deletion.

## Verification and assurance boundary

Local continuation verification (2026-09-17): 1,442 backend tests passed,
one existing duplicate-case skip; the 154-test #45 suite passed separately.
The full run includes 247 existing #44 OAuth/privacy tests. Frontend checks
and production build passed; npm audit and locked Python SCA reported no
known vulnerabilities. The publication/privacy scan passed with zero findings.
Hosted results must be checked on the PR's exact head; these local results
do not substitute for hosted CI or independent review.

Fictional tests are in `tests/test_gmail_sync.py` and
`tests/security/test_gmail_sync_privacy.py`, alongside the existing #44 suites.
They exercise all supported positive shapes, per-platform spoofs, required
signals, bounded wire/MIME work, query restrictions, continuation/idempotency,
reconnect races, unchanged application rows, API guards and full erasure.
Body/HTML/raw/auth/credential sentinels are checked against SQLite and live
sidecars before checkpointing, logs/events, API output, traceback strings,
diagnostics, actual ZIP exports and actual SQLite backups.

Python memory cannot be securely wiped, and an OS crash dump/swap file or
external tracing agent is outside the implementation's non-retention promise.
No real credentials or mailbox content are used by these tests. R-16 and R-17
remain OPEN; independent review, live accuracy evaluation and any wider Gmail
distribution decision remain separate from this self-verification.
