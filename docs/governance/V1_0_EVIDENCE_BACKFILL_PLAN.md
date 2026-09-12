# v1.0 evidence backfill plan

This plan organizes existing v1.0 work without inventing historical approvals or
rerunning controls solely to make paperwork look complete. The exact frozen
candidate still needs one completed release evidence pack.

| Area | Classification | Existing evidence | Required action |
|---|---|---|---|
| Product scope and local-first trust model | Needs polish | README, architecture inventory, threat model, local-access guide | Confirm reconstructed ADR-0001 and align public wording after v1.0 freeze. |
| OS-account/localhost residual risk R-15 | Existing | Risk register, L1 closure review, commit history | Link ADR-0002 and retain the explicit review triggers. |
| Access-key/session exchange | Needs Owner confirmation | Implementation, regression tests, local-access documentation | Confirm ADR-0003; link exact tests and assessed commit. |
| Build once / verify same artifact | Needs Owner confirmation | Release and review-candidate workflows, build scripts | Confirm ADR-0004; capture the actual hosted run, source SHA, artifact digest, and clean-install result. |
| CycloneDX 1.7 SBOM | Existing, needs release binding | SBOM documentation, generator/validator, historical validated SBOM | Capture the frozen candidate's SBOM digest, validation output, component count, and artifact association. |
| Hosted provenance | Needs executed evidence | Prepared SHA-pinned workflows and SLSA assessment | Confirm ADR-0006; capture signed provenance and independent verification for the exact artifact. Do not claim a Build level without requirement evidence. |
| Local tests and AppSec | Existing, needs release binding | Dated 271-test local assessment; ASVS/SSDF/SAMM mappings | Rerun applicable checks on the frozen SHA and record deltas. Preserve R-15; do not inflate framework results. |
| Hosted CI, CodeQL, dependency review, Scorecard | Needs polish / current verification | GitHub runs now exist; historical report predates them | Select the exact candidate runs, review conclusions and findings, and link immutable run URLs in the evidence pack. |
| Privacy/publication | Existing process, needs final human review | Publication gate, history scan, sanitized candidate report | Run the gate on all relevant refs/artifacts and perform semantic review of documents, screenshots, and archive contents. |
| Clean Windows install and scheduled task | Needs evidence / Owner confirmation | Hosted harness and migration plan | Capture clean-runner evidence. Do not change the live scheduled task without OD-004 approval. |
| Release notes and changelog | Not required retroactively beyond v1.0 | Candidate report and assurance report | Draft v1.0 notes from verified shipped behavior; do not imply the tag or release already exists. |
| ADR history | Not required retroactively as accepted fact | Repository implementation and security docs | Keep reconstructed ADRs Proposed until the Owner confirms them; do not invent meeting dates or decisions. |
| Final publication approval | Missing by design until ready | Technical gate and this governance model | Record the Owner's decision for the exact source SHA and artifact digest only after gate PASS. |

## Completion test

Backfill is complete when one reviewer can start from the evidence pack, identify
the exact source and artifact, reproduce or inspect every mandatory result,
distinguish historical from current evidence, see all residual risks, and verify
both the technical verdict and separate Owner approval. Backfill does not permit
editing a historical report to claim checks that were not run at that time.
