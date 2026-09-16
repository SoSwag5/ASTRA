# ASTRA project state

**Snapshot date:** 2026-09-16 (Asia/Dubai), refreshed after #42 closed and #43 implementation opened for review
**Rule:** This is a handoff snapshot, not a substitute for live verification.
Refresh it at session end when repository or release state changes.

## Released product

- Current release: [`v1.0.0`](https://github.com/SoSwag5/ASTRA/releases/tag/v1.0.0),
  published 2026-09-13.
- Frozen source commit: `81ad2d38869980fe854d92f26a9ae16b774f58a6`.
- Release artifact: `astra-1.0.0-rc.1.zip`, SHA-256
  `a5842744bad86a249381f5c1c4f509785375c994af1cbc70fef5f6e283b4399f`.
- CycloneDX 1.7 SBOM: 246 components, SHA-256
  `6f8b681e352a8efb58b344f22a28eabad5090aa37f5b123c0ef06ab0a16ea293`.
- Final release gate: **APPROVED WITH DOCUMENTED RESIDUAL RISK**, blockers `[]`.
- Provenance and SBOM attestations were independently verified for the released
  artifact. The gate did not authorize publication; the Owner approved and
  published the release separately.
- The `v1.0.0` tag, source, artifacts, digests, attestations, and release record
  are immutable. Corrections ship from later commits and versions; never rebuild,
  replace, move, or retag v1.0.0.

See [the immutable release record](../release/V1_0_0_RELEASE_RECORD.md) for the
evidence chain and run URLs.

## Milestone state

- Next milestone: **v1.1 — Discovery & Application Intelligence** (reprioritized
  by the Owner on 2026-09-13; the prior next milestone, Operational Security &
  Resilience, moved to v1.2 without being dropped). See
  `docs/governance/OWNER_DECISIONS.md` OD-010 and
  `docs/planning/V1_1_DISCOVERY_AND_APPLICATION_INTELLIGENCE.md`.
- v1.1 architecture/security approval: **COMPLETE (OD-018, 2026-09-13).**
  ADR-0007, ADR-0008, ADR-0009 are Accepted as architecture decisions
  (implementation evidence for each remains Pending); the v1.1 threat-model
  delta is Approved; risks R-16 (2/3=6, HIGH), R-17 (2/2), R-18 (2/2) are
  registered OPEN with treatment planned for v1.1 — registered, not
  residual-accepted. See `docs/governance/V1_1_OWNER_REVIEW_PACKET.md`.
- v1.1 implementation status: **issue #37 (Discovery Query Planner) COMPLETE**
  and merged to `master` via [PR #51](https://github.com/SoSwag5/ASTRA/pull/51)
  (squash commit `a1e6373356b59e379f1b33910f3b678ddf4211fd`), following three
  rounds of independent Codex review and a final Codex APPROVE. `master` now
  carries `backend/query_planner.py` and its 123-test regression suite.
  **Issue #38 (common job-provider framework + Greenhouse migration) is now
  also COMPLETE**, merged to `master` via
  [PR #53](https://github.com/SoSwag5/ASTRA/pull/53) (squash commit
  `c6c8f8bc58c6171d67017d2e8d52761d67a18bd7`) after three rounds of
  independent Codex review (round 2: findings F1-F8 remediated; round 3:
  findings B1-B6 remediated; final remediation closed remaining findings) and
  a final independent APPROVE, with Owner-authorized merge. `master` now
  carries `backend/job_providers/` (`contracts.py`, `transport.py`,
  `greenhouse.py`, `registry.py`, `compatibility.py`) and 40 new tests (458
  total on the branch). Verified evidence for #38: all hosted required/
  informational checks green at the merged head (Security Verification,
  Python 3.13/3.14, SCA, dependency review, CodeQL python/javascript-
  typescript/actions), `python scripts/publication_gate.py` → PASS, and a
  live-verified fetch against GitLab's real public Greenhouse board
  (COMPLETE/HEALTHY, 227 real postings) over the pinned transport. (Session
  note: the task that requested this refresh used the labels "Provider
  Contract Gate" and "First Real Jobs Gate" for this evidence; neither term
  exists elsewhere in ASTRA's governance vocabulary, so this snapshot records
  the actual named checks above instead of adopting undefined gate names.)
  **Issue #39 (Lever + Ashby provider migration) is now also COMPLETE**,
  merged to `master` via
  [PR #55](https://github.com/SoSwag5/ASTRA/pull/55) (squash commit
  `6a23397028c679f9ac51a0cba9909addc826edd4`) after three rounds of
  independent Codex review (initial review: findings 1-6 remediated; final
  retest: two remaining HIGH blockers — Ashby invalid-jobUrl fallback and
  Lever normalized-ID collision — remediated) and a final independent
  APPROVE, with Owner-authorized merge. `master` now carries
  `backend/job_providers/lever.py` and `backend/job_providers/ashby.py`
  migrated onto the #38 framework, with `contracts.py` gaining shared
  `valid_downstream_url()` validation and a `PAGINATION_LIMIT_REACHED`
  completion reason, and `compatibility.py` fixed to stop hardcoding the
  Greenhouse source label and dropping `remote_status` for other providers.
  Verified evidence for #39: candidate regression 675 passed / 0 failed / 0
  errors, all hosted required/informational checks green at the merged head
  (Security Verification, Python 3.13/3.14, SCA, dependency review, CodeQL
  python/javascript-typescript/actions), `python scripts/publication_gate.py`
  → PASS, and live-verified fetches against Lever's own `leverdemo` public
  board and real Ashby boards already in ASTRA's source list (Ziina, Lean
  Technologies). Workable was evaluated per #39's acceptance criteria: a
  public `apply.workable.com` widget endpoint is technically accessible but
  lacks official Workable documentation establishing it as a supported
  integration surface, so it is classified **NEEDS OWNER/PERMISSION
  DECISION** and was not implemented. SmartRecruiters remains on its legacy,
  unmigrated path; `FormAdapter`/`LeverAdapter`/`AshbyAdapter` (the separate
  application-form seam) were untouched.
  **Issue #40 (Normalization + conservative cross-provider deduplication) is
  now also COMPLETE**, merged to `master` via
  [PR #57](https://github.com/SoSwag5/ASTRA/pull/57) (squash commit
  `b1f754997afe84798f0ab19ee552a89a03de2098`) after independent review
  confirmed all six remediation findings fixed (generic ATS roots,
  fingerprint-only matching, long-content hashing, the transitive bridge,
  indexed candidate lookup, and canonical `job_url` enrichment; remediation
  commit `17255d9`), with Owner-authorized merge. `master` now carries
  `backend/deduplication.py` and `backend/normalization.py`, the additive
  `JobObservation` model (`backend/models.py`), and ADR-0010 (now Accepted).
  `Job` remains the stable, compatibility-facing canonical row; no historical
  `Job` row was merged, deleted, or reparented, and no `Application`/document/
  event foreign key changed. Verified evidence for #40: all hosted required/
  informational checks green at the merged head (Security Verification,
  Python 3.13/3.14, SCA, dependency review, CodeQL python/javascript-
  typescript/actions), and the repository's own regression/migration/privacy
  test suites for normalization, deduplication, and `JobObservation`
  integration. Historical duplicate `Job` rows from before #40 are not
  consolidated (deliberate scope boundary, Owner Decision 2).
  **Issue #41 (Eligibility + Explainable Ranking) is now also COMPLETE**,
  merged to `master` via [PR #59](https://github.com/SoSwag5/ASTRA/pull/59)
  (squash commit `3faebd370a5e4566cb5e02f1a0eabdb38622b60b`) after a
  remediation commit (`5d59978`) fixed six independently-found issues
  (US/UK-only geography over-matching, workflow-state preservation gaps,
  reassessment not running for duplicate/no-profile jobs, an unbounded
  eligibility/work-authorization model, experience-scope attribution, and
  bounded legacy-vs-new shadow comparison) and a final independent review
  returned APPROVE, with Owner-authorized merge. `master` now carries
  `backend/assessment.py` (deterministic domain/seniority/geography
  assessment, a six-code hard-reject taxonomy, and the provisional
  seven-component scoring model) and `backend/experience.py` (scoped
  experience-clause parsing); no schema/migration change — the
  authoritative derived assessment persists at `Job.analysis['fit_assessment']`
  (`Settings.assessment_mode`, default `NEW`; `evaluate_legacy()` retained
  for `SHADOW`/`LEGACY` rollback and #42 comparison evidence). The
  pre-#41 pipeline hard-rejected relevant postings (on experience gaps,
  seniority words, or an out-of-track title) *before* #40's persistence
  seam ever saw them; discovery now persists every structurally valid
  posting first and only hides a genuinely hard-incompatible one via the
  existing `SKIP` status, never by skipping persistence (Owner Decision 1).
  Verified evidence for #41: all hosted required/informational checks green
  at the merged head (Security Verification, Python 3.13/3.14, SCA,
  dependency review, CodeQL python/javascript-typescript/actions), and a
  full local regression (864 passed / 1 skipped, same 7 pre-existing
  Playwright browser-binary failures as `master`, 0 unexplained
  regressions). `backend/normalization.py`, `backend/deduplication.py`,
  provider transport, and the frontend are untouched.
  Issue **#42** (Discovery evaluation harness) is now **COMPLETE and CLOSED**:
  the deterministic offline harness foundation merged via PR #61, PR #63
  carried the Owner-adjudicated 80-case reference snapshot, and PR #64
  (squash commit `68d79edaaaf09e12aa24e090e7192709d65ba646`) fixed evaluation
  provenance so it survives squash merges. The quality gate remains PROPOSED
  and `INSUFFICIENT_DATA` pending expansion and approval; no production
  calibration was adopted. Issue **#43** (Discovery funnel telemetry) is
  **IMPLEMENTED AND AWAITING INDEPENDENT REVIEW** on
  `feature/43-discovery-telemetry`, based on
  `68d79edaaaf09e12aa24e090e7192709d65ba646` — not merged, and merge remains an
  Owner decision. Issues #44-#48 remain not started under the approved
  12-issue backlog ("v1.1 — Discovery & Application Intelligence" milestone,
  issues #37-#48).
- Governance integration advances `master` from the frozen release commit without
  moving or modifying the immutable v1.0.0 tag, source, or artifacts.

## Current residual risks and follow-up

- R-01, R-02, R-03, R-07, and R-08 remain historical accepted residuals under
  their existing event triggers. The Owner declined to invent dated
  expirations for these (OD-008); only R-15 carries a dated review.
- R-15 remains the accepted v1.0 OS-account/localhost trust-boundary decision,
  now with a dated review of 2026-12-12 alongside its existing event triggers
  (OD-008; issue #27, closed).
- R-04 and R-05 are mitigated but remain subject to dependency and AI-change
  review.
- R-09's hosted installation path passed; live scheduled-task migration is
  deferred to the v1.3 Professional Distribution / Installer milestone (OD-009)
  and requires separate Owner approval when undertaken.
- Applicable ASVS L1 is closed. R-12 retains open L2 hardening work.
- R-13 and R-14 remain open L2 hardening/resilience risks. The prior isolated
  WIP (`hardening/l2-r13-r14`) has been rebased onto current `master`
  (commit `f4b8f6f`) and mapped to the v1.2 milestone via issue #33; it awaits
  independent review before a PR is opened, and is not merged.
- R-06, R-10, and R-11 post-release documentation debt is resolved: issues
  #24-#26 are closed and `docs/security/RISK_REGISTER.md` reflects the final
  publication evidence, the authoritative 6.7/10 Scorecard figure, and the
  released-candidate provenance references. The frozen v1.0.0 files were not
  rewritten.

## Resolved post-release issues

| Issue | Resolution | Release impact |
|---|---|---|
| [#24](https://github.com/SoSwag5/ASTRA/issues/24) | Closed. R-06 set to Closed using the final publication evidence (PR #29). | Documentation correction after v1.0; v1.0.0 not rebuilt. |
| [#25](https://github.com/SoSwag5/ASTRA/issues/25) | Closed. Scorecard reference corrected from 7.1 to 6.7 (PR #30). | Documentation correction after v1.0; no security regression implied. |
| [#26](https://github.com/SoSwag5/ASTRA/issues/26) | Closed. R-11 now points to the released candidate and final gate/release references (PR #31). | Documentation correction after v1.0; avoids a self-referential artifact digest. |
| [#27](https://github.com/SoSwag5/ASTRA/issues/27) | Closed. R-15 carries a dated review/expiry; other standing acceptances left event-triggered per OD-008 (PR #32). | Owner governance decision; v1.0 remains immutable. |

Open follow-up: [#33](https://github.com/SoSwag5/ASTRA/issues/33) tracks the
rebased R-13/R-14 hardening branch into the v1.2 milestone; not yet reviewed
or merged.

## v1.1 implementation status

| Issue | Resolution | Notes |
|---|---|---|
| [#37](https://github.com/SoSwag5/ASTRA/issues/37) | Closed. Discovery query planner merged via [PR #51](https://github.com/SoSwag5/ASTRA/pull/51) (squash commit `a1e6373356b59e379f1b33910f3b678ddf4211fd`). | Deterministic, rule-based query expansion (`backend/query_planner.py`); 123 tests; three rounds of independent Codex review, final Codex APPROVE, Owner-authorized merge. |
| [#38](https://github.com/SoSwag5/ASTRA/issues/38) | Closed. Common job-provider framework + Greenhouse migration merged via [PR #53](https://github.com/SoSwag5/ASTRA/pull/53) (squash commit `c6c8f8bc58c6171d67017d2e8d52761d67a18bd7`). | `backend/job_providers/` contract, transport, registry, compatibility seam; Greenhouse migrated off `recall.py`; 40 new tests; three rounds of independent Codex review, final APPROVE, Owner-authorized merge; live-verified against GitLab's real Greenhouse board. Lever/Ashby/SmartRecruiters/`FormAdapter` untouched. |
| [#39](https://github.com/SoSwag5/ASTRA/issues/39) | Closed. Lever + Ashby provider migration merged via [PR #55](https://github.com/SoSwag5/ASTRA/pull/55) (squash commit `6a23397028c679f9ac51a0cba9909addc826edd4`). | `backend/job_providers/lever.py` (bounded pagination, normalized identity) and `backend/job_providers/ashby.py` (validated jobUrl-first identity, Hybrid/Remote/OnSite/Unknown semantics) migrated onto the #38 framework; shared `valid_downstream_url()` added to `contracts.py`; `compatibility.py` source-label/remote_status bug fixed. Three rounds of independent Codex review, final APPROVE, Owner-authorized merge; live-verified against Lever's `leverdemo` board and real Ashby boards (Ziina, Lean Technologies). Workable: **NEEDS OWNER/PERMISSION DECISION**, not implemented. SmartRecruiters/`FormAdapter` untouched. |
| [#40](https://github.com/SoSwag5/ASTRA/issues/40) | Closed. Normalization + conservative cross-provider deduplication merged via [PR #57](https://github.com/SoSwag5/ASTRA/pull/57) (squash commit `b1f754997afe84798f0ab19ee552a89a03de2098`). | Additive `JobObservation` provenance table (`backend/models.py`); `Job` remains the stable canonical row; versioned normalization (`backend/normalization.py`) and conservative dedupe hierarchy (`backend/deduplication.py`) with fingerprint-only evidence always `CANDIDATE`, never a destructive `MATCH`; indexed candidate lookup; non-transitive-bridge protection; forward-safe additive migration with `legacy_incomplete` backfill (no historical consolidation); ADR-0010 Accepted. Independent review confirmed six remediation findings fixed, Owner-authorized merge. |
| [#41](https://github.com/SoSwag5/ASTRA/issues/41) | Closed. Eligibility + explainable ranking merged via [PR #59](https://github.com/SoSwag5/ASTRA/pull/59) (squash commit `3faebd370a5e4566cb5e02f1a0eabdb38622b60b`). | `backend/assessment.py` (domain/seniority/geography assessment, six-code hard-reject taxonomy, seven-component provisional scoring, score means ranking priority not probability) and `backend/experience.py` (scoped experience-clause parsing); discovery now persists every structurally valid posting through #40 before assessing it, hiding a hard reject via the existing `SKIP` status rather than skipping persistence; `evaluate_legacy()` retained for `SHADOW`/`LEGACY` rollback and #42 shadow-comparison evidence; no schema/migration change (`Job.analysis['fit_assessment']`). A remediation commit fixed six independently-found issues before a final independent APPROVE and Owner-authorized merge. `backend/normalization.py`/`backend/deduplication.py`/provider transport/frontend untouched. |
| [#42](https://github.com/SoSwag5/ASTRA/issues/42) | **Closed.** Deterministic evaluation + calibration harness merged via [PR #61](https://github.com/SoSwag5/ASTRA/pull/61) (squash commit `fab8acda48d65f1a03ae1b97465369ec4742957a`), [PR #63](https://github.com/SoSwag5/ASTRA/pull/63) (Owner-adjudicated reference snapshot) and [PR #64](https://github.com/SoSwag5/ASTRA/pull/64) (squash commit `68d79edaaaf09e12aa24e090e7192709d65ba646`, squash-merge-safe provenance). | Offline evaluation only: 80-case corpus with Owner-adjudicated reference labels. The quality gate remains `PROPOSED` / `INSUFFICIENT_DATA` pending eligibility-sample and corpus expansion — **no gate has passed**. Candidate policies are exploratory; no production calibration was adopted. `docs/evaluation/fit_evaluation_provenance_v1.json` pins the SHA-256 of `backend/{assessment,career_tracks,deduplication,discovery,evaluation,experience,models,normalization,policy,recall,services}.py`; those files must not be edited without regenerating that manifest under Owner authorization. |
| [#43](https://github.com/SoSwag5/ASTRA/issues/43) | **IMPLEMENTED, AWAITING INDEPENDENT REVIEW.** Discovery funnel telemetry on `feature/43-discovery-telemetry`, based on `68d79edaaaf09e12aa24e090e7192709d65ba646`. Not merged. | New `backend/discovery_telemetry.py` owns one versioned contract (`discovery-telemetry-v1`) persisted in the existing `AutomationRun.report` JSON — **no schema change or migration**. Monotonic funnel `FETCHED → STRUCTURALLY_VALID → CANONICAL_UNIQUE → LOCATION_COMPATIBLE → ELIGIBILITY_NOT_INCOMPATIBLE → RELEVANT → NEW`, derived from explicit stage membership and checked by an invariant validator, never clamped. `DISPLAYED`/`SAVED`/`APPLIED` are reported separately as engagement outcomes; `DISPLAYED` is explicitly `UNAVAILABLE` because ASTRA records no display event. Provider failure, truthful zero, partial completion and skipped sources stay distinguishable. Retention is exactly 90 days. Read-only local API at `/api/search/telemetry*`. #41 decision behaviour, #40 identity/dedupe, provider transport and #42 evidence are unchanged; `backend/recall.py` was deliberately left untouched because it is a provenance-pinned #42 input. See [`docs/architecture/DISCOVERY_TELEMETRY.md`](../architecture/DISCOVERY_TELEMETRY.md). |

## Git and collaboration snapshot

- Canonical remote: `https://github.com/SoSwag5/ASTRA.git`.
- Protected default branch: `master`.
- Final integration base: `81ad2d38869980fe854d92f26a9ae16b774f58a6`.
- Governance worktree: separate local checkout `astra-release-governance-v1`.
- Governance branch: `governance/release-governance-v1`.
- Original governance commit `f2307be` is preserved locally on
  `backup/governance-release-governance-v1-f2307be`.
- Governance pull request:
  [#28 — Add ASTRA Release Governance v1](https://github.com/SoSwag5/ASTRA/pull/28),
  targeting `master`.
- Claude Code owns implementation/remediation branches assigned by the Owner.
  Codex owns this governance branch and independently reviews other branches
  without editing them.
- The Owner approved ADR-0001 and ADR-0003 through ADR-0006 on 2026-09-13 and
  authorized PR #28 to merge only after its updated required checks pass. When
  this file is present on `master`, Governance v1 is active project policy.

## Authoritative evidence

- Final gate: `release-security-gate.json` attached to v1.0.0; gate run
  [34732173819](https://github.com/SoSwag5/ASTRA/actions/runs/34732173819).
- Candidate build and attestations: run
  [34722561421](https://github.com/SoSwag5/ASTRA/actions/runs/34722561421).
- Release/tag annotation and GitHub release assets bind the frozen source,
  artifact digest, and SBOM digest.
- `docs/release/RELEASE_SECURITY_ASSURANCE_REPORT.md` is a dated pre-remote local
  assessment. `docs/security/SLSA_V1.2_ASSESSMENT.md` assesses an earlier candidate.
  Neither replaces the final release record.
- `docs/security/RISK_REGISTER.md` is the current source risk register; the
  post-release corrections #24-#27 are applied and closed.

## Exact next action

Governance v1 is merged; the four post-release documentation corrections
(#24-#27) are complete; the v1.1 mission, architecture, backlog, three ADRs,
and threat-model delta are all Owner-approved (OD-011 through OD-018).
Issue #37 (Discovery Query Planner), issue #38 (common job-provider
framework + Greenhouse migration), issue #39 (Lever + Ashby provider
migration), issue #40 (Normalization + conservative cross-provider
deduplication), and issue #41 (Eligibility + Explainable Ranking) are all
complete and merged to `master` (PR #51, PR #53, PR #55, PR #57, PR #59).
ADR-0010 is Accepted. Issue #42 (Discovery evaluation harness) is **COMPLETE
and CLOSED** (PR #61, PR #63, PR #64); the quality gate remains PROPOSED and
`INSUFFICIENT_DATA` pending corpus expansion and approval, and no production
calibration was adopted. Issue #43 (Discovery funnel telemetry) is
**IMPLEMENTED AND AWAITING INDEPENDENT REVIEW** on
`feature/43-discovery-telemetry`; it is not merged, and merge remains an Owner
decision after review. Issues #44-#48 have not started. Governance v1 rules
continue to apply (dedicated feature branch, no
direct push to `master`, focused scope, tests, independent review before
Owner-authorized merge). Workable remains **NEEDS OWNER/PERMISSION DECISION**
(a technically accessible public widget endpoint, but no official Workable
documentation establishing it as a supported integration surface) and is not
registered as a provider. The rebased `hardening/l2-r13-r14` branch (issue #33) remains
parked for v1.2 and awaits independent review before a PR is opened — not
touched by v1.1 implementation.
