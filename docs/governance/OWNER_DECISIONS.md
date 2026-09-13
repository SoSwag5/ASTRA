# Owner decision register

Ayham is the only authority for product requirements, architecture direction,
residual-risk acceptance, release approval, and publication. Technical gate
success informs these decisions but does not replace them.

| ID | Date | Decision | State | Evidence / follow-up |
|---|---|---|---|---|
| OD-001 | 2026-09-13 | Accept R-15 for v1.0: ASTRA trusts the local OS-account/localhost boundary and does not provide application-user authorization. | Reaccepted for v1.0.0; dated review/expiry still required | `docs/security/RISK_REGISTER.md`; ADR-0002; issue #27. Retain the networked/hosted/multi-user/multi-tenant triggers. |
| OD-002 | 2026-09-13 | Approve reconstructed ADR-0001 and ADR-0003 through ADR-0006. | Completed | The Owner approved all five decisions for Governance v1 in PR #28. The ADRs are Accepted. |
| OD-003 | 2026-09-13 | Integrate Release Governance v1 with the frozen release, push it, and open a PR without merging. | Completed | Governance is rebased on `81ad2d3` and PR #28 was opened. OD-007 records the later merge authorization. |
| OD-004 | Pending | Approve or reject the live scheduled-task rename/migration. | Owner review required | Existing task remains unchanged; follow `docs/security/WINDOWS_INSTALLATION.md`. |
| OD-005 | 2026-09-13 | Approve and publish v1.0.0 from source `81ad2d3` and artifact `a5842744…b4399f` after the final gate. | Completed | Public release `v1.0.0`; full values and run links are in `docs/release/V1_0_0_RELEASE_RECORD.md`. Future releases require a new exact-SHA/digest approval. |
| OD-006 | 2026-09-13 | Treat v1.0.0 as immutable and start v1.1 only after Owner approval and Governance v1 merge. | Active direction | Do not rebuild, replace, retag, or rewrite v1.0.0. Current next milestone is v1.1; implementation is NOT STARTED. |
| OD-007 | 2026-09-13 | Merge PR #28 into `master` only if its updated required checks remain green. | Authorized with condition | Revalidate locally, push the approval record, require a green hosted result for the exact head, then merge and stop before v1.1 implementation. |
| OD-008 | 2026-09-13 | Set R-15's next formal review date to 2026-12-12, in addition to its existing event triggers. Do not add invented dated expirations to R-01, R-02, R-03, R-07, or R-08; those remain event-triggered historical accepted residuals, since Release Governance v1 does not require a dated expiry for them and no rationale supports an arbitrary date. | Completed | `docs/security/RISK_REGISTER.md` R-15; issue #27. Revisit if a future governance change requires dated review for other standing acceptances. |
| OD-009 | 2026-09-13 | Defer migration of the existing live Windows Scheduled Task to the Professional Distribution / Installer milestone (v1.3). Do not rename or migrate the live task now; it remains untouched. Future clean installs may use the productized `ASTRA Local Discovery` naming, which current policy already supports. | Active direction | `docs/SCHEDULED_TASK_MIGRATION.md`; R-09 in the risk register; tracked as milestone-entry work for v1.3, not immediate action. |
