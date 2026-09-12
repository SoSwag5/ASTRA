# ASTRA — Security Telemetry

A small, honest, **local** detection layer. Preventive controls call
`security_events.record(...)`; events are appended as one JSON object per line to
`data/security-events.log`. It is not a SIEM, makes no network call, and stores no
unnecessary PII. Reasons and fields are control-character-stripped and
length-capped to prevent log injection (CWE-117).

Read events via `python -m backend.doctor` (count) or
`GET /api/privacy/security-events`.

## Event taxonomy

| Event | Severity | CWE | Control that emits it |
|---|---|---|---|
| `INVALID_ORIGIN_BLOCKED` | WARNING | CWE-352 | `Origin` allowlist (middleware) |
| `CSRF_REJECTED` | WARNING | CWE-352 | `Sec-Fetch-Site: cross-site` guard |
| `PEER_BLOCKED` | WARNING | CWE-668 | non-loopback peer rejection |
| `UPLOAD_REJECTED` | NOTICE | CWE-434 | structural/type upload validation |
| `UPLOAD_ACTIVE_CONTENT_BLOCKED` | WARNING | CWE-434 | active/embedded PDF content |
| `SSRF_DESTINATION_BLOCKED` | WARNING | CWE-918 | `validate_url` outbound check |
| `SECRET_STORAGE_UNAVAILABLE` | ERROR | CWE-522 | credential store fail-closed |

## End-to-end scenarios (verified 2026-09-12)

**Scenario A — malicious PDF upload**
- ATTEMPT: PDF containing `/JavaScript` (active content)
- CONTROL: `validate_document` byte-scan (before the parser runs)
- RESULT: rejected; the file never reaches the parser or disk profile
- EVENT: `UPLOAD_ACTIVE_CONTENT_BLOCKED` (WARNING)
- REGRESSION TEST: `tests/security/test_controls.py::test_pdf_active_content_blocked`

**Scenario B — SSRF to cloud metadata**
- ATTEMPT: outbound fetch to `http://169.254.169.254/latest/meta-data`
- CONTROL: `validate_url` rejects non-global resolved IP
- RESULT: request never sent
- EVENT: `SSRF_DESTINATION_BLOCKED` (WARNING), field `host=169.254.169.254`
- REGRESSION TEST: `test_controls.py::test_ssrf_blocks_private_and_dangerous_targets`

**Scenario C — cross-origin website drives the local API**
- ATTEMPT: `GET /api/settings` with `Origin: https://evil.example`
- CONTROL: Origin allowlist in the guard middleware
- RESULT: 403 before the handler runs
- EVENT: `INVALID_ORIGIN_BLOCKED` (WARNING), field `origin`, `path`
- REGRESSION TEST: `test_http_boundary.py` (`origin_evil_blocked`)

**Scenario D — cross-site request (no/edited Origin)**
- ATTEMPT: browser cross-site request, `Sec-Fetch-Site: cross-site`
- CONTROL: Sec-Fetch-Site guard
- RESULT: 403
- EVENT: `CSRF_REJECTED` (WARNING)
- REGRESSION TEST: `test_http_boundary.py` (`csrf_cross_site_blocked`)

Each scenario was reproduced live: the control fired, the request was blocked, and
the structured event was written and read back. Mappings use CWE/OWASP rather than
forcing MITRE ATT&CK, which is the natural fit for application-security controls.
