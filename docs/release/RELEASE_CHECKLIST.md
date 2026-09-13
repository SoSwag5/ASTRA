# ASTRA release checklist

Complete against one frozen source SHA and one immutable artifact. Attach the
filled [evidence pack](RELEASE_EVIDENCE_PACK_TEMPLATE.md). A missing required item
blocks release.

## Scope and freeze

- [ ] Owner confirmed version, change class, scope, compatibility, and target.
- [ ] Required PRs are merged; source SHA and clean tree are recorded.
- [ ] Branch ownership and concurrent work are reconciled.
- [ ] Changelog, release notes, user docs, migration, and rollback agree with the
      shipped behavior.
- [ ] Required ADRs, threat deltas, risk records, security findings, and framework
      deltas are complete.

## Verification

- [ ] Required Python, frontend, security, and targeted regression tests pass.
- [ ] Production build succeeds from locked inputs.
- [ ] Python and npm SCA pass; Dependency Review findings are resolved.
- [ ] CodeQL/SAST results for the exact source are reviewed and blocking findings
      are closed.
- [ ] Applicable ASVS L1 controls have no open PARTIAL/FAIL result; N/A items have
      architecture rationale and Owner decision where required.
- [ ] Clean Windows install, startup, restart/persistence, and demo isolation pass
      on the supported package.
- [ ] Upgrade/rollback and scheduled-task migration pass when affected.

## Artifact and supply chain

- [ ] The hosted workflow built one artifact from the frozen source.
- [ ] Manifest and SHA-256 identify the exact artifact.
- [ ] CycloneDX 1.7 SBOM was regenerated, reviewed, schema-validated, and digested.
- [ ] Artifact and SBOM attestations were created by the expected hosted workflow.
- [ ] An independent verification binds repository, workflow, source SHA,
      predicate, and subject digest.
- [ ] No SLSA level or other assurance claim exceeds the recorded evidence.

## Privacy and publication

- [ ] Publication gate passes over current refs/history and the exact archive.
- [ ] A human inspected documents, Markdown, images, manifests, notices, and the
      archive for semantic private data.
- [ ] Test/demo content is fictional; credentials, sessions, private paths, and
      live application records are absent.
- [ ] Public security and framework wording matches the evidence pack.

## Decision and publication

- [ ] Generated release security gate for the exact candidate says PASS.
- [ ] Independent reviewer records READY FOR OWNER REVIEW.
- [ ] Owner reviews the evidence pack and records APPROVED for the exact source
      SHA and artifact digest.
- [ ] A separately authorized publisher creates the tag/release without
      rebuilding or altering the artifact.
- [ ] Published tag, download digest, SBOM, provenance, and install path are
      verified after publication.
- [ ] `PROJECT_STATE.md` and post-release monitoring are updated.
