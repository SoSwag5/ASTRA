# Issue #48 local corrections and validation

**Owner-authorized implementation owner: Codex, 2026-10-02.** Claude's two
commits are preserved. Codex took over after the Owner said "you proceed".
This record covers local tests/documentation only; it does not freeze or
approve a complete v1.1 release. Independent re-review of these corrections
is pending. The [release evidence pack](V1_1_0_RELEASE_EVIDENCE_PACK.md)
retains the technical verdict BLOCKED.

## Corrections

- **R48-1:** importing mailbox/state modules did not detect AI imports inside
  functions. The guard now checks known declared imports at every AST nesting
  level and supported positional literal import calls, then checks import-time dependencies.
  Fifteen challenge scenarios cover lazy absolute/relative imports, aliases,
  nested methods, conditional imports and common literal loaders, with benign
  strings/comments and similarly named modules as controls. The exact original
  fictional bypass is now rejected before it executes. Computed imports,
  transitive lazy dependencies and complete runtime reachability remain outside
  this dependency test's claim, as do keyword/indirect loader forms;
  introducing AI classification requires separate
  design and runtime abuse review.
- **R48-2:** the unreleased changelog now covers included #37–#46/#46.2 changes,
  and [release-note drafts](V1_1_0_RELEASE_NOTES_DRAFT.md) describe the included
  behavior, limits, migration prerequisites and missing package verification.
  Unmerged #47 and offline-model candidates are distinguished from that scope.
- **Source inventory:** records the latest local #47 visual revision
  `772fe7e87586720d9db6bed06cb1a12d3af14649`, distinct from draft PR #78's older
  head. Neither is included in master or validated by these local #48 results.
- **Evidence attribution:** the prior Codex frontend/publication checks at
  `fbbafe433ecbcf4b21f5c494dea285390cd30ad0` remain separate from Claude's
  implementation evidence and from this correction's self-verification.

## Exact source and environment

Committed test/product snapshot:
`90e48ea76620ff1d876fb2907bb194b4c219916d`, based on master
`22642e88f516f827c1dc4250bc72eb259306fafd`. The full/security/frontend checks
use a clean detached single-branch clone with its own lockfile-installed
frontend dependencies and production build. Python 3.13.2's installed product
versions match all 47 lock pins; Node is 24.21.0. pip-audit 2.10.0 uses a separate
hash-enforced assurance environment. Application tests isolate both database
and data directory before application imports.

The final evidence commit changes documentation/assessment records only. Its
exact SHA, tree comparisons and final scan outputs are retained in the
Owner-local handoff, not represented as the source of earlier test runs.

## Source-bound results (2026-10-02)

| Check | Result | Evidence file / scope |
|---|---|---|
| Original lazy-import bypass | Expected FAIL, exit 1 | `lazy-probe.txt`; fictional probe added temporarily, rejected before execution and removed before commit |
| Initial corrected assurance/gate tests | 74 PASS | `targeted.xml`; working tree that became 90e48ea |
| Consolidated v1.1 security suite | 532 PASS, no failures/errors/skips; 1,587 deselected by the requested marker | `security-suite.xml`; exact 90e48ea |
| Full Python suite | 2,118 PASS, one existing intentional skip, no failures/errors/deselection; 467.52 seconds | `full-suite.xml` / `full-suite.txt`; exact 90e48ea, no deselection |
| Frontend tests | All six scripts PASS | `frontend-tests.txt`; exact 90e48ea |
| Production frontend build | PASS | `frontend-build.txt`; exact 90e48ea, existing bundle over 500 kB warning retained |
| Python SCA | **FAIL**, exit 1: six advisories in pypdf 6.18.0 | `python-sca.json`; exact unchanged 90e48ea product lock |
| npm SCA | PASS, zero advisories at every severity | `npm-sca.json`; exact 90e48ea lock |
| Changed ASVS records and gate tests | 74 PASS | `docs-check.xml`; final evidence working tree, product/test source unchanged |
| Official ASVS requirements | 345 IDs, levels and requirement text unchanged | `asvs-current.json`; current 15.2.1 is PARTIAL; assess_asvs returns the expected blocker |
| Final branch-history publication scan | Runs after this evidence commit; result in final exact-SHA handoff | Scan is branch-local history evidence, not an archive or all-worktrees approval |

