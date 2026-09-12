# Release Security Assurance Report

**Product:** ASTRA · **Version:** `1.0.0-rc.1` · **Assessment date:** 2026-09-12
**Reference runtime:** Python 3.13.2 (Windows x64)
**Local assurance:** **PASS FOR REMOTE ASSURANCE** · **Overall decision:** **BLOCKED** (remote controls unrun)

> **Status note (2026-09-12, later the same day):** this document records the
> *local* RC assessment made before any remote existed. The repository has since
> been created, published and pushed, and the remote controls described below as
> "not executed" are being executed on <https://github.com/SoSwag5/ASTRA>. The
> authoritative outcome is the generated `release/release-security-gate.json`
> from a hosted run, not this narrative. Nothing below has been back-edited to
> claim a result it did not have at the time.

> Green results below were executed locally in this assessment. Remote-only
> controls (hosted build, signed provenance, attestation, CodeQL, dependency
> review, repository protections) are marked **not executed** — at the time of
> writing no GitHub remote existed and pushing was not authorized. "BLOCKED" is
> the machine-enforced, fail-closed outcome from
> `scripts/release_security_gate.py`, not a default.

## 1. Decision

**Local assurance: PASS FOR REMOTE ASSURANCE. Overall: BLOCKED for public `v1.0.0`.**

- **Application-security baseline (local): met.** All applicable ASVS 5.0.0
  Level 1 controls are PASS or N/A (0 PARTIAL, 0 FAIL). The two authorization
  requirements `v5.0.0-8.2.1`/`v5.0.0-8.2.2` are **N/A by architecture**: ASTRA is
  single-user with no application identities, roles, or user-scoped objects, so
  there is no per-consumer authorization to enforce. The shared-host/local-peer
  exposure of default keyless mode is an **accepted architectural residual risk
  (R-15)**, formally recorded by the maintainer — not a claim that loopback equals
  authentication. Optional access-key sessions, loopback binding, and demo
  isolation are unchanged.
- **Remote-only assurance: not established.** No hosted build, provenance,
  attestation, CodeQL, or dependency-review run exists yet; no remote is
  configured. The machine gate therefore stays fail-closed **BLOCKED** with 18
  remote-only blockers, and must **not** read "READY FOR PUBLIC v1.0.0" until they
  actually execute and pass (`release/release-security-gate.json`).

## 2. Evidence executed this assessment (local)

| Control | Result | Evidence |
|---|---|---|
| Full test suite | **271 passed, 0 failed, 0 skipped** (`pytest -q`, Python 3.13.2) | `tests/` incl. `tests/security/` |
| Auth/session regressions | PASS | `tests/security/test_access_sessions.py` |
| Real-Chromium teardown acceptance | PASS (keyed + keyless) | `tests/security/test_browser_termination.py` |
| Release-gate logic (incl. tamper cases) | PASS | `tests/security/test_assurance_gate.py` |
| Private-data / publication scan | **PASS** — 356 objects, 0 findings | `scripts/publication_gate.py` |
| Frontend checks (locale/order/link-safety) | PASS (9 link-safety scenarios) | `frontend/check-*.cjs` |
| Frontend build | PASS | `npm run build` (vite) |
| Python SCA | **0 known vulnerabilities** | `release/closure-python-sca.json` |
| npm SCA | **0 vulnerabilities** | `release/closure-npm-sca.json`; `npm audit` |
| SBOM spec & validation | **PASS** — CycloneDX **1.7**, **246 components** | `release/astra-1.0.0-rc.1.cdx.validation.json` |
| SBOM digest (unchanged this pass) | `sha256:6f8b681e352a8efb58b344f22a28eabad5090aa37f5b123c0ef06ab0a16ea293` | `security/sbom.cdx.json` |
| Release Security Gate | **BLOCKED** (fail-closed) | `release/release-security-gate.json` |

## 3. Authentication / session (token-exchange model)

`backend/access.py` + `frontend/src/access.tsx`. The optional configured access
key (`APP_TOKEN`) is an **exchange credential only** — never the browser session
identifier.

- **Static key**: verified with constant-time `secrets.compare_digest`; accepted
  only at `POST /api/access`; never placed in URLs, browser storage, telemetry, or
  API responses. Verified by `test_access_http_contract` / `test_access_sessions`.
- **Session token**: `secrets.token_urlsafe(32)` (256-bit), stored server-side as a
  **SHA-256 digest only**; idle (15 min) and absolute (8 h) expiry enforced
  server-side; reauthentication rotates and revokes the prior session; configured-key
  rotation and process restart invalidate all sessions; 5-failure/60-second
  process-wide brute-force lockout with `Retry-After` (closes `6.3.1`).
- **Client teardown**: close / `pagehide` / offline / 401 unmount the private React
  tree, clear keys, abort fetches, revoke blob URLs; `POST /api/access/lock` returns
  `Clear-Site-Data`. localStorage holds only non-sensitive prefs; no
  IndexedDB/service-worker/Cache Storage. Verified by real-Chromium tests (closes
  `7.2.2`, `14.3.1`).

## 4. Security regression results

