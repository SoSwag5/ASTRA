# v1.1.0-beta.3 candidate — evidence record

**Status: candidate, unpublished. Not approved, not released. The package built from `e465625` failed exact-package browser testing (installer-order defect below) and must not be published; a repaired source awaits a new exact package and re-verification.**
Reviewed source anchors: `c494112` (reviews, browser pass) and `ddb087c` (final
two-string copy change; backend content identical to `c494112`). Base
`1896f1ee105e0c5558461c71a75a7077b2f6abad`, branch `feature/beta-3-usability`.
Hosted verification of the candidate is pending on
[draft PR #86](https://github.com/SoSwag5/ASTRA/pull/86). Private verification logs
are not public; this record does not link them.

## Independent and browser evidence (scoped)

- **Source review (separate read-only Codex reviewer), SCOPED APPROVE at `c494112`:**
  67 targeted backend tests passed, plus two adversarial actual-startup probes for
  zero-source upgrade and record preservation. Seeding made zero network requests and
  started no scan; `backend/models.py` unchanged. Backend content is identical at `ddb087c`.
- **UI review (separate read-only Codex reviewer), SCOPED PASS at `c494112`:** 37
  component/model checks plus 12 atomic-reopen assertions. This is component testing,
  not a physical browser run.
- **Root browser pass (Codex) on the built `c494112` in an isolated fictional workspace,
  from a source checkout:** Finance CV import and persistent facts confirmation; optional
  tracker skip; custom-only roles (Financial Analyst, Business Analyst, Policy Research
  Assistant) saved; dirty and pending busy locks; saved-write plus failed-refresh
  recovery; dismissal and reopen showing the latest unconfirmed facts; a failed
  explicit reopen refusing a stale dialog, with retry working. Sources directory groups
  (including hospital and government), the 77/52/25 counts, filter empty state,
  non-HTTPS error, a valid fictional manual link shown as unverified; Mark checked is the
  user's own review only. A scan preview was cancelled without creating a run. OS reduced
  motion was true and Match system respected it; explicit Full showed page and button
  animation durations; Reduce removed transitions; rapid period changes kept the latest
  selection and date. At 390px width there was no horizontal overflow; keyboard dialog
  containment and Escape were checked; dark and light were reviewed visually.
  These are source-checkout browser checks. They are not packaged-release proof, not
  200% zoom, not every historic action and not broad ranking validation.
- Reviewers were Codex reviewers. Claude Code was the implementer and used the pinned
  Anthropic frontend-design skill; no Claude independent review is claimed.

## Implementer self-check

The implementer's own results (Claude Code, 3 October 2026):

| Check | Result |
|---|---|
| Frontend `npm test` (13 scripts; source/model/SSR-markup checks, not browser runs) | PASS |
| Frontend `npm run build` (`tsc -b` + vite) | PASS |
| Targeted pytest: starter_catalog, cross_major_workflow, search_workspace | 13 passed |
| Full backend pytest, isolated fictional `DATABASE_URL` and `HUNTER_DATA_DIR`, keyring fail backend | 2219 passed, 1 skipped, 0 failed |
| `scripts/publication_gate.py` (pattern scan, not proof of no PII) | PASS, 1427 objects, 0 findings |
| `backend/models.py` | unchanged |

Test isolation: tests use a test-only catalogue seam
(`tests/test_campaign_reliability.isolated(..., bundled_sources=False)`) so hermetic
fixtures do not receive real boards; `tests/test_starter_catalog.py` runs real
startup and a process restart with the bundled catalogue. No production flag skips
tests or weakens scan behaviour.

Source catalogue truth: 77 unique destinations, 74 manual links and 3 public feeds;
52 recorded route/feed checks succeeded (49 manual pages and 3 JSON feeds); 25 need a
browser check or were inconclusive. Not 77 verified working, not 50 automated feeds,
not matching validation.

## Later changes

`c494112`: setup now opens only after the latest saved state reloads (`openSetup`), so a
dismissed pending refresh cannot reappear as stale confirmed facts. Frontend only:
`npm test` and `npm run build` re-run and pass; the backend suite above was not
repeated because no backend or test file changed. Source-pattern checks, not a
browser run (the root browser pass above later exercised it).

`ddb087c`: two copy strings only (neutral setup pending hint; scan intro mentions the included boards). `npm test` and `npm run build` passed; guards unchanged.

## Installer-order defect caught by the exact package (after e465625)

The exact package built from `e465625` was browser-tested and the failure was caught:
`setup.bat` runs `scripts/initialize.py`, which creates the Settings row before the
server first starts, so startup no longer saw a fresh workspace and added the three
starter feeds **paused**. After setup, Start scanning reported that no source was
enabled, contradicting the promise of ready starter feeds. Source-only startup tests
had missed the real installer ordering. That candidate is not to be published.

Repair (new source anchor; package and browser re-verification pending):
`scripts/initialize.py` now reads freshness before initializing, then seeds the catalogue
with that flag, so only a truly new workspace enables the three feeds. Existing
workspaces, including those with zero sources, still get them paused and no choice is
overwritten. `backend/models.py` is unchanged. New integration tests run the actual
`scripts/initialize.py` in a child process, then the real app lifespan: a fresh
install has 77 sources, 3 enabled, no jobs, applications or scans and no network;
after pausing a feed and editing a manual link, repeated setup and restart preserve
every choice; an existing zero-source workspace gets 77 sources, all paused. The new
tests fail against the previous installer script. `scripts/clean_install.py` now also
asserts the three enabled starter feeds straight after the real installer, so the
hosted exact-package check covers this permanently. Implementer results for the repair: `tests/test_starter_catalog.py` 8 passed (2 new tests fail against the old installer script); full backend suite on isolated fictional data 2221 passed, 1 skipped, 0 failed. `clean_install.py` itself was not executed here (needs the exact ZIP); its new assertion's response shape was checked against a real installer-then-startup run (three feeds, all enabled). Frontend untouched. No browser or hosted result is claimed for the repaired source.

## NOT RUN

Packaged ZIP build, clean install, SBOM and provenance, hosted CI (CodeQL, dependency
audit, full hosted suite) and the release security gate (pending on PR #86), 200% zoom,
another-PC novice acceptance, live Gmail/OAuth, real scans, AI requests, upgrade on a
real workspace. Remaining unchecked boxes in the
[plan](../planning/BETA_3_RELEASE_PLAN.md) carry the reason they are partial.
