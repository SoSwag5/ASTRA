# Beta 3 usability — implementation handoff

## Session declaration

Owner: Claude Code (sole implementation owner). Ownership history: Claude began
the work and stopped at a usage quota; Codex continued under explicit Owner
authorization (fixes, tests, catalogue research); Claude now finishes at the
Owner's explicit request while Codex verifies separately. Technical self-checks
here are not independent verification. Branch/worktree:
`feature/beta-3-usability` in its own `astra-beta-3-usability-claude` worktree.
Base SHA: `1896f1ee105e0c5558461c71a75a7077b2f6abad`. Task: frontend usability
for beta 3 — setup and search-focus feedback, app-wide interaction motion with
reduced-motion parity, an animated disclosure, and clearer optional Gmail
setup. Change class: compatible early-beta usability and source change (frontend, a
read-only bundled source catalogue seeded additively at startup, release path and
version metadata for beta 3); no security control is weakened and no dependency
is added. `backend/models.py` is unchanged. Protected concurrent work: the `astra-beta-release-publish`,
`astra-beta-2-remediation`, `astra-beta-3-startup-claude` and
`astra-beta-3-startup-review` worktrees, the live localhost:8787 installation,
CVs, data and `.claude` files (none touched). Starting evidence: clean tree at
base; `npm ci`, all 12 `npm test` scripts and `npm run build` pass at base. The
`npm test` scripts are source/model/SSR-markup checks, not browser runs.
Next action: implement, then build, `npm test` and targeted isolated pytest.

## Finish record (3 October 2026)

Completed by Claude Code in this session: pending/busy guards (Close and Escape
are ignored while a write runs; with a saved-but-unrefreshed state Close is
allowed and asks the server once more, so no one is stranded and `next` sends only
`wizard_step`, never stale settings); source-level regression checks in
`frontend/check-usability.cjs` (labelled as source/model checks, not browser runs);
beta 3 customer docs, changelog, notes, plan, candidate evidence and project
state; `review-candidate.yml` paths moved to beta 3 (historical beta 2 records
kept). Results and commit are in the
[candidate evidence](../release/V1_1_0_BETA_3_EVIDENCE.md).

Not done: browser/UI acceptance, packaged ZIP, hosted CI, independent review,
another-PC novice test, publication. Next action: Codex verifies the exact commit
and prepares hosting; the Owner decides publication.

## Review repair: stale setup reopening (after 13814791)

An independent reviewer found that Escape (and a failed fire-and-forget retry on
Close) could leave the cached profile in place, so reopening setup from Settings
showed a stale confirmed profile after a successful write whose reload failed.
Repair: `openSetup()` in `frontend/src/main.tsx` awaits the atomic `reload()`
before opening setup at step 1, refuses to open on failure with a visible error
toast (the Settings button remains the retry), and ignores duplicate requests
while loading. Settings' Open setup wizard uses it; startup already awaited
`reload()`; these are the only two `setWizard(true)` sites (checked in
`check-usability.cjs`). Escape on the wizard now also makes a best-effort reload.
In-flight (`aria-busy`) Close/Escape stays blocked; pending dismissal stays allowed.
`npm test` and `npm run build` pass; the new checks read source and are not a
browser run. Backend unchanged.

## Installer-order repair (after e465625)

The exact package showed that `setup.bat` -> `scripts/initialize.py` created the Settings row before first startup, leaving starter feeds paused. `initialize.py` now captures freshness first and seeds with it; integration tests run the real script then lifespan; `clean_install.py` asserts three enabled feeds. See the candidate evidence. Package, browser and hosted re-verification are pending.
