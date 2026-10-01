# Visual revision validation and handoff

Session: 2026-09-30, Asia/Dubai. Implementation owner: Codex, explicitly
assigned by the Owner. Branch: `feature/47-visual-motion`; worktree basename:
`astra-47d-visual-motion`. Starting SHA: `fe8e8a85728f06b302aaacd713fe6e9e01cf7d6a`.
This record is versioned with the candidate; the task handoff identifies the
exact ending SHA and final asset digests. Independent review is pending here.

## Work and boundaries

Audited and preserved inherited uncommitted edits, with an external local
backup before modification. Completed semantic recolouring, boot-time theme
preservation, browser chrome/favicon, page and section transitions, More tools
disclosure, common control states, recorded-event progress rails and truthful
loading/error feedback. Repaired observed narrow-sidebar clipping and header
overlap. Improved chart contrast, reduced-motion handling and missing-evidence
rules. Main checkout and other worktrees were not modified.

Changed areas: frontend shell, shared tokens/styles, Progress/model, Settings
appearance/focus, Today view entry, theme bootstrap/favicon, focused tests and
these design/governance records. No backend, schema, dependency version,
authentication, provider, scheduler or data-boundary code changed. No ADR,
threat-model delta, risk acceptance or security finding was needed for this
presentation-only revision. Existing risks remain unchanged.

## Executed checks

- Node **24.21.0**, `npm ci --ignore-scripts` from the existing lockfile:
  122 packages installed, audit reported zero vulnerabilities.
- `npm test`: PASS. Existing checks: 5 locale scenarios plus invalid-input
  fallbacks; three sorting modes; 9 safe-link scenarios; 117 Gmail OAuth safety
  checks; 4 Stop states; single-flight polling and 5 estimate texts;
  46 Progress rendering/wording checks; 30 Settings checks; 29 Gmail operations
  checks. Added **45** visual evidence/preference checks and **156** palette
  contrast pairs across light and dark.
- `npm run build`: PASS, 1,607 modules. Existing warning: `access.tsx` has both
  static and dynamic imports, so the dynamic import does not split a chunk.
- Real Chromium on isolated fictional data: **164 browser assertions** across
  1440px light/dark, 390px light/dark and 320px light. All seven main pages and
  all seven Settings sections inspected. Covered overflow, section focus,
  More tools keyboard expansion/inert collapse, dialog focus/trap/restoration,
  page motion, disclosure intermediate height, real-request loading delay,
  refresh failure/retry, theme chrome and OS/in-app reduced motion.
- **11 additional action/lifecycle assertions**: stable save button width,
  busy acknowledgement, refused-save feedback with preserved draft, real
  successful save to copied fictional data, saved weekly-target projection,
  synthetic active-scan counts changing then stopping, and unsupported
  View Transition fallback focus. Active scan responses were browser fixtures;
  no actual scan ran. Saved-target testing did not alter the original preview.
- Real-page matrix: zero JavaScript page errors and zero external requests.
  Screenshots and motion recordings are retained outside the repository.
- Final targeted reflow: **10 assertions**, Progress and Appearance at
  1440/1024/840/390/320px after the last layout adjustment, all passed.
- Changed-file publication pattern scan: **25 files, zero findings**; manual source review
  found no added private records, credentials, private paths or external assets.
  This scoped check is not a full history/archive publication gate.

## Limits and next step

No live CV, Gmail, application, scan or AI service was used. Backend regressions
were not run because backend code is unchanged. Hosted CI/SAST, a release
artifact, full publication gate and accessibility certification were not run
or claimed. Real browser evidence is Chromium only; unsupported View Transition
behavior was also exercised. Screen-reader semantics and keyboard behavior
were inspected, but no human assistive-technology usability audit is claimed.

Next: read-only independent review of the committed SHA in a separate
worktree, bounded remediation if necessary, and final loopback preview/asset
verification recorded in the task. Publication and release decisions stay
with the Owner. This implementation report does not independently approve
its own code.

## Bounded independent-review correction

