# From the first public ASTRA snapshot to beta

**Comparison dates: 12 September → 2 October 2026, 20 days.** This is a source
comparison, not a claim about hours worked, hiring outcomes or production usage.
Baseline: the latest master ancestor before 23:59:59 Dubai on 12 September,
[`cf9a6bc30ce93cedc9bed48b3ba0fefbbcd8eef8`](https://github.com/SoSwag5/ASTRA/tree/cf9a6bc30ce93cedc9bed48b3ba0fefbbcd8eef8).
Endpoint: the source SHA named by the v1.1.0-beta.1 release manifest. Do not use
a later moving master as the beta endpoint.

| Area | 12 September source | Beta source |
|---|---|---|
| Product | Already a local discovery, CV review, document-preparation and application-tracking workspace | More complete provider, assessment, confirmation and review workflows |
| Career focus | Career-track selection already existed; it was not added for this beta | Explainable fit, experience and eligibility assessment expanded; broader career quality still needs validation |
| Discovery | Earlier adapter/discovery implementation and optional scheduled discovery wording | Greenhouse/Lever/Ashby provider contracts, telemetry, diagnostics, conservative deduplication and manual-only preview/start/stop |
| Gmail | No Gmail modules in the baseline backend tree | Optional OAuth, bounded synchronization, deterministic confirmation parsing and review-first reconciliation; primary account only |
| UI | Earlier frontend and fictional demo already existed | App-wide visual system, responsive light/dark layouts, state feedback and reduced-motion-aware page/control transitions |
| Security | Local request controls, PDF worker limits, SSRF checks, credential storage and supply-chain workflows already existed | Expanded adversarial and integration coverage, threat/risk governance, #48 guard corrections and pypdf advisory remediation |
| Delivery | setup.bat/run.bat and prepared ZIP/provenance workflows | Friendly launchers, beginner guide, beta-specific version plumbing and exact-artifact release assurance |

Source evidence: inspect backend trees and diffs between the baseline and the
release SHA, especially `backend/job_providers`, `backend/assessment.py`,
`backend/gmail_*`, `backend/application_reconciliation.py`, frontend components,
and the linked #47/#48 validation records. Existing security work is acknowledged
as baseline work; it is not counted again as a newly invented beta capability.

## Why it matters for a cybersecurity graduate

The portfolio value is a usable product supported by inspectable engineering:
threat boundaries, adversarial tests, dependency triage, secure OAuth handling,
data-minimization decisions, SBOMs, artifact identity and release gates. Explain
your own decisions and verification, and disclose AI assistance honestly.
Framework mappings are not certifications or proof of production experience.

The largest evidence gap is **real-world product validation**: broader career
relevance, live confirmation accuracy, novice installation on another PC, and
safe upgrade behaviour. More code and test counts alone cannot close that gap.
Cloud architecture is a future direction, not an AWS deployment claim.
