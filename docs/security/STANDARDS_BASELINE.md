# Standards authority and claim boundary
Reviewed 2026-09-12. Normative choices are version-specific, not automatically advanced by tool updates.

| Baseline | Official authority | Use |
|---|---|---|
| NIST SSDF 1.1 | https://csrc.nist.gov/pubs/sp/800/218/final | Overarching process; 42 tasks imported from official supplemental SSDF table |
| OWASP ASVS 5.0.0 | https://github.com/OWASP/ASVS/releases/tag/v5.0.0_release | 345 requirements; L1 baseline and L2 assessment; version-qualified IDs |
| OWASP SAMM v2 | https://owaspsamm.org/model/ | Five business functions, fifteen practices; conservative evidence assessment |
| CycloneDX 1.7 | https://cyclonedx.org/schema/bom-1.7.schema.json | JSON schema, packaged in maintained CycloneDX library |
| SLSA v1.2 | https://slsa.dev/spec/v1.2/build-requirements | Provenance and hosted-builder requirement assessment |
| GitHub attestations | https://github.com/actions/attest | Current actions/attest implementation; two attestations, independently verified |

NIST 1.1 remains the chosen final normative baseline. No SSDF 1.2 claim is made and no draft delta is normative.
ASVS requirement text in asvs-5.0.0-requirements.json is from the official May 2025 release JSON, not the moving latest build. Copyright OWASP contributors; CC BY-SA 4.0: https://creativecommons.org/licenses/by-sa/4.0/. Adapted ASVS mappings are shared under the same license. SAMM-derived assessment material also follows OWASP CC BY-SA 4.0. SSDF task text is transcribed from NIST's official supplemental workbook; its source contains replacement characters in some punctuation.
No external certification exists. Do not claim an ASVS level, SLSA Build level, or release approval from the presence of these files.
