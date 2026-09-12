# ASTRA Release Governance v1

## Purpose and principles

This policy governs patches, security patches, minor and major releases,
architecture changes, dependency updates, cloud/security changes, and residual
risk. It preserves a practical solo-maintainer workflow while separating
implementation, independent assurance, technical readiness, and Owner approval.

1. Evidence is tied to the exact source SHA and, when applicable, artifact
   digest.
2. A configured control is not an executed control. Missing or stale evidence
   remains NOT RUN or BLOCKED.
3. Technical gate PASS does not authorize publication.
4. Governance cannot waive private-data findings, invalid SBOMs, failed
   provenance verification, failed required tests, or applicable ASVS L1
   failures.
5. Process depth follows security, compatibility, data, deployment, and
   operational impact.

## Roles and lifecycle

| Role | Accountable for |
|---|---|
| Owner — Ayham | Requirements, priority, architecture direction, scope, residual-risk acceptance, release approval, and publication |
| Claude Code — primary implementation engineer | Implementation, tests, remediation, implementation evidence, and truthful handoff |
| Codex — independent review and assurance | Separate-worktree or read-only review, evidence challenge, finding verification, and release-gate review |

Normal lifecycle:

1. Owner defines the outcome and makes reserved decisions.
2. Claude Code implements and tests on an owned branch/worktree.
3. Codex reviews independently without editing the implementation worktree.
4. Claude Code remediates confirmed findings.
5. Codex verifies the exact remediation commit.
6. The release security gate evaluates the exact candidate and fails closed.
7. The Owner reviews the evidence pack and approves or rejects publication.
8. A tag or release is created only under separate explicit authorization.

For a solo-maintainer project, the two-agent review is useful assurance but is
not represented as an independent organizational audit.

## Branches, worktrees, and ownership

| Pattern | Purpose |
|---|---|
| `master` | Protected integration and release source |
| `release/<version>` | Frozen release preparation and evidence-only fixes |
| `feature/<topic>` | Compatible product capability |
| `fix/<topic>` | Defect correction |
| `security/<topic>` | Security remediation; use an opaque name when disclosure requires it |
| `governance/<topic>` | Policy, templates, roadmap, and assurance process |

- One active implementation owner is allowed per branch.
- Concurrent agents use separate worktrees. Reviewers inspect read-only or use a
  separate review branch.
- A reviewer does not silently change or merge the implementation branch.
- Branch ownership, base SHA, and exact next action appear in every handoff.
- If the base moves, record the drift and integrate only when doing so will not
  disturb an active release candidate.

## Versioning

ASTRA follows Semantic Versioning for the public product interface and supported
behavior.

- **Patch `v1.0.1`:** backward-compatible defect correction, security
  remediation, documentation correction, or narrowly scoped operational fix.
- **Minor `v1.1.0`:** backward-compatible functionality or substantial
  operational/security capability, such as the operational-resilience phase.
- **Major `v2.0.0`:** breaking compatibility or a major security-boundary and
  architecture change, including application identities, authorization, and
  multi-user or tenant isolation.

Roadmap examples: v1.1 operational resilience; v1.2 installer/update lifecycle;
v1.5 AWS reference architecture; v2.0 multi-user identity and authorization.

A security fix may ship out of band as a patch when delay would expose users or
release integrity, the change is backward-compatible, scope is minimized, and
the security-patch evidence requirements pass. If safe remediation requires a
breaking trust-model or data-format change, use a major version or an explicitly
supported migration release.

## Release classifications and evidence

| Class | Trigger | Required review and evidence |
|---|---|---|
| Standard patch | Compatible bug, docs, narrow operational fix | Targeted tests; regression suite proportionate to affected code; dependency/SBOM delta if relevant; changelog/release notes; technical gate; Owner release approval |
| Security patch | Confirmed vulnerability or security hardening with user exposure | Private finding record where needed; severity and affected versions; root cause; remediation and negative regression; SAST/SCA as applicable; threat/risk/framework deltas; artifact/provenance checks; coordinated disclosure decision; Owner approval |
| Minor release | Compatible feature or substantial operational/security capability | Feature and regression tests; architecture review; threat-model delta; migration/operations docs when relevant; full release evidence pack; framework deltas; technical gate; Owner approval |
| Major release | Breaking API/data/installation behavior or material trust-boundary change | Approved ADRs; compatibility and migration plan; full threat model; ASVS/SSDF/SAMM reassessment; privacy review; clean install and upgrade/rollback tests; full supply-chain evidence; technical gate; explicit Owner approval |
| Emergency/hotfix | Active exploitation, critical confidentiality/integrity risk, or release-channel failure | Narrowest safe fix; minimum two-person/agent challenge when available; focused negative regression; SCA/SAST relevant to scope; source/artifact identity; documented deferred checks and expiry; Owner approval. No mandatory control may be reported PASS when skipped. |

