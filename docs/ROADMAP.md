# ASTRA product and assurance roadmap

The roadmap communicates direction rather than a release promise. Scope and
timing remain Owner decisions. Open 8-15 meaningful issues when a milestone
starts; do not pre-create a large speculative backlog.

## Reprioritization (2026-09-13)

The Owner reprioritized this roadmap after real-world use of `v1.0.0`. The
previous next milestone, **v1.1 — Operational Security & Resilience**, is
retained but moved to **v1.2**. See `docs/governance/OWNER_DECISIONS.md` OD-010
for the decision record and rationale, and
`docs/planning/V1_1_DISCOVERY_AND_APPLICATION_INTELLIGENCE.md` for the v1.1
product mission and architecture planning this reprioritization produced.

Observed product problems driving the change:

- Discovery frequently reports healthy sources but produces zero new useful
  jobs.
- Search does not behave like a real user searching for roles such as "SOC
  Analyst Level 1".
- The user manually discovers and applies to significantly more jobs than
  ASTRA records.
- Gmail contains application confirmations and status emails that ASTRA does
  not currently reconcile.
- ASTRA's dashboard therefore under-reports real progress and creates a false
  impression that little job-search activity is happening.

The next release improves the core discovery/tracking loop before further
platform-maturity work.

## v1.0 — Secure Local-First Foundation — RELEASED

- Released as immutable `v1.0.0` from source `81ad2d3` on 2026-09-13.
- Preserves the local-first product boundary and manual final submission.
- Final gate: APPROVED WITH DOCUMENTED RESIDUAL RISK, zero blockers; hosted
  provenance and CycloneDX 1.7 SBOM attestations verified.
- Post-release documentation/governance debt is tracked in issues #24-#27 and
  does not change the frozen release.

## v1.1 — Discovery & Application Intelligence — NEXT, NOT STARTED

v1.1 begins only after the Owner approves the product mission and backlog in
`docs/planning/V1_1_DISCOVERY_AND_APPLICATION_INTELLIGENCE.md`. When the
milestone starts, select 8-15 meaningful issues from that plan's proposed
backlog with explicit owners and acceptance criteria; do not treat existing
local experiments as milestone work.

- Replace the current weak discovery experience with a query-planner and
  provider-adapter architecture (retrieve broadly, rank second).
- Add an interpretable, explainable ranking model with a measurable evaluation
  set and per-source funnel telemetry.
- Add read-only Gmail application-confirmation capture for two user-owned
  accounts via OAuth, with a confidence-gated reconciliation policy.
- Redesign the progress/dashboard experience around verified discovery and
  application events, not gamification.
- The human remains responsible for final application submission; ASTRA does
  not submit applications autonomously.

## v1.2 — Operational Security & Resilience

- Improve recovery, backup validation, diagnostics, resource controls, and
  security-event coverage.
- Exercise incident response and recovery paths using synthetic data.
- Reassess open ASVS L2 and SAMM roadmap items affected by the work.
- Triage R-12, R-13, R-14, and any remaining post-release documentation debt
  into the milestone or a preceding documentation patch as appropriate.

## v1.3 — Professional Distribution & Upgrade Lifecycle

- Design signed installation, upgrade, rollback, migration, and uninstall
  paths.
- Validate upgrades from supported versions on clean Windows environments.
- Define update-channel integrity and support boundaries before
  implementation.
- Execute the deferred live Windows Scheduled Task migration (OD-009) under
  explicit Owner approval, per `docs/SCHEDULED_TASK_MIGRATION.md`.

## v1.5 — AWS Reference Architecture

- Produce an Owner-approved AWS reference architecture and Infrastructure as
  Code with explicit identity, secrets, network, logging, backup, cost, and
  observability boundaries.
- Keep the local-first edition supported; a reference architecture is not a
  production-hosting claim.

## v2.0 — Identity, Authorization & Multi-User Security

- Introduce application identities, authorization, tenant boundaries, and data
  isolation only through approved ADRs and a full threat-model update.
- Reopen R-15 and every ASVS control previously scoped N/A because v1.0 was
  single-user and local-only.
- Provide compatibility and data-migration guidance for the new trust model.

## v2.1+ — Production Security Maturity

- Strengthen operational monitoring, vulnerability response, resilience,
  independent assurance, and measurable SAMM practices using real evidence.
- Reassess SSDF, ASVS, SAMM, CycloneDX, and SLSA claims for each material
  change.
