# Security risk register
Owner: Maintainer. Reviewed 2026-09-13. Risk matrix: likelihood 1 unlikely, 2 plausible, 3 likely; impact 1 limited, 2 material, 3 severe. Score L*I: 1-2 low, 3-4 moderate, 6-9 high. These are design/process ratings, not CVSS. Existing acceptances in security/RISK_REGISTER.md are historical; new risks below are proposed, not silently accepted.

| ID | Risk | L/I | State | Evidence / treatment | Due or recheck |
|---|---|---|---|---|---|
| R-01 | DNS validation/connect race | 2/2 | Historical accepted residual | policy.py; fixed providers and redirect checks; consider pinned resolution transport | Network change / next release |
| R-02 | Unencrypted local data | 2/3 | Historical accepted residual | OS account/DACL and user disk encryption; FDE not independently checked | Installation review |
| R-03 | Local processes access loopback APIs | 2/3 | Historical accepted residual | main.py optional APP_TOKEN; no multi-user identity boundary | Any exposure/auth change |
| R-04 | Dependency substitution | 1/3 | Mitigated, not eliminated | requirements.lock.txt hashes, npm integrity; authorship not established by hashes | Every dependency change |
| R-05 | Paid AI request abuse | 1/2 | Mitigated | ai_usage.py, test_ai_limit_failure_restart_and_rollover and concurrency regression | AI change |
| R-06 | Private employment table in report, reachable history and old ZIP | 3/3 | Closed | Confirmed CWE-359. Narrow history repair with external private bundle; old ZIP quarantined; structural scanner regression. Publication gate PASS against released source `81ad2d3`/artifact `a584274…4399f`: 537 objects, 0 findings; packaged bytes independently scanned, 0 findings across 187 entries; all 4 packaged images reviewed by hand (gate run 34732173819). Closure approved by the Owner; see issue #24 | Closed at v1.0.0 release |
| R-07 | Deleted data remains in external backups | 2/2 | Historical accepted residual | privacy.py scoped deletion; no forensic-erasure promise | Backup/privacy change |
| R-08 | PDF native exploit despite resource limits | 2/3 | Historical accepted residual | document_security.py/pdf_worker.py; not an exploit sandbox | Parser update |
| R-09 | Clean Windows installation and live task migration | 2/2 | Hosted acceptance PASS; live-task migration still unverified | clean_install.py on GitHub-hosted Windows, run 34721409583: setup.bat, empty database, demo isolation, synthetic mutation, restart persistence, demo API denial, shutdown, cleanup | Live-task migration before final release |
| R-10 | No actual hosted SAST/CI/repository controls | 2/3 | Closed | CodeQL (python/js-ts/actions) green with all 9 alerts fixed; pip-audit and npm audit clean; dependency review proven on PRs; branch and tag protection active; secret scanning, push protection, Dependabot and private reporting enabled; Scorecard 7.1/10 reviewed | Next release |
| R-11 | No signed/verified hosted provenance | 2/3 | Closed for the assessed candidate | Signed provenance and CycloneDX 1.7 SBOM attestations for artifact 8113a6ff on source b698bfde, independently verified off-runner with a tamper negative control; SLSA v1.2 Build L2 assessed satisfied, L3 not met | Every new candidate |
| R-12 | ASVS L1/L2 control verification gaps | 2/3 | Applicable L1 closed (all PASS/N-A); L2 gaps open hardening | Full requirement CSV; L1 authorization 8.2.1/8.2.2 accepted N/A under R-15 | Before final release / next L2 pass |
| R-15 | Local-peer / shared-host access within the OS trust boundary | 2/2 | Accepted architectural residual (v1.0) | Single-user architecture (no app identities/roles/user-scoped objects); loopback binding; optional access-key sessions; demo isolation; see detail below | Dated review 2026-12-12, or immediately on any trigger below |
| R-13 | AI response resource limits and local provider availability | 2/2 | Open L2 hardening | providers.py HTTP body handling; test and add streaming byte cap in focused remediation | Before next AI change |
| R-14 | Incomplete/tamperable security event coverage | 2/2 | Open L2 | security_events.py; missing auth/quota/error events and immutable sink | Within 90 days |

Privacy incident root cause: a report reused real records as test evidence; heuristic secret scanning was incorrectly treated as full privacy assurance. Similarity review must cover all Markdown, images, notices and archives, not just databases. Process change: publication requires document/image review; release approval is blocked by absent evidence. Keep backup locations and raw records out of public reports.

## R-15 — Local-peer / shared-host access (accepted architectural residual, v1.0)

- **Asset:** Local application data (application records, job records, CV/profile facts, settings) served by the loopback API.
- **Threat:** A malicious process, or another OS user/process with sufficient access to the same host/OS-user environment, reaches the loopback API and reads or modifies local application data.
- **Trust-boundary assumption:** ASTRA's supported security boundary is the local operating-system user account / localhost environment. ASTRA does not provide multi-user tenancy, multiple application identities, inter-user roles, per-record authorization between application users, or hostile-user isolation between OS users sharing one machine.
- **Likelihood:** 2 (plausible only on a shared or already-compromised host).
- **Impact:** 2 (material — local data exposure/modification; no remote/multi-tenant blast radius).
- **Compensating controls (retained, not weakened):** loopback-only binding; optional access-key exchange with 256-bit expiring server-side sessions, logout/invalidation, and brute-force lockout; Host/Origin/cross-site request rejection; `ASTRA_DEMO_ONLY` isolation; data-directory ACL guidance; no automatic external submission.
- **Accepted residual risk:** A caller already inside the local OS-user/host boundary is treated as within ASTRA's trusted scope. ASVS 5.0.0 `8.2.1`/`8.2.2` (per-consumer function/data authorization) are therefore **N/A by architecture**.
- **Rationale:** Standard trust model for a personal single-user local desktop/web application; enforcing inter-user authorization would require introducing application identities the product intentionally does not have.
- **Owner:** Maintainer.
- **Next formal review date:** 2026-12-12 (Owner decision, recorded 2026-09-13; see `OWNER_DECISIONS.md` OD-008).
- **Review trigger (whichever comes first):** the dated review above, or immediately on any of:
  - ASTRA becomes network accessible beyond localhost;
  - ASTRA becomes multi-user;
  - the authentication architecture materially changes;
  - authorization or user ownership is introduced;
  - cloud-hosted application operation begins.
