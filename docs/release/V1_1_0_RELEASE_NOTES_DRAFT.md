# ASTRA v1.1.0 — unreleased draft

**Pre-candidate draft. Do not distribute as shipped release notes.** No v1.1.0
package, frozen source, artifact digest or Owner release approval exists.
These notes describe implemented changes in `master` at
`22642e88f516f827c1dc4250bc72eb259306fafd` and the local #48 assurance work.
They must be reconciled with the complete frozen candidate before publication.

## Highlights

- Discovery builds bounded searches from the confirmed resume/search focus,
  retrieves public Greenhouse, Lever and Ashby postings, and reports source
  health and funnel counts. A healthy source does not guarantee relevant jobs.
- Job observations support conservative deduplication. Explainable ranking and
  eligibility warnings remain separate; scores are review priorities rather
  than hiring probabilities or inferred work authorization.
- A primary Gmail account can provide minimized read-only application-confirmation
  evidence. Deterministic parsers consider sender, template, extracted fields
  and receiver authentication signals. Weak or ambiguous evidence needs review.
- Application state has a permitted-transition table and recorded provenance.
  Automated confirmation evidence can set only APPLIED, at HIGH confidence on
  a unique corroborated match. Manual states cannot be overwritten by weaker
  automated evidence. No job or application is created from a message.
- Discovery has explicit preview/Start/Stop controls. The app prepares review
  material; final application submission remains manual.

## Fixes and reliability

- Contradictory requisition URLs block automatic reconciliation even when
  other fields agree. Ambiguous matches remain reviewable.
- Scan cancellation and source/report handling were corrected under #46.2-A/B.
  Polling is bounded and does not start a scan merely by opening a page.
- Provider response limits and failure isolation prevent one oversized source
  from blocking the other providers in the tested fictional scenarios.

## Security and privacy

Gmail requests exactly `gmail.readonly`. OAuth uses PKCE, unpredictable
single-use state, a loopback callback and authenticated account binding.
Credentials stay in the native OS credential store, with no plaintext fallback,
and are excluded from normal exports, backups and diagnostics. Full email
bodies are not retained as application evidence. These controls do not prevent
a process running as the same OS user from accessing that user's credentials.

External content is untrusted. Validated provider connections, response caps,
escaped display and strict advisory output validation are tested controls.
Authenticated malicious senders and sufficiently informed spoofed confirmations
remain possible. Generic and SmartRecruiters fetches retain the documented
legacy transport limitation. R-16, R-17 and R-18 remain OPEN pending Owner
decisions. No security certification, ASVS level or SLSA level is claimed here.

See the [evidence pack](V1_1_0_RELEASE_EVIDENCE_PACK.md),
[risk register](../security/RISK_REGISTER.md) and
[as-built threat delta](../security/THREAT_MODEL_CHANGE_V1_1_DISCOVERY_GMAIL.md#issue-48-as-built-reconciliation-2026-10-01).

## Install or upgrade — release validation pending

1. Wait for an Owner-approved package and its verified hashes. This draft
   does not authorize installing an unbuilt release.
2. The current source build uses Windows, Python 3.13 and Node 24. Hosted tests
   also exercise Python 3.14. Final packaged-user prerequisites must be checked
   against the actual package; source-build tools are not automatically package
   prerequisites.
3. Before a validated upgrade, make a local backup using the documented data
   workflow. Gmail credentials are deliberately excluded; account setup may
   need to be repeated. Stored schema additions are tested with fictional data.
4. Follow the final package's installation instructions, then verify startup,
   restart, existing records and manual review controls. Actual v1.1 clean
   install, v1.0-to-v1.1 package upgrade and package rollback are NOT RUN.
5. Retain the prior verified package and data backup for the rollback procedure.
   Schema-level rollback tests do not establish package rollback success.

Current references: [Windows installation](../security/WINDOWS_INSTALLATION.md)
and [data protection](../security/DATA_PROTECTION.md). Do not replace or retag
the immutable v1.0.0 package.

## Compatibility and known limitations

- The 2026-10-02 Python dependency audit found six advisories in pinned pypdf
  6.18.0. The [finding records](../security/V1_1_PYPDF_SCA_FINDINGS.md) are TRIAGED;
  remediation and a clean independently reviewed rerun are required before
  release. Existing PDF-parser containment does not clear this blocker.
- Changes described above preserve the existing job row and legacy status
  projections. New evidence/state tables are additive; package migration
  acceptance remains pending.
- The secondary Gmail slot is disabled until primary-account sync, parsing and
  reconciliation validation satisfies OD-012. OD-013 requires two accounts for
  final v1.1.0, so this is a release blocker rather than a completed feature.
- The #47 dashboard and its visual/motion follow-ups are local and unmerged.
  The latest local visual revision is
  `772fe7e87586720d9db6bed06cb1a12d3af14649`; draft PR #78 still carries the older
  `4a13fc83bee7bd594b61f2ad1b830594a523f742`. Neither is included in this master
  inventory, and their UI results are not full-release evidence.
- The evaluation harness and failed blind-evaluation closeout are not measured
  production ranking quality. Offline #46.2-D/E/F candidates are excluded.
- No live mailbox accuracy, second-account operation or automatic compromise
  detection is claimed. Applications are submitted manually. Scheduled-task
  migration remains deferred under OD-009.

## Verify the download — no downloadable v1.1 artifact yet

| Field | Current state |
|---|---|
| Frozen source / candidate | NOT FROZEN |
| Package / manifest / SHA-256 | NOT RUN |
| CycloneDX SBOM / SHA-256 | NOT RUN for v1.1 |
| Hosted provenance and SBOM attestations | NOT RUN for v1.1 |
| Independent artifact/attestation verification | NOT RUN for v1.1 |
| Final release gate / Owner approval | BLOCKED / pending |

Fill these fields from the same frozen, built and independently verified
artifact. A local test result or a v1.0.0 attestation cannot fill a v1.1 field.
