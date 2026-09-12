# Security architecture inventory
Evidence-first review of source at the RC baseline; existing controls reused.

| Surface / trust boundary | Implementation and evidence | Limits / action |
|---|---|---|
| Browser to local API | backend/main.py guard: loopback peer, TrustedHost, Origin and Sec-Fetch-Site checks, optional constant-time APP_TOKEN comparison; tests/security/test_http_boundary.py | Other local users/processes can call loopback without a token; not an OS-user authentication boundary |
| Demo vs private | main.py guard checks ASTRA_DEMO_ONLY before private routes; test_demo_only_denies_every_private_route | /demo alone does not disable APIs; publish only fictional static output or demo-only mode |
| Sensitive endpoints | /api/profile; /api/import/cv, /api/import/tracker; /api/jobs and actions; /api/records; /api/settings; /api/files; privacy, campaign, search and recall routers | Endpoint inventory generated in ENDPOINT_INVENTORY.md; some dict inputs and full-model responses need finer review |
| API to data stores | backend/models.py SQLAlchemy/SQLite, parameterized persistence; ai_usage.py separate usage SQLite; workbook.py spreadsheet mirror | Product data, backups, CVs and reports are private; no application-wide encryption |
| File handling | document_security.py type/magic checks, 10 MB upload, 30 MB archive expansion, 1000 entries, 200:1 ratio; pdf_worker.py 512 MiB and 20-second child deadline; file_download containment | Resource isolation is not exploit isolation or antivirus; filesystem junction review remains important |
| Job providers | adapters.py fixed provider APIs; policy.py public address/port validation; redirects revalidated, max five, trust_env=False, 5 MB decoded response, 25-second timeout | DNS connect-time race remains; public HTTP is allowed by generic URL validator |
| Optional AI | providers.py fixed HTTPS OpenAI, consent; loopback Ollama; no model tools; ai_usage.py UTC persistent cap, failed attempts charged, single lease, cooldown and no retries | Model response not trustworthy; network response bytes not independently capped; local Ollama quota differs |
| Concurrency | mutation_lock, reliability.ProcessLock, SQLite immediate transaction for AI reservation; release-control tests | No global queue bound/rate limiter; same-user overload possible |
| Telemetry | security_events.py fixed taxonomy, empty free-text fields, UTC JSONL, 1 MB rotation and one backup | Authentication failures not fully logged; same-user tamper resistance absent; other business/error logs require review |
| Secrets | backend/privacy.py native keyring, APP_TOKEN environment; test_credential_backend_fails_closed | OS account boundary; do not put secrets in source, diagnostics or artifacts |
| Source to CI | hash lock, npm ci, SHA-pinned actions, CI/CodeQL definitions | No remote run, branch protection, secret scanning activation or independent review evidence |
| CI to artifact | build_release.py deterministic ZIP and SHA manifest; publication gate; validated SBOM and release workflow | Old RC ZIP quarantined after report PII discovery; new artifact requires fresh verification |
| Backup / restore | reliability.py SQLite backup API and rotation; privacy.py scoped deletion/export; protect_local_data.ps1 DACL | External backups not erased; restoration must use disposable data before live recovery |
| Updates | manual installation from reviewed source/archive; Dependabot config | No automatic signed updater; consumers must verify release digest/provenance |

Manual review required for all shipped documents and images; regex scanning previously missed real record rows. A clean scanner is a useful check, not privacy proof.
