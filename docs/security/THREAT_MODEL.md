# ASTRA threat model
Scope and established application data flows: [existing model](../THREAT_MODEL.md) and [architecture inventory](ARCHITECTURE_INVENTORY.md). This document extends the existing model for software assurance.

Assets: application records, CV/application content, local databases, configuration, API credentials, untrusted remote listings, AI prompts/responses, telemetry, backups, source/history, build identity, SBOMs and release artifacts. Personal content and credentials are high-confidentiality; source and public release metadata require high integrity. The OS account is trusted; loopback is not proof of the caller's OS identity. ASTRA's supported trust boundary is the local OS user account / localhost environment: it implements no application identities, roles, or inter-user authorization, so a caller already inside that boundary is in scope. This shared-host/local-peer exposure is an accepted architectural residual risk (R-15), and ASVS 5.0.0 8.2.1/8.2.2 are N/A on that basis.

| Boundary / abuse case | STRIDE | Control and evidence | Residual risk |
|---|---|---|---|
| Browser -> API: malicious site reads or mutates private state | S/I/T/E | Host/Origin/cross-site/peer guard; HTTP boundary regression | Local process bypass of browser headers; accepted R-03/R-15 |
| API -> DB/files: injection, traversal or malicious filename | T/I/E | ORM parameters, file containment, fixed telemetry; formula and traversal tests | Dict assignment and selective response fields need detailed review; R-12 |
| API -> job provider: private URL, redirect, proxy bypass | S/I/E | validate_url, trust_env=False, per-redirect validation; SSRF/redirect regressions | DNS re-resolution race; R-01 |
| Import -> parser: decompression bomb or oversized PDF | D/E | Type/structure bounds, child memory/time limit; parser regression | Child retains OS privileges, heuristic active-content scan; R-08 |
| API -> AI: quota bypass, retry/concurrent abuse, prompt injection | T/D/I | consent, deterministic limits, persistent reservation, no retries/tools; AI budget regressions | Untrusted advice and uncapped response bytes; R-13 |
| API -> logs: secret/path leakage or repudiation | I/R/T | Fixed taxonomy and bounded logs; telemetry regression | No immutable log store; R-14 |
| Source -> CI: committed secret/private report, malicious contributor/dependency | I/T/E | Publication scan, human artifact review, lock hashes, CodeQL and SCA workflow | Known scanners do not detect all PII or malicious dependencies; R-06/R-10 |
| CI -> artifact: swapped ZIP, forged manifest or wrong source | T/S/R | Source identity, manifest, digest, hosted attestation and independent verification design | Hosted provenance not executed; R-11 |
| Installation -> OS: task rename creates duplicate schedules | D/T | Explicit migration plan and disposable installation tests | Live task unchanged; R-09 |

CWE use: confirmed private record inclusion is CWE-359; missing coverage is an assurance gap, not automatically a CWE. SSRF attack class CWE-918 does not mean every URL path is currently exploitable. No CVSS score is published without a confirmed exploit scope and a complete CVSS v4.0 vector. General release/process risks use the risk matrix.

Revisit on new providers, binding changes, authentication changes, imports/parsers, cloud features, dependency changes or incidents. Maintainer records changed trust boundary, new abuse tests and resulting risk decision.