The sole skip is the existing `test_must_not_collapse[MN15_three_record_transitive_bridge]`,
not a newly disabled check. All 230 inventoried test functions have collected
cases in the passing consolidated XML. The repository publication regression
ran and passed inside the full suite; no test was deselected.

The original bypass was a function-local import of backend.providers inside a
fictional mailbox module. The corrected guard rejects that source; no provider,
mailbox or model call occurs. The 15 challenge cases cover supported imports and
benign controls, without claiming full runtime reachability.

## Fresh findings and final disposition

The six [pypdf findings](../security/V1_1_PYPDF_SCA_FINDINGS.md),
SF-2026-48-01 through -06, are TRIAGED. The affected installed/locked version
and text-extraction operation are verified; an application exploit is not.
Existing parser bounds are containment, not a clean SCA result. The proposed
upgrade and bounded regression plan are concrete, but no dependency change,
waiver, independent remediation verification or fixed artifact exists.

ASVS 15.2.1 is PARTIAL after this audit. The current Level 1 counts are
39 PASS, 30 N/A and 1 PARTIAL. The machine gate rejects the unresolved control;
neither its logic nor the official requirements were weakened. Previous clean
scan/baseline evidence remains historical only. This update records incomplete
verification rather than asserting an unmeasured overdue deadline.

**Local correction work is ready for independent re-review; release verdict
remains BLOCKED.** Dependencies need a separate reviewed remediation. The
unmerged #47 source, two-account scope, R-16/17/18 Owner decisions, as-built
threat/framework approval and exact package/hosted assurance prerequisites also
remain open in the evidence pack. This pass cannot close issue #48 or approve
a release merely because its tests pass.

## Evidence digests

| Owner-local evidence file | SHA-256 |
|---|---|
| full-suite.xml | `79e12fb42355eac86078910f2562e96ef1cf79875e577d748c33b16a795b7cb9` |
| security-suite.xml | `561ab243eb365c9915b069d2491efef4692af2d32d6ba9a5d4739e1644c70e44` |
| python-sca.json | `be9c0a15ac7e6116c40178e0bfdddb26532cc22101cf3c4a5a6a56eff3b04808` |
| npm-sca.json | `af8178de00f16cafb242fbe6310ab2cd3c7f4bc3dda373864086b1d88b3e7679` |
| docs-check.xml | `feaf1c6b16b76ac6f46c5143400a6481ea1c7b0ec046780bbacd8820a43e3bf0` |

## Evidence custody and checks not performed

Raw logs, XML, scan JSON, checksums and the final exact-SHA handoff remain
Owner-local in `ASTRA_48_FINAL_QA_2026-10-02`. The Python SCA JSON hash is recorded
in the finding intake; the evidence manifest records the other digests. No
private logs or machine paths are committed. Human diff review supplements the
publication pattern scanner; neither proves absence of every possible PII item.

Hosted CI, current CodeQL alert triage/Dependency Review, a complete frozen
candidate, package build/SBOM/attestations, exact-ZIP clean install/upgrade/rollback
and final hosted release gate are NOT RUN. A local fail-closed gate probe with
missing hosted/artifact inputs is distinct from release execution. Independent
re-review of Codex's implementation and explicit Owner release approval are
pending. No push, merge, tag, upload or publication occurred.

All application tests use isolated fictional data. No live scan, OAuth consent,
mailbox, real CV/application record or app AI request is authorized by this run.
There is no new production behavior, dependency, schema or release artifact.
