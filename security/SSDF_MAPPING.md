# NIST SSDF (SP 800-218 v1.1) — Practice Mapping (ASTRA)

*Mapped against NIST SP 800-218 SSDF **v1.1 (final)**. (SSDF 1.2 exists only in
draft and is not treated as final here.) Scope is honest for a solo project — where
a practice is organizational and doesn't apply, it's marked N/A; where it's missing
it's marked GAP.*

## PO — Prepare the Organization

| Practice | ASTRA | Status |
|---|---|---|
| PO.1 Define security requirements | Threat model + ASVS mapping define requirements | IMPLEMENTED / locally reviewed |
| PO.3 Supporting toolchain | pytest, secret scanner, SBOM, dependency audit, CodeQL CI | IMPLEMENTED / locally reviewed |
| PO.4 Criteria for software security checks | CI gates: tests + security suite + dependency review must pass | IMPLEMENTED / locally reviewed |
| PO.2 Roles & responsibilities | Solo project | N/A |

## PS — Protect the Software

| Practice | ASTRA | Status |
|---|---|---|
| PS.1 Protect code from unauthorized change | Git history, reviewed changes, CI on push | IMPLEMENTED / locally reviewed |
| PS.2 Provide provenance / verify integrity | CycloneDX SBOM (`security/sbom.cdx.json`), pinned deps | IMPLEMENTED (hash-enforced install; no signed provenance attestation) |
| PS.3 Archive & protect each release | Git tags; local DB backups rotated | PARTIAL |

## PW — Produce Well-Secured Software

| Practice | ASTRA | Status |
|---|---|---|
| PW.1 Design meeting security requirements | Documented trust boundaries + secure defaults | IMPLEMENTED / locally reviewed |
| PW.2 Threat modeling / design review | `docs/THREAT_MODEL.md` | IMPLEMENTED / locally reviewed |
| PW.4 Reuse well-secured components | Maintained deps; audited; no custom crypto | IMPLEMENTED / locally reviewed |
| PW.5 Secure coding practices | ORM, input validation, output encoding, SSRF choke point | IMPLEMENTED / locally reviewed |
| PW.7 Code review | Changes reviewed; CodeQL static analysis | IMPLEMENTED / locally reviewed |
| PW.8 Testing (SAST/DAST/regression) | 209 tests incl. 41 security tests; CodeQL configured, remote execution pending | IMPLEMENTED / locally reviewed |
| PW.9 Secure default configuration | rules/dry-run/loopback/PREPARE-ONLY defaults | IMPLEMENTED / locally reviewed |

## RV — Respond to Vulnerabilities

| Practice | ASTRA | Status |
|---|---|---|
| RV.1 Identify & confirm vulnerabilities | dependency audit, secret scan, CodeQL, `SECURITY.md` reporting | IMPLEMENTED / locally reviewed |
| RV.2 Assess, prioritize, remediate | `docs/INCIDENT_RESPONSE_EXERCISE.md` runbook + risk register | IMPLEMENTED / locally reviewed |
| RV.3 Root-cause analysis | Regression test required per fix (documented practice) | PARTIAL |

## Honest gaps

- No signed releases / hash-pinned lockfile yet (PS.2/PS.3).
- Root-cause discipline is documented but only lightly exercised on a solo project.
