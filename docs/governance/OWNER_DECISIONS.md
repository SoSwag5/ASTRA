# Owner decision register

Ayham is the only authority for product requirements, architecture direction,
residual-risk acceptance, release approval, and publication. Technical gate
success informs these decisions but does not replace them.

| ID | Date | Decision | State | Evidence / follow-up |
|---|---|---|---|---|
| OD-001 | 2026-09-13 | Accept R-15 for v1.0: ASTRA trusts the local OS-account/localhost boundary and does not provide application-user authorization. | Reaccepted for v1.0.0; dated review/expiry still required | `docs/security/RISK_REGISTER.md`; ADR-0002; issue #27. Retain the networked/hosted/multi-user/multi-tenant triggers. |
| OD-002 | Pending | Confirm or amend reconstructed ADR-0001 and ADR-0003 through ADR-0006. | Owner review required | Use `ADR_OWNER_REVIEW_PACKET.md`; all five ADRs remain Proposed until the Owner decides. |
| OD-003 | 2026-09-13 | Integrate Release Governance v1 with the frozen release, push it, and open a PR without merging. | Authorized and implemented | Governance is rebased on `81ad2d3`; merge remains a separate Owner decision after ADR review. |
| OD-004 | Pending | Approve or reject the live scheduled-task rename/migration. | Owner review required | Existing task remains unchanged; follow `docs/security/WINDOWS_INSTALLATION.md`. |
| OD-005 | 2026-09-13 | Approve and publish v1.0.0 from source `81ad2d3` and artifact `a5842744…b4399f` after the final gate. | Completed | Public release `v1.0.0`; full values and run links are in `docs/release/V1_0_0_RELEASE_RECORD.md`. Future releases require a new exact-SHA/digest approval. |
| OD-006 | 2026-09-13 | Treat v1.0.0 as immutable and start v1.1 only after Owner approval and Governance v1 merge. | Active direction | Do not rebuild, replace, retag, or rewrite v1.0.0. Current next milestone is v1.1; implementation is NOT STARTED. |
