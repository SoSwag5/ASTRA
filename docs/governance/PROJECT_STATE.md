# ASTRA project state

**Snapshot date:** 2026-09-14 (Asia/Dubai)
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
  Next authorized implementation target is **issue #39** (Lever + Ashby
  providers, with Workable evaluated inside that issue); #39 implementation
  has not started. Issues beyond #39 remain not started under the approved
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

## Resolved v1.1 issues

| Issue | Resolution | Notes |
|---|---|---|
| [#37](https://github.com/SoSwag5/ASTRA/issues/37) | Closed. Discovery query planner merged via [PR #51](https://github.com/SoSwag5/ASTRA/pull/51) (squash commit `a1e6373356b59e379f1b33910f3b678ddf4211fd`). | Deterministic, rule-based query expansion (`backend/query_planner.py`); 123 tests; three rounds of independent Codex review, final Codex APPROVE, Owner-authorized merge. |
| [#38](https://github.com/SoSwag5/ASTRA/issues/38) | Closed. Common job-provider framework + Greenhouse migration merged via [PR #53](https://github.com/SoSwag5/ASTRA/pull/53) (squash commit `c6c8f8bc58c6171d67017d2e8d52761d67a18bd7`). | `backend/job_providers/` contract, transport, registry, compatibility seam; Greenhouse migrated off `recall.py`; 40 new tests; three rounds of independent Codex review, final APPROVE, Owner-authorized merge; live-verified against GitLab's real Greenhouse board. Lever/Ashby/SmartRecruiters/`FormAdapter` untouched. |

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
Issue #37 (Discovery Query Planner) and issue #38 (common job-provider
framework + Greenhouse migration) are both complete and merged to `master`
(PR #51, PR #53). The next authorized implementation target is issue #39
(Lever + Ashby providers, migrated onto the #38 framework, with Workable
evaluated inside that issue per its acceptance criteria — not assumed);
it has not been started. Governance v1 rules apply to #39 as they did to
#37/#38 (dedicated feature branch, no direct push to `master`, focused
scope, tests, independent review before Owner-authorized merge). The
rebased `hardening/l2-r13-r14` branch (issue #33) remains parked for v1.2
and awaits independent review before a PR is opened — not touched by v1.1
implementation.
