# Security verification plan
Run only in disposable storage. tests/conftest.py overrides DATABASE_URL, HUNTER_DATA_DIR, APP_TOKEN and keyring before app imports. Never run setup against the live installation as a clean-install test.

| Check | Scope | Evidence |
|---|---|---|
| Python suite | LOCAL/BOTH | pytest JUnit results on Python 3.13; 3.14 hosted matrix remains a target until executed |
| Security regression | BOTH | tests/security: SSRF/private redirects, CSRF/Host/Origin, injection, traversal, parser bounds, demo API denial, AI limits/concurrency, telemetry |
| Frontend | BOTH | npm test (locale/order checks), npm run build; not a full frontend security test suite |
| SAST | REMOTE | Existing CodeQL python, JavaScript/TypeScript and Actions jobs; remote results unavailable |
| SCA | BOTH | pip-audit authoritative hash lock, npm audit; failures/outages block |
| Publication | BOTH | publication_gate.py source/history/metadata plus human document/image review |
| SBOM | BOTH | generate_sbom.py and validate_sbom.py schema/graph checks |
| Installation | REMOTE plus same-host rehearsal | clean_install.py on Windows hosted runner; setup, empty DB, synthetic record, restart, demo denial, cleanup |
| Provenance | REMOTE | Hosted attest plus independent gh verification of ZIP and SBOM predicate |

A file called evidence is not proof. Record command outcome, source commit, artifact hash when relevant, UTC date, runtime and limitations. No skipped/failed mandatory check is treated as passed. Dedicated new gate tests must demonstrate refusal of missing/failed/skipped and wrong-source evidence, and rejection of malformed SBOM graphs. SAST job success is not itself a zero-findings result; review uploaded SARIF/code-scanning findings before release.
