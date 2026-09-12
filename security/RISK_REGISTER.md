# ASTRA — Risk Register

*Last reviewed: 2026-09-12. Severity is qualitative (single-user local app); CVSS
is used only where a genuine technical vulnerability warrants it — none currently
do, so none are asserted.*

| ID | Asset | Threat | Likelihood | Impact | Severity | Existing controls | Residual risk | Decision | Review trigger |
|---|---|---|---|---|---|---|---|---|---|
| R-01 | Internal network / metadata | SSRF via DNS-rebinding TOCTOU (validate then reconnect) | Low | Medium | **Low** | `validate_url` per-request + per-redirect; fixed provider hosts; arbitrary import disabled | Small rebinding window on a host that resolves public-then-private | ACCEPT + backlog DNS-pinning | if user-supplied fetch targets are ever added |
| R-02 | Local files / DB | At-rest confidentiality if OS account compromised | Low | High | **Medium** | OS account trust boundary; in-app guidance to enable BitLocker | App does not encrypt at rest | ACCEPT (delegated to OS FDE, documented) | if distributed to less-technical users |
| R-03 | Loopback API | Another local process as same user calls the API | Low | Low–Med | **Low** | loopback + Origin + Sec-Fetch-Site; optional `APP_TOKEN` | Same-user local process can reach API (and already can read `data/`) | ACCEPT (token available, not mandatory — UX) | if threat model gains untrusted local processes |
| R-04 | Supply chain | Dependency tampering between pin and install | Low | Medium | **Low** | pinned versions; SBOM; audits; CI dependency review | Lockfile lacks integrity hashes | MITIGATE — add hash-pinned lock | next dependency refresh |
| R-05 | AI provider | Excess spend / data exposure via OpenAI | Low | Medium | **Low** | opt-in; per-request consent; only job+skills sent; rules mode default | No hard per-day token budget | MITIGATE — add budget cap | if AI usage becomes routine |
| R-06 | Public repo | Personal job-search history / name / paths published | **Medium** | Medium | **Medium (P1)** | secret scan clean; `.gitignore` excludes data | UAE campaign reports + one absolute path + name in test fixtures remain tracked | **OWNER DECISION** — gitignore/sanitize before public release | before making the repo public |
| R-07 | Deleted data | User expects forensic erasure | Low | Low | **Low** | scoped delete + secure_delete + VACUUM; explicit limitation copy | Backups/snapshots/SSD remnants persist | ACCEPT (clearly documented) | — |

## Priority actions

- **R-06 (P1, before public release):** decide on the campaign/audit reports and
  absolute paths — recommended: `git rm --cached` + `.gitignore` the personal
  reports, keep them locally.
- **R-04 / R-05 (P2 hardening):** hash-pinned lockfile; AI per-day budget.
- **R-01 (P3 defense-in-depth):** DNS-pinning for outbound fetches.
