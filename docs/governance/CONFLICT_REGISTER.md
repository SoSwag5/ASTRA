# Governance conflict register

This register records disagreements between snapshots, policies, and current
repository evidence. Resolve conflicts explicitly; do not silently rewrite dated
assurance records.

| ID | Conflict | Resolution for governance v1 | Follow-up |
|---|---|---|---|
| C-001 | The initiating brief described a repository with no remote, while the current repository is public at `SoSwag5/ASTRA`. | Treat the brief as historical context. Verify hosted state at every session. | Refresh `PROJECT_STATE.md` before the governance PR. |
| C-002 | `RELEASE_SECURITY_ASSURANCE_REPORT.md` contains a pre-remote assessment and a later status note, while hosted runs now exist. | Preserve the dated report. Use the exact hosted run's generated gate and evidence pack for a current decision. | Create a new candidate evidence pack; do not back-edit historical results. |
| C-003 | Some security documents still say remote execution is pending. | Treat those statements as time-scoped until updated through a dedicated evidence change. Never infer PASS from the existence of a remote. | Reconcile after remote assurance completes. |
| C-004 | Security documents exist under both root `security/` and `docs/security/`. | `docs/security/` is the current governance source unless a file explicitly identifies another generated source. Avoid deleting or merging duplicates during this pass. | Inventory and consolidate in a separate reviewed documentation issue. |
| C-005 | The repository default branch is `master`, while generic examples often use `main`. | ASTRA governance names `master` as the protected default branch. | Revisit only through an Owner-approved repository change. |
| C-006 | The governance branch was based on `cf9a6bc`; `master` advanced to `846b8d7` during the pass. | Keep the isolated branch stable and record drift. | Integrate after v1.0 freeze, then rerun validation. |
| C-007 | R-15 is recorded as an accepted architectural residual without an expiry, while `docs/security/SECURE_SDLC.md` requires risk exceptions to expire within 90 days. | Preserve the historical decision and flag the missing expiry; governance does not invent an Owner date. | Owner adds an expiry/reapproval date or amends the exception policy through explicit review. |
| C-008 | `codeql.yml`, `release.yml`, and `review-candidate.yml` existed locally but were not registered by GitHub Actions; their public API endpoints returned 404. | Record these controls as NOT RUN. The concurrent `chore/register-release-workflows` branch appears intended to remediate registration, but its name is not proof of completion. | After that work merges, verify registration and successful exact-SHA runs before changing release status. |