A separate read-only reviewer independently tested and built initial visual
SHA `c64a5b9249922592cf531b38a6d8e31c1e593bc2`. Its synthetic render found one
P2: a composition with exactly one stage/outcome hid the visible legend.
The corrected candidate displays its label and count even for one segment,
with two additional rendering regressions (single rejected stage and all-failed
scan). Re-review and the corrected exact SHA are recorded in the task handoff.

## Research-led follow-up — 2026-10-01

Starting SHA: `01c92453d4179523805c7b09954a29a013a6dffe` on
`feature/47-visual-motion`. The Owner requested research into polished AI-built
interfaces, a 20-mistake audit, and implementation. Sources, application to all
20 items and deliberate limits are in [the research audit](UI_UX_RESEARCH_AUDIT.md).

Changes: content entrances and capped staggering, keyed tab content, animated
desktop navigation layout, interruptible native transitions with ordered
callbacks, structured Today/Applications loading, transform-based rail updates
and finite sheen, scrollbar reservation, mobile input sizing, safe-area offsets,
overlay overscroll containment and current browser titles. Existing palette,
evidence semantics, draft safeguards and reduced-motion choices remain in use.
No dependencies or backend files changed.

Executed on Node 24.21.0 using the existing installed lockfile dependencies:

- Full frontend test command: all 11 scripts passed, including **56 visual and
  preference checks** (11 new interruption/callback regressions) and **156
  contrast pairs**. The other suites passed with the counts recorded above.
- Production type-check and build: passed, 1,607 modules. The existing mixed
  static/dynamic import warning for `access.tsx` remains nonblocking.
- Fresh Chromium matrix: **164 assertions passed**, covering all seven main
  pages and all seven Settings sections at 1440 light/dark, 390 light/dark
  and 320 light; loading/retry, dialogs, focus, More tools and reduced motion.
- Additional motion/reflow run: **32 assertions passed**. Real pointer clicks
  25ms apart retained the final destination and focus; delayed content exposed
  actual entrance animations; sidebar and tabs responded; frame samples
  captured the rail moving between recorded one-quarter and one-half values;
  live OS reduced motion stopped movement and hover lift. Progress/Appearance
  also fit 1024, 840, 720, 390 and 320px. Resting Today had no active animation.
- Action/lifecycle run: **11 assertions passed** on copied fictional data:
  stable busy button, refused save with draft retained, real local successful
  save, saved target, mocked scan status progression/end, and fallback focus.
- No JavaScript page errors or external requests in the main matrix. The
  additional motion run issued no non-GET requests. Scan status was simulated;
  no scan, Gmail, CV or AI operation ran. Screenshots, frame samples and video
  remain outside the repository.

Browser coverage is Chromium on this Windows machine, not Safari/iOS or a
human screen-reader audit. No universal frame-rate or zero-layout-shift claim
is made. Backend and hosted security checks were not rerun for frontend-only
changes. Exact commit, scoped privacy scan, independent review and served-asset
verification are recorded in the final task handoff. Nothing was pushed,
merged, tagged or published.

### Independent P2 correction: native hit testing

Independent review of `911151050095a141530434caa562dcee38d75f34` passed the
frontend tests/build but found that the second pointer click during a page
transition could target HTML instead of the navigation button. A third click
masked that loss in the initial three-click probe. The reviewer reproduced
the failure at 25, 80, 120 and 200ms intervals. The initial candidate was not
approved.

The correction removes the implicit root and all interactive surfaces from
named snapshots. Headings and decorative navigation markers retain native
motion, while content entrances, palette changes and sidebar resizing animate
on the live DOM. This keeps controls available to hit testing. Departing
overlays retain their exit animation.

`scripts/check_motion_browser.py --url <loopback-fictional-preview>` is a
committed native-browser regression (requires installed Python Playwright and
Chromium). It passed **16 two-click scenarios / 48 assertions** at the four
intervals, desktop/mobile, light/dark: latest destination, focus and cleanup.
The 32 motion/reflow checks also passed again. The broader matrix and final
asset/re-review results for the corrected exact SHA are in the task handoff.
