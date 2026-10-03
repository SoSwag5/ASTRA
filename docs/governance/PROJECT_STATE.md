# ASTRA project state

## Beta 3 candidate — 3 October 2026 (Asia/Dubai)

**v1.1.0-beta.3 is an unpublished candidate** on `feature/beta-3-usability`
(base `1896f1e`). Claude Code owns implementation (continuing Codex's Owner-authorized
work after a quota stop); Codex verifies separately. Scope: persistent setup/focus
feedback, visible motion with a Match system / Reduce / Full choice, a Sources &
websites directory (77 destinations: 74 manual links, 3 public feeds; not "77
verified"), additive no-network startup seeding (fresh workspaces enable three feeds;
existing ones get them paused), clearer optional Gmail copy. Nothing is published,
tagged, independently verified or approved; published beta 2 is unchanged. See the
[plan](../planning/BETA_3_RELEASE_PLAN.md), [handoff](../planning/BETA_3_USABILITY_HANDOFF.md)
and [candidate evidence](../release/V1_1_0_BETA_3_EVIDENCE.md).

## Published beta 2 — 2 October 2026 (Asia/Dubai)

**v1.1.0-beta.2 is public** after the Owner explicitly approved its exact frozen
source and ZIP digest. [Download and customer instructions](https://github.com/SoSwag5/ASTRA/releases/tag/v1.1.0-beta.2)
and the [release record](../release/V1_1_0_BETA_2_RELEASE_RECORD.md) supersede the
preparation snapshot. Frozen tag: `c1b805241888f4499afab3d30df5d97a0f428f36`.
ZIP SHA-256: `251386acf6ffdfb9a85466889a7196a411700fe2c8fe998db1fe8e55675e8e62`.
PRs #83 and #84 merged; integrated master `8cdbb893d9481fd7e4ab16ba5da86c9a15142ae4`
has the same source tree. An anonymous download and all 20 public asset digests
match the reviewed files; public provenance and SBOM verification pass.

Codex owns the explicitly requested implementation and technical self-review.
This is not independent approval. Both final hosted complete test suites pass
2,199 tests with one existing skip; the exact candidate's five mandatory jobs
and final review gate pass. Rule-based is recommended/default, with optional AI
in advanced Settings. Five-step setup, custom-only roles, CV fact review,
optional tracker, scan control, PDF/origin corrections and fictional CV workflows
are implemented and regression-tested. B2-01/B2-02 are not independently CLOSED.

Codex now owns `docs/beta-2-release-record` from the integrated master above to
record publication and refresh dated state/checklist/planning copy. Released
source/assets and beta 1/v1.0 are preserved; runtime, risk acceptance, protected
evaluations and live Owner data are unchanged. Ending SHA and documentation-PR
checks are recorded in the PR/task, without changing the frozen release.

Final v1.1/#48 remains open: R-16/17/18, optional Gmail live/account validation,
broad matching quality and another-PC novice acceptance are incomplete. There
is no controlled evidence of AI superiority. The next step is the
[public ZIP pre-LinkedIn checklist](../release/PRE_LINKEDIN_CHECKLIST.md), then
the [bounded future-update plan](../planning/BETA_FOLLOWUP_CHECKLIST.md).

## Historical beta 1 publication — 2 October 2026


**v1.1.0-beta.1 is public**, under the Owner's explicit push/release instruction.
[Download and evidence](https://github.com/SoSwag5/ASTRA/releases/tag/v1.1.0-beta.1)
and the [release identity record](../release/V1_1_0_BETA_1_RELEASE_RECORD.md)
supersede the preparation-state paragraphs below. The tag points to
`29d70d5ca004d75f0e421aea6174a30b0cd39ce3`; its verified ZIP SHA-256 is
`baa0bc339f5f575b250ef9147dc9e37cfaa8c352a0ef7184a14b3e23f3ce559f`.
The final gate passed on that same artifact, and a public re-download matched.
The tooling correction merged through PR #81; all three Dependabot alerts are
FIXED. Issue #47 is closed; superseded tooling PR #80 is closed.

Codex implemented the release integration and performed technical self-review;
this is not independent approval or a human evidence sign-off. The Claude cloud
review prompt, LinkedIn draft/captions, dated source comparison, cross-major
import tests and another-PC checklist are prepared. The actual cloud review,
brother-PC acceptance and final CV AWS/photo edits remain pending. Issue #48
stays open: final v1.1's second-account/live validation and R-16/17/18 decisions
are not completed by publishing this early beta. v1.0.0 is unchanged.

## Historical beta preparation

**Active release preparation: v1.1.0-beta.1, Owner-authorized on 2026-10-02.**
Codex owns the isolated release branch. The Owner requested push/public beta
publication, easier installation, a cloud review prompt and career-facing drafts.
This authorization does not silently accept pending residual risks or turn
unexecuted gates into PASS. The #47 and #48 states below are dated history;
their source changes are now integrated locally in this preparation branch.
Original worktrees, private evaluation material and v1.0.0 are preserved.

PR #79 integrated the initial beta source into master as `a193235ef8180466a1580b311bf334bf7521ada5`.
Its exact-source tests, installation and provenance passed, but default-branch
Scorecard then found three urllib3 advisories in the separate tooling lock.
Publication remains BLOCKED while the narrow 2.8.0 tooling correction, expanded
CI audit and a fresh source-bound candidate are verified. The initial ZIP is
superseded and must not be published or substituted for the new artifact.

The beta-specific [evidence record](../release/V1_1_0_BETA_1_EVIDENCE.md) and
[release notes](../release/V1_1_0_BETA_1_NOTES.md) are the current preparation
context. New pypdf remediation, version plumbing and cross-major import checks
are Codex implementation, with self-verification distinguished from independent
review. Hosted checks and source/artifact review must execute before publication.
The existing final v1.1 evidence pack below is historical and remains incomplete;
the beta does not close two-account/live validation or Owner residual-risk decisions.

## Historical #48 and #47 snapshots


**Snapshot date:** 2026-10-02 (Asia/Dubai), refreshed for Owner-authorized
Codex corrections to issue #48 after Claude Code reached its usage limit.
The branch is local and unpushed; the release remains BLOCKED.
The 2026-09-29 refresh (PR #75, #46.2-C v3 blind FAIL) and the #46 closeout
below remain historical evidence.

## Research-led motion follow-up (2026-10-01, Asia/Dubai)

Codex continues the Owner-authorized sole implementation of issue #47 on
`feature/47-visual-motion`, from `01c92453d4179523805c7b09954a29a013a6dffe`.
The [20-point research audit](../architecture/UI_UX_RESEARCH_AUDIT.md) informed
new content, sidebar, tab and progress motion, interruption safety and loading
refinements. This remains a compatible frontend-only v1.1 visual change, with
no new dependency, backend behavior, security boundary, ADR or release decision.

The frontend suites/build, 164 browser-matrix checks, 32 motion/reflow checks
and 11 action/lifecycle checks passed on isolated fictional data. See the
[validation record](../architecture/VISUAL_MOTION_VALIDATION.md) for coverage
and limits. This candidate still requires its bounded independent review and
final served-asset verification, recorded in the task handoff after commit.

GitHub rechecked on 2026-10-01: issue #47 is open; PR #78 remains open/draft at
`4a13fc83bee7bd594b61f2ad1b830594a523f742`. That older hosted state does not
validate this local candidate. No push, merge, publication or release is
authorized; other worktrees and private evaluation material remain untouched.

## Local visual candidate update (2026-09-30, Asia/Dubai)

The Owner explicitly assigned Codex sole implementation ownership of
`feature/47-visual-motion` in the existing `astra-47d-visual-motion` worktree,
continuing the uncommitted visual work above base
`fe8e8a85728f06b302aaacd713fe6e9e01cf7d6a`. This frontend-only #47 follow-up
includes the earlier local A/B/C follow-ups. Other worktrees remain protected.
It is a compatible visual/interaction revision within the planned v1.1 minor
release; no release version or security boundary changed.

Live GitHub verification still found draft PR #78 OPEN at
`4a13fc83bee7bd594b61f2ad1b830594a523f742`; its checks cover that older head.
This visual branch is local only. No push, merge, tag, release or publication
is authorized. The historical #47 evidence below is not evidence for this
candidate. See [the visual system](../architecture/VISUAL_MOTION_SYSTEM.md)
and [the validation record](../architecture/VISUAL_MOTION_VALIDATION.md).
Independent review of the exact visual commit remains pending at this record.

**Snapshot date:** 2026-09-30 (Asia/Dubai), refreshed for the #47 draft pull
request (awaiting independent review). The 2026-09-29 refresh for the PR #75
merge (#46.2-B v7 source-map closeout) and the #46.2-C v3 blind FAIL, and the
#46 closeout below, remain historical evidence.
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
  **COMPLETE and merged** to `master` via
  [PR #65](https://github.com/SoSwag5/ASTRA/pull/65) (squash commit
  `ad39e54925fe17286ae03e5866d4ea1cc1259094`), with post-merge CI and
  Scorecard green.
  Issue **#44** is **COMPLETE, MERGED and CLOSED** via
  [PR #66](https://github.com/SoSwag5/ASTRA/pull/66), squash commit
  `c53eb4e1f26f90087b1ca6522db9bbf71e63a463`. Its live OAuth validation
  passed (self-verified; independent review explicitly waived by the Owner
  for #44 only). Manual consent-screen pixels were not retained; no Google
  verification, wider distribution approval or residual-risk acceptance is
  claimed. R-16 remains OPEN.
  Issue **#45** is **COMPLETE, MERGED and CLOSED** via
  [PR #67](https://github.com/SoSwag5/ASTRA/pull/67), squash commit
  `11a69b0921d55072aa4f552a0319320ab73d6741`; post-merge CI and Scorecard
  are green on that commit. `master` carries `backend/gmail_sync.py`,
  `backend/gmail_confirmations.py`, `backend/gmail_content.py` and
  `backend/gmail_messages.py`; see
  [Gmail sync](../architecture/GMAIL_SYNC.md) for architecture, limitations
  and the fictional verification corpus. #45 had **no live mailbox
  validation** and **no independent review**; R-16 and R-17 remain OPEN.
  Issue **#46** is **COMPLETE, MERGED and CLOSED** via
  [PR #68](https://github.com/SoSwag5/ASTRA/pull/68). The independently
  approved head was `006e9111a196e940d8d11163548ef642c2007e5c`
  (tree `ff4c42808a36d031721085c587db51073e591a10`); the squash merge to
  `master` is `7ecd0b78277f67db0a44db176db467bcfb1f5a17`, whose tree is
  exactly the approved tree, so the merged content is the reviewed candidate.
  Claude Code was the Owner-authorized implementation owner. An independent
  review of the first candidate `150a45a` returned **CHANGES REQUIRED** on
  four reproduced defects (conflicting requisition URLs auto-linking; the
  first manual status change recorded as legacy migration; unmatched
  MEDIUM evidence consumed as an unrecoverable no-action; order-dependent
  state summaries and histories). All four are fixed on the same branch with
  regression coverage. A second independent review of `f0382e6` reproduced a
  further bounded-processing defect -- `reconcile_pending()` applied its limit
  to each queue separately, so a run could process twice the requested amount
  -- which is also fixed: the two queues now share one budget and
  `considered + revisited` never exceeds the requested limit. A third
  independent review of `687229c` reproduced a reconciliation-scheduling
  defect: the revisit queue was ordered by `gmail_application_links.id`, so
  the oldest unmatched items were re-selected on every run and a later item
  was never reached even after it became actionable. That is fixed by durable
  scheduling -- an additive `revisit_sequence` rotation stamp allocated from a
  monotonic counter in a new single-row `reconciliation_scheduler` table, plus
  a durable `next_queue` pointer -- so fairness survives separate requests,
  process restarts and multiple workers, and `limit=1` alternates between the
  queues instead of favouring one. A fourth independent review, of the exact
  commit `006e911`, returned **APPROVE**, and the Owner authorized the merge
  on that exact SHA. Post-merge evidence on `7ecd0b7`: Python 3.13 tests,
  Python 3.14 tests, the publication gate (`scripts/publication_gate.py`, run
  inside both test jobs), SCA, Security Verification, CodeQL python,
  CodeQL javascript-typescript, CodeQL actions and Scorecard analysis all
  **success**
  ([run 35492914924](https://github.com/SoSwag5/ASTRA/actions/runs/35492914924));
  `dependency-review` is gated on `pull_request` and therefore reports
  `skipped` for a push to `master`, having passed on the approved PR head.
  Verification was offline and deterministic throughout: **no live mailbox
  validation** was performed, no live Gmail or private user data was used, and
  **real-world reconciliation accuracy remains unmeasured**. **R-18 remains
  OPEN** and **no residual-risk acceptance or release approval is implied**.
  At that closeout #46.2, #47 and #48 had **not started** (for later #46.2
  progress see *Exact next action* below), and no tag, release or publication
  work was performed.
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
| [#44](https://github.com/SoSwag5/ASTRA/issues/44) | Closed; merged via [PR #66](https://github.com/SoSwag5/ASTRA/pull/66), squash `c53eb4e1f26f90087b1ca6522db9bbf71e63a463`. | Live OAuth PASS, self-verified; the Owner waived independent review for #44. R-16 remains OPEN. See [Gmail OAuth](../architecture/GMAIL_OAUTH.md). |
| [#45](https://github.com/SoSwag5/ASTRA/issues/45) | **Closed.** Bounded read-only Gmail sync and confirmation evidence merged via [PR #67](https://github.com/SoSwag5/ASTRA/pull/67) (squash commit `11a69b0921d55072aa4f552a0319320ab73d6741`); post-merge CI and Scorecard green. | PRIMARY bounded read-only sync and deterministic initial-confirmation evidence only; `gmail_confirmations` is additive and leaves the pinned `models.py` untouched. **No live mailbox validation and no independent review**; R-16 and R-17 remain OPEN. See [Gmail sync](../architecture/GMAIL_SYNC.md). |
| [#46](https://github.com/SoSwag5/ASTRA/issues/46) | **Closed.** Merged via [PR #68](https://github.com/SoSwag5/ASTRA/pull/68); independently approved head `006e9111a196e940d8d11163548ef642c2007e5c` (tree `ff4c42808a36d031721085c587db51073e591a10`), squash commit `7ecd0b78277f67db0a44db176db467bcfb1f5a17` carrying that same tree. Post-merge Python 3.13/3.14 tests, publication gate, SCA, Security Verification, CodeQL python/javascript-typescript/actions and Scorecard are green ([run 35492914924](https://github.com/SoSwag5/ASTRA/actions/runs/35492914924)); `dependency-review` runs only on `pull_request` and passed on the approved PR head. | Additive `backend/application_state.py` (canonical states, the single permitted-transition table, the append-only `application_state_transitions` history and the `application_states` projection), `backend/application_reconciliation.py` (deterministic multi-field Gmail matching, `gmail_application_links`) and `backend/application_state_api.py` (bounded reads plus the user's confirm/reject). `application_states.current_state` is authoritative; `Job.status`, `Application.status` and `Application.tracking['stage']` remain compatibility projections. Campaign tracking, the job status action, the browser-confirmation path and Gmail reconciliation all funnel through one state service; existing and tracker-imported applications are bootstrapped truthfully and lazily on first contact. **No evaluation-provenance-pinned file was modified** (`backend/models.py`, `backend/policy.py`, `backend/services.py` hashes still match `docs/evaluation/fit_evaluation_provenance_v1.json`). Review remediation on the same branch fixed four independently reproduced defects: a contradictory job-specific requisition URL now blocks automatic linking instead of merely withholding agreement; the first manual status change on a previously untracked job is recorded as a `USER_ACTION` with manual authority rather than `LEGACY_MIGRATION`; HIGH/MEDIUM evidence that cannot be linked stays a resolvable Needs Review item and unresolved unattached items are revisited; and `ensure_all_states()` read-repair makes summaries and histories complete and order-independent, with a nonexistent application still distinguishable from an uninitialized one. A second remediation round fixed a bounded-processing defect in `reconcile_pending()`: the requested limit now bounds the whole run rather than each queue independently. A third round replaced the reconciliation scheduler with durable state -- a `revisit_sequence` rotation stamp on each link and a persisted `next_queue` pointer, both additive -- so every eligible unresolved item is attempted within `ceil(U / r)` runs and queue alternation survives restarts. A fourth independent review, of the exact commit `006e911`, returned **APPROVE**. Verification was offline and deterministic: **no live mailbox validation**, no live Gmail or private user data, and **real-world reconciliation accuracy remains unmeasured**. **R-18 remains OPEN**, and **no residual-risk acceptance or release approval is implied**. See [Application state](../architecture/APPLICATION_STATE.md); hosted results belong to the exact PR head and to the merge commit. |
| [#43](https://github.com/SoSwag5/ASTRA/issues/43) | **Closed.** Discovery funnel telemetry merged to `master` via [PR #65](https://github.com/SoSwag5/ASTRA/pull/65) (squash commit `ad39e54925fe17286ae03e5866d4ea1cc1259094`); post-merge CI and Scorecard green. | New `backend/discovery_telemetry.py` owns one versioned contract (`discovery-telemetry-v1`) persisted in the existing `AutomationRun.report` JSON — **no schema change or migration**. Monotonic funnel `FETCHED → STRUCTURALLY_VALID → CANONICAL_UNIQUE → LOCATION_COMPATIBLE → ELIGIBILITY_NOT_INCOMPATIBLE → RELEVANT → NEW`, derived from explicit stage membership and checked by an invariant validator, never clamped. `DISPLAYED`/`SAVED`/`APPLIED` are reported separately as engagement outcomes; `DISPLAYED` is explicitly `UNAVAILABLE` because ASTRA records no display event. Provider failure, truthful zero, partial completion and skipped sources stay distinguishable. Retention is exactly 90 days. Read-only local API at `/api/search/telemetry*`. #41 decision behaviour, #40 identity/dedupe, provider transport and #42 evidence are unchanged; `backend/recall.py` was deliberately left untouched because it is a provenance-pinned #42 input. See [`docs/architecture/DISCOVERY_TELEMETRY.md`](../architecture/DISCOVERY_TELEMETRY.md). |
| [#47](https://github.com/SoSwag5/ASTRA/issues/47) | **Open.** Draft [PR #78](https://github.com/SoSwag5/ASTRA/pull/78) at `4a13fc8`, awaiting independent review; follow-ups A/B/C local and unpushed. | Required by OD-013 for v1.1.0. Not assessed by #48. |
| [#48](https://github.com/SoSwag5/ASTRA/issues/48) | **Open.** Local assurance corrections and current verification on `governance/48-v1.1-assurance` (tests and documentation only), not pushed. | 36 requirements traced to tests, plus eight gap tests for controls the ADRs required but nothing tested. ASVS OAuth rows corrected, SSDF and threat-delta as-built reconciliation, pre-candidate [evidence pack](../release/V1_1_0_RELEASE_EVIDENCE_PACK.md). Technical verdict BLOCKED; fresh Python SCA found six pypdf advisories, ASVS 15.2.1 is PARTIAL, and OD-019/OD-020 are pending. |

## Git and collaboration snapshot

- Canonical remote: `https://github.com/SoSwag5/ASTRA.git`.
- Protected default branch: `master`.
- `master` head after the #46 closeout:
  `7ecd0b78277f67db0a44db176db467bcfb1f5a17`
  (tree `ff4c42808a36d031721085c587db51073e591a10`), the #46 squash merge of
  PR #68. Its #46 integration base was
  `11a69b0921d55072aa4f552a0319320ab73d6741`
  (tree `e0b8648f8dab8172c59de3c8df84d631263eb1d8`), the #45 squash merge.
- `master` head when this snapshot was refreshed:
  `22642e88f516f827c1dc4250bc72eb259306fafd`, the PR #77 squash merge of
  2026-09-29 (#46.2-C v3 closeout documentation). Its single parent is
  `902c80b30db6d4a73f95a0c56b567a0683a2ad09` (the PR #75 merge). Its tree,
  `1f699af8aa1a33409b78a74159110057b9b3d67e`, equals the merged PR head's,
  `bcff33f2fef27c70392d5e21844b40de10e9eb88`. GitHub records no review
  decision on PR #77. Post-merge CI
  ([run 36590869577](https://github.com/SoSwag5/ASTRA/actions/runs/36590869577))
  and Scorecard ([run 36590869180](https://github.com/SoSwag5/ASTRA/actions/runs/36590869180))
  passed. The #46 entries in this section are historical.
- At the #46 closeout no implementation branch was active. `feature/46-application-reconciliation-state-model`
  is merged; #45 was merged without independent review, while #46's final head
  `006e9111a196e940d8d11163548ef642c2007e5c` was independently reviewed and
  approved before merge.
- The following governance worktree details are historical context, not the
  active #46 implementation location.
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

#46 is **COMPLETE, MERGED and CLOSED**. Its six independently reproduced
defects across three review rounds were fixed with regression coverage, a
fourth independent review of the exact commit
`006e9111a196e940d8d11163548ef642c2007e5c` returned **APPROVE**, and the
Owner authorized merging [PR #68](https://github.com/SoSwag5/ASTRA/pull/68) on
that exact SHA. The squash merge is
`7ecd0b78277f67db0a44db176db467bcfb1f5a17`, carrying the approved tree
`ff4c42808a36d031721085c587db51073e591a10` unchanged. Post-merge Python
3.13/3.14 tests, the publication gate, SCA, Security Verification, CodeQL
python/javascript-typescript/actions and Scorecard all passed on that commit;
`dependency-review` runs only on `pull_request` and passed on the approved PR
head. Issue #46 is closed with that evidence recorded.

There has been **no live mailbox validation** of #46, no live Gmail or private
user data was used, and **real-world reconciliation accuracy remains
unmeasured** — no claim is made about real-world Gmail parsing or
reconciliation accuracy. **R-18 remains OPEN.** **No residual-risk acceptance,
certification or release approval is implied.**

Since this #46 closeout, the Owner authorized bounded #46.2 work. **#46.2-A
manual scan control is merged** through [PR #73](https://github.com/SoSwag5/ASTRA/pull/73)
at `2d40c8067996f9f919bda63b716507d371bc8daa`, after independent review of
the final head `37e2ee360631e2d22335a35320da1a593ce12e6c`. This is source
integration evidence; the separate Owner-data scan is recorded below.

**#46.2-B/C integration is merged.**
[PR #71](https://github.com/SoSwag5/ASTRA/pull/71) merged into `master` on
2026-09-27 as merge commit `a4983d455d2dde5a20c1ea7303e3fae2d8dc145d`. Its
parents are `2d40c8067996f9f919bda63b716507d371bc8daa` (A) and the PR head
`810143a43100e3dda72b550c75b9e57de99df33a`.

- *Review.* The Owner's handoff records `810143a` as the independently reviewed
  head. GitHub records no review on the PR, and the review notes are not in
  Git.
- *Post-merge CI on `a4983d4`* ([run 36322023733](https://github.com/SoSwag5/ASTRA/actions/runs/36322023733))
  passed. That covers Python 3.13 and 3.14 tests (each runs the publication
  gate), Security Verification, SCA, and CodeQL for python,
  javascript-typescript and actions. Scorecard also passed.
  `dependency-review` runs only on pull requests and reports `skipped` on push.
- *What changed in production.*
  - The Discovery responsiveness fix: run summaries, the Today lookup, page
    polling and the scan-time estimate.
  - `scripts/verify_sources.py` is retired to a no-op, so nothing fetches
    outside Start Scan.
  - No source was added, enabled or reconfigured. No SmartRecruiters decision
    was made.
- *What the merge does not establish.* It does not validate any semantic
  quality, it does not cover the 55 researched employers, and it does not show
  that any posting is open.

**#46.2-B source closeout (v6) and the E v3 decision review are merged.**
[PR #74](https://github.com/SoSwag5/ASTRA/pull/74) merged into `master` on
2026-09-27 as `89d2f907caa49487d585f4268339cd4092c1a267`. Its parents are
`a4983d4` and the head `9906c782f4c6b3e0bca28ec88551c7212b6d1fc0` of
`fix/46.2-b-closeout-e-review`, and its tree is identical to that head's.

- *Review.* The PR record reports an independent read-only review with
  **APPROVE** at `9906c78`. GitHub records no review object.
- *Post-merge CI* ([run 36327990794](https://github.com/SoSwag5/ASTRA/actions/runs/36327990794))
  and Scorecard ([run 36327990625](https://github.com/SoSwag5/ASTRA/actions/runs/36327990625))
  passed on `89d2f90`. `dependency-review` was skipped on push, as designed.

**#46.2-B v7 closeout is merged.**
[PR #75](https://github.com/SoSwag5/ASTRA/pull/75) merged into `master` on
2026-09-28 as the squash commit `902c80b30db6d4a73f95a0c56b567a0683a2ad09`,
from head `58bc50f2c8b2e9da4854f9eaa8831e60f5bde827`. The squash commit's
tree is identical to that head's.

- *Review.* GitHub records no review decision on PR #75. This snapshot does not
  restate a review outcome.
- *Post-merge CI* ([run 36459740757](https://github.com/SoSwag5/ASTRA/actions/runs/36459740757))
  and Scorecard ([run 36459740472](https://github.com/SoSwag5/ASTRA/actions/runs/36459740472))
  passed on `902c80b`. `dependency-review` was skipped on push, as designed.
- *Source map.* It stands at 0 / 49 / 6.

Three kinds of #46.2-B/C evidence stay separate. None stands in for another.

1. **Source coverage (B research).**
   - PR #71 carried source map v4 and v5: 0 supported feed, 48 `MANUAL_LINK`
     and 7 unresolved, out of 55 employers.
   - PR #74 carried v6: 0 / 50 / 5. PureHealth and ADPHC became
     `MANUAL_LINK`.
   - The **v7 closeout** from `fix/46.2-b-final-closeout` is merged
     ([PR #75](https://github.com/SoSwag5/ASTRA/pull/75), `902c80b`). It
     rechecked the five v6-unresolved employers and PureHealth once from the
     Owner's machine on 2026-09-27. The committed tool `scripts/source_route_check.py`
     did the checks with enforced, logged pacing: every same-host interval was
     at least 2.000 s. The v6 log still does not establish its own pacing.
     **Result: 0 / 49 / 6.**
   - The published v7 run log is a marked, redacted derivative. Two opaque
     parameters in DoH's published Careers link are replaced by their
     SHA-256, and the unchanged raw log is kept privately by the Owner. The
     values were already published in PR #75's history, and redaction does
     not remove them from it.
   - PureHealth is `UNRESOLVED` again. Its robots.txt still answers with a
     Cloudflare 403. v4 treated that as "do not fetch this host". v5 and v6
     read it as "unavailable"; v6 stated that 4xx rule but not that it
     reversed v4. That is how the v6 homepage read was made. v7 restores the
     v4 rule.
   - Six are unresolved, each with an exact Owner-browser action:
     - Zayed University: a certificate-verifying TLS handshake to
       `www.zu.ac.ae` was attempted but reset before verification completed,
       and the robots.txt requests to `www.zu.ac.ae` and
       `careers.zu.ac.ae` ended in a connection reset.
     - DoH: its careers link goes to a host whose certificate expired on
       2025-09-09.
     - Emirates Islamic: Cloudflare bot-protection page at robots.txt.
     - HCT: robots.txt redirect loop.
     - du: robots.txt disallows all paths.
     - PureHealth: Cloudflare bot-protection page (403) at robots.txt.
   - No researched employer has a *verified* Greenhouse, Lever or Ashby
     board, so no controlled scan was prepared and run 107 was not repeated.
     A `MANUAL_LINK` is never coverage or an open posting. See the
     [source map](../planning/AI_NATIVE_DISCOVERY_46_2B_SOURCE_MAP.md).
2. **Semantic quality (C). NOT VALIDATED; the v3 blind round FAILED.**
   - The role-understanding candidate is offline and shadow-only.
     Production discovery and ranking do not import it, and no AI model is
     connected. No candidate is adopted and production is unchanged.
   - Historical v2 evidence, preserved: on 15 assisted, in-sample development
     items the v2 candidate agreed with 14 Owner tiers. That shows no
     improvement on unseen jobs.
   - The v3 blind round ran once and failed criterion C3. On 11 scored
     postings (2 Owner-shown, 9 Owner-hidden) the candidate agreed with 5
     Owner tiers against the current path's 1. The pre-registered bar was 7
     of 11. C0, C1, C2, C4 and C5 passed. The missed-warning check was
     untested, because no posting was labelled as targeting UAE nationals. See
     the [aggregate outcome](../evaluation/DISCOVERY_46_2C_V3_BLIND_OUTCOME.md)
     and the [C status](../evaluation/DISCOVERY_46_2C_PUBLIC_STATUS.md).
   - The 12-job holdout is **revealed and consumed**. It must never be reused
     as blind or used to tune the candidate.
   - [PR #76](https://github.com/SoSwag5/ASTRA/pull/76) is **CLOSED and NOT
     MERGED** (closed 2026-09-29, no merge commit), and its candidate is
     rejected after the blind FAIL. No Owner decision remains about its fate.
     It was renamed "#46.2-C v3 blind evaluation failed C3 (closed; candidate
     not merged)". Its earlier "awaiting Owner labels" title and description are
     historical only. Its pushed head
     `66c33268e4012ca2d4a192aadc663a0f1e2f23ff` is the sealed, pre-result
     state.
   - The full fixed comparison output is retained privately and is not
     published. The public summary is a redacted derivative, so individual
     rows cannot be reproduced from this repository. The local branch
     `research/46.2-c-blind-eval` (head `c0b71c3bb650f3131b493ad8581eb762bf903630`)
     holds the private output and is preserved as audit evidence. It must not
     be pushed or merged, and neither may any commit descended from
     `5e9b47342f0ccd3aa0fb26e650bd9b5809455cc8`.
   - A v4 plan with a fresh evaluation set is proposed and not started.
3. **Controlled scan (run 107, 2026-09-27).**
   - The scan fetched nine configured Ashby, Lever and Greenhouse sources
     through the merged A build's in-app preview and confirmation. The Owner
     delegated the in-app controls for this run.
   - 924 postings checked, 72 UAE-located, 79 new; no source error.
   - One board's detail enrichment was partial.
   - The run took 439 s against a preview estimate of "under a minute".
   - It proves only that those nine feeds could be fetched through the manual
     confirmation path on that date. It proves nothing about #41 accuracy,
     posting availability, or the 55-employer map. Source names stay
     private. See the
     [controlled-scan record](../planning/AI_NATIVE_DISCOVERY_46_2B_CONTROLLED_SCAN.md).

**Discovery responsiveness fix (merged with PR #71).**

- *Cause.* Polled endpoints decoded every run's per-posting decision audit on
  each poll, and page refreshes could stack.
- *Fix.* Summaries are cached per run version, the Today lookup gets
  `LIMIT 1`, the page runs one refresh at a time, and the job list is refetched
  only on change. The preview estimate now uses posting volume and shows the
  slowest recent pace.
- *Evidence.* It is measured on a fictional replay only. It did not measure
  scan-worker throughput or prove the cause of run 107's 439 s.
- *A contracts preserved:* preview, single-use confirmation, scope binding,
  Stop and restart handling. See the
  [responsiveness note](../evaluation/DISCOVERY_46_2B_RESPONSIVENESS.md).

**#46.2-E:**

- **E v2** (local `research/46.2-e-hybrid-comparison-v2` at `94fd479`) was
  independently reviewed as **REPORT ACCURATE**. Its hybrid showed **no
  measured improvement** and stays unadopted.
- **E v3** (local `research/46.2-e-v3-plan` at `931a108`) is a pre-registered
  plan that tests one mechanism, alias morphology in current search. Nothing
  was run.
- **A decision review** of that plan was merged with PR #74:
  [E v3 decision review](../planning/DISCOVERY_46_2E_V3_DECISION_REVIEW.md).
  It recommends keeping the one mechanism but amending the plan before any
  measurement set exists. The candidate must reach both title matchers, and
  the miss metric must not depend on the top-20 cutoff. The measurement set
  needs an author outside this repository and its sessions. The review awaits
  an Owner decision; no set was created and no search design was adopted.

**#46.2-F** remains **NOT VALIDATED** pending a genuinely independent fictional
challenge. G and H are not started.

**#46.2-C v3 closeout is merged** as PR #77 (`22642e8`, 2026-09-29); see
the git snapshot above. The C outcome is unchanged: NOT VALIDATED.

**#47 (progress dashboard) is not merged.** It is draft
[PR #78](https://github.com/SoSwag5/ASTRA/pull/78) at head
`4a13fc83bee7bd594b61f2ad1b830594a523f742`, awaiting independent review. Its
follow-ups A, B and C are local, stacked and unpushed. The latest local
visual/motion revision is `772fe7e87586720d9db6bed06cb1a12d3af14649`, on
`feature/47-visual-motion`, with scoped frontend/browser review. It is also
unmerged; PR #78's older checks do not validate that revision.

**#48 has local corrections and current verification, local and unpushed; release remains BLOCKED.** It is
on `governance/48-v1.1-assurance` in the worktree
`astra-48-release-assurance`, based on `22642e8`. It changes tests and
documentation only; no product code changed. See the session handoff
below and the
[v1.1.0 pre-candidate evidence pack](../release/V1_1_0_RELEASE_EVIDENCE_PACK.md).
The technical verdict is **BLOCKED**: there is no frozen candidate, the
second-account scope is unresolved (OD-020), and the R-16/17/18 decisions
are pending (OD-019). The fresh Python audit also finds six unresolved pypdf
advisories, making ASVS 15.2.1 PARTIAL. Starting #48 before #47 merged departs from the
Owner's 2026-09-30 sequencing. This pass was requested in the 2026-10-01
session, and anything that depends on #47 is marked BLOCKED, not assessed.

**Next actions:**

- Codex owns the #48 local corrections, explicitly requested
  by the Owner on 2026-10-02 after Claude stopped at its weekly limit.
  The separate-clone review of `fbbafe4` found a guard overclaim and unfinished
  release drafts. Corrections and source-bound results are recorded in the
  latest session handoff. Do not describe Codex's own corrections as
  independently approved.
- Independent re-review of Codex's corrected `governance/48-v1.1-assurance`
  exact commit before any push, pull request or merge. Codex's own changes
  cannot be independently approved by their implementer.
- Assign and complete a separate pypdf dependency-remediation change for
  [SF-2026-48-01 through -06](../security/V1_1_PYPDF_SCA_FINDINGS.md). The fresh
  strict Python scan fails; ASVS 15.2.1 is PARTIAL. Do not carry forward older
  clean-SCA claims or waive this failure.

- Independent Codex review of the #47 draft pull request at its exact head
  SHA (see the #47 sections below). Merge waits for that review and the Owner.
- Independent review of the #46.2-C v3 closeout documentation at its exact
  final SHA, before any push, pull request or merge. Nothing from it has been
  pushed.
- Never push or merge `research/46.2-c-blind-eval` from the local checkout, or
  any commit descended from `5e9b473`. Do not use a push that includes all
  local branches. Keep that branch and its worktree as private audit evidence.
- Owner decisions:
  - decide whether to commission the C v4 plan and fresh evaluation set, and
    name a second labeller (see the
    [aggregate outcome](../evaluation/DISCOVERY_46_2C_V3_BLIND_OUTCOME.md));
  - do the Owner-browser checks for the six unresolved employers (the source
    map gives each exact action);
  - decide whether HCT's robots redirect loop may be read as RFC 9309
    "unavailable";
  - decide whether a bot-protection 403 at robots.txt may be read as
    "unavailable" (PureHealth) and whether an employer-published third-party
    jobs-search link counts as a `MANUAL_LINK` route;
  - approve, amend or reject the E v3 amendments;
  - name the independent measurement author and second labeller;
  - OD-019: decide R-16, R-17 and R-18 for v1.1.0 (evidence pack section 8
    recommends independent review of the #44 OAuth layer and the #45 parser,
    plus a bounded live validation of the primary mailbox, first);
  - OD-020: resolve the two-account scope of v1.1.0 (OD-013 against
    OD-012);
  - approve or amend the #48 threat-model as-built reconciliation and the
    ASVS/SSDF delta after independent review.
- Keep #47, #48 and v1.2 work separate. After #47 merges, re-run #48 against
  the integrated state (route-guard test, threat-delta check of any new
  Gmail-triggering entry point) before freezing a candidate.
- Do not tag, publish a release, or modify v1.0.0.
- Preserve the parked `hardening/l2-r13-r14` branch and all concurrent
  worktrees.

## Session handoff: #48 v1.1 release assurance (first pass)

## #47 Progress/dashboard redesign — draft PR, awaiting independent review

Implementation owner: Claude Code, on `feature/47-progress-dashboard` (fresh
worktree `astra-47-progress`) from `master`
`22642e88f516f827c1dc4250bc72eb259306fafd`. Codex performs independent
assurance; nothing is approved, merged or released by this work.

- Plan and metric/source contract:
  [Progress dashboard](../architecture/PROGRESS_DASHBOARD.md), written before
  any #47 code (commit `aa38a10`).
- Read-only projection `backend/progress.py` (`/api/progress`,
  `/api/progress/needs-review`, `/api/progress/applications`); no schema, state,
  matching or transition change; no evaluation-provenance-pinned file touched.
- Progress, Today and Applications redesigned on verified events; the
  unverified "quality applications" meter and the unreachable legacy
  `Dashboard` block are removed from the UI.
- Verification was offline with fictional records only. No live mailbox,
  job or application data was used; real-world accuracy remains unmeasured.
  R-16, R-17 and R-18 remain OPEN. No residual-risk acceptance or release
  approval is implied.

## Session handoff: #47 Progress/dashboard redesign

- **Session date/time and timezone:** 2026-09-30, Asia/Dubai (afternoon).
- **Implementation owner:** Claude Code. Codex reviews independently; the Owner
  controls merge and publication.
- **Branch and worktree:** `feature/47-progress-dashboard`, fresh worktree
  `astra-47-progress`.
- **Starting SHA / ending SHA:** `22642e88f516f827c1dc4250bc72eb259306fafd`
  (equal to `origin/master` when checked) / the commit containing this record,
  reported in the pull request.
- **Task and release classification:** `feature/` change within the v1.1
  milestone (Phase C); minor-release depth when v1.1 is assured under #48. No
  version, tag or release change.
- **Work completed:** see the section above and the pull request.
- **Files changed:** `backend/progress.py`, `backend/main.py` (router mount),
  `tests/test_progress.py`, `frontend/src/{Progress.tsx,progressModel.ts,
  progress.css,tokens.css,Campaign.tsx,campaign.css,main.tsx,readiness.css}`,
  `frontend/check-progress.cjs`, `frontend/package.json` (test script only),
  `docs/architecture/PROGRESS_DASHBOARD.md`,
  `docs/security/ENDPOINT_INVENTORY.md`, `CHANGELOG.md`, this file.
- **Tests executed and exact results** (Python 3.13.2, main checkout's `.venv`;
  fictional isolated storage only):
  - `tests/test_progress.py`: 24 passed.
  - `tests/test_progress.py`, `test_application_state.py`,
    `test_discovery_telemetry.py`, `test_campaign.py`, `test_api.py`: 348 passed.
  - Full suite on the tree of `a6639d2`: **2099 passed, 1 skipped, 1
    deselected, 0 failed** (7 min 22 s). The skip is the existing
    `test_job_deduplication.py` MN15 case ("covered by
    test_three_record_transitive_bridge_never_collapses"). The deselected test
    is the repository-wide gate test, reported under security checks. The later
    commits change only `frontend/src/Progress.tsx` and this file.
  - Frontend on `5d4bee1`: `tsc -b` clean; `npm run build` succeeded;
    `npm test` — all 7 check scripts passed, including 40 new Progress checks.
  - Manual browser QA against an isolated fictional workspace: Progress, Today
    and Applications at 1280/768/390/320 px in both themes and at 640 px (200%
    zoom equivalent) — no page-level horizontal overflow; keyboard-only
    confirm/reject, focus restoration, live-region text, an "already resolved
    elsewhere" item, a server error and reduced motion; an empty workspace.
    Screenshots contain fictional data only and are kept outside Git.
- **Security checks executed and exact results** (at `5d4bee1`):
  - Repository-wide `scripts/publication_gate.py`: **BLOCKED**, 1,574 objects,
    2 findings — both `private_machine_path` in historical versions of
    `docs/planning/AI_NATIVE_DISCOVERY_46_2_BENCHMARK.md` carried only by
    preserved local branches (commits `a5c25aa`/`7b4dd07`, neither an ancestor
    of this branch). Unchanged, and not weakened or suppressed.
  - Exactly what a push of this branch publishes (`rev-list --objects` beyond
    `origin`, scanned with the gate's own `scan()`, plus commit metadata):
    20 blobs, 0 findings.
  - The gate in a single-branch clone of this branch: **PASS**, 1,099 objects,
    0 findings. In that clone, `tests/security/test_publication_scope.py` and
    `tests/security/test_assurance_gate.py`: 56 passed.
  - Changed files grepped for machine paths and personal email addresses: none.
- **Checks not run and why:** hosted CI, CodeQL and dependency review (they run
  on the pull request's head); Python 3.14 locally (hosted CI covers it);
  SCA/`npm audit` (no dependency or lockfile change); live Gmail or any real
  data (out of scope by design); a browser-level automated UI test (the
  repository has no such framework).
- **Security findings opened/changed/closed:** none.
- **ADRs, threat deltas, risk records, and framework deltas:** none required —
  no trust-boundary, persistence, schema or privacy-boundary change; the new
  local GET routes are recorded in the endpoint inventory and expose a subset of
  fields the #46 review route already returns. Rationale in §8 of the contract.
- **Owner decisions still required:** none to proceed with review. Optional
  follow-ups for the Owner: whether to add an in-app control for Gmail sync and
  reconciliation (out of #47's scope), and whether to remove the now-unused
  Recharts dependency in a separate dependency change.
- **Commit(s) and pull request:** `aa38a10` (plan and contract), `8909f20`
  (projection and tests), `e19f0dd` (frontend), `a6639d2` (bounds and docs),
  `5d4bee1` (queue refresh), then this record. A draft pull request targets
  `master`; its number and exact head are recorded on the pull request.
- **Known conflicts, blockers, or branch drift:** the repository-wide
  publication gate stays BLOCKED by known historical findings on preserved
  local branches (unchanged, not weakened); the branch-scope results are
  recorded above. The main checkout's untracked `n.json` was preserved.
- **Exact next action:** independent Codex review of the pull request at its
  exact head SHA. Merge and any release wait for that review and the Owner.

## Session handoff: #46.2-C v3 closeout documentation

This is the historical Claude first pass. Its AI-guard claim was challenged
as R48-1 and corrected by the Owner-authorized Codex continuation below;
the old counts and verification claims remain tied to the old source.

The previous handoff (#46.2-C v3 closeout documentation) is complete: it
merged as PR #77 (`22642e8`). Its text remains in the history of this file
at that commit.

- **Session date/time and timezone:** 2026-10-01, Asia/Dubai.
- **Implementation owner:** Claude Code. Codex reviews independently; the
  Owner decides and publishes.
- **Branch and worktree:** `governance/48-v1.1-assurance`, in the worktree
  `astra-48-release-assurance`. Local only; nothing was pushed.
- **Starting SHA / ending SHA:** `22642e88f516f827c1dc4250bc72eb259306fafd`
  (equal to `origin/master` when checked) / the last commit on the branch,
  reported in the review handoff.
- **Task and release classification:** issue #48, Phase D release assurance
  for the v1.1.0 minor release. Tests and documentation only; no product
  code, dependency, schema or release artifact changed.
- **Work completed:**
  - A traceability inventory (`tests/security/v1_1_assurance_inventory.py`)
    maps 36 requirements from ADR-0007/0008/0009 and the threat-model delta
    to 229 named test functions. All ten abuse cases are covered. A
    `v1_1_assurance` marker (in `tests/conftest.py`) runs them as one suite.
  - `tests/security/test_v1_1_assurance.py` adds eight gap tests for
    controls the ADRs required but nothing tested directly:
    - an oversized provider response failing only its own source;
    - no raw-HTML sink in the frontend;
    - AI requests that offer no tools;
    - hostile model replies refused;
    - model advice leaving application state unchanged;
    - the mailbox path unable to load an AI module;
    - failed authentication capping at exactly MEDIUM;
    - every private route keeping the demo, access-key and cross-site
      guards.

    It also adds seven checks that keep the inventory and the ASVS records
    consistent. Every gap test passes against unchanged product code. The
    failures seen while writing them were mistakes in test setup, not
    product defects.
  - ASVS mapping: OAuth client rows 10.1.1, 10.1.2, 10.2.1 and 10.2.3 are
    now applicable and PASS. Until now every OAuth row said there was no
    OAuth client. 65 rows were re-reviewed in total; Level 1 is unchanged
    at 40 PASS / 30 N/A, and the gate's ASVS check reports no blockers.
  - SSDF: ten tasks gained v1.1 evidence, with no status change. Stale
    pre-release rows are recorded as a follow-up.
  - Threat-model delta: as-built reconciliation per abuse case, surfaces
    added since planning, and gaps found.
  - ADR-0007/0008/0009 and the ADR index: dated evidence updates.
  - R-16 and R-18: stale "not merged" facts corrected. All three risks stay
    OPEN.
  - OD-019 (R-16/17/18 decision) and OD-020 (two-account scope) are
    registered as Pending.
  - The pre-candidate [v1.1.0 evidence pack](../release/V1_1_0_RELEASE_EVIDENCE_PACK.md)
    is drafted, with the technical verdict BLOCKED.
  - One stale changelog statement corrected: #46 was independently
    reviewed.
- **Tests and checks executed** (local, Windows, Python 3.13.2, on the
  working tree that became the branch's commits):
  - Baseline on `22642e8` before any change: the 16 v1.1 security-relevant
    test files, 979 passed, 0 failed.
  - Consolidated suite `python -m pytest -m v1_1_assurance`: 517 passed,
    0 failed, 0 errors, 0 skipped.
  - `tests/security/test_v1_1_assurance.py` plus
    `tests/security/test_assurance_gate.py`: 59 passed.
  - Full suite, with `frontend/dist` built offline: 2102 passed,
    1 skipped, 0 failed, 1 deselected. The skip is the existing intentional
    `test_must_not_collapse[MN15_three_record_transitive_bridge]`; the
    deselection is the repository-wide publication-gate test below.
  - Relative links and anchors in the changed Markdown: 68 links, 0 broken.
  - A scan of the added lines for machine paths and email addresses found
    none.
  - Publication gate (`scripts/publication_gate.py`) on a single-branch
    clone of the final commit: result reported in the review handoff,
    because it must run after this record is committed.
- **Checks not run and why:**
  - Hosted CI: nothing was pushed.
  - Frontend `npm test`: no frontend file changed. The production build was
    run, only so that `tests/security/test_browser_termination.py` has
    `frontend/dist`.
  - The repository-wide publication gate (`test_real_repository_still_passes`,
    deselected): it scans every local ref and is BLOCKED by known historical
    findings on unpublished local branches.
  - Candidate build, SBOM, provenance, clean install and release gate: no
    v1.1.0 candidate exists.
- **Security findings opened/changed/closed:** none. The gaps were missing
  tests and stale documentation, not code defects.
- **ADRs, threat deltas, risk records, and framework deltas:**
  - ADR-0007/0008/0009 evidence sections and the ADR index;
  - the threat-delta as-built reconciliation;
  - R-16/R-17/R-18 facts (states unchanged: OPEN);
  - the ASVS and SSDF deltas, recorded in the evidence pack, section 9.
- **Owner decisions still required:**
  - OD-019 and OD-020;
  - approval of the threat-delta reconciliation and the ASVS/SSDF delta
    after independent review;
  - the items under *Next actions* above.
- **Commit(s) and pull request:** two local commits. The first holds the
  tests and the ASVS mapping they check; the second holds the remaining
  documentation. No pull request was created; publication waits for review
  and the Owner.
- **Known conflicts, blockers, or branch drift:**
  - #48 started before #47 merged, against the Owner's 2026-09-30
    sequencing; this pass was requested on 2026-10-01. The #47 stack also
    edits `CHANGELOG.md` and this file, so expect simple conflicts on
    rebase.
  - The pending Dependabot PRs (#1-#9, #69) are untouched.
  - Concurrent worktrees were not modified.
- **Exact next action:** independent Codex review of
  `governance/48-v1.1-assurance` at its exact commit. Publication, a pull
  request and any merge wait for that review and for the Owner.

## Session handoff: #48 Owner-authorized Codex continuation (2026-10-02)

- **Owner and authority:** Codex is the sole implementation owner for these
  local corrections after the Owner's "you proceed". Claude stopped at its
  usage limit. No second process owns this branch.
- **Branch / base:** `governance/48-v1.1-assurance`, in the existing
  `astra-48-release-assurance` worktree, starting at
  `fbbafe433ecbcf4b21f5c494dea285390cd30ad0`. Claude's commits are preserved.
- **Scope:** assurance test corrections, truthful threat/inventory claims,
  release-document drafts and evidence recording. Production code, dependencies,
  schemas, preview, live data, private labels and other worktrees are protected.
- **Current evidence:** 74 corrected assurance/gate tests pass; the original
  lazy-import bypass is rejected. At committed test source `90e48ea`, 532
  consolidated security cases pass, all six frontend test scripts and the
  production build pass, and npm audit finds zero advisories. Python SCA fails
  with six pypdf advisories; SF-2026-48-01 through -06 are TRIAGED and ASVS
  15.2.1 is PARTIAL. The full suite passes 2,118 cases, with one existing
  intentional skip and no failures/errors/deselection; the publication
  regression runs. Current mapping/gate checks also pass 74 cases. All 345
  official ASVS IDs/levels/text are preserved. Results and evidence digests
  are recorded in the
  [local validation record](../release/V1_1_0_LOCAL_ASSURANCE_VALIDATION.md).
- **Findings / framework delta:** SF-2026-48-01 through -06 opened and TRIAGED;
  none closed. ASVS 15.2.1 changes PASS to PARTIAL with fresh scan evidence,
  and JSON/CSV/summary agree (L1: 39 PASS, 30 N/A, 1 PARTIAL). SSDF/ADRs
  remain unchanged by this continuation; risk states stay OPEN.
- **Checks not run:** hosted CI and candidate-specific CodeQL/Dependency Review,
  complete candidate/package build, SBOM/attestations, exact-ZIP install/upgrade/
  rollback and hosted release gate, because no approved complete candidate
  exists. Live Gmail/OAuth/AI/scans and data migration were not performed.
- **Commits / files:** `90e48ea76620ff1d876fb2907bb194b4c219916d` corrects the
  two assurance test files, threat claims, changelog/release drafts and handoff;
  the later evidence-only commit records current results, ASVS assessment and
  six finding records. Exact ending SHA and post-commit publication results
  are in the Owner-local handoff. No new PR was created.
- **Owner decisions:** R-16/17/18, two-account scope, threat/framework approval,
  release approval and publication remain reserved. No acceptance is inferred
  from authorization to correct tests and documents.
- **Review:** the prior separate-clone review found R48-1 and R48-2. Verification
  of Codex's own correction is self-verification; independent re-review of the
  corrected exact commit remains pending.
- **Outcome / next action:** local corrections and current verification are
  recorded in the validation handoff. Release remains **BLOCKED**. Assign
  dependency remediation and independent re-review, resolve #47 integration,
  two-account scope and Owner risk decisions, then freeze and verify the complete
  candidate and package. No push, merge, tag or publish occurred.
