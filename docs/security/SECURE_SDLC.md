# ASTRA Secure SDLC
Baseline: NIST SP 800-218 SSDF 1.1. Scope: local Windows application, source, dependencies, build and release assurance. Owner for every stage: **Maintainer**. This is a solo-maintainer process; no independent two-person review is claimed.

| Stage | Security activities and controls | Entry | Required evidence / exit |
|---|---|---|---|
| PLAN / GOVERN | Maintain requirements, applicability, risk priorities, tool versions and ownership; review every release and after a material boundary change. Manual. | Change request with intended scope | ASVS mapping, SSDF mapping, risk register, named owner and acceptance criteria |
| DESIGN | Threat Modeling and Secure Architecture Review; inspect data flows and STRIDE abuse cases; record alternatives and residual risk. Manual plus boundary regressions. | Requirements defined | THREAT_MODEL.md and architecture inventory updated; material design gaps block release |
| IMPLEMENT | Secure Implementation; parameterized persistence, typed inputs, URL validation, bounded parsing, no model tools; update lock and regression for each fix. Manual review plus dependency integrity enforcement. | Reviewed design | Source diff, test, lock hashes; no private fixtures or credentials |
| VERIFY | Security Regression Testing, SCA, frontend tests/build, publication scan and CodeQL SAST. Automated; manual review checks coverage and findings. | Reproducible source snapshot | Evidence from tests/security, audit results and CI jobs bound to source; missing or skipped mandatory checks fail |
| RELEASE | Release Assurance and Supply-Chain Assurance: clean source, build_release.py, validated SBOM, archive-content/manifest verification, hosted attestations, independent verification, clean Windows installation. | Verification prerequisites pass | Release Security Gate passes; assurance report identifies artifact hash, source, run and risks; explicit owner authorization before public push/release |
| OPERATE / RESPOND | Vulnerability Management, backups, dependency updates, incident triage and recovery exercises. Manual operations supported by security_events and reliability backup routines. | Supported installation/release | Closure and recovery evidence; root-cause findings feed requirements and tests |

## Enforced controls and locations
- `scripts/publication_gate.py`: tracked/untracked non-ignored source, reachable history, commit metadata; content heuristics require supplementary document/image review.
- `requirements.lock.txt`, `setup.bat`: exact product dependency versions and wheel hashes.
- `requirements-assurance.lock.txt`: isolated SCA/SBOM/validation tools, not product dependencies.
- `scripts/generate_sbom.py`, `scripts/validate_sbom.py`: complete locked Windows environment, npm dependency graph, strict CycloneDX schema validation.
- `.github/workflows/ci.yml`, `codeql.yml`, `release.yml`: configured enforcement; remote execution is pending until an authorized repository exists.
- `scripts/release_security_gate.py`: exact mandatory job outcomes, source/artifact identity and ASVS blocking findings; never infer PASS from file existence.

## Exceptions and approvals
Maintainer records risk ID, affected requirement, rationale, likelihood/impact, compensating control, evidence, expiry (maximum 90 days), and recheck trigger. Proposed acceptance is distinct from owner approval. No exception can turn an unexecuted check into PASS or waive private data, invalid SBOM, failed provenance verification, or an applicable L1 failure for this v1.0 target. L2 limitations may remain documented where they do not invalidate the intended claim. Record source commit and artifact digest in every release decision. Gate success is technical evidence; public publication still requires owner authorization.

Review requirements and action/tool pins monthly and at each release. Dependabot PRs are reviewed for upstream release notes, changes in permissions and actual tests. Pin updates do not prove safety. Track open findings, overdue fixes, applicable ASVS gaps, regression failures and executed clean-install/provenance checks. No numerical maturity target overrides evidence.
