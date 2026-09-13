# ASTRA project state

**Snapshot date:** 2026-09-13 (Asia/Dubai)
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

- Next milestone: **v1.1 — Operational Security & Resilience**.
- v1.1 implementation status: **NOT STARTED**. Planning, issue triage, or local
  exploratory changes do not start the governed milestone. It begins only after
  Owner approval and merge of Release Governance v1.
- The primary worktree is clean on `master` at the frozen release commit. This
  governance worktree did not modify it.

## Current residual risks and follow-up

- R-01, R-02, R-03, R-07, and R-08 remain historical accepted residuals under
  their existing triggers.
- R-15 remains the accepted v1.0 OS-account/localhost trust-boundary decision.
  Its missing dated review/expiry is tracked by issue #27.
- R-04 and R-05 are mitigated but remain subject to dependency and AI-change
  review.
- R-09's hosted installation path passed; live scheduled-task migration remains
  unverified and requires separate Owner approval.
- Applicable ASVS L1 is closed. R-12 retains open L2 hardening work.
- R-13 and R-14 remain open L2 hardening/resilience risks for future governed
  planning.
- R-06, R-10, and R-11 have release evidence supporting closure, but their
  source-controlled wording has post-release documentation debt in issues
  #24-#26. The frozen v1.0.0 files are not rewritten.

## Open post-release issues

| Issue | Required follow-up | Release impact |
|---|---|---|
| [#24](https://github.com/SoSwag5/ASTRA/issues/24) | Set R-06 to CLOSED using the final publication evidence. | Documentation correction after v1.0; do not rebuild v1.0.0. |
| [#25](https://github.com/SoSwag5/ASTRA/issues/25) | Correct the released-commit Scorecard reference from 7.1 to 6.7. | Documentation correction after v1.0; no security regression implied. |
| [#26](https://github.com/SoSwag5/ASTRA/issues/26) | Point R-11 to the released candidate and final gate/release references. | Documentation correction after v1.0; avoid self-referential artifact digests. |
| [#27](https://github.com/SoSwag5/ASTRA/issues/27) | Add a dated review/expiry to R-15 and decide whether other standing acceptances need the same treatment. | Owner governance decision; v1.0 remains immutable. |

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
- This branch is pushed and PR #28 is open. It must not be merged until the Owner
  reviews the proposed ADRs and explicitly authorizes the merge.

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
- `docs/security/RISK_REGISTER.md` is the current source risk register, subject to
  post-release corrections #24-#27.

## Exact next action

The Owner reviews PR #28 and chooses APPROVE or REVISE for ADR-0001 and ADR-0003
through ADR-0006. Apply requested revisions, rerun governance validation, and
merge only after explicit Owner authorization. Start v1.1 planning and
implementation only after that merge.
