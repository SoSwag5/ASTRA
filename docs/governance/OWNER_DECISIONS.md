# Owner decision register

Ayham is the only authority for product requirements, architecture direction,
residual-risk acceptance, release approval, and publication. Technical gate
success informs these decisions but does not replace them.

| ID | Date | Decision | State | Evidence / follow-up |
|---|---|---|---|---|
| OD-001 | 2026-09-12 | Accept R-15 for v1.0: ASTRA trusts the local OS-account/localhost boundary and does not provide application-user authorization. | Recorded in existing repository history; expiry reconciliation required | `docs/security/RISK_REGISTER.md`; ADR-0002. The record has no expiry while the Secure SDLC sets a 90-day maximum. Owner should add an expiry/reapproval date and retain the networked/hosted/multi-user/multi-tenant triggers. |
| OD-002 | Pending | Confirm or amend reconstructed ADR-0001 and ADR-0003 through ADR-0006. | Owner review required | Review after v1.0 freeze; no historical approval is inferred from implementation alone. |
| OD-003 | Pending | Choose when to integrate Release Governance v1. | Owner review required | Recommended: review and merge after the v1.0 source/evidence freeze so governance work does not disturb the candidate. |
| OD-004 | Pending | Approve or reject the live scheduled-task rename/migration. | Owner review required | Existing task remains unchanged; follow `docs/security/WINDOWS_INSTALLATION.md`. |
| OD-005 | Per release | Approve the exact source SHA and artifact digest for publication. | Required for release | Record in the completed release evidence pack after technical gate PASS. |
