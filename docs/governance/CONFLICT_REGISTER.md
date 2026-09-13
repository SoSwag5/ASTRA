# Governance conflict register

This register records drift between the original Governance v1 snapshot and the
frozen v1.0.0 state. Resolved entries remain visible as history.

| ID | Drift or conflict | Final integration resolution | State / follow-up |
|---|---|---|---|
| C-001 | The initiating brief described no remote; v1.0.0 is now public at `SoSwag5/ASTRA`. | Rebased Governance v1 onto released `master` and recorded the public release as authoritative. | Resolved. |
| C-002 | `RELEASE_SECURITY_ASSURANCE_REPORT.md` is a pre-remote assessment that ends BLOCKED. | Preserved it as a dated historical record. Added `V1_0_0_RELEASE_RECORD.md` for the final gate and publication evidence. | Resolved without rewriting history. |
| C-003 | `SLSA_V1.2_ASSESSMENT.md` names an earlier attested candidate rather than the released artifact. | The immutable release record points to the final release and gate. Issue #26 tracks the source-controlled risk-register correction; a future evidence update may supersede the earlier assessment. | Open documentation follow-up; v1.0 unchanged. |
| C-004 | Security documents exist under both root `security/` and `docs/security/`. | `docs/security/` remains the governance source unless a file identifies a generated source elsewhere. | Separate consolidation review; no deletion in this PR. |
| C-005 | Generic branch examples used `main`, while ASTRA uses `master`. | Governance names `master` as the protected default branch. | Resolved. |
| C-006 | Governance v1 was based on `cf9a6bc`; v1.0.0 froze at `81ad2d3`. | Preserved `f2307be` on a local backup branch and cleanly rebased the governance commit onto `81ad2d3`; no release files conflicted. | Resolved. |
| C-007 | R-15 has an event trigger but no dated review/expiry, while Governance v1 requires time-bounded reapproval. | Preserved the accepted v1.0 decision and linked issue #27. No expiry was invented. | Owner decision open. |
| C-008 | CodeQL, release, and review-candidate workflows were not registered in the original snapshot. | The workflows are now registered and active; the released artifact's hosted provenance and SBOM attestations were verified. | Resolved for v1.0; reverify every candidate. |
| C-009 | R-06, R-10, and R-11 text at the frozen release commit does not reflect the final release evidence. | Kept the immutable tag untouched and linked issues #24-#26 from durable project state. | Open post-release documentation debt. |
| C-010 | A local `hardening/l2-r13-r14` worktree has uncommitted changes, while governed v1.1 work is explicitly not started. | Left that worktree untouched and recorded that local exploration does not establish milestone start. | Owner must decide its disposition after Governance v1 merges. |