| Area | Result | Notes |
|---|---|---|
| SSRF (direct) | PASS | `policy.validate_url` blocks non-global addresses |
| Redirect SSRF | PASS | re-validated per redirect |
| Plaintext HTTP external fetch | PASS (blocked) | `policy.py` now HTTPS + port 443 only |
| Proxy-env bypass | PASS | `trust_env=False` on outbound fetches |
| XML entity / encoding bypass | PASS | DOCTYPE/ENTITY + **NUL-byte (UTF-16/32)** rejection |
| Parser resource limits | PASS | 512 MiB Job Object + 20 s + page/char caps |
| API input validation | PASS | `backend/input_rules.py` — types, dates, ranges; **NaN/±Infinity rejected** (`math.isfinite`, `allow_nan=False`); unknown-field rejection |
| Response security headers | PASS | outer `response_policy` covers guard rejections, TrustedHost + early errors |
| Demo / private boundary | PASS | `ASTRA_DEMO_ONLY=1` → `/api/*` 404, `/demo` 200 |

## 5. Artifact integrity (build-once / verify-same-bytes)

`scripts/release_security_gate.py::artifact_checks` opens the candidate ZIP and
verifies every packaged file against the manifest SHA-256 set, the packaged SBOM
against the validated SBOM bytes, the packaged manifest, and the exact member set;
tamper cases (mutated archive / SBOM / file / manifest) are covered by
`test_release_gate_rejects_artifact_or_sbom_tampering`. A separate
`.github/workflows/review-candidate.yml` + `scripts/verify_candidate_run.py`
**re-verify an already-built candidate** rather than rebuilding it at approval, so
the bytes attested are the bytes reviewed. Locally the prior RC `.zip` is quarantined
for privacy hygiene, so the gate blocks on artifact presence — the authoritative
artifact is produced by the hosted build.

## 6. Framework status (evidence-backed; no certification claimed)

| Framework | State | Public wording supported |
|---|---|---|
| **NIST SSDF 1.1** | 42 tasks: 12 IMPLEMENTED / 28 PARTIAL / 2 NOT | "Secure SDLC **aligned with** NIST SSDF 1.1" |
| **OWASP ASVS 5.0.0** | L1 = **40 PASS / 30 N/A / 0 PARTIAL / 0 FAIL** (applicable L1 baseline met; `8.2.1`/`8.2.2` N/A under R-15); L2 assessed with open gaps | "applicable **ASVS 5.0.0 Level 1 controls verified** (PASS or justified N/A) against an ASTRA-specific baseline" — no L2 level claim |
| **OWASP SAMM v2** | 15 practices assessed; demonstrated lower bound level 0 | "maturity **assessed using** OWASP SAMM v2" |
| **CycloneDX 1.7** | 246 components, schema-validated, digest recorded | "release SBOM **generated and validated** as CycloneDX 1.7" |
| **SLSA v1.2** | provenance workflow prepared; **no hosted build/attestation yet** | "SLSA v1.2-aligned provenance **workflow prepared**; hosted execution and verification pending" — **no Build level** |

## 7. Remote-only items (require a GitHub remote + explicit authorization)

Hosted CI test matrix; CodeQL SAST; dependency review; hosted release build +
SLSA v1.2-aligned signed provenance (`actions/attest`); independent
`gh attestation verify`; repository protections (secret scanning/push protection,
Dependabot, required checks, branch/tag protection); OpenSSF Scorecard. All **not
executed**.

## 8. Known limitations & accepted residual risk

- **ASVS `8.2.1`/`8.2.2` — accepted architectural residual (R-15)**: default
  keyless mode delegates trust to the local OS-user/host boundary; a non-same-user
  local process on a shared machine could reach the loopback API. Accepted for a
  single-user local application; mitigations retained (loopback binding, optional
  access-key sessions, data-dir ACLs, demo isolation). Review trigger: any move to
  multi-user/networked/hosted operation.
- Full from-scratch `setup.bat` on a clean Windows VM not yet run (recommended final
  gate; ideally an ephemeral hosted runner).
- At-rest encryption delegated to OS account + full-disk encryption.
- App-scoped deletion; no forensic-erasure claim.
- Live scheduled task `Ayham Job Hunter - Local Discovery` unchanged; future-install
  naming migration documented in `docs/SCHEDULED_TASK_MIGRATION.md`.

## 9. Final decision

**Local assurance PASS FOR REMOTE ASSURANCE; overall BLOCKED — not ready for
public `v1.0.0`.** Local security engineering, tests (271), applicable ASVS L1
baseline (all PASS/N-A), dependency integrity, validated CycloneDX 1.7 SBOM,
token-exchange session security, input validation, artifact-integrity controls,
and demo isolation are in place and evidence-backed. Promotion to
`READY FOR PUBLIC v1.0.0` requires the remote-only controls in §7 to actually
execute and pass: (a) a first green remote CI + CodeQL + dependency-review run;
(b) a hosted build with verified SLSA v1.2-aligned provenance; (c) a clean-Windows
install acceptance on a hosted runner; (d) repository protections + OpenSSF
Scorecard review.
