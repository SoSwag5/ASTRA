# Remote enablement after local closure

Status: executed. <https://github.com/SoSwag5/ASTRA> now exists and is public,
and the sanitized history has been pushed; steps 1-6 below are done. No tag or
release has been created, and publication of a release remains a separate,
explicitly authorized action. The sequence is kept as the record of how this was
carried out, and as the procedure for any future candidate.

**Local prerequisite:** close ASVS 8.2.1/8.2.2 across the default installation,
including secure credential provisioning, first-launch/recovery and migration.
Rerun local assurance and review its changes. The current local verdict is
BLOCKED LOCALLY, even though the other reviewed L1 items have evidence.

## Exact later sequence

1. **Maintainer: create an empty GitHub repository**, choosing visibility deliberately.
   Public source itself is publication; a private staging repository may require
   paid GitHub security/attestation capabilities. Do not add a starter README or
   license that conflicts with this repository. Confirm the intended remote URL.
2. **Maintainer: explicitly authorize the first push.** Before it, rerun the
   publication gate over all refs and review the exact source/docs/screenshots.
   Configure `origin` only for the chosen empty destination, then push the sanitized
   branch. Do not push backups or tags. Existing local history is not rewritten.
3. **GitHub: enable Actions, dependency graph/Dependabot alerts, code scanning and
   private vulnerability reporting** where the repository plan supports them.
   Enable secret scanning/push protection where available. Use restricted write
   permissions and protect the main branch: required PR review, required **Security
   Verification**, no force pushes/deletion, and documented maintainer bypass rules.
4. **Let CI execute on the candidate source:** Python 3.13 and 3.14 matrix,
   built frontend tests/Chromium acceptance, npm audit, Python SCA, publication scan,
   and CodeQL Python/JavaScript-TypeScript/Actions. Inspect findings; a completed
   CodeQL job alone does not mean no findings. Only after green matrix results
   describe 3.14 as continuously tested/supported.
5. **Exercise a real pull request** against the intended base so dependency review
   actually runs. It is intentionally skipped on plain pushes/manual release
   dispatch. Record its exact base/head and merge/source relationship; include
   the result in candidate-bound maintainer review.
6. **Run and review OpenSSF Scorecard** on the actual repository. Save the result,
   investigate failed checks and document residual risks. Do not infer a score
   from local workflow files. Review repository protections and reporting settings.
7. **Dispatch Release Assurance** on the exact frozen commit, initially with `{}`
   maintainer review. It builds the candidate on hosted Windows, generates and
   validates CycloneDX, creates the ZIP/checksum/manifest, runs clean `setup.bat`
   on a separate hosted Windows runner, tests empty startup/restart persistence
   and demo API denial, then creates and verifies artifact/SBOM attestations.
   Its final gate is expected to remain BLOCKED until reviewed evidence exists.
8. **Download and review that exact candidate.** Record run ID, source SHA, artifact
   SHA-256, SBOM validation, both attestation verifications and clean-install result.
   Inspect contents, notices, fictional screenshots and residual risks. Keep a
   source/artifact-bound JSON review containing `reviewer`, `source_commit`,
   `artifact_sha256` and these objects, each with `status: PASS` and a real evidence
   URL/reference: `publication_content`, `codeql_findings_triaged`,
   `dependency_review`, `repository_controls`, `scorecard_reviewed`, `residual_risks`.
   Never fill PASS for an unperformed check.
9. **Dispatch Review Existing Candidate** on the same source commit with that
   candidate run ID and completed review JSON. This workflow downloads the existing
   artifact without rebuilding it; checks authoritative GitHub job outcomes,
   source/repository/workflow identity and install digest; independently re-verifies
   both attestations; then runs the Release Security Gate over the exact bytes.
   The separate review stage avoids invalidating the reviewed digest with a fresh
   SBOM timestamp/rebuild. Changed source requires a new candidate and review.
10. **Stop for publication authorization.** A green technical gate does not publish
    anything. Only after explicit approval create the intended release/tag, upload
    the reviewed artifact/SBOM/checksum/evidence, then download the public artifact
    and run a final installation rehearsal. No SLSA Build level or certification
    follows automatically from signing an artifact.

## Prepared workflows and remaining external evidence

`ci.yml`: runtime/frontend/Chromium, SCA, CodeQL, PR dependency review, publication
scan and fail-closed verification aggregation. `codeql.yml`: Python,
JavaScript/TypeScript and Actions. `release.yml`: hosted build, SBOM, install,
provenance and verification. `review-candidate.yml`: exact-artifact review gate.
Third-party action references use full commit SHAs. No workflow publishes a release.

Useful authoritative references: [GitHub CLI attestation verification](https://cli.github.com/manual/gh_attestation_verify),
[GitHub API pagination used by candidate binding](https://cli.github.com/manual/gh_api),
and [OpenSSF Scorecard](https://github.com/ossf/scorecard/blob/main/README.md).
