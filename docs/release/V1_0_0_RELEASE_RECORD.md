# ASTRA v1.0.0 immutable release record

This record was added after publication to link Governance v1 to the exact
released source and artifacts. It does not alter or replace the release.

## Identity

| Field | Released value |
|---|---|
| Release | [`v1.0.0`](https://github.com/SoSwag5/ASTRA/releases/tag/v1.0.0) |
| Published | 2026-09-13 |
| Source commit | `81ad2d38869980fe854d92f26a9ae16b774f58a6` |
| Artifact | `astra-1.0.0-rc.1.zip` |
| Artifact SHA-256 | `a5842744bad86a249381f5c1c4f509785375c994af1cbc70fef5f6e283b4399f` |
| SBOM | CycloneDX 1.7 JSON, 246 components |
| SBOM SHA-256 | `6f8b681e352a8efb58b344f22a28eabad5090aa37f5b123c0ef06ab0a16ea293` |
| Final gate | **APPROVED WITH DOCUMENTED RESIDUAL RISK** |
| Blockers | `[]` |

## Evidence chain

- [Release Assurance run 34722561421](https://github.com/SoSwag5/ASTRA/actions/runs/34722561421)
  built the artifact from the released source. Its tests on Python 3.13/3.14,
  SCA, CodeQL analyses, build, clean installation, provenance, and attestation
  verification jobs passed. Its initial aggregate gate failed before final
  residual-risk review; this failed run is retained as part of the audit trail.
- [Review Existing Candidate run 34732173819](https://github.com/SoSwag5/ASTRA/actions/runs/34732173819)
  reviewed the same existing artifact and produced the final successful gate with
  decision `APPROVED WITH DOCUMENTED RESIDUAL RISK`, the released source and
  artifact digest, and zero blockers.
- Provenance and CycloneDX SBOM attestations were verified against the repository,
  signer workflow, source commit, predicate, and released artifact digest.
- The gate record has `publication_authorized: false` by design. Ayham separately
  authorized publication, and the annotated tag and public release record that
  decision.

## Residual risk and follow-up

The release includes the risks documented in `docs/security/RISK_REGISTER.md`,
including the accepted R-15 OS-account/localhost boundary and open L2 hardening
items R-13 and R-14. Post-release documentation corrections are tracked in
issues [#24](https://github.com/SoSwag5/ASTRA/issues/24),
[#25](https://github.com/SoSwag5/ASTRA/issues/25),
[#26](https://github.com/SoSwag5/ASTRA/issues/26), and
[#27](https://github.com/SoSwag5/ASTRA/issues/27).

## Immutability

Do not rebuild, replace, retag, or rewrite v1.0.0. Correct documentation or code
on later commits, preserve links to this record, and ship product changes only in
a later version after the applicable governance and release gates pass.
