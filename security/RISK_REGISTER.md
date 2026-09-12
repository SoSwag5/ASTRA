# Risk register — 2026-09-12

| ID | Final state | Control / remaining limitation |
|---|---|---|
| R-01 | ACCEPTED residual | DNS checked before request and redirects; fixed providers reduce, but do not remove, reconnect TOCTOU risk. |
| R-02 | ACCEPTED residual | No app encryption at rest. Windows account and disk encryption define confidentiality. Disk encryption was not independently verified. |
| R-03 | ACCEPTED residual | Same-user processes can reach loopback API; optional bearer token, no multi-user authorization. |
| R-04 | MITIGATED | All 47 pinned packages have wheel SHA-256 hashes, enforced by setup and CI. Hashes do not establish benign authorship. |
| R-05 | MITIGATED | Persistent UTC-day remote request cap (default 20, configurable 0–100), 40k input characters, 1k output tokens, one active lease, cooldown, timeouts and no retries. Failed remote attempts count. Same-user file tampering/reset is out of scope. |
| R-06 | MITIGATED pending final publication gate | Private reports preserved in ignored storage, fictional fixtures, unpublished history rewritten after full bundles, commit email sanitized while author name preserved. Re-run tree/history scanner before every release. |
| R-07 | ACCEPTED residual | Scoped deletion, secure_delete and WAL reclamation do not guarantee forensic erasure or remove external backups. |
| R-08 | LIMITATION | PDF resource limits are not an OS exploit sandbox. Heuristic active-content scan can miss encoded constructs. No claim of malware-free input. |
| R-09 | VERIFICATION GAP | Same-host fresh install is not a clean Windows VM. GitHub workflows and account security features still need first remote activation/run. |

CI code scanning and dependency review are configured, not claimed as successfully run.
Legacy security logs in private backups may contain old free-text fields; current writes
retain only fixed taxonomy. A static demo page is not access control: demo-only server
mode denies all API routes; never publish the private backend.
