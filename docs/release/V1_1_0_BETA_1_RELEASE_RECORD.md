# ASTRA v1.1.0-beta.1 release record

Published **2 October 2026, 05:06 Asia/Dubai** as an **early beta**, under the
Owner's explicit request to push and release. This record was added after
publication; it does not alter the frozen tag or replace an asset.

## Immutable identity

- [Public release](https://github.com/SoSwag5/ASTRA/releases/tag/v1.1.0-beta.1)
- Source/tag: `29d70d5ca004d75f0e421aea6174a30b0cd39ce3`
- Source tree: `3de96a3644209cff52f17e551a8d2bd87f6e806b`
- ZIP: `astra-1.1.0-beta.1.zip`, 4,703,195 bytes
- ZIP SHA-256: `baa0bc339f5f575b250ef9147dc9e37cfaa8c352a0ef7184a14b3e23f3ce559f`
- SBOM SHA-256: `76e3aa05e938c57011b64d52df66e6aef10c2c83bf158d44acb2ae45d5c0aceb`
- Manifest hashes cover 391 files; the ZIP also contains the manifest itself.

The public asset was downloaded again after publication. Its checksum,
GitHub asset digest and tag source agree with the reviewed candidate.
v1.0.0 remains immutable and unchanged. New work on master may differ from
this tag; evaluate the beta by its tag and digest.

## Executed evidence

| Control | Actual result and binding |
|---|---|
| [PR #81 CI](https://github.com/SoSwag5/ASTRA/actions/runs/36947005648) | All required checks succeeded before merge; dependency review PASS |
| [Release candidate](https://github.com/SoSwag5/ASTRA/actions/runs/36947063617) | Exact source above: verification, build, clean-install, provenance and verify-attestation succeeded |
| Hosted Python 3.13 | 2,174 passed, one existing skip; zero failures/errors; 443.829 seconds in the candidate test report |
| Hosted Python 3.14 | 2,174 passed, one existing skip; zero failures/errors; 631.024 seconds in the candidate test report |
| Frontend | Eleven test scripts, TypeScript and production build passed; npm audit reported zero advisories |
| Strict Python SCA | 47 product and 50 assurance-tool dependencies, zero reported advisories; no advisory suppression |
| CodeQL | Python, JavaScript/TypeScript and Actions succeeded; three exact-source analyses returned zero results and empty errors; zero open repository alerts at review |
| SBOM | CycloneDX 1.7 schema PASS; 246 application components, excluding separately audited tooling |
| Exact-ZIP clean install | PASS on GitHub-hosted Windows: manifest, setup, empty database, demo, fictional mutation, restart persistence, demo API denial, shutdown and temporary cleanup |
| Attestations | GitHub build provenance and SBOM predicate verified against exact source/ZIP; local verification also matched the validated SBOM |
| Package review | CRC, member set/hashes, packaged SBOM and source manifest matched; privacy-pattern scan found zero findings; public documents/images manually inspected |
| Packaged demo | Fresh fictional desktop, evidence-review and 390px screenshots captured from the ZIP; zero browser errors and no mobile horizontal overflow |
| [Final review gate](https://github.com/SoSwag5/ASTRA/actions/runs/36949063668) | **APPROVED WITH DOCUMENTED RESIDUAL RISK**; zero blockers; reviewed the existing ZIP without rebuilding |
| [Scorecard](https://github.com/SoSwag5/ASTRA/actions/runs/36948587334) | Succeeded on master `32ca007471620b6a4bbaed90dff49309fd2b3d00`, whose tree equals the candidate tree; 6.2 overall, Vulnerabilities 10/10 (zero detected) |

The first candidate gate deliberately returned BLOCKED with missing
source/artifact-bound review fields. The later Review Existing Candidate run
verified the five successful mandatory jobs and attestations, then evaluated
the review against that same source and digest. A failed first gate was not
relabeled as success. The final gate's `publication_authorized: false` field
correctly separates technical readiness from the Owner's explicit instruction.

Scorecard's weak indicators remain: review, young-project maturity, fuzzing,
CII badge, contributing organisations and signed-release detection scored zero;
branch protection scored 3 and packaging was undetected. These are disclosed,
not rewritten to improve a score. Actual strict master checks, admin enforcement,
release-tag protections, read-only default workflow permissions, secret scanning
and push protection were verified through GitHub APIs. Separate provenance
verification does not establish a signed Windows installer.

## Findings and review status

The earlier pypdf 6.18.0 dependency findings were remediated with 6.19.0. Three
later urllib3 findings in the assurance lock were remediated with 2.8.0 and a
second strict lock audit was added to CI. All three GitHub tooling alerts were
FIXED by publication; the graph showed 2.8.0. Finding records remain REMEDIATED
pending independent verification, not silently CLOSED.

Codex owns the Owner-authorized integration, remediation and technical
self-review. The attached maintainer review says so explicitly. Neither the
gate nor this record represents an independent audit, a human evidence sign-off,
ASVS certification, compliance or a SLSA Build level. The requested independent
Claude cloud review is **NOT RUN**.

The privacy scan supplements manual review; it cannot prove absence of all PII.
Upstream public licence attribution is preserved. A local package-review helper
initially used archive-prefixed paths and flagged those attribution emails; using
the repository gate's relative-path convention resolved that helper error.
No private record was removed or a new waiver added. Earlier failed preparation
runs remain documented in the beta evidence history and Owner-local QA.

## Novice distribution and remaining scope

The ZIP contains START HERE.html, Install ASTRA.bat, Open ASTRA.bat and the built
frontend. It needs Python 3.13 and internet to install dependencies; no Git,
Node, paid AI service or ASTRA administrator privilege is required. It is not
a standalone signed installer, and general update/rollback is unverified.

- #47 is integrated and closed; PRs #78, #79 and #81 are merged. Duplicate
  tooling PR #80 was closed as superseded.
- #48 final-v1.1 scope stays open. R-16/17/18 remain OPEN; final Owner decisions,
  secondary Gmail enablement and primary-mailbox accuracy evidence remain pending.
- Ten fictional PDF scenarios across five majors passed. They establish bounded
  import/review behavior, not broad career relevance or ranking quality.
- Brother-PC acceptance is NOT RUN; its checklist is ready.
- Cloud review and LinkedIn/caption drafts are prepared; neither review nor
  public posting is represented as completed.
- The 12 September comparison uses public baseline
  `cf9a6bc30ce93cedc9bed48b3ba0fefbbcd8eef8`: 20 calendar days to 2 October.
- ASTRA CV bullets are drafted; the actual AWS qualification and chosen
  photograph require verified Owner inputs. No AWS deployment or certificate
  was invented and the approved CV remains unchanged.

## Session handoff

Implementation owner: Codex, continuing under the Owner's explicit instruction.
The post-release documentation branch starts from merged master `32ca007` and
changes only this record, PROJECT_STATE and the beta evidence index. No runtime,
dependency, policy, risk acceptance, private evaluation, live service, scheduled
task or released byte is changed. No new ADR or security-boundary delta is needed.
The public release is complete; final v1.1 and real-world validation remain open.
Next action: run the independent cloud review against the immutable tag, then
execute another-PC acceptance before describing broader readiness.
