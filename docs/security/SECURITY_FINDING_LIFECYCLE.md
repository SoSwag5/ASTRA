# Security finding lifecycle

Use one durable record per suspected or confirmed security weakness. Store
undisclosed vulnerability details in an access-controlled location and keep only
safe references in the public repository.

## States

`DETECTED` → `TRIAGED` → `CONFIRMED` or `FALSE POSITIVE` →
`REMEDIATION PLANNED` → `REMEDIATED` → `REGRESSION TESTED` → `VERIFIED` →
`CLOSED`

- **DETECTED:** source, date, initial evidence, and reporter recorded.
- **TRIAGED:** ownership, exposure, urgency, disclosure sensitivity, and safe
  reproduction plan recorded.
- **CONFIRMED:** weakness and affected scope reproduced with synthetic data;
  severity uses evidence and a full CVSS v4.0 vector only when applicable.
- **FALSE POSITIVE:** reviewer records why the behavior is not a weakness and the
  evidence that disproves it; then close.
- **REMEDIATION PLANNED:** fix, negative test, release class, disclosure,
  compatibility, and rollback are agreed.
- **REMEDIATED:** implementation is committed; this is not closure.
- **REGRESSION TESTED:** the negative reproduction and relevant surrounding tests
  pass on the remediation commit.
- **VERIFIED:** an independent reviewer verifies the exact commit and evidence.
- **CLOSED:** release/disclosure/risk records are complete and no required action
  remains.

## Finding template

- **ID / title:**
- **State / state history with dates:**
- **Reporter / owner / independent reviewer:**
- **Private evidence location:**
- **Affected versions, source SHA, components, and data:**
- **Preconditions and safe synthetic reproduction:**
- **Impact, likelihood, CWE if confirmed, CVSS v4.0 score/vector if used:**
- **Root cause:**
- **Remediation and alternatives:**
- **Negative regression and surrounding tests:**
- **Threat-model, risk, ADR, framework, SBOM, and release deltas:**
- **Disclosure/advisory decision:**
- **Remediation commit / verification result / fixed release:**
- **Residual risk and Owner decision:**
- **Closure rationale:**

Release blockers remain blocking until VERIFIED or covered by an Owner decision
that the applicable policy permits. Documentation changes alone do not remediate
a product weakness.
