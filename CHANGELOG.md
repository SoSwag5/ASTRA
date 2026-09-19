# Changelog

All notable ASTRA changes are recorded here. Entries follow Keep a Changelog
categories and Semantic Versioning. Dates and version headings are added only
when a release is approved; this file does not establish that a release exists.

## [Unreleased]

### Added

- One authoritative application-state model with an explicit permitted-transition
  table, an append-only transition history carrying manual/automated provenance,
  and conservative deterministic multi-field reconciliation of Gmail
  confirmation evidence. `APPLIED` is the only state an automated signal may
  set, at HIGH confidence and a unique strong match only; MEDIUM enters a Needs
  Review queue and LOW never mutates state. Additive schema; existing
  applications are bootstrapped truthfully on first contact. No live mailbox
  validation and no independent review; R-18 remains OPEN (#46).

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
