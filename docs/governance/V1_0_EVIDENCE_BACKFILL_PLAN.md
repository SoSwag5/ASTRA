# v1.0 evidence backfill closure plan

ASTRA v1.0.0 is released and immutable. This plan records which evidence now
exists and which governance/documentation follow-ups remain. It never authorizes
editing the tag or rebuilding the released artifact.

| Area | Final classification | Released evidence | Remaining action |
|---|---|---|---|
| Product scope and local-first trust model | Implemented; governance confirmation pending | Frozen source, README, architecture inventory, threat model, local-access and privacy docs | Owner reviews ADR-0001. |
| OS-account/localhost residual risk R-15 | Accepted for v1.0.0 | Risk register, L1 closure, release approval, ADR-0002 | Issue #27 adds a dated review/expiry and evaluates other standing acceptances. |
| Access-key/session exchange | Implemented; governance confirmation pending | Frozen implementation, session/security tests, local-access documentation | Owner reviews ADR-0003. |
| Build once / verify same artifact | Executed; governance confirmation pending | Candidate run 34722561421, final review run 34732173819, released artifact digest | Owner reviews ADR-0004. Reverify each future candidate. |
| CycloneDX 1.7 SBOM | Executed; governance confirmation pending | 246 components, schema validation and SBOM attestation; released digest recorded | Owner reviews ADR-0005. Regenerate and validate for future dependency changes. |
| Hosted provenance | Executed and verified; governance confirmation pending | Provenance and SBOM attestations verified against source/artifact; release/gate records | Owner reviews ADR-0006. Preserve the evidence-specific SLSA wording. |
| Local and hosted AppSec | Executed for release | Python 3.13/3.14 tests, SCA, CodeQL, security verification, clean install, applicable ASVS L1 closure | Carry R-12, R-13, and R-14 into governed post-release planning. |
| Repository controls and Scorecard | Executed/reviewed | Registered workflows, branch/tag protection, security features, final Scorecard 6.7 | Issue #25 corrects the stale 7.1 reference. |
| Privacy/publication | Executed for release | Publication gate, packaged-byte scan, manifest/member checks, manual review of four packaged images | Issue #24 changes R-06 state to CLOSED. Continue semantic review every release. |
| Release provenance reference | Executed; stale source wording remains | Final release and gate identify source `81ad2d3`, artifact `a5842744…`, and SBOM `6f8b681e…` | Issue #26 replaces the superseded R-11 candidate reference without creating a self-reference cycle. |
| Clean Windows install and scheduled task | Hosted install passed; live migration open | Hosted setup/startup/restart/demo/shutdown/cleanup evidence | Live scheduled-task migration remains separately Owner-controlled. |
| Release notes and immutable record | Complete for release governance | Public GitHub release, annotated tag, and `V1_0_0_RELEASE_RECORD.md` | Future corrections belong to later commits/releases. |
| ADR history | Owner review pending | Reconstructed ADRs state their evidence and remain Proposed | Do not mark ADR-0001 or ADR-0003 through ADR-0006 Accepted without Owner decisions. |
| Final publication approval | Complete for v1.0.0 | Final gate had zero blockers; Owner separately authorized and published the exact source/artifact | Repeat exact-SHA/digest approval for every future release. |

## Closure test

The v1.0 release evidence chain is closed through the immutable release record.
Governance backfill remains open only for the five proposed ADR decisions and
issues #24-#27. Those follow-ups change later repository state and do not modify
the v1.0.0 tag or artifacts.
