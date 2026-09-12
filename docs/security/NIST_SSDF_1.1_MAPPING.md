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
| PW.1.1 | IMPLEMENTED | STRIDE boundaries and abuse cases reviewed. | docs/security/THREAT_MODEL.md | Revisit on design change |
| PW.1.2 | IMPLEMENTED | Requirements, risks and decisions tracked. | docs/security/RISK_REGISTER.md; docs/security/OWASP_ASVS_5.0.0_MAPPING.csv | Review every release |
| PW.1.3 | PARTIAL | Native credential store and structured local events. | backend/privacy.py; backend/security_events.py | No identity/log service integration; intentional local scope |
| PW.2.1 | PARTIAL | Automated boundary regressions plus maintainer review. | tests/security/test_http_boundary.py; docs/security/ARCHITECTURE_INVENTORY.md | No independent design reviewer or full design-rule verification |
| PW.4.1 | PARTIAL | Pinned maintained dependencies. | requirements.lock.txt; frontend/package-lock.json | Supplier/component assurance remains incomplete |
| PW.4.2 | PARTIAL | Reusable central security controls. | backend/policy.py; backend/document_security.py | Complete ASVS verification outstanding |
| PW.4.4 | PARTIAL | SCA and inventory available. | scripts/generate_sbom.py; .github/workflows/ci.yml | Audits do not establish all supplier requirements |
| PW.5.1 | PARTIAL | Coding controls and regressions present. | tests/security; docs/security/OWASP_ASVS_5.0.0_MAPPING.csv | Open control-level findings |
| PW.6.1 | PARTIAL | Modern Python/TypeScript tooling. | setup.bat; frontend/tsconfig.json | Bundled native toolchain security not fully assessed |
| PW.6.2 | PARTIAL | Explicit runtime and exact dependencies. | setup.bat; requirements.lock.txt | 3.14 verification and native build-option inventory pending |
| PW.7.1 | IMPLEMENTED | Manual and SAST verification strategy defined. | docs/security/SECURITY_TESTING.md | Review by change risk |
| PW.7.2 | PARTIAL | Findings recorded and SAST configured. | .github/workflows/codeql.yml; docs/security/RISK_REGISTER.md | CodeQL never executed remotely |
| PW.8.1 | IMPLEMENTED | Executable boundary/abuse tests required. | docs/security/SECURITY_TESTING.md | Maintain coverage |
| PW.8.2 | PARTIAL | Disposable regression suite. | tests/security; tests/conftest.py | Full ASVS and clean-host acceptance pending |
| PW.9.1 | IMPLEMENTED | Local/rules/demo/security defaults defined. | docs/security/DATA_PROTECTION.md; backend/main.py | Public exposure unsupported |
| PW.9.2 | PARTIAL | Defaults implemented/documented. | setup.bat; README.md; backend/main.py | Clean-host installation not yet proven |
| RV.1.1 | PARTIAL | Intake and advisory sources specified. | SECURITY.md; .github/dependabot.yml | Private channel and alerts not active |
| RV.1.2 | PARTIAL | Source review found privacy weakness. | tests/security; docs/security/RISK_REGISTER.md | Hosted SAST and repeat review pending |
| RV.1.3 | PARTIAL | Owner, disclosure and triage process defined. | SECURITY.md; docs/security/VULNERABILITY_MANAGEMENT.md | Private reporting not active |
| RV.2.1 | IMPLEMENTED | Risk rationale/classification and blocking decisions recorded. | docs/security/RISK_REGISTER.md | CVSS only on confirmed suitable vulnerability scope |
| RV.2.2 | PARTIAL | Private-report issue remediated; other responses tracked. | scripts/publication_gate.py; docs/security/RISK_REGISTER.md | Close remaining release blockers |
| RV.3.1 | IMPLEMENTED | R-06 root cause recorded. | docs/security/RISK_REGISTER.md | Apply to subsequent findings |
| RV.3.2 | NOT IMPLEMENTED | No longitudinal root-cause trend evidence. | docs/security/OWASP_SAMM_ROADMAP.md | Quarterly pattern review |
| RV.3.3 | PARTIAL | Expanded source/history and report pattern checks. | scripts/publication_gate.py | Complete manual content/image review and class-wide tests |
| RV.3.4 | IMPLEMENTED | Privacy incident feeds mandatory artifact review and evidence gate. | docs/security/SECURE_SDLC.md; docs/security/RISK_REGISTER.md | Verify sustained operation |

Allowed claim: A Secure SDLC and task-level evidence mapping aligned with NIST SSDF 1.1 have been implemented; partial and unimplemented tasks are disclosed. This is not full implementation of every task.