Dependency updates use the class matching impact. A major runtime, framework, or
security-tool update normally requires at least minor-release depth even when
Dependabot labels it as routine. Review upstream changes, permissions, lockfile
deltas, behavior, licensing, SBOM changes, and actual tests.

Cloud, identity, secrets, persistence, privacy, update-channel, and deployment
changes always require an ADR and threat-model delta. They use minor or major
release depth according to compatibility and boundary impact.

## Required decision records

- **ADR:** required by the triggers in `docs/architecture/adr/README.md`.
- **Threat-model delta:** required when assets, actors, data flows, boundaries,
  entry points, deployment, or abuse cases change.
- **Risk acceptance:** required when a known residual remains beyond the normal
  fix window or blocks a control. Only the Owner may approve it.
- **Framework evidence delta:** required when a change affects ASVS, SSDF, SAMM,
  CycloneDX, or SLSA mappings or claims.
- **Security finding:** required for suspected or confirmed security defects;
  follow the lifecycle in `docs/security/SECURITY_FINDING_LIFECYCLE.md`.
- **Migration/rollback:** required for changes to stored data, installation,
  scheduled tasks, configuration, update channels, or supported interfaces.

## Definition of Done

A change is done when all applicable statements are true:

- [ ] Owner intent and acceptance criteria are satisfied.
- [ ] The branch has one recorded implementation owner and no unresolved
      concurrent-edit conflict.
- [ ] Code, tests, configuration, and user/operational docs agree.
- [ ] Required targeted, regression, security, build, and install checks passed
      on the exact reviewed source; unrun checks are explicit.
- [ ] No confirmed blocker or unresolved required review remains.
- [ ] Privacy/publication review used synthetic data and inspected documents,
      images, history, and release contents as applicable.
- [ ] Dependency locks, notices, SBOM, artifact manifest, provenance, and
      verification evidence were updated when affected.
- [ ] ADRs, threat changes, risks, findings, framework deltas, changelog, and
      release notes were updated when required.
- [ ] Independent review findings were remediated or explicitly dispositioned;
      only the Owner accepted residual risk.
- [ ] The handoff names the exact source SHA, checks, results, commit/PR, and next
      action.

A release additionally requires the exact candidate's fail-closed gate to pass,
a completed evidence pack, and explicit Owner approval of the exact source SHA
and artifact digest.

## Release freeze and approval

Freeze the candidate source before collecting final evidence. Build once from
that source, calculate its digest, and verify the same artifact through install,
SBOM, provenance, privacy, and release review. Any source or artifact change
invalidates the affected evidence and starts the relevant checks again.

The release decision has two distinct fields:

- **Technical verdict:** PASS or BLOCKED from executable evidence.
- **Owner decision:** APPROVED or REJECTED for the named source and artifact.

Only PASS plus APPROVED permits an authorized publisher to tag or release.

## Post-release process

Within seven days of a standard release, or sooner for a security release:

1. Verify the published tag, source SHA, artifact digest, SBOM, provenance, and
   download/install path.
2. Confirm the release notes, security wording, and supported-version statement
   match the shipped artifact.
3. Monitor vulnerability, dependency, workflow, and user-reported failures.
4. Record escaped defects, evidence gaps, rollbacks, or incidents as findings.
5. Update `PROJECT_STATE.md`, the changelog, risk register, and roadmap.
6. Hold a short retrospective for any failed gate, hotfix, rollback, privacy
   finding, or material process failure; assign one concrete improvement owner.
7. Archive release evidence under retention rules without committing private
   data or secrets.
