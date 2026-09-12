# ASTRA — Security Testing

All security tests are **deterministic, safe, and isolated**: they run the real
app against a throwaway database (`DATABASE_URL` → temp path), never make outbound
requests to third parties, and never touch the real OS keychain (the credential
backend is monkeypatched). No real malware is stored in the repo — adversarial
fixtures are minimal synthetic byte strings.

Run: `.venv/Scripts/python.exe -m pytest tests/security -q`
Full suite: `.venv/Scripts/python.exe -m pytest -q` → **201 passed**.

## Coverage

| Category | Threat / CWE | Method | Location | Result |
|---|---|---|---|---|
| Origin allowlist | CSRF / CWE-352 | evil vs local vs absent Origin | `test_http_boundary` | PASS |
| Sec-Fetch-Site guard | CSRF / CWE-352 | cross-site header → 403 | `test_http_boundary` | PASS |
| Host allowlist | DNS rebinding / CWE-350 | bad Host → 400 | `test_http_boundary` | PASS |
| Path traversal | CWE-22 | 4 encoded/relative payloads → 404 | `test_http_boundary` | PASS |
| Security headers | CWE-1021/79 | runtime header assertions (8) | `test_http_boundary` | PASS |
| Content-length bound | DoS | oversized declared length → 413 | `test_http_boundary` | PASS |
| Content-type gate | — | non-JSON mutation rejected | `test_http_boundary` | PASS |
| Autopilot lock | consent | `AUTO_ALLOWED` rejected | `test_http_boundary` | PASS |
| URL import disabled | SSRF | `/api/import/url` → 400 | `test_http_boundary` | PASS |
| SQL injection | CWE-89 | payloads stored inert, table intact | `test_http_boundary` | PASS |
| Stored XSS | CWE-79 | script payload stored as data | `test_http_boundary` | PASS |
| SSRF URL validation | CWE-918 | 14 dangerous URL forms blocked | `test_controls` | PASS |
| Formula injection | CWE-1236 | 8 payloads + real workbook round-trip | `test_controls` | PASS |
| PDF active content | CWE-434 | 4 active-content payloads blocked | `test_controls` | PASS |
| Upload type/magic | CWE-434 | non-PDF / double-ext / PE header | `test_controls` | PASS |
| Credential fail-closed | CWE-522 | insecure backend → refuse | `test_controls` | PASS |
| Prompt injection | LLM01 | injected instructions ignored | `test_controls` | PASS |
| Telemetry + log injection | CWE-117 | event recorded, control chars stripped | `test_controls` | PASS |

Existing project tests additionally cover adversarial uploads (10 cases), archive
bomb / zip-slip, XLSX dimension bounds, PDF parser timeout, privacy export/delete
isolation, and the offline browser rehearsal (0 external requests).

## Limitations

- Tests assert HTTP/behavioral outcomes, not the absence of every possible bug.
- Real-browser DOM XSS execution is not exercised in CI; the defense (React
  escaping, no `dangerouslySetInnerHTML`, `script-src 'self'` CSP) is verified by
  code review + stored-as-data tests.
- SSRF tests assert rejection at the validation function; they intentionally do not
  probe real internal hosts.
