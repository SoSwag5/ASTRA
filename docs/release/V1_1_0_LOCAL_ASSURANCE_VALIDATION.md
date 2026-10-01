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
  level and literal dynamic imports, then checks import-time dependencies.
  Fifteen challenge scenarios cover lazy absolute/relative imports, aliases,
  nested methods, conditional imports and common literal loaders, with benign
  strings/comments and similarly named modules as controls. The exact original
  fictional bypass is now rejected before it executes. Computed imports,
  transitive lazy dependencies and complete runtime reachability remain outside
  this dependency test's claim; introducing AI classification requires separate
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

## Validation status

Initial corrected assurance and release-gate tests: **74 passed**. The exact
original lazy-import challenge produces the expected assertion failure naming
`backend.providers`; the fictional probe was removed before committing.

The committed snapshot and full-run results will be recorded here after
execution. Full-suite, consolidated-suite, frontend, SCA and final publication
reruns are **NOT RUN for the corrected committed snapshot** at this draft stage.
Do not use this provisional record as a release PASS.

All application tests use isolated fictional data. No live scan, OAuth consent,
mailbox, real CV/application record or app AI request is authorized by this run.
There is no new production behavior, dependency, schema or release artifact.
