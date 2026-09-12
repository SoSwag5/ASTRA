# ASTRA release evidence pack — VERSION

This pack supports review of one immutable candidate. Replace every placeholder;
use NOT RUN, NOT APPLICABLE with rationale, or BLOCKED when evidence is absent.
Do not copy results from another SHA or artifact.

## 1. Candidate identity

- Version / candidate:
- Release classification:
- Source repository and full SHA:
- Source tree status and tag, if any:
- Hosted build workflow and immutable run URL:
- Artifact filename and SHA-256:
- Manifest filename and SHA-256:
- SBOM filename and SHA-256:
- Evidence collector / independent reviewer / date:

## 2. Source and scope

- Included changes, issues, PRs, ADRs, and migrations:
- Compatibility statement:
- Supported OS/runtime/install path:
- Files or features deliberately excluded:
- Branch protection and required checks observed:

## 3. Quality evidence

| Check | Environment | Exact result | Evidence link/file |
|---|---|---|---|
| Python tests | | | |
| Frontend tests | | | |
| Production build | | | |
| Targeted regressions | | | |
| Clean install / startup / restart | | | |
| Upgrade / rollback, when applicable | | | |

## 4. Application security

| Control | Result | Findings / evidence |
|---|---|---|
| CodeQL / SAST | | |
| Security regression suite | | |
| Input, SSRF, CSRF/Origin/Host, session, logging, parser checks affected by change | | |
| ASVS applicable blockers | | |
| Manual security review | | |

Open findings, false positives, accepted residuals, and expiry/review triggers:

## 5. Composition and dependencies

- Python SCA command/result/evidence:
- npm SCA command/result/evidence:
- Dependency Review result:
- Lockfile and hash verification:
- License/notice delta:
- Unexpected/new components reviewed:

## 6. SBOM and supply chain

- CycloneDX spec version:
- Generator and validator versions:
- Component count and completeness review:
- Schema/semantic validation result:
- Artifact-to-SBOM association:
- Provenance attestation identity and result:
- SBOM attestation identity and result:
- Independent verification command/result:
- Source SHA and subject digest match:
- SLSA assessment and conservative claim wording:

## 7. Privacy and publication

- Source/current-ref/history publication scan:
- Release archive scan:
- Human semantic review of docs, Markdown, images, manifests, and notices:
- Synthetic-data confirmation:
- Credentials, sessions, private paths, and application records absent:
- Public claim review:

## 8. Architecture, threats, and risk

- ADRs added/updated/confirmed:
- Threat-model delta:
- Risk register changes:
- Security findings and lifecycle states:
- Residual risk proposed:
- Owner risk acceptance ID/date/expiry, if applicable:

## 9. Framework deltas

- NIST SSDF 1.1:
- OWASP ASVS 5.0.0:
- OWASP SAMM v2:
- CycloneDX 1.7:
- SLSA v1.2:
- Exact approved public wording:

## 10. Deployment and operations

- Installation and prerequisite verification:
- Configuration/secrets behavior:
- Data migration and backup:
- Scheduled task/service impact:
- Rollback procedure and result:
- Monitoring/support/incident readiness:

## 11. Final decision

- Generated release gate file and SHA-256:
- Technical verdict: PASS / BLOCKED
- Blocking reasons:
- Independent reviewer conclusion:
- Release notes/changelog reviewed:

## 12. Explicit Owner approval

- Owner: Ayham
- Decision: APPROVED / REJECTED
- Exact source SHA:
- Exact artifact SHA-256:
- Accepted residual-risk IDs:
- Publication authorization and channel:
- Decision date/time and record link:

Technical PASS without this approval does not authorize a tag, release, upload,
or publication.
