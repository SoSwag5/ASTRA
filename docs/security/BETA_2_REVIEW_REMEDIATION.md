# Beta 2 review remediation — 2 October 2026

Codex is the sole implementation owner of `fix/beta-2-remediation`, based on
`87c2f9260d74a5578021ee767ecdc30d67f66fd8`, by the Owner's explicit instruction
to perform the corrections here. The supplied Claude review summary informed
the investigation. Its complete report and independent execution evidence were
not supplied. Verification of these changes is technical self-review, not
independent approval. Published beta 1 artifacts and other worktrees are preserved.

## Finding records

| ID | Confirmed weakness / root cause | Correction / negative evidence | State |
|---|---|---|---|
| B2-01 | Default localhost development origin admitted mutation requests from a separate browser origin. | Default accepts only the actual application port; an explicit development opt-in is restricted to the known development origin. Foreign-origin negative tests retain unchanged data. | Remediation implemented; final source-bound review pending |
| B2-02 | Raw PDF byte heuristics could miss escaped active-content names. | Follow decoded catalog/object references inside the existing bounded subprocess, reject active actions/embedded content, bound graph complexity, and validate legacy original-PDF downloads before serving. Atomic rejection preserves prior data. | Remediation implemented; final source-bound review pending |
| B2-03 | Literal section headings and PDF painting order could omit profile/skill facts. | Explicit heading aliases, delimiter-separated skills and layout extraction; fictional delayed-summary and upload regressions. | Functional correction; not a security certification |
| B2-04 | First custom-only career save generated technical targets before marking focus confirmed. | Set the confirmed flag before computing saved target titles; five PDF-to-confirmed-scan regressions require custom-only roles. | Functional correction |

B2-01 requires a separate malicious browser origin; same-OS-user processes
remain inside the documented trust boundary. B2-02 requires importing or
already holding a crafted PDF. No exploitation in real records is established.
No CVSS score is assigned from the limited evidence. Detailed reproductions and
failed pre-fix runs are kept in Owner-local QA. Public regression fixtures use
only synthetic data.

The security findings are not labelled VERIFIED or CLOSED by their implementer.
Independent verification or an explicit, policy-permitted Owner disposition
remains necessary before treating them as closed. Mandatory gates stay fail closed.

## Threat and framework delta

Browser origins and imported PDFs are existing entry points; the corrections
tighten validation at those boundaries. New assets, identities, cloud flows,
permissions or external submission paths are not introduced. Ordinary web/mail
links in inert PDFs remain supported. Complex, malformed or active PDFs can be
rejected even if a reader displays them; originals are retained, never silently
deleted. The bounded parser is not a malware detector or a sanitizing guarantee.

NIST SSDF practices for vulnerability remediation, verification and release
integrity gain regression evidence. OWASP ASVS request-origin and input/file
handling evidence changes within the existing scoped mappings; applicability
and level claims do not increase. OWASP SAMM verification/defect-management
activity is documented without raising a maturity score. Python/npm dependency
versions are unchanged. A fresh CycloneDX 1.7 SBOM and exact-artifact provenance
checks are still required; no SLSA Build level is asserted.

## Compatibility and rollback

No database schema migration is introduced. Existing confirmed focus and AI
provider choices are preserved. Setup's stored completion marker remains 10;
legacy advanced steps resume on the new finish page. New users use rule-based.
Default development origin access now requires explicit opt-in. Unsupported PDF
originals remain on disk but cannot be downloaded through ASTRA until replaced
by an inert supported CV.

Test in a separate extracted directory. Keep the previous installation and a
private data backup; do not run two copies against the same database. Returning
to beta 1 also returns its known limitations and is not a security remedy.
General automatic upgrade/rollback remains unvalidated.

## Gap disposition

The outside-profession fixture is retained with `OUTSIDE` relevance uncertainty
and a lower score, consistent with the existing conservative policy. Extending
hard rejection, collecting live cross-career coverage and calibrating relevance
are deferred to a separately evaluated change. Protected evaluation inputs and
labels are untouched. No unknown eligibility is inferred as eligible.

Gmail second-account/live validation and R-16/17/18 remain open; this candidate
does not finish issue #48's final v1.1 assurance scope.
