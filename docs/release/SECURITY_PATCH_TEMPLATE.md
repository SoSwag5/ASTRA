# Security patch record — ID / VERSION

Keep this record private until the Owner approves disclosure when the finding is
not yet public.

- **Finding ID:**
- **Release classification:** Security patch / emergency hotfix
- **Owner / implementation owner / reviewer:**
- **Affected versions:**
- **Fixed version:**
- **Disclosure state and advisory:**

## Workflow

1. Triage privately and assign a finding owner.
2. Confirm scope with a safe synthetic reproduction.
3. Agree the narrow remediation, negative regression, release class, and
   disclosure plan.
4. Implement on an owned security branch and run the required focused and
   surrounding checks.
5. Obtain independent review of the exact remediation commit.
6. Build once, verify the exact artifact, and complete the evidence pack and
   fail-closed release gate.
7. Obtain Owner approval before tagging, publishing, or disclosing.

## Summary and impact

Describe the weakness, affected asset, attacker prerequisites, scope, and user
impact. Use CWE only for a confirmed weakness. If scoring a vulnerability, use
CVSS v4.0 with the complete vector and assumptions.

## Reproduction and root cause

- Safe synthetic reproduction:
- Root cause:
- Affected paths/components:
- Evidence location and access restrictions:

## Remediation

- Chosen fix and rationale:
- Alternatives considered:
- Compatibility/data/deployment impact:
- Rollback plan:

## Verification

- Negative regression test:
- Targeted tests:
- Relevant SAST/SCA/security checks:
- Full regression and build/install checks:
- Exact source SHA / artifact digest:
- Independent reviewer result:

## Governance deltas

- Security finding lifecycle state:
- ADR / threat-model delta:
- Risk record / Owner acceptance:
- ASVS / SSDF / SAMM / SBOM / SLSA delta:
- Changelog/release notes/advisory:

## Release decision

- Technical gate: PASS / BLOCKED
- Deferred checks, reason, owner, and expiry:
- Owner approval for exact source/artifact:
- Publication and notification plan:

Emergency handling may shorten elapsed time but does not turn skipped mandatory
controls into PASS.
