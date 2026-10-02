# Beta release tooling dependency findings — 2026-10-02

Reporter and remediation owner: Codex, under the Owner's release instruction.
Independent reviewer: pending the requested cloud review. States below are
**REMEDIATED; independent verification pending**, not independently closed.

## Detection and affected scope

The Scorecard run on integrated source `a193235ef8180466a1580b311bf334bf7521ada5`
([run 36945975374](https://github.com/SoSwag5/ASTRA/actions/runs/36945975374))
reported three urllib3 advisories. Dependabot identified the affected manifest
as `requirements-assurance.lock.txt`, which pinned **urllib3 2.7.0**. The earlier
candidate `3a9554097626ca04756156ca4e8f2a25d8135e11` has that same source tree.

This dependency belongs to the separate release tools environment, via requests
and auditing tooling. It is not installed by the 47-package product lock or
included as a product Python component in the SBOM. That distinction explains
why a clean product audit did not detect it; it does not justify ignoring it.
Tooling uses network services and is part of the supply-chain trust boundary.
No successful ASTRA attack, malicious server fixture or credential exposure was
observed or reproduced. No ASTRA-specific CVSS/CWE finding is asserted.

| Durable record | Public advisory / upstream severity | Affected / fixed versions |
|---|---|---|
| SF-BETA-TOOLS-01: Deflate streaming loop | [GHSA-gh4c-6fx4-qh6g](https://github.com/urllib3/urllib3/security/advisories/GHSA-gh4c-6fx4-qh6g), Moderate | >=2.6.2,<2.8.0 / 2.8.0 |
| SF-BETA-TOOLS-02: Unbounded chunk-size buffering | [GHSA-vxq7-64xx-v4gw](https://github.com/urllib3/urllib3/security/advisories/GHSA-vxq7-64xx-v4gw), High | >=1.10.3,<2.8.0 / 2.8.0 |
| SF-BETA-TOOLS-03: HTTPS proxy TLS configuration | [GHSA-8988-9cw3-xx77](https://github.com/urllib3/urllib3/security/advisories/GHSA-8988-9cw3-xx77), High | >=1.26.0,<2.8.0 / 2.8.0 |

Each record was detected and triaged on 2026-10-02, then remediated through the
same narrow dependency change: **urllib3 2.8.0**, with official PyPI wheel hashes.
[Upstream release](https://github.com/urllib3/urllib3/releases/tag/2.8.0).
The remaining tooling pins and all product pins are unchanged. No application
schema, persisted data, cloud identity or runtime request boundary changed.

## Verification and prevention

A fresh tools environment was installed with the full assurance hash lock.
Strict pip-audit on that lock returned no known vulnerabilities without ignores.
The old lock is retained in isolated QA for a bounded metadata-only audit;
no vulnerable dependency needs to be executed to demonstrate the intake.

CI now audits **both** product and assurance locks, uploads both JSON reports,
and propagates either failure through mandatory Security Verification. Product
SCA remains distinct from tooling SCA. SBOM generation and validation must run
successfully with the updated tools before a fresh ZIP is accepted.

The prior unpublished ZIP is superseded. Its clean Windows install and provenance
checks are dated evidence, not permission to publish an artifact containing the
old tooling lock. Rebuild from the corrected source and verify the same new digest.
No advisory is suppressed and no failed gate is treated as PASS. Independent
verification, final release identity and the cloud review remain separate inputs.
