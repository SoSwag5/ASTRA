# Gmail OAuth and credential storage (issue #44)

*Implements [ADR-0007](adr/0007-gmail-oauth-credential-storage.md) and the
read-only boundary of [ADR-0008](adr/0008-gmail-read-only-mailbox-trust-boundary.md).*

**Status: implemented; live Google OAuth validation pending.** This document
describes controls that exist in code and are covered by automated tests. It
does **not** claim that a live consent-screen run has been performed, that
Google OAuth verification has been granted, or that ASTRA is approved to
distribute a restricted-scope Gmail integration. See
[Live validation](#live-validation-procedure) and
[Distribution limits](#distribution-and-verification-limits).

Scope of issue #44 is the **authorization and credential layer only**. No
Gmail message listing, history synchronization, mailbox scan, message or
thread persistence, parsing, confirmation classification, evidence record,
application matching, transition or reconciliation exists yet; those are
issues #45-#47.

## Files

| File | Responsibility |
|---|---|
| `backend/gmail_oauth.py` | The standards flow: fixed endpoints, PKCE S256, single-use state, the loopback listener, token exchange, scope validation, identity lookup, revocation. No database knowledge. |
| `backend/gmail_accounts.py` | The `gmail_accounts` table, its additive schema initialization, the OS-backed credential store, and the connect/disconnect services. |
| `backend/gmail_api.py` | The minimal local API, mounted behind ASTRA's existing guard middleware. |
| `frontend/src/GmailConnection.tsx` | The minimal connect/status/cancel/disconnect controls. |

### Why the table is not in `backend/models.py`

`backend/models.py` is a SHA-256-pinned input of issue #42's evaluation
provenance manifest (`docs/evaluation/fit_evaluation_provenance_v1.json`),
and `tests/test_fit_evaluation.py` verifies those hashes. Editing it would
invalidate #42's durable provenance, which `PROJECT_STATE.md` reserves for a
separate Owner-authorized regeneration. Issue #43 set the same precedent by
leaving the pinned `backend/recall.py` untouched. `backend/gmail_accounts.py`
therefore declares its table against the shared `Base` and owns its own
idempotent, additive initialization. `tests/test_gmail_oauth.py::test_models_py_is_not_modified_by_this_feature`
asserts the boundary by recomputing the pinned hash.

## Setting up your own Google Cloud project

ASTRA ships **no** OAuth client. Each installation uses the user's own
client, and the repository contains no client ID, no client secret, no
downloaded client JSON, no token and no Gmail address.

1. Create a **dedicated** Google Cloud project for ASTRA — not a personal
   project already used for something else. A dedicated project keeps
   ASTRA's OAuth consent configuration, scope set and access grants
   separate from anything else you run.
2. Enable the **Gmail API** in that project.
3. Configure the OAuth consent screen as an **External** app in **Testing**
   mode, and add your own Google account as a test user. Testing mode is the
   correct configuration for personal use and is what makes a restricted
   scope usable without Google verification.
4. Add exactly one scope: `https://www.googleapis.com/auth/gmail.readonly`.
5. Create credentials → **OAuth client ID** → application type **Desktop
   app**.
6. Copy the client ID. Do **not** download the JSON file into the
   repository, and do not commit it anywhere.
7. Set the client ID as an environment variable and restart ASTRA:

   ```
   ASTRA_GMAIL_CLIENT_ID=<your-client-id>.apps.googleusercontent.com
   ```

8. Open **Privacy & Local Data → Gmail connection** and choose
   *Connect Gmail (read-only)*.

### Client secret

ASTRA does **not** accept, store or send a client secret, and has no code
path that could persist one. Google's installed-app documentation lists
`client_secret` as *optional* for a Desktop app token exchange, and PKCE
replaces it: an installed application cannot keep a secret confidential, so
treating one as confidential would be a false assurance.

If a future Google change made a secret mandatory for this flow, that is a
**stop condition**, not something to work around: persisting a confidential
client secret needs an explicit Owner decision and a storage design, because
neither SQLite nor an ASTRA settings file is an acceptable location for one.
`configuration_status()` reports `client_secret_required: false` so this
assumption is visible rather than implicit.

The client ID itself is treated as **configuration, not a secret** (Google's
own guidance for native apps), but it is still validated strictly against
`^[0-9]{6,32}-[a-z0-9_-]{8,64}\.apps\.googleusercontent\.com$`, length-bounded
to 200 characters, and never returned in an API response or written to a log
— it identifies the Owner's project and has no purpose in either.

## Scope

ASTRA requests exactly one scope:

```
https://www.googleapis.com/auth/gmail.readonly
```

It never requests `https://mail.google.com/`, any Gmail
modify/send/compose/insert/settings scope, Drive, Contacts, or
OpenID/`profile`/`email` scopes. It sends `include_granted_scopes=false` so a
broader grant this client received earlier is not silently inherited.

`gmail.readonly` is a Google **Restricted** scope. ADR-0007 selected it
deliberately over `gmail.metadata`, which cannot read message bodies and does
not support the Gmail `q` search parameter that #45 needs to bound its sync.

## PKCE, state and attempt lifecycle

| Control | Implementation |
|---|---|
| Code verifier | `secrets.token_urlsafe(64)` — ~86 chars from the RFC 7636 unreserved set, 512 bits of entropy, inside the 43..128 range. |
| Code challenge | `base64url(SHA-256(verifier))`, unpadded. `S256` only; `plain` is never offered. |
| `state` | `secrets.token_urlsafe(32)` — 256 bits, unique per attempt, compared in constant time. |
| Lifetime | 5 minutes (`ATTEMPT_TTL_SECONDS = 300`), which is also the total authorization deadline. |
| Uniqueness | One active attempt per account slot. Starting a new one supersedes the old one and clears its secrets. |
| Single use | A callback is consumed atomically under the manager lock **before** any token exchange, so a replay cannot trigger a second exchange. |
| Restart | The attempt store is process memory only. Restarting ASTRA invalidates every pending attempt by construction. |
| Persistence | `state`, the verifier, the authorization code and the access token are never written to the database, a file, browser storage, a log, or telemetry. |

Terminal attempts (completed, failed, expired, cancelled, superseded) are
removed from memory and their secrets released. Only a bounded, secret-free
status record per slot is retained so a polling UI sees the outcome.

## Loopback callback listener

- Binds only to the numeric loopback address `127.0.0.1` on port `0`
  (kernel-assigned ephemeral port). Never `0.0.0.0`, `::`, a hostname
  wildcard, a LAN address, or ASTRA's own API port.
- `allow_reuse_address = False`, so the port is never silently shared.
- Fixed path `/astra/gmail/oauth2/callback`; GET only. Any other method or
  path is rejected without touching attempt state.
- Request line bounded to 2048 bytes (414), headers to 32 (431), query to
  4096 bytes. Per-connection socket timeout 5s; `HTTP/1.0` so no keep-alive
  holds the listener.
- Duplicate `state`/`code`/`error`, a missing `state`, a missing or empty
  `code`, `code` together with `error`, and any unexpected parameter are all
  rejected. Parameters Google legitimately adds (`scope`, `authuser`,
  `prompt`, `hd`, `session_state`, `error_description`, `error_subtype`) are
  tolerated without making the callback ambiguous.
- Serves at most one accepted callback, then closes immediately — also on
  terminal failure, cancellation, or the deadline.
- The response is a small static page with `Cache-Control: no-store`,
  `Referrer-Policy: no-referrer`, `nosniff` and `default-src 'none'`. It
  reflects no query value, no account identity and no error detail.
- `log_message` is overridden to a no-op. The default handler would write the
  full request line — including the authorization code and `state` — to
  stderr. Nothing about a callback is ever logged.
- Browser `Origin`/`Referer` are deliberately **not** consulted: Google's
  redirect carries neither reliably, and neither is authority for an OAuth
  callback. `state` and PKCE are the controls, and a local request without
  the correct `state` cannot complete the flow.

The redirect URI sent during token exchange is byte-identical to the one used
in the authorization request.

## Transport controls

All three outbound calls (token exchange, profile lookup, revocation) share
one hardened client:

| Control | Value |
|---|---|
| Destination | Fixed HTTPS constants only. `_FixedHostBackend` refuses any host outside `{accounts.google.com, oauth2.googleapis.com, gmail.googleapis.com}` and any port but 443. |
| TLS | Standard verification against the system trust store; `check_hostname` on, `CERT_REQUIRED`. Never disabled. |
| Redirects | `follow_redirects=False`. A 3xx is a bounded error, never a hop elsewhere. |
| Proxies | `trust_env=False` — no `HTTP(S)_PROXY`/`NO_PROXY`/`SSLKEYLOGFILE` inheritance. ASTRA has no approved proxy policy. |
| DNS/hosts redirection | After connecting, the peer address must be globally routable; a poisoned answer pointing at loopback, a private range or a metadata address is refused. No extra DNS lookup is made, so there is no unbounded resolution step. |
| Deadlines | Bounded connect/read/write/pool timeouts; 30s total per call, 8s for revocation. |
| Response size | 256 KB cap, enforced while streaming rather than after buffering. |
| Response shape | Expected status, `application/json` content type, and a strict JSON-object check. |
| Retries | **None** for the authorization-code exchange — codes are single-use and an ambiguous retry could produce a confusing or unsafe outcome. No retry loop for revocation either. |
| Logging | No request, response, header or body is ever logged. A raw Google error string never reaches an exception message or an API response. |

The job-provider transport (`backend/job_providers/transport.py`) is
deliberately **not** reused: it is GET-only, follows bounded redirects,
retries on 429/5xx, and can embed a URL in a `POLICY_BLOCKED` message — all
correct for public job boards and all wrong for a credential exchange.

No new dependency was added. `httpx` and `httpcore` are already pinned with
hashes in `requirements.lock.txt`, and the rest is Python standard library,
so the SBOM and dependency-review inputs are unchanged.

## Granted-scope validation

ASTRA never relies on what it requested. After the exchange it inspects the
`scope` Google actually granted:

- `gmail.readonly` missing → `SCOPE_MISSING_REQUIRED`, nothing stored.
- Anything beyond `gmail.readonly` → `SCOPE_BROADER_THAN_REQUESTED`, nothing
  stored, and the user is told to remove ASTRA at their Google account
  permissions page and connect again.

Three things are kept distinct and must not be conflated:

1. **Requested scope** — the constant in `REQUESTED_SCOPES`.
2. **Token-reported granted scope** — validated above, stored normalized as
   non-secret metadata.
3. **Manual consent-screen evidence** — a human observing what the consent
   screen asked for. **This has not been performed yet.** A mocked test is
   not consent-screen evidence.

## Authorized-identity binding

Before any credential is stored, the transient access token is used to call
`GET https://gmail.googleapis.com/gmail/v1/users/me/profile`. The address
that returns is the only identity ASTRA trusts — never the address the user
intended, never a login hint (ASTRA sends none at all), never a UI selection.
This closes the account-mix-up case in the v1.1 threat-model delta.

Only `emailAddress` is kept. `messagesTotal`, `threadsTotal` and `historyId`
are dropped: they are not needed to prove identity, and mailbox counts are
not exposed. No message or thread data is requested or stored, and
`threadId` is never persisted (Owner Decision 6).

### Residual limitation: no immutable provider identifier

Verified against Google's published `users.getProfile` reference: at the
`gmail.readonly` scope the response carries **no opaque immutable subject
identifier** — only `emailAddress`. ASTRA therefore records the
authenticated address as the account identity, labelled
`identity_kind = 'GMAIL_PROFILE_EMAIL'`, rather than:

- inventing a stable identifier from display text, or
- requesting an OpenID/`userinfo.email` scope purely to obtain one, which
  issue #44 forbids.

This is sufficient for #44's security purpose — the credential is bound to
the account Google actually authorized, so it cannot be attached to a
different account record — but the identity is **authenticated, not
immutable**: a Google Workspace administrator renaming a mailbox would
present as a different identity on the next connect. That is a recorded
limitation, not a silent assumption. If #45 needs a genuinely immutable
identifier, it is a separate Owner decision about scope.

### Email normalization rule

`identity_key` lowercases **only the domain** (DNS is case-insensitive) and
leaves the local part byte-identical. Dot-folding and `+tag` folding are
deliberately **not** applied: they are Gmail-specific delivery conveniences,
and applying them would change mailbox identity semantics — wrongly merging
two genuinely distinct mailboxes on a Google Workspace domain.
`authorized_email` stores the address exactly as Google returned it, for
display and confirmation.

## Account model

Two isolated slots are architected; only `PRIMARY` is activated (OD-012).
`SECONDARY` is rejected with the stable code `SECONDARY_NOT_ENABLED` at both
the service and API layers, and the status endpoint reports its gate
explicitly rather than making it look merely unconnected.

`gmail_accounts` stores **only non-secret metadata**: `slot`, `status`,
`authorized_email`, `identity_key`, `identity_kind`, `granted_scopes`,
`credential_key`, `connected_at`, `last_validated_at`, `disconnected_at`,
`last_remote_revocation`, `sync_state`, plus `id`/`created_at`/`updated_at`.

It stores **no** refresh token, access token, authorization code, PKCE
verifier, `state`, raw token response, client secret, Gmail message, subject,
sender, history value or `threadId`. Because ASTRA's private export dumps
every mapped table and the daily backup copies the SQLite file verbatim,
"no secret in this table" *is* the control that keeps tokens out of exports
and backups.

Constraints: `slot` is unique for every row; `identity_key` and
`credential_key` are unique among **connected** rows via partial unique
indexes (`WHERE status = 'CONNECTED'`), so a disconnected tombstone — which
clears both keys — cannot collide with another tombstone while two connected
records still cannot share a mailbox identity or a credential entry.

`sync_state` is a structural placeholder for #45's per-account cursor. It is
account-scoped, always `{}` in #44, and cleared by disconnect and by a
reconnect, so #45 can never resume a cursor belonging to a mailbox that
previously occupied the slot.

### Schema upgrade

`initialize_gmail_schema()` is additive and idempotent: it creates one new
table and its two partial unique indexes if they are absent, and never
touches an existing table, column, index or row. An existing database
upgrades by gaining one empty table — no migration step, no backfill, no
destructive statement. It runs from `lifespan` in `backend/main.py` after
`models.initialize()`.

## Credential storage

Refresh tokens live in the existing native OS credential store, reached
through `backend.privacy.credential_backend()` so Gmail inherits the same
fail-closed rule already tested for the OpenAI key: only a native
Windows/macOS/SecretService backend is accepted. On Windows the backend must
additionally be `keyring.backends.Windows` — the Credential Manager backend,
DPAPI-protected under the **current user** profile, never machine-wide, as
ADR-0007 requires.

There is **no** fallback of any kind: no plaintext, no environment variable,
no SQLite column, no settings JSON field, no local token file, no token
cache, no browser storage, no serialized OAuth-library credential file, no
process argument. If the native store is unavailable, connecting fails
closed with `CREDENTIAL_STORE_UNAVAILABLE`.

- **Namespace:** `ASTRA-Gmail-OAuth`, deliberately separate from the
  `LocalJobHunter` service the OpenAI key uses, so Gmail credentials are
  independently enumerable and deletable and can never be confused with or
  overwritten by the AI-provider credential.
- **Credential key:** `{slot}-{secrets.token_hex(16)}` — derived from the
  trusted local slot plus 128 bits of local randomness, never from the email
  address or any other externally supplied string, and never reused across a
  disconnect/reconnect cycle.
- **Presence checks** read the entry and release it immediately; `keyring`
  offers no existence API. The value is never returned, compared or logged.

### Connection ordering and partial failure

1. Validate the callback (shape, `state`, single use).
2. Exchange the code.
3. Validate the **granted** scopes.
4. Query and validate the actual authorized identity.
5. Check slot and identity conflicts.
6. Store the refresh token in the OS credential store.
7. Persist the non-secret account metadata.
8. Clear every transient token and the attempt state.

Nothing is reported as connected until steps 6 and 7 both succeed. If step 7
fails, the credential written in step 6 is deleted — an orphaned secret that
nothing can later find or revoke would be worse than no credential at all —
and the result is `PERSISTENCE_FAILED`. If metadata exists but its credential
does not, status reports `DISCONNECTED_INCONSISTENT` and never `CONNECTED`,
so #45 cannot later try to use a credential that is not there.

If Google returns no refresh token (it omits one when reusing a prior grant),
ASTRA does **not** overwrite an existing stored token with an empty value and
does **not** report the account as newly connected; it returns
`REFRESH_TOKEN_NOT_RETURNED` with instructions to reconnect with explicit
consent.

## Access tokens

Memory-only. Wrapped in `Secret`, whose `repr`/`str`/`format` all redact, so
an f-string, a container dump, a logging call or a traceback cannot expose
the value. Never persisted, never cached across restarts, never placed in a
returned API model. The lifetime is bounded to the identity lookup and the
reference is released immediately afterwards. Python cannot cryptographically
wipe memory and no such claim is made — `clear()` only drops the reference so
the value becomes collectable sooner.

## Disconnect and revocation

Per account, in this order:

1. Block new token use for that local account.
2. Invalidate any pending OAuth attempt for the slot.
3. Read the refresh token from the secure store, **only** to revoke it.
4. Attempt Google revocation at the fixed HTTPS endpoint — `POST` with the
   token in the **form body**, never the query string.
5. Delete the local refresh token regardless of that result.
6. Delete that account's Gmail sync state.
7. Record the disconnection metadata.

Two results are reported separately, so a failed Google revocation is never
presented as an overall success:

- `local_disconnected` — always `true`.
- `remote_revocation` — `SUCCEEDED`, `FAILED`, or
  `NOT_ATTEMPTED_NO_LOCAL_CREDENTIAL`.

Local disconnection succeeds even when Google is unavailable, DNS fails, TLS
fails, the request times out, Google returns an error, the token is already
invalid, or the response is malformed. Revocation is never retried
indefinitely. Repeated disconnects are idempotent.

**Disconnect is not erasure.** It removes credential access and sync state.
It does not delete application records, already-created minimized evidence,
or application transition history — those stand on their own evidence
(ADR-0008, Owner Decisions 7 and 8). #44 creates no Gmail-derived data at
all, so there is nothing of that kind to preserve yet; the boundary is
established now so #45 inherits it.

Removing Gmail-derived data is a **separate future action**. The one existing
path that also removes Gmail credentials is **Delete All Local Data**, whose
documented scope already includes all credentials (it removes the OpenAI key
too). That path makes no Google revocation call — only Disconnect does.

## Security events

Nine bounded codes were added to the existing taxonomy in
`backend/security_events.py`: `GMAIL_OAUTH_ATTEMPT_STARTED`,
`GMAIL_OAUTH_CALLBACK_REJECTED`, `GMAIL_OAUTH_ATTEMPT_ENDED`,
`GMAIL_OAUTH_CONNECTED`, `GMAIL_OAUTH_SCOPE_MISMATCH`,
`GMAIL_OAUTH_IDENTITY_CONFLICT`, `GMAIL_ACCOUNT_DISCONNECTED`,
`GMAIL_REMOTE_REVOCATION_FAILED`, `GMAIL_CREDENTIAL_STORE_FAILED`.

`record()` previously discarded every caller-supplied field. It still does,
except through one narrow, reviewable allowlist: `BOUNDED_FIELDS` declares
which fields an event may carry (`slot`, `result`) and the exact fixed token
set each may take. An unknown field name, a value outside the set, or a
non-string is dropped. So an event can carry a slot and a bounded outcome
without ever admitting an arbitrary string — no token, code, verifier,
`state`, callback URL, email address, client ID or raw Google message can
reach the log through this path. Reason text is authored per event and
remains a constant. Events that existed before #44 record byte-identically.

## API

All routes are mounted on the same app as the rest of ASTRA's private API and
inherit its guard middleware unchanged — loopback-only peers, the TrustedHost
allowlist, the Origin allowlist, `Sec-Fetch-Site: cross-site` rejection, the
`Sec-Fetch-Dest` browser-navigation block, the optional access-key session,
bounded request size, and `Cache-Control: no-store` on every response. No
control is weakened or bypassed for OAuth.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/gmail/status` | Both slots, configuration state, store state, secondary gate. |
| POST | `/api/gmail/accounts/{slot}/authorize` | Start an attempt; returns the consent URL. |
| GET | `/api/gmail/accounts/{slot}/authorize` | Bounded attempt status. |
| POST | `/api/gmail/accounts/{slot}/authorize/cancel` | Cancel a pending attempt. |
| POST | `/api/gmail/accounts/{slot}/disconnect` | Disconnect; reports local and remote results apart. |

State changes are POST — matching every other state-changing ASTRA route,
including `/api/privacy/delete`. `DELETE` was avoided because the shared
guard requires a bounded `Content-Length` on non-GET requests, which a
browser `fetch` does not reliably send for a bodyless DELETE; using POST
keeps that control intact instead of relaxing it for one route.

The slot is the **only** caller input, validated against a fixed two-value
map. A caller cannot choose a callback host, a Google endpoint, a scope, a
client ID or a credential key. Responses carry no token field — not even as a
null placeholder — no authorization URL query secret in a log, no raw Google
error, and no credential-store implementation detail beyond the safe status
`OS_SECURE_STORE`. Per-slot locks prevent concurrent start/disconnect races.

The authorization URL is returned once to the trusted local frontend so it
can open the system browser. It is never logged and never stored.

## Minimal UI

**Privacy & Local Data → Gmail connection** shows whether the integration is
connected, starts the primary account's authorization, shows the address
Google actually authorized, shows bounded pending/success/error status,
cancels a pending attempt, disconnects, and shows the second slot as not yet
enabled.

It never renders a token, an authorization code, a PKCE value, a `state`
value, a raw Google response, a callback URL or a stack trace. Every message
comes from a fixed authored map keyed by the backend's bounded codes; an
unknown code falls back to a generic line rather than being echoed. Nothing
is written to `localStorage`, `sessionStorage` or IndexedDB, so closing the
tab or reloading clears every transient frontend OAuth value. The consent URL
passes through `safeLink` and is opened with `noopener,noreferrer`.
`frontend/check-gmail-oauth.cjs` asserts all of this and runs in `npm test`.

## Export, backup, diagnostic and deletion review

| Path | Result |
|---|---|
| Private export (`/api/privacy/export`) | Dumps mapped tables and data-directory files. Never reads a credential. `gmail_accounts` is exported and contains only approved non-secret metadata. |
| Daily backup (`backend/reliability.py`) | Copies the SQLite file. No credential is read or copied; the file contains no secret. |
| Diagnostics (`backend/doctor.py`, `/api/privacy/self-check`) | Reports only bounded connection state (`client configured; primary=CONNECTED, secondary=DISCONNECTED`). Never a token, an address or a client ID. |
| Security events | Bounded taxonomy plus the two allowlisted enum fields. |
| API serialization | No token field exists on any returned model. |
| OAuth attempts | Process memory only; no table models one. |
| Delete All Local Data | Removes Gmail credentials and account rows alongside the OpenAI key. Makes no Google revocation call. |
| Disconnect | Removes credential access and sync state only. Application records and history are untouched. |

`tests/security/test_gmail_oauth_secrets.py` proves this with high-entropy
sentinel values, asserting their absence from application logs, captured
stdout/stderr, the security-event file, the SQLite database bytes (including
`-wal`/`-shm` after a checkpoint), the private export archive, a daily backup
snapshot, diagnostic output, every API response body, and exception strings
and tracebacks.

## Live validation procedure

Required before #44 can be called operationally complete. **Not yet
performed.** When it is run, record what was observed — never the values.

1. Confirm the dedicated ASTRA Google Cloud project is the one in use.
2. Confirm the OAuth client type is **Desktop app**.
3. Start the connection; the system browser opens Google's consent screen.
4. **Record exactly which permissions the consent screen requests.** It must
   ask only to read Gmail messages and settings. This is the consent-screen
   evidence that no mocked test can supply.
5. Confirm the callback arrives on a random `127.0.0.1` ephemeral port.
6. Confirm `state` and PKCE validation succeed (the flow completes).
7. Confirm the token exchange succeeds.
8. Confirm the profile lookup returns the address you actually authorized,
   and that the UI shows that address.
9. Confirm the refresh token is present in Windows Credential Manager under
   the service name `ASTRA-Gmail-OAuth`. **Do not display the value.**
10. Confirm no plaintext token exists on disk: search the data directory and
    the SQLite file for the token's first characters *without printing them*,
    or simply confirm `gmail_accounts` has no token column.
11. Confirm status reports the connected account.
12. Disconnect; confirm local access is removed.
13. Confirm the reported Google revocation result matches reality — check
    the Google account permissions page.
14. Confirm no message content was requested or stored.

**Never** paste a client secret, authorization code, access token or refresh
token into chat, a log, a screenshot, an issue, or a commit. Never run the
live proof against the normal ASTRA database if you want it isolated — use a
separate `HUNTER_DATA_DIR`. Automated tests never touch a real mailbox.

## Distribution and verification limits

- This design covers **personal/local-first use**: one user running their own
  installation with their own OAuth client in Testing mode.
- `gmail.readonly` is a Google **Restricted** scope. Distributing ASTRA's
  Gmail integration to parties beyond the developer's own accounts requires
  Google OAuth verification and a restricted-scope security assessment.
- **Neither has been applied for, started, or granted.** Nothing in this
  document or in the code may be read as evidence that it has.
- Wider distribution requires a separate, explicit Owner decision and a
  Google verification readiness review before it ships (ADR-0007,
  "Distribution scope").

## Incident response: suspected token compromise

If a Gmail refresh token may have been exposed:

1. In ASTRA: **Privacy & Local Data → Gmail connection → Disconnect Gmail**.
   This deletes the local token and asks Google to revoke it. Check the
   reported revocation result.
2. Independently, at <https://myaccount.google.com/permissions>, remove
   ASTRA's access. Do this **even if** ASTRA reported `SUCCEEDED` — it is the
   authoritative revocation, and it is the only remedy if ASTRA reported
   `FAILED`.
3. Review recent Gmail account activity at
   <https://myaccount.google.com/notifications>.
4. Treat the local OS account as the trust boundary (ADR-0002, R-15): if that
   account itself may be compromised, change the Google password and review
   all sessions, not just ASTRA's grant.
5. Reconnect only after the cause is understood. A reconnect issues a fresh
   token under a fresh credential key; the old key is never reused.
6. Record the event in `docs/security/INCIDENT_RESPONSE.md` terms if it was a
   real exposure rather than a precaution.

## Recovery after losing the Windows profile

The refresh token is DPAPI-protected under your Windows user account, and
ASTRA deliberately keeps **no** backup of it — a backed-up credential would
defeat the protection. Losing or recreating the Windows profile therefore
means the token cannot be decrypted, which is the intended behaviour.

Recovery is a reconnect, not data recovery: open **Privacy & Local Data →
Gmail connection** and connect again. Nothing else is lost — applications,
their history and every other record are stored separately from the
credential (ADR-0007, "Operational impact"). If a restored database still
carries a connected `gmail_accounts` row whose credential is gone, status
reports `DISCONNECTED_INCONSISTENT` and the account is treated as
disconnected until you reconnect.

## Threats and residual risks

| Threat | Control | Residual |
|---|---|---|
| Authorization-code interception by another local process | Ephemeral loopback port, fixed path, 256-bit single-use `state` compared in constant time, PKCE S256, atomic consume-before-exchange | A process running **as the same OS user** can inspect ASTRA's memory. This is R-15's existing boundary (ADR-0002), not a new one. |
| Callback replay / CSRF | Single-use atomic consume; the listener closes after one callback; a new attempt supersedes the old one | — |
| Account mix-up | Identity taken from Google's authenticated profile only; no login hint is sent; identity and credential-key uniqueness among connected rows | The identity is authenticated but not immutable — see the `getProfile` limitation above. |
| Refresh-token theft at rest | OS credential store, DPAPI CurrentUser, no plaintext fallback, excluded from export/backup/diagnostics by construction | Same-OS-user compromise (R-15/R-16). DPAPI raises the bar; it does not eliminate it. |
| Token in logs/exports/backups/diagnostics | `Secret` wrapper redacts every representation; no token column exists; bounded security-event fields; sentinel negative tests across nine artifact classes | — |
| Scope creep to a mutating capability | Exactly one requested scope; granted scope validated and a broader grant rejected before storage; the only Gmail API URL in the feature is the profile lookup, asserted by test | A future change could add one — which is why the assertion is a test, not a comment. |
| Redirect/DNS/proxy diversion of a credential call | Fixed HTTPS hosts, TLS verification, redirects disabled, proxies ignored, non-routable peer refused | A local CA the user installed could MITM; that is inside the OS trust boundary. |
| False revocation success | Local and remote results reported separately; `FAILED` is never reported as `SUCCEEDED` | Google-side revocation can still fail silently after returning 200; step 2 of the incident procedure covers this. |

**Risk R-16 remains OPEN.** These controls and their tests are the treatment
ADR-0007 anticipated, but R-16 is not accepted or closed by the existence of
this code. Its residual is reassessed only after independent review, and the
live-validation evidence above is part of what that review needs. See
`docs/security/RISK_REGISTER.md`.
