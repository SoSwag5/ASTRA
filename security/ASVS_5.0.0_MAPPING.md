# OWASP ASVS 5.0.0 — Applicable Requirements Mapping (ASTRA)

*Security review mapped against applicable OWASP ASVS 5.0.0 requirements. This is
**not** a certification and makes no "ASVS Level 2 certified" claim.* ASTRA is a
single-user, local-first application, so many multi-user/session/auth requirements
are **N/A by architecture** and are marked as such honestly.

Status: **PASS** (implemented + tested) · **PARTIAL** · **N/A** (architecture) ·
**GAP**. Requirement IDs are chapter-level (`Vx.x`) since ASVS point releases renumber.

| Area (ASVS chapter) | Requirement theme | Status | Evidence |
|---|---|---|---|
| V1 Encoding & Sanitization | Output encoding for untrusted content | PASS | React auto-escaping; no `dangerouslySetInnerHTML`; stored-as-data tests |
| V1 | HTML/DOM injection defense | PASS | CSP `script-src 'self'`; XSS payloads stored inert |
| V1 | OS command injection | PASS | no shell; subprocess uses arg arrays (`pdf_worker`), no `shell=True` |
| V1 | SQL injection | PASS | SQLAlchemy ORM parameterized; injection test |
| V1 | Spreadsheet formula injection | PASS | `safe()` neutralization + round-trip test |
| V2 Validation & Business Logic | Input validation at boundary | PASS | Pydantic models; length/type caps |
| V2 | Anti-automation / rate limits | PARTIAL | mutation lock, daily limits; no global rate limiter (single-user) |
| V3 Web Frontend Security | CSRF defenses | PASS | Origin allowlist + Sec-Fetch-Site guard |
| V3 | Security headers (CSP/XFO/nosniff/Referrer/Permissions) | PASS | runtime header tests |
| V3 | Clickjacking | PASS | `frame-ancestors 'none'` + XFO DENY |
| V4 API & Web Service | Content-type / method enforcement | PASS | JSON/multipart only; bounded body |
| V4 | SSRF defense | PASS | `validate_url`, 14-form test |
| V5 File Handling | Upload type/size/structure validation | PASS | magic-byte/MIME/ext/archive checks |
| V5 | Safe parsing / resource limits | PASS | sandboxed subprocess + Job Object cap (verified) |
| V5 | Path traversal | PASS | `resolve()`+`is_relative_to`; traversal tests |
| V6 Authentication | User authentication | N/A | single-user local app; optional `APP_TOKEN` for non-default bind |
| V7 Session Management | Sessions/cookies | N/A | no sessions/cookies |
| V8 Authorization | Access control | N/A (loopback) | loopback + Origin/CSRF; documented decision R-03 |
| V9 Self-contained Tokens | JWT etc. | N/A | none used |
| V10 OAuth/OIDC | — | N/A | none used |
| V11 Cryptography | No custom crypto; use platform | PASS | DPAPI via keyring; no home-rolled crypto |
| V11 | Secret management | PASS | OS credential store, fail-closed, never logged |
| V12 Secure Communication | TLS to external services | PASS | https-only outbound; `trust_env=False`; no redirects to untrusted |
| V13 Configuration | Secure defaults | PASS | rules mode, dry-run, loopback, PREPARE-ONLY by default |
| V13 | Dependency / supply chain | PARTIAL | SBOM + audits + CI; lockfile without hashes (see GAP) |
| V14 Data Protection | Sensitive data at rest | PARTIAL | app-level not encrypted; delegated to OS FDE (documented) |
| V14 | Data deletion / minimization | PASS | scoped delete + secure_delete + VACUUM |
| V16 Logging & Error Handling | No sensitive data in logs/errors | PASS | generic 500s; redacted security events; log-injection stripping |
| V16 | Security event logging | PASS | CWE-mapped telemetry |

## Notable GAP / hardening backlog

- **Lockfile hashes:** `requirements.lock.txt` pins versions but lacks `--hash`
  integrity pins. Backlog item (see risk register R-04).
- **Anti-automation:** no global rate limiter — acceptable for single-user
  loopback, revisit if ever multi-user.
- **At-rest encryption:** delegated to OS full-disk encryption by design; would be
  first-class in a distributed build.
