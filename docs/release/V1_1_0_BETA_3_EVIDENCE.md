# v1.1.0-beta.3 candidate — implementer's technical self-check

**Status: candidate, unpublished. READY FOR INDEPENDENT REVIEW — not approved, not
PASS for release.** These are the implementer's own checks (Claude Code, 3 October
2026), not independent verification. Base `1896f1ee105e0c5558461c71a75a7077b2f6abad`,
branch `feature/beta-3-usability`. The exact commit SHA is stated in the task report
and `git log`; later commits supersede it.

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

## NOT RUN

Browser/UI acceptance, packaged ZIP build, clean install, SBOM/provenance, hosted CI
(CodeQL, dependency audit), release security gate, independent review, another-PC
novice acceptance, live Gmail/OAuth, real scans, AI requests, upgrade on a real
workspace. The manual and automatic checklists in the
[plan](../planning/BETA_3_RELEASE_PLAN.md) remain open.
