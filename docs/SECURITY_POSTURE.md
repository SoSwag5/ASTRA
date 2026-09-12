# ASTRA — Security Posture (evidence table)

*Last verified: 2026-09-12 against isolated instances (never the real database).*
*Method: static code review + dynamic tests. 51 control checks + 201 automated
tests, all passing. No claim of "secure" or "compliant" — this is a mapped,
tested posture with documented limitations.*

Status legend: **VERIFIED EFFECTIVE** · **VERIFIED — LIMITED** · **PARTIAL** ·
**BY DESIGN N/A**. Every row was independently checked; a prior report's PASS was
not accepted as evidence.

| # | Control | Threat / CWE | Implementation | Test evidence | Status | Limitation |
|---|---|---|---|---|---|---|
| 1 | Loopback-only bind + peer check | Remote access / CWE-668 | `guard` middleware rejects non-loopback `req.client.host`; lifespan refuses public bind without `APP_TOKEN` | `test_http_boundary`; peer check unit-verified | VERIFIED EFFECTIVE | Peer identity is IP-level; a local process on loopback is in-scope (see #6) |
| 2 | Origin allowlist | CSRF / CWE-352 | Cross-origin `Origin` → 403 | `origin_evil_blocked` PASS | VERIFIED EFFECTIVE | Requests with no `Origin` rely on #3/#4 |
| 3 | Sec-Fetch-Site CSRF guard | CSRF / CWE-352 | `cross-site` → 403 (unspoofable by web content) | `csrf_cross_site_blocked` PASS | VERIFIED EFFECTIVE | Non-browser local clients don't send it (see #6) |
| 4 | Host allowlist (DNS rebinding) | CWE-350 | TrustedHostMiddleware allowlist | `bad_host_blocked` 400 PASS | VERIFIED EFFECTIVE | — |
| 5 | Security headers | Clickjacking/XSS/CWE-1021 | CSP (`script-src 'self'`, `frame-ancestors 'none'`), XFO DENY, nosniff, Referrer-Policy, Permissions-Policy, Cache-Control no-store — applied to API **and** static | 8 header assertions PASS at runtime | VERIFIED EFFECTIVE | `style-src` allows `'unsafe-inline'` (React/recharts); scripts do not |
| 6 | Same-machine process reaching the API | CWE-668 | Loopback + Origin/CSRF + optional `APP_TOKEN` | Documented decision below | PARTIAL (by design) | A trusted local process can call the loopback API; adding a mandatory token hurts single-user UX. See Risk R-03 |
| 7 | Path traversal on file download | CWE-22 | `resolve()` + `is_relative_to(DATA)` + suffix allowlist | 4 traversal payloads → 404 PASS | VERIFIED EFFECTIVE | — |
| 8 | SSRF outbound validation | CWE-918 | `validate_url`: scheme/port/credential checks + `getaddrinfo` → reject non-global IPs; revalidated per redirect | 14 dangerous URL forms blocked; metadata + `::ffff:127.0.0.1` included | VERIFIED EFFECTIVE | DNS-rebinding TOCTOU residual (fixed provider hosts mitigate). See Risk R-01 |
| 9 | Arbitrary URL fetch disabled | CWE-918 | `/api/import/url` returns 400; sources restricted to 4 fixed provider hosts | `import_url_disabled` PASS | VERIFIED EFFECTIVE | — |
| 10 | Upload structural validation | CWE-434 | extension + MIME + magic-byte + double-extension + size | 10-case adversarial param test (existing) | VERIFIED EFFECTIVE | — |
| 11 | PDF active-content block | CWE-434 | rejects `/JavaScript /JS /Launch /EmbeddedFile /OpenAction` | 4 active-content payloads blocked | VERIFIED EFFECTIVE | Heuristic byte-scan; parser also runs sandboxed (#13) |
| 12 | XLSX archive-bomb / zip-slip | CWE-409/CWE-22 | entry count, expansion ratio, path traversal, macro/external-link, XXE checks | `test_archive_bomb_and_traversal` (existing) | VERIFIED EFFECTIVE | — |
| 13 | Sandboxed PDF parsing | CWE-400 | separate process, Windows **Job Object** 512 MB cap, 20 s timeout | 900 MB alloc in child → `MemoryError` (verified) | VERIFIED EFFECTIVE | Job Object is the real, working mechanism (not aspirational) |
| 14 | Spreadsheet formula injection | CWE-1236 | `safe()` prefixes `'` to values starting `= + - @ \t \r`; applied to all untrusted cells | round-trip write+read test; 8 payloads neutralized | VERIFIED EFFECTIVE | — |
| 15 | SQL injection | CWE-89 | SQLAlchemy ORM, parameterized throughout | injection payloads stored inert, table intact | VERIFIED EFFECTIVE | — |
| 16 | Stored XSS from job data | CWE-79 | untrusted content stored verbatim as data; React escapes at render; no `dangerouslySetInnerHTML` | `xss_stored_as_data` PASS; frontend grep clean | VERIFIED EFFECTIVE | — |
| 17 | Credential storage | CWE-522 | native OS keychain (`keyring.backends.Windows` = Credential Manager/DPAPI), fail-closed, no plaintext fallback, never logged/echoed | backend classified at runtime; `cred_not_echoed` PASS; fail-closed unit test | VERIFIED EFFECTIVE | Confidentiality bounded by the OS user account (assumption #1) |
| 18 | AI prompt-injection boundary | LLM01 | job/CV text passed as data; model has no tools; output validated (evidence IDs ⊆ facts); consequential actions need code + user | rule-provider ignores injected instructions | VERIFIED EFFECTIVE | Model may still give wrong commentary; it cannot act |
| 19 | AI resource bounds | LLM10 | request timeouts (45/90 s), strict JSON schema, per-request consent, no auto-retry loops | code review | VERIFIED — LIMITED | No hard per-day token budget |
| 20 | External submission disabled | Abuse/consent | API entrypoint always raises (`fixture is None`); `AUTO_ALLOWED` rejected by settings | structural; `autopilot_auto_rejected` PASS | VERIFIED EFFECTIVE | PREPARE-ONLY is structural, not just copy |
| 21 | Data deletion scope | Privacy | allowlisted files only; refuses links/unknown entries; `secure_delete` + WAL truncate + VACUUM | existing `test_privacy_review` | VERIFIED — LIMITED | Cannot erase OS backups/snapshots/SSD remnants (stated) |
| 22 | Secret in repo/history | CWE-540 | custom scanner + `.gitignore` excludes data/backups/CV | secret scan: 0 findings / 1477 files | VERIFIED EFFECTIVE | See publication-gate PII note below |
| 23 | Dependency vulnerabilities | CWE-1395 | project auditor + npm audit + SBOM | 0 vulns (48 PyPI + 193 npm); SBOM 241 components | VERIFIED — LIMITED | "no known advisories" ≠ "non-malicious" |
| 24 | Security telemetry | Detection | structured local event log with CWE-mapped taxonomy | attack→event chain verified for 4 event types | VERIFIED EFFECTIVE | Local only; not a SIEM |

## Documented design decision — Risk R-03 (local process access)

A mandatory per-launch capability token was considered to stop *other local
processes* from calling the loopback API. Decision: **not added by default.**
Rationale: (a) the realistic threat is a malicious *website*, which is already
stopped by loopback + Origin + Sec-Fetch-Site; (b) a hostile local process running
as the same user can already read `data/` directly, so an API token adds little
confidentiality; (c) a mandatory token harms the single-user "double-click and
go" UX. `APP_TOKEN` remains available and is enforced when set. This is an honest,
scoped trade-off, recorded in the risk register, not an oversight.

## Publication-gate note (P1, awaiting owner decision)

The code and history contain **no secrets** (0 findings). However, personal
artifacts remain that should be resolved before *public* release: the owner's
first name appeared in an outbound `User-Agent` and a hardcoded script path (both
now fixed), and the tracked UAE campaign/audit reports contain the owner's real
job-search history and one absolute machine path. Recommendation: exclude those
reports from the public repo (gitignore + `git rm --cached`) or sanitize them.
This is the repository owner's decision. See the review summary.
