# v1.1 dependency intake — pypdf 6.18.0

## Current beta remediation update — 2026-10-02

The intake below is retained as dated history. All six records now have state
**REMEDIATED; independent verification pending**. Codex owns this separate beta
remediation by explicit Owner instruction. Both dependency specifications use
pypdf 6.19.0; the hash lock was refreshed from official PyPI wheel metadata.
All 47 exact product versions were freshly hash-installed. Strict pip-audit
2.10.0 reported zero known vulnerabilities without ignores, and npm audit
reported zero. The targeted 64 tests passed, including fictional extraction,
active-content rejection, existing-profile preservation and release controls.

[Upstream 6.19.0 release](https://github.com/py-pdf/pypdf/releases/tag/6.19.0)
contains the fixed dependency version for all six intake advisories. This
remediates the dependency findings; it does not assert a confirmed ASTRA exploit,
execution of all upstream exploit fixtures, or an independently verified closure.
No schema/data migration is introduced. Preserve v1.0 as a recovery artifact;
returning to its affected parser is not vulnerability remediation.

The exact frozen beta source must repeat SCA, regression, SBOM, packaging and
hosted checks. Local L1 15.2.1 component evidence is restored; final release
approval and independent review are separate. R-16/17/18 are unchanged.
See [beta evidence](../release/V1_1_0_BETA_1_EVIDENCE.md).

## Historical #48 intake (before remediation)

**Historical release verdict: BLOCKED. Finding states: TRIAGED, 2026-10-02.** These six
separate records share the same intake, affected dependency and remediation
path. No finding is independently verified, remediated or closed.

## Shared evidence and scope

- Reporter: Codex local release-assurance rerun. Remediation owner: the
  implementation engineer assigned to a separate dependency-remediation change;
  not assigned yet. Independent reviewer: not assigned.
- Affected source: `90e48ea76620ff1d876fb2907bb194b4c219916d`, and its unchanged
  product dependency lock inherited from master
  `22642e88f516f827c1dc4250bc72eb259306fafd`. `requirements.txt` and
  `requirements.lock.txt` pin `pypdf==6.18.0`. The local product environment
  matches all 47 locked package versions, including this version.
- Reproduction of the dependency finding: hash-enforced assurance environment,
  pip-audit 2.10.0, `python -m pip_audit --disable-pip --require-hashes --strict
  -r requirements.lock.txt --format=json --output=python-sca.json`. Exit 1:
  six advisories in one package. No application attack or malicious PDF was
  executed. Application exploitability remains unconfirmed.
- Evidence custody: Owner-local `ASTRA_48_FINAL_QA_2026-10-02`, files
  `python-sca.json` and `python-sca.txt`. JSON SHA-256:
  `be9c0a15ac7e6116c40178e0bfdddb26532cc22101cf3c4a5a6a56eff3b04808`.
  The report contains package/advisory results, not Owner documents or tokens.
- Source exposure review: `backend/document_security.py::extract_pdf` validates
  the upload and launches `backend.pdf_worker`; that worker constructs a strict
  `PdfReader` and invokes `page.extract_text()`. The upload is capped at 10 MB;
  the worker has a 512 MiB OS memory limit, a 100-page limit and a 200,000-character
  output cap. The parent imposes a 20-second subprocess timeout and rejects a
  failed parser without replacing the existing profile. Some limits apply after
  parsing begins. These are containment controls, not proof of advisory absence.
- The upstream advisories rate all six **Moderate**. No ASTRA-specific CVSS v4.0
  score/vector or confirmed application CWE classification is asserted. Any CWE
  below is explicitly upstream attribution. No exploitation was observed.
- State history for each: DETECTED and TRIAGED on 2026-10-02. Ownership,
  affected versions, exposure limits and the safe validation plan are recorded.
  No synthetic exploit reproduction or independent verification is claimed.

## SF-2026-48-01 — ToUnicode font mapping memory consumption

- Advisory: [GHSA-fp3h-c4fm-7vvf](https://github.com/py-pdf/pypdf/security/advisories/GHSA-fp3h-c4fm-7vvf),
  CVE-2026-102995 / PYSEC-2026-4154; published 2026-09-11.
- Affected versions: below 6.18.1; fixed in 6.18.1. Upstream CWE-400.
- Exposure: the described font decoding occurs during text extraction, which
  ASTRA calls. This establishes a relevant operation, not an escaped worker
  boundary or successful application denial of service.
- State: TRIAGED. Test plan: bounded fictional text/font PDF fixtures in an
  isolated parser environment; retain ordinary extraction and fail-closed
  timeout/memory behavior. No fixture or exploit was run in this intake.

## SF-2026-48-02 — Page-label memory consumption

- Advisory: [GHSA-w23x-9jrw-r45c](https://github.com/py-pdf/pypdf/security/advisories/GHSA-w23x-9jrw-r45c),
  CVE-2026-103000 / PYSEC-2026-4160; published 2026-09-16.
- Affected versions: below 6.19.0; fixed in 6.19.0. Upstream CWE-400.
- Exposure: no explicit page-label API use was found in the reviewed application
  paths. Indirect reachability is not independently established or disproved.
- State: TRIAGED. Test plan: source review of the fixed page-label path plus
  bounded fictional fixtures if application reachability is established.

## SF-2026-48-03 — Attachment lookup runtime consumption

- Advisory: [GHSA-v247-6f48-mgcj](https://github.com/py-pdf/pypdf/security/advisories/GHSA-v247-6f48-mgcj),
  CVE-2026-102999 / PYSEC-2026-4159; published 2026-09-16.
- Affected versions: below 6.19.0; fixed in 6.19.0. Upstream CWE-400 / CWE-407.
- Exposure: no explicit pypdf attachment-access API use was found. Upload
  validation rejects the EmbeddedFile token; this is not a complete proof that
  every indirect attachment path is unreachable.
- State: TRIAGED. Test plan: fixed-path source review and preserve active-content
  rejection; any necessary attachment fixture stays bounded and fictional.

## SF-2026-48-04 — Malformed FlateDecode runtime consumption

- Advisory: [GHSA-jw7q-gvrg-4vj3](https://github.com/py-pdf/pypdf/security/advisories/GHSA-jw7q-gvrg-4vj3),
  CVE-2026-102997 / PYSEC-2026-4156; published 2026-09-11.
- Affected versions: below 6.18.1; fixed in 6.18.1. Upstream CWE-400 / CWE-407.
- Exposure: text extraction can decode PDF streams. Application reachability of
  the specific fallback on a malformed stream remains unconfirmed.
- State: TRIAGED. Test plan: bounded fictional compressed-stream cases and
  unchanged parent timeout/failure behavior, without uncontrolled resource use.

## SF-2026-48-05 — Font-width memory consumption

- Advisory: [GHSA-g9cg-prrw-2r8q](https://github.com/py-pdf/pypdf/security/advisories/GHSA-g9cg-prrw-2r8q),
  CVE-2026-102996 / PYSEC-2026-4155; published 2026-09-11.
- Affected versions: below 6.18.1; fixed in 6.18.1. Upstream CWE-400.
- Exposure: the upstream description includes text extraction, which ASTRA
  performs. The application worker's containment does not remove the finding.
- State: TRIAGED. Test plan: bounded fictional font-width cases and verify
  extraction compatibility, parser rejection and existing profile preservation.

## SF-2026-48-06 — Form appearance-generation runtime consumption

- Advisory: [GHSA-php9-fj8v-98fj](https://github.com/py-pdf/pypdf/security/advisories/GHSA-php9-fj8v-98fj),
  CVE-2026-102998 / PYSEC-2026-4157; published 2026-09-16.
- Affected versions: below 6.19.0; fixed in 6.19.0. Upstream CWE-400.
- Exposure: no application use of updating PDF form fields with flattening was
  found in the reviewed paths. This is operation-level triage, not a scanner
  exclusion or independently verified false positive.
- State: TRIAGED. Test plan: fixed-path source review; bounded fictional forms
  only if a relevant application operation is established.

## Proposed remediation and closure requirements

1. Assign a separate dependency-remediation change; issue #48's authorized
   corrections remain tests/documentation only. Upgrade both pypdf pins to a
   supported audited version **at least 6.19.0**, the minimum covering all six
   reported advisories. Recreate the complete hash-locked dependency file using
   the established locking process; review the precise dependency/licence delta.
   This is a proposal, not an applied or independently approved fix.
2. Install the new lock into an isolated product environment. Use fictional
   documents to verify text extraction (including Arabic text), upload rejection,
   time/memory bounds, existing-profile preservation and surrounding PDF/import
   tests. Any resource-consumption challenge must be tightly bounded. Re-run
   Python and npm SCA on the exact remediation commit without ignore switches.
3. Run the applicable full security/quality gates, independently review the
   exact commit and evidence, then reconcile the ASVS record and all six states.
   Do not close a record because the version string changed or tests alone pass.
4. The proposed change is dependency-only: no planned schema/data migration.
   Compatibility and package behavior remain to be tested. Preserve the old
   immutable release for recovery; rollback to the affected dependency is not
   vulnerability remediation. Regenerate SBOM and package provenance for the
   final candidate. No fixed release, remediation commit or artifact exists yet.

The vulnerability policy requires triage within three calendar days (met by
this intake) and a medium-severity remediation target of 30 days from
confirmation. Application confirmation and a remediation deadline have not
been established here; none is fabricated. **Regardless of those timeframes,
the policy explicitly blocks release on unresolved pip-audit findings.** There
is no Owner exception or residual-risk acceptance for these records.

The advisories are already public; only their safe identifiers and bounded
source review are committed. No undisclosed exploit, private PDF or live CV
belongs in this record. Framework delta: ASVS 15.2.1 is PARTIAL pending current
dependency disposition; this does not assert a measured overdue deadline. The
v1.1 evidence pack, release-note limitations and project handoff reflect the
failed scan. R-16/17/18 and all prior Owner decisions remain unchanged.
