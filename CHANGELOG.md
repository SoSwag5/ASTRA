# Changelog

## 1.1.0-beta.1 — 2026-10-02

Early beta preparation integrating the reviewed #47 visual/motion work and
corrected #48 assurance inventory. Added consistent release version metadata,
friendly Windows install/open launchers, a beginner guide, beta notes, another-PC
checklist, source comparison and independent cloud-review prompt. Updated pypdf
to 6.19.0 with refreshed hashes and added fictional cross-major CV import tests.
Primary-only Gmail, live accuracy, broader ranking and final v1.1 acceptance
remain open. Publication is conditional on the exact candidate's executed gates.

All notable ASTRA changes are recorded here. Entries follow Keep a Changelog
categories and Semantic Versioning. Dates and version headings are added only
when a release is approved; this file does not establish that a release exists.

## [Unreleased]

### Beta 3 candidate (not released)

- Setup and career-focus saves show persistent outcome text, busy and unsaved
  hints; a write that succeeded but could not refresh offers Refresh instead of
  a second write and blocks advancing on stale data. Focus choices are locked
  while a save runs.
- Animated disclosures and pages, Progress period transitions, consistent
  hover/focus/press states and an Appearance motion choice (Match system,
  Reduce motion, Full motion). Full motion overrides an operating-system
  reduced-motion setting only after an explicit choice.
- A **Sources & websites** directory: 77 unique destinations (74 manual links,
  3 supported public feeds) with check dates, search, groups and user-added
  links. Fresh workspaces enable three starter feeds; existing workspaces get
  them paused. Startup seeding makes no network request and creates no jobs.
- Optional Gmail setup copy no longer presents developer setup as a dead end.
- Release workflow paths now refer to beta 3.

### Added

- Resume-driven discovery query planning with explicit search-focus confirmation,
  career tracks and bounded role/query variants (#37). Ranking remains a
  review priority, not a hiring probability or work-authorization decision.

- A shared public-job-provider framework for Greenhouse, Lever and Ashby,
  with pinned validated connections, bounded responses, isolated source
  failures and explicit completeness reporting (#38, #39). Workable was
  evaluated but is not an enabled provider.

- Job observations and conservative cross-provider normalization/deduplication;
  weak candidate matches and transitive bridges do not automatically merge
  distinct applications or postings (#40).

- Separate eligibility warnings and explainable technical-role ranking,
  plus a fictional evaluation harness and discovery funnel/source telemetry
  (#41, #42, #43). These do not establish real-world ranking quality.

- Primary-account Gmail OAuth with exactly read-only scope, PKCE/state checks,
  authenticated account binding, native credential storage and explicit
  disconnect/revocation outcomes (#44). The secondary slot remains disabled.

- Manual Start Scan with preview, confirmed source selection and Stop handling;
  responsive discovery polling and corrected cancellation/reporting boundaries
  (#46.2-A/B). Scheduled-task migration remains deferred.

- Aggregate-only source-research and failed blind-evaluation closeout records
  (#46.2-B/C). No role-model promotion, calibrated fit claim or validated
  offline-model capability is introduced by those records.

- Consolidated v1.1 negative-test traceability, corrected OAuth security
  mappings, as-built threat evidence and a blocked pre-candidate release pack
  (#48). This is assurance preparation, not a published v1.1 release.

- A Progress page built on verified events: the Gmail Needs Review queue with
  confirm/reject through the existing #46 rules and a read-only candidate list
  for ambiguous items, period figures from canonical transition history, Gmail
  evidence and discovery telemetry (Asia/Dubai windows, cross-source
  deduplication, partial and unavailable data written out rather than shown as
  zero), the canonical application journey and discovery health. Every figure
  shows how it is counted. Today drops the unverified "quality applications"
  meter and Applications shows canonical state. Awaiting independent review
  (#47).

- One authoritative application-state model with an explicit permitted-transition
  table, an append-only transition history carrying manual/automated provenance,
  and conservative deterministic multi-field reconciliation of Gmail
  confirmation evidence. `APPLIED` is the only state an automated signal may
  set, at HIGH confidence and a unique strong match only; a contradictory
  requisition URL blocks automatic linking outright; HIGH and MEDIUM evidence
  that cannot be linked stays resolvable in a Needs Review queue and LOW never
  mutates state. Additive schema; existing applications are bootstrapped
  truthfully and the read models are order-independent. Independently
  reviewed before merge (four rounds, final APPROVE); no live mailbox
  validation; R-18 remains OPEN (#46).

- PRIMARY Gmail bounded incremental read-only sync and deterministic initial
  application-confirmation evidence, with minimized storage, hostile-content
  controls and fictional privacy/spoofing regressions (#45).

- Release Governance v1: session handoff, change classification, ADRs, release
  evidence, security decision templates, GitHub contribution templates, and an
  evidence-based roadmap.

## [1.0.0] - 2026-09-13

### Added

- Local-first job discovery and application tracking with manual control over
  final submission.
- Evidence-backed security controls, automated release gating, a validated
  CycloneDX 1.7 SBOM, and verified hosted provenance/SBOM attestations.

### Security

- Released from source `81ad2d3` after the final gate reported APPROVED WITH
  DOCUMENTED RESIDUAL RISK and zero blockers.
- The accepted local OS-account/localhost trust boundary and other residual risks
  remain documented in the security risk register.

[Unreleased]: https://github.com/SoSwag5/ASTRA/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/SoSwag5/ASTRA/releases/tag/v1.0.0
