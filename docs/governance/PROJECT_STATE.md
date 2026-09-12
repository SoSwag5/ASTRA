# ASTRA project state

**Snapshot date:** 2026-09-13 (Asia/Dubai)
**Rule:** This is a handoff snapshot, not a substitute for live verification.
Refresh it at session end when repository state changes.

## Product and release

- Product: ASTRA, a single-user, local-first Windows job discovery and
  application-tracking application.
- Release target: `v1.0.0`; repository evidence does not contain a Git tag as of
  this snapshot.
- Candidate named by the assurance documents: `1.0.0-rc.1`.
- Public-release status: **BLOCKED unless the current commit's generated release
  security gate says PASS and the Owner separately approves publication**.
- Historical local assessment: 271 tests passed; applicable ASVS 5.0.0 L1
  controls were recorded as PASS or justified N/A; CycloneDX 1.7 SBOM validation
  passed. These results apply only to the assessed source and do not establish
  the current release decision.
- Accepted residual risk: R-15, the local OS-account/localhost trust boundary,
  with mandatory review if ASTRA becomes networked, hosted, multi-user, or
  multi-tenant. The existing record has no explicit expiry even though the
  Secure SDLC requires exception expiry within 90 days; this needs Owner
  reconciliation and is not silently corrected here.

## Git and collaboration snapshot

- Canonical remote: `https://github.com/SoSwag5/ASTRA.git`.
- Default branch: `master`.
- Remote repository: public.
- Governance worktree: a separate local checkout named
  `astra-release-governance-v1` (record the absolute path in the private session
  handoff, not in public repository content).
- Governance branch: `governance/release-governance-v1`.
- Governance base: `cf9a6bc30ce93cedc9bed48b3ba0fefbbcd8eef8`.
- Concurrent implementation moved `master` to
  `846b8d7020730fec5dac01d6c978010dafc18587` while this governance pass was in
  progress. Do not rebase or merge this branch until the Owner chooses the
  post-v1.0 integration point.
- Pull request #16 was merged. Pull requests #1-#9 and #15 were open Dependabot
  proposals at the snapshot time. No open non-PR issues were returned by the
  public GitHub API.
- CI and Scorecard for `master` commit `846b8d7` completed successfully. This is
  source validation, not hosted release/provenance evidence.
- The public GitHub Actions API registered `ci.yml` and `scorecard.yml`, but
  returned 404 for `codeql.yml`, `release.yml`, and `review-candidate.yml` even
  though those files existed locally. Concurrent work then moved the active
  checkout to `chore/register-release-workflows` at `a77927b`. Treat CodeQL,
  hosted release, provenance, and review-candidate evidence as NOT RUN until the
  files are registered on `master` and exact runs pass. The active implementation
  checkout was on `chore/register-release-workflows` at `a77927b` when this
  governance snapshot closed.

## Current work boundaries

- Claude Code owns implementation and remediation branches assigned by the
  Owner.
- Codex owns this governance branch and may independently review other branches
  without modifying them.
- No agent may merge this governance branch, create a tag/release, publish, or
  alter the live scheduled task without explicit Owner authorization.
- The existing scheduled task keeps its current name until the Owner approves
  the migration procedure in `docs/security/WINDOWS_INSTALLATION.md`.

## Authoritative evidence

- `release/release-security-gate.json` from the exact candidate run controls the
  technical release verdict.
- `docs/release/RELEASE_SECURITY_ASSURANCE_REPORT.md` is a dated local assessment,
  not a live dashboard.
- `docs/security/RISK_REGISTER.md` holds accepted and open risks.
- GitHub run URLs, source SHA, artifact digest, SBOM digest, and attestation
  verification output must be captured in the release evidence pack.

## Exact next action

Complete and review this governance branch in isolation. After the v1.0 source
and remote assurance state are frozen, update this snapshot, resolve the two
or more commits of branch drift, rerun documentation/privacy validation, and open a
governance pull request for Owner review. Do not merge it during the v1.0 freeze.
