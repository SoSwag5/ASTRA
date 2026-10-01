# NIST SSDF 1.1 task mapping

Official SP 800-218 final baseline; all 42 tasks in PO/PS/PW/RV are covered in [CSV](NIST_SSDF_1.1_MAPPING.csv). No task is excluded merely because the project has one developer. Missing training, independent review, operational repetition and remote controls remain explicit.

| Task | Status | Implementation | Evidence | Gap |
|---|---|---|---|---|
| PO.1.1 | IMPLEMENTED | Lifecycle, infrastructure and release requirements documented. | docs/security/SECURE_SDLC.md | Review on each release |
| PO.1.2 | PARTIAL | All requirement rows assessed. | docs/security/OWASP_ASVS_5.0.0_MAPPING.csv | Close applicable L1 gaps |
| PO.1.3 | PARTIAL | Component selection and update policy. | requirements.lock.txt; docs/security/VULNERABILITY_MANAGEMENT.md | No supplier requirements/attestation agreement evidence |
| PO.2.1 | IMPLEMENTED | Maintainer explicitly owns all lifecycle stages. | docs/security/SECURE_SDLC.md | Reassess when contributors join |
| PO.2.2 | NOT IMPLEMENTED | Training gap recorded. | docs/security/OWASP_SAMM_ROADMAP.md | Record role-specific training and proficiency review |
| PO.2.3 | PARTIAL | Maintainer release authority defined. | docs/security/SECURE_SDLC.md | Owner sign-off and periodic review evidence pending |
| PO.3.1 | IMPLEMENTED | Tools, stage integration and evidence defined. | docs/security/SECURITY_TESTING.md | Maintain pins |
| PO.3.2 | PARTIAL | Pins and least privilege prepared. | .github/workflows/ci.yml; requirements-assurance.lock.txt | Remote execution and settings unverified |
| PO.3.3 | PARTIAL | Structured SBOM/gate evidence configured. | scripts/generate_sbom.py; scripts/release_security_gate.py | Hosted evidence absent |
| PO.4.1 | IMPLEMENTED | Mandatory controls and refusal criteria defined. | docs/security/SECURE_SDLC.md; scripts/release_security_gate.py | Apply on every release |
| PO.4.2 | PARTIAL | Machine evidence and missing-result rejection. | scripts/release_security_gate.py | Hosted retention/required checks pending |
| PO.5.1 | PARTIAL | Disposable tests and separated assurance environment. | tests/conftest.py; .github/workflows/ci.yml | Development shares live host; remote isolation pending |
| PO.5.2 | PARTIAL | Data DACL script. | scripts/protect_local_data.ps1 | Endpoint patching/FDE/account posture not assessed |
| PS.1.1 | PARTIAL | Local Git and least-privilege workflow. | .github/workflows/ci.yml | Remote branch rules/account protections not configured |
| PS.2.1 | PARTIAL | Digest and manifest produced locally. | scripts/build_release.py | No distributed verified release/provenance |
| PS.3.1 | PARTIAL | Local artifact handling and private preservation. | scripts/build_release.py; docs/security/RISK_REGISTER.md | Protected published archive/retention unverified |
| PS.3.2 | PARTIAL | CycloneDX inventory and graph. | scripts/generate_sbom.py; security/sbom.cdx.json | Hosted provenance/distribution pending |
| PW.1.1 | IMPLEMENTED | STRIDE boundaries and abuse cases reviewed. v1.1 (#48): Planning-stage delta for Gmail OAuth, mailbox and provider surfaces (OD-017), reconciled against the as-built code with ten abuse cases traced to tests. | docs/security/THREAT_MODEL.md; docs/security/THREAT_MODEL_CHANGE_V1_1_DISCOVERY_GMAIL.md | Revisit on design change |
| PW.1.2 | IMPLEMENTED | Requirements, risks and decisions tracked. v1.1 (#48): R-16, R-17 and R-18 registered for v1.1; ADR-0007 to ADR-0010 record the decisions. | docs/security/RISK_REGISTER.md; docs/security/OWASP_ASVS_5.0.0_MAPPING.csv; docs/architecture/adr/0007-gmail-oauth-credential-storage.md; docs/architecture/adr/0009-external-job-provider-trust-boundary.md | Review every release |
| PW.1.3 | PARTIAL | Native credential store and structured local events. v1.1 (#48): Gmail refresh tokens and the OAuth client secret reuse the native OS credential store; provider fetches reuse one shared capped transport. | backend/privacy.py; backend/security_events.py; backend/gmail_accounts.py; backend/job_providers/transport.py | No identity/log service integration; intentional local scope |
| PW.2.1 | PARTIAL | Automated boundary regressions plus maintainer review. v1.1 (#48): ADR-0007 to ADR-0009 passed an Owner security review before code (OD-018). #37 to #43 and #46 had independent agent review before merge. | tests/security/test_http_boundary.py; docs/security/ARCHITECTURE_INVENTORY.md; docs/governance/OWNER_DECISIONS.md | Two-agent review is not an organizational audit; #44 and #45 merged without independent review |
| PW.4.1 | PARTIAL | Pinned maintained dependencies. | requirements.lock.txt; frontend/package-lock.json | Supplier/component assurance remains incomplete |
| PW.4.2 | PARTIAL | Reusable central security controls. v1.1 (#48): Central controls added: job_providers/transport.py (pinned dial, caps, redirect revalidation) and gmail_content.safe_url. | backend/policy.py; backend/document_security.py; backend/job_providers/transport.py; backend/gmail_content.py | Complete ASVS verification outstanding |
| PW.4.4 | PARTIAL | SCA and inventory available. | scripts/generate_sbom.py; .github/workflows/ci.yml | Audits do not establish all supplier requirements |
| PW.5.1 | PARTIAL | Coding controls and regressions present. v1.1 (#48): Negative tests for every v1.1 abuse case. | tests/security; docs/security/OWASP_ASVS_5.0.0_MAPPING.csv; tests/security/v1_1_assurance_inventory.py | Open control-level findings |
| PW.6.1 | PARTIAL | Modern Python/TypeScript tooling. | setup.bat; frontend/tsconfig.json | Bundled native toolchain security not fully assessed |
| PW.6.2 | PARTIAL | Explicit runtime and exact dependencies. | setup.bat; requirements.lock.txt | 3.14 verification and native build-option inventory pending |
| PW.7.1 | IMPLEMENTED | Manual and SAST verification strategy defined. | docs/security/SECURITY_TESTING.md | Review by change risk |
| PW.7.2 | PARTIAL | Findings recorded and SAST configured. v1.1 (#48): CodeQL (python, javascript-typescript, actions) runs on every push; it passed on 22642e8 (CI run 36590869577). v1.1 PRs record independent review findings and their remediation. | .github/workflows/codeql.yml; docs/security/RISK_REGISTER.md; .github/workflows/codeql.yml (CI run 36590869577) | CodeQL findings for the frozen v1.1.0 candidate are not yet triaged; #44 and #45 had no independent review |
| PW.8.1 | IMPLEMENTED | Executable boundary/abuse tests required. v1.1 (#48): Consolidated v1.1 security regression suite (python -m pytest -m v1_1_assurance). | docs/security/SECURITY_TESTING.md; tests/security/v1_1_assurance_inventory.py; tests/security/test_v1_1_assurance.py | Maintain coverage |
| PW.8.2 | PARTIAL | Disposable regression suite. v1.1 (#48): The consolidated v1.1 suite passed locally at 22642e8 plus the #48 tests (517 passed, 0 failed); hosted Python 3.13/3.14 suites passed on 22642e8. | tests/security; tests/conftest.py; tests/security/test_v1_1_assurance.py | Full ASVS and clean-host acceptance pending |
| PW.9.1 | IMPLEMENTED | Local/rules/demo/security defaults defined. | docs/security/DATA_PROTECTION.md; backend/main.py | Public exposure unsupported |
| PW.9.2 | PARTIAL | Defaults implemented/documented. | setup.bat; README.md; backend/main.py | Clean-host installation not yet proven |
| RV.1.1 | PARTIAL | Intake and advisory sources specified. | SECURITY.md; .github/dependabot.yml | Private channel and alerts not active |
| RV.1.2 | PARTIAL | Source review found privacy weakness. v1.1 (#48): The #48 review found four ADR-required controls without a direct test, and a stale ASVS claim that no OAuth client existed. The tests were added and the mapping corrected; no code defect was found. | tests/security; docs/security/RISK_REGISTER.md; docs/security/THREAT_MODEL_CHANGE_V1_1_DISCOVERY_GMAIL.md | Hosted SAST and repeat review pending |
| RV.1.3 | PARTIAL | Owner, disclosure and triage process defined. | SECURITY.md; docs/security/VULNERABILITY_MANAGEMENT.md | Private reporting not active |
| RV.2.1 | IMPLEMENTED | Risk rationale/classification and blocking decisions recorded. | docs/security/RISK_REGISTER.md | CVSS only on confirmed suitable vulnerability scope |
| RV.2.2 | PARTIAL | Private-report issue remediated; other responses tracked. | scripts/publication_gate.py; docs/security/RISK_REGISTER.md | Close remaining release blockers |
| RV.3.1 | IMPLEMENTED | R-06 root cause recorded. | docs/security/RISK_REGISTER.md | Apply to subsequent findings |
| RV.3.2 | NOT IMPLEMENTED | No longitudinal root-cause trend evidence. | docs/security/OWASP_SAMM_ROADMAP.md | Quarterly pattern review |
| RV.3.3 | PARTIAL | Expanded source/history and report pattern checks. | scripts/publication_gate.py | Complete manual content/image review and class-wide tests |
| RV.3.4 | IMPLEMENTED | Privacy incident feeds mandatory artifact review and evidence gate. | docs/security/SECURE_SDLC.md; docs/security/RISK_REGISTER.md | Verify sustained operation |

**v1.1 delta (issue #48, 2026-10-01).** Ten tasks gained v1.1 evidence:
PW.1.1, PW.1.2, PW.1.3, PW.2.1, PW.4.2, PW.5.1, PW.7.2, PW.8.1, PW.8.2 and
RV.1.2. Each change is marked `v1.1 (#48):`. No status changed. PW.7.2's
gap had said CodeQL never ran remotely, which was false; it now names the
real remaining gaps. Other rows still carry pre-release wording that v1.0
evidence has since overtaken: PO.3.2, PO.3.3, PS.1.1 and RV.1.1 describe
hosted checks, branch protection and private reporting as absent, but R-10
in the risk register records them active since v1.0.0. Those rows are outside v1.1 scope
and were left unchanged. Correcting them is a proposed follow-up, not a
silent edit.

Allowed claim: A Secure SDLC and task-level evidence mapping aligned with NIST SSDF 1.1 have been implemented; partial and unimplemented tasks are disclosed. This is not full implementation of every task.
