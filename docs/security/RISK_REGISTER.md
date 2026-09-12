# Security risk register
Owner: Maintainer. Reviewed 2026-09-12. Risk matrix: likelihood 1 unlikely, 2 plausible, 3 likely; impact 1 limited, 2 material, 3 severe. Score L*I: 1-2 low, 3-4 moderate, 6-9 high. These are design/process ratings, not CVSS. Existing acceptances in security/RISK_REGISTER.md are historical; new risks below are proposed, not silently accepted.

| ID | Risk | L/I | State | Evidence / treatment | Due or recheck |
|---|---|---|---|---|---|
| R-01 | DNS validation/connect race | 2/2 | Historical accepted residual | policy.py; fixed providers and redirect checks; consider pinned resolution transport | Network change / next release |
| R-02 | Unencrypted local data | 2/3 | Historical accepted residual | OS account/DACL and user disk encryption; FDE not independently checked | Installation review |
| R-03 | Local processes access loopback APIs | 2/3 | Historical accepted residual | main.py optional APP_TOKEN; no multi-user identity boundary | Any exposure/auth change |
| R-04 | Dependency substitution | 1/3 | Mitigated, not eliminated | requirements.lock.txt hashes, npm integrity; authorship not established by hashes | Every dependency change |
| R-05 | Paid AI request abuse | 1/2 | Mitigated | ai_usage.py, test_ai_limit_failure_restart_and_rollover and concurrency regression | AI change |
| R-06 | Private employment table in report, reachable history and old ZIP | 3/3 | Remediation in verification; release blocker until final scan/review | Confirmed CWE-359. Narrow history repair with external private bundle; old ZIP quarantined; structural scanner regression | Before any publication |
| R-07 | Deleted data remains in external backups | 2/2 | Historical accepted residual | privacy.py scoped deletion; no forensic-erasure promise | Backup/privacy change |
| R-08 | PDF native exploit despite resource limits | 2/3 | Historical accepted residual | document_security.py/pdf_worker.py; not an exploit sandbox | Parser update |
| R-09 | Clean Windows installation and live task migration | 2/2 | Open remote verification | clean-install workflow/harness; live task unchanged; migration plan | Before final release |
| R-10 | No actual hosted SAST/CI/repository controls | 2/3 | BLOCKING | Workflows configured, remote absent; activate technical protections and review Scorecard | Before final release |
| R-11 | No signed/verified hosted provenance | 2/3 | BLOCKING | release.yml and SLSA assessment; no attestation exists | Before final release |
| R-12 | ASVS L1/L2 control verification gaps | 2/3 | BLOCKING for applicable L1 | Full requirement CSV, including field selection, input review and authorization boundaries | Before final release |
| R-13 | AI response resource limits and local provider availability | 2/2 | Open L2 hardening | providers.py HTTP body handling; test and add streaming byte cap in focused remediation | Before next AI change |
| R-14 | Incomplete/tamperable security event coverage | 2/2 | Open L2 | security_events.py; missing auth/quota/error events and immutable sink | Within 90 days |

Privacy incident root cause: a report reused real records as test evidence; heuristic secret scanning was incorrectly treated as full privacy assurance. Similarity review must cover all Markdown, images, notices and archives, not just databases. Process change: publication requires document/image review; release approval is blocked by absent evidence. Keep backup locations and raw records out of public reports.
