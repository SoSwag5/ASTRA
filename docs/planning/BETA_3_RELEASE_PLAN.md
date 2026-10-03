# ASTRA beta 3 release plan — 2–3 October 2026

**Status (3 October 2026): beta3 is published.** Exact frozen source bf658efd83573ca44e5ae1c98254570e1e7900e7 / ZIP SHA-256 07d5bcbff219ed34dcc602612856064a1a469ad886e4b74ea8138a2203f87732 passed the hosted install, independent package/browser checks and final technical gate. All 19 public asset hashes and source-bound attestations were verified after publication. See the [release record](../release/V1_1_0_BETA_3_RELEASE_RECORD.md), [public download](https://github.com/SoSwag5/ASTRA/releases/tag/v1.1.0-beta.3) and [simple test checklist](../release/BETA_3_USER_TEST_CHECKLIST.md). Owner testing order: own-PC now, brother-PC after final v1.1; another-PC acceptance remains NOT RUN. Final issue #48, independent broad relevance and live/account/risk decisions remain open. Historical dated source checkboxes below are not new package runs; the current release record identifies exact executed scope. Optional future batches are proposals, not required extra version numbers.

The [complete next-update checklist](https://github.com/SoSwag5/ASTRA/releases/download/v1.1.0-beta.3/ASTRA_NEXT_UPDATE_PLAN.md) expands each future batch into manual, automatic and comparison checks. It is a publication-time plan; the Owner testing-order update above takes precedence.

## Where we stand

The public product is **v1.1.0-beta.3**, an early local-first beta. It imports a selectable-text PDF CV, lets you correct extracted facts and choose custom or technical target roles, collects supported public job boards after preview/confirmation, scores with rules, prepares documents for review and tracks applications. You apply on the employer's website. Opening ASTRA does not scan or submit anything. AI, Excel import and Gmail are optional.

The backend has substantial automated assurance, but this does not prove that a first-time user finds the app easy or that the top-ranked jobs are good. The biggest immediate gap is the path from an empty installation to a useful search. In beta 2, source lists depended on old migration scripts, action feedback was understated and some content changes were instant; the beta 3 candidate addresses these (see the sections below) but remains unpackaged. Public Gmail setup, another-PC acceptance and broad matching quality remain unvalidated. Docker startup has a known VERSION-file omission; do not advertise Docker as verified until fixed and run.

## Current release: beta 3 — make the existing workflow usable

One implementation owner works in an isolated branch; a separate reviewer checks an exact commit. This plan is acceptance criteria, not evidence of completion. All boxes remain open until the evidence record records an executed result. Technical self-checks by the implementer are not independent verification.

### A. Clear setup and actions — IMPLEMENTED, NOT YET VERIFIED

- [x] CV selection has a busy state, visible server-confirmed success, filename/context and next step. *(source browser check at c494112, fictional Finance CV; not packaged)*
- [x] Confirming facts shows a persistent check + “Facts confirmed” message; errors remain visible and explain retry. No false confirmation on failed writes. *(source browser check at c494112)*
- [ ] Career choices show hover, focus, press and selected states. Dirty changes explain why Continue is unavailable. Saving custom-only roles works without technical boxes. *(Not yet checked: custom-only roles saved and dirty/pending locks observed; hover/focus/press states were not individually checked)*
- [x] Optional tracker import can be skipped. Rule-based is the default/recommended option. AI is advanced and optional. *(source browser check at c494112: skip path; tracker import itself not exercised)*
- [ ] Every important action family has pending, success, failure and recovery feedback. A toast supplements persistent evidence; colour or hover alone is insufficient. *(Not yet checked: setup families observed; other action families and recovery paths not all exercised)*
- [ ] Setup focus is contained, headings readable, scrollbars useful and buttons comfortably spaced at narrow width and 200% zoom. *(Not yet checked: narrow 390px width showed no horizontal overflow and keyboard dialog containment was checked; 200% zoom NOT RUN)*

### B. Motion that answers the click — IMPLEMENTED, NOT YET VERIFIED

- [ ] Pages and Settings sections animate actual content; click targets remain live throughout. *(Not yet checked: explicit Full motion showed page and button animation durations; click-through during transitions not separately shown)*
- [x] Progress periods show selected state immediately and update figures for the latest request only, with a brief content transition. *(source browser check at c494112: rapid period changes kept the latest selection and date)*
- [ ] Accordions animate opening and closing; arrows rotate; keyboard activation and focus remain correct. Rapid toggles settle in the requested state. *(Not yet checked: component-level disclosure checks only; physical rapid-toggle browser check pending)*
- [ ] Drawers and dialogs enter/exit smoothly and return focus. No delayed action, double save or hidden overlay blocks the page. *(Not yet checked: dialog keyboard containment and Escape checked; enter/exit animation and focus return not individually confirmed)*
- [ ] Buttons, uploads, links, track cards and tabs have consistent hover/focus/press feedback. *(Not yet checked: not individually checked in a browser)*
- [x] Normal motion is visibly testable in Appearance; OS or app reduced motion removes nonessential movement while retaining all state information. *(source browser check at c494112: OS reduced motion true, Match system respected it, Full showed animation, Reduce removed transitions)*
- [ ] Typing, background polling and passive refresh do not replay decorative page entrances. *(Not yet checked: not checked in a browser)*

### C. Useful sources included — IMPLEMENTED, NOT YET VERIFIED

- [x] At least 50 distinct official destinations have individually recorded checks. Report reachable pages separately from robots/challenge blocks and unverified entries; never claim 50 automated feeds. Current catalogue: 77 unique destinations — 74 manual links and 3 supported public feeds. 52 recorded route/feed checks succeeded (49 manual pages and 3 JSON feeds); 25 need a browser check or were inconclusive. This is not 77 verified working sources and not matching validation. *(source browser check at c494112 shows the 77/52/25 truth; the checks themselves are dated research records, not live verification)*
- [x] Include government and hospitals/healthcare alongside companies, major UAE job portals and recruiters. No numeric padding with duplicate brands or generic homepages. *(source browser check at c494112: government and hospital groups present)*
- [x] Include a small, checked public-feed starter set (three on a fresh workspace: Cloudflare and Netcracker on Greenhouse, Lean Technologies on Ashby; existing workspaces receive them paused). Scanning requires user preview and confirmation; no startup network requests or scheduled scans. *(source review approved seeding at c494112; fresh and zero-source upgrade probes; not packaged)*
- [x] Expose the complete directory with search/group filters, counts and plain “Scan in ASTRA” / “Open website” labels. *(source browser check at c494112: groups, search filter and empty state)*
- [ ] Major portals include role/location search links where supported. LinkedIn/Indeed account scraping is outside this release; manual links and job-description import remain available. *(Not yet checked: role/location link behaviour not individually checked)*
- [x] Adding a supported company board or a manual link gives clear feedback. User-added links are labelled unverified. *(source browser check at c494112: valid fictional manual link shows unverified; non-HTTPS refused with an error; adding a supported board not exercised)*
- [x] Additive startup seeding is repeatable, does not create jobs/applications, does not overwrite custom links, re-enable paused feeds or change existing source preferences. *(separate source reviewer SCOPED APPROVE at c494112: 67 targeted backend tests and two adversarial actual-startup probes (zero-source upgrade, record preservation); zero network, no scan, no jobs or applications)*
- [x] Display source check dates and limitations. A reachable careers page is not proof of open, eligible or relevant vacancies. *(source browser check at c494112; Mark checked is the user review only)*

### D. Optional Gmail without a dead end — IMPLEMENTED, NOT YET VERIFIED

- [ ] If configured, Connect Gmail is prominent, read-only and explicit about consent. *(Not yet checked: no browser or live check)*
- [ ] If unavailable, plain wording explains that advanced setup is required in this beta and core search works without Gmail. Technical instructions sit in an advanced disclosure. *(Not yet checked: not browser-checked)*
- [ ] Pending/cancelled/expired/failed/connected/disconnected states stay truthful. No raw OAuth payload or credentials enter the UI. *(Not yet checked: mocked states only; no live check)*
- [ ] Public one-click OAuth, Google verification and second-account validation are separate later work; do not imply they are complete.

### Narrow threat delta for beta 3

The delta is small. A bundled read-only catalogue adds manual links and three public
feeds; links open only when the user clicks them. Startup seeding makes zero network
requests and creates no jobs or applications. Upgrades do not widen scan scope:
existing workspaces get the new feeds paused and keep every source choice. Scans
still require preview and confirmation. Public boards return global jobs; ASTRA applies
the configured UAE/role filters. No dependency, endpoint, credential or model-request
path is added. This is a reviewed description, not an independent finding.

### E. Assurance, files and release — NOT YET COMPLETE

- [ ] Independent review: separate read-only Codex reviewers inspected the source and UI (see evidence). Claude was the implementer and applied the pinned Anthropic frontend-design skill; Claude was not an independent reviewer. The review is scoped to c494112 and does not cover the package.
- [ ] Fix scope-critical regressions before freezing. After two unsuccessful approaches to a cosmetic improvement, document and defer it. Security, data-loss, broken installation or core-workflow blockers cannot be waived by time spent.
- [ ] Run automated and browser acceptance below against the exact candidate, then the exact ZIP.
- [ ] Customer release page says what works today, what changed, how to install, and that this is early beta. Add fictional-data screenshots. Keep private grading, developer comparisons and cloud-review prompts out of customer-facing notes.
- [ ] Keep one workspace index and one current plan; future evidence goes under versioned release folders. Inventory before cleanup. Remove only confirmed regenerable caches/temporary fictional tests; preserve real data/backups, original CVs, credentials, git history, active work and release evidence.
- [ ] Freeze source SHA and ZIP SHA-256, complete fail-closed gates and obtain exact-candidate Owner approval before publication.
- [ ] Download public assets again and verify identity; another-PC novice acceptance remains a separately recorded manual check.

## Manual checklist for every release

Use a fresh fictional workspace and the packaged ZIP. Record PASS / FAIL / NOT RUN, screenshot or short evidence, operating system, version, exact source and digest. Do not substitute developer-checkout success for package success.

1. Download, extract, follow START HERE, install and open. Root URL shows your workspace; demo requires explicit selection. Open again and verify no duplicate process. Try an occupied port: clear recovery steps, no unrelated process killed.
2. Upload fictional selectable-text CV. Verify name, skills, education and projects against the original; correct one fact, confirm and reopen. Try invalid/empty/scanned PDF and verify useful errors without changing saved facts.
3. Skip tracker; choose custom-only business or policy roles; save and continue. Change choices after saving: Continue must not use stale choices. Leave/reopen setup and confirm durable feedback.
4. Browse all source groups; verify government, hospital and portal links. Inspect starter feeds and add a fictional/manual link. Pause one starter, restart and confirm it stays paused. No scan begins merely by opening.
5. Open scan preview, cancel it and verify no scan. In a bounded explicitly approved test, confirm once, inspect progress/results, stop and check source-level failure reporting. No applications submitted.
6. Use a synthetic relevant and irrelevant job. Inspect match explanation, eligibility warning and original link. Prepare documents, review them and record a manually submitted application. Scores are advisory, not validated confidence percentages.
7. Click every route, Settings section, period, filter, disclosure, modal and drawer. Repeat rapid clicks. Observe visible transitions and correct final state. Type and wait through polling: no repeated entrance flashes.
8. Repeat essential actions in light/dark, narrow window, keyboard-only and 200% zoom. Focus visible, no clipped labels/primary actions. Test OS and in-app reduced motion; same functionality without nonessential movement.
9. Disconnect/unconfigured Gmail and rule-based mode work without accounts. Validate mocked Gmail failures automatically; live mailbox checks require a separate approved test and must be marked NOT RUN if absent.
10. Save, restart, verify persistence. Test backup/restore in a fictional workspace if affected. Stop through ASTRA's launcher. Repeat the installation with an inexperienced person on another computer; record instructions needed.

## Automatic checklist for every release

- [x] Targeted tests for changed behavior, including negative/error paths and races; isolate DATABASE_URL and HUNTER_DATA_DIR before imports. *(67 targeted backend tests passed in the source review; implementer ran 13 targeted plus the full suite)*
- [x] Frontend tests and production build. Source-pattern checks are reported accurately; browser execution remains separate. *(13 scripts and build PASS, repeated after the final copy change; source-pattern, not browser)*
- [ ] Full backend suite on supported Python versions in hosted CI; investigate new failures/skips.
- [ ] CodeQL/SAST, dependency/SCA audit, dependency review when triggered, and publication/privacy scan run on the exact reviewed commit.
- [x] Source seeding: fresh install, repeated startup, existing paused feed, modified built-in entry, custom source, demo isolation and no jobs/applications created. *(covered by tests/test_starter_catalog.py and the source reviewer probes; package not tested)*
- [x] Scan preview/token single-use, concurrent actions and Stop/source-disable boundary regressions remain passing when affected. *(full backend suite passed 2219/1 skipped at c494112 backend content, which is identical at ddb087c; a scan preview was also cancelled in the browser without creating a run)*
- [ ] Rule provider makes no model request; cloud cap 0 denies, approval required, credential storage fails closed and secrets excluded from records/logs.
- [ ] Build exact package; verify version, file manifest, included frontend/source catalog, locked dependencies, SBOM, provenance and SHA-256.
- [ ] Execute clean install, upgrade and launch smoke against package; ensure no private database, key, CV or machine path leaks into release files.
- [ ] Technical security gate PASS on exact source/artifact, with any required risk decisions evidenced. Configured checks alone are not PASS.

## How we decide whether it is better

Run the same fictional CVs and tasks on beta 2 and candidate. Record elapsed time, clicks, errors, hints needed, successful completion and recovery. Useful targets: no manual source configuration required for a first preview; every critical save has obvious success/error; all tasks remain keyboard accessible; no startup scanning; no false source-verification claims. Motion is checked visually and for interruption, not merely by finding CSS. Matching improvement requires fixed independent labels and a held-out set; do not count a nicer interface or more downloaded listings as better ranking.

## Following updates, in order

### Beta 4 — installation, recovery and runtime confidence

Fix and execute the Docker build (include VERSION, non-root runtime, persistent-data permissions, health check, dependency/image scanning and clean container smoke). Test supported Windows installation, occupied-port recovery, upgrade, rollback, backup/restore and damaged/missing state using fictional data. Add a privacy-safe support report only if its allowlist/redaction tests pass. Evaluate an easier installer and code-signing eligibility; signing identifies publisher, not proof of safety. Publish only measured operational improvements. Optional repeated loops (extra polishing passes, unrequested features) are frozen until the exit criteria of the current beta are met. Exit: another-PC novice can install, restore and recover without developer intervention.

### Beta 5 — prove search usefulness

Use independently authored fictional CVs for multiple majors, including cybersecurity, business/finance, AI/software and international relations, measured by an independent process. Measure extraction per field, false/omitted facts, relevance precision and missed suitable jobs separately from UAE geography coverage. Freeze labels and held-out set before tuning. Report eligibility separately from fit. Improve only measured weaknesses; keep any hybrid/AI experiment unadopted if it does not improve held-out results. Add source health and shortlist usability improvements when evidence identifies the need. Exit: reproducible comparison to beta 3 with confidence limits and remaining gaps.

### Final v1.1 / issue #48 — security and live evidence closure

Complete pending R-16/17/18 decisions and independent evidence required by the authoritative gate; validate primary Gmail end to end before second account; confirm public/downloaded package on another PC and broad matching limitations. Close #48 only when its actual requirements are met. A beta release does not close it.

### Later v1.2 — optional convenience, after the core works

Design public Gmail OAuth with Google verification/exceptions assessed and a maintainer-controlled client/consent flow; until verified, Gmail stays an optional advanced setup. Explore opted-in scheduled scanning with visible schedule, pause, bounds and fresh-source checks; current manual-only behavior remains until an approved design and tests exist. Consider job-alert import or sanctioned APIs for large portals; no LinkedIn login scraping. Expand providers only with documented access permission and demonstrated user value. AI remains optional and requires independent benefit evidence.

## Research and the 20 recurring UI mistakes

Research leads to testable decisions, not a copied aesthetic. References: [Anthropic frontend-design](https://github.com/anthropics/skills/blob/41bbe19d1a1a7eaab5e7bb9050a417e5c6cffc8f/skills/frontend-design/SKILL.md), [W3C status messages](https://www.w3.org/WAI/WCAG22/Understanding/status-messages.html), [W3C interaction animation](https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions.html), [Vercel interface guidelines](https://vercel.com/design/guidelines), [web.dev animation performance](https://web.dev/articles/animations-guide), [NN/g system status](https://www.nngroup.com/articles/visibility-system-status/), [Google restricted scopes](https://developers.google.com/identity/protocols/oauth2/production-readiness/restricted-scope-verification), [LinkedIn automation restrictions](https://www.linkedin.com/help/linkedin/answer/a1341387/prohibited-software-and-extensions). Pinterest references are visual inspiration only, not functional or accessibility evidence.

| Mistake | ASTRA acceptance check |
|---|---|
| 1. Save looks identical to failure | Persistent icon/text status after server acknowledgement |
| 2. Errors vanish in toast | Inline actionable errors, entered values preserved |
| 3. Disabled button gives no reason | Dirty/required/busy explanation beside setup action |
| 4. Colour-only or hover-only state | Text + icon + keyboard-accessible state |
| 5. Generic empty screen | Useful first action and included source set |
| 6. Dense cards and unclear hierarchy | Human screenshot review, readable spacing/line lengths |
| 7. Tiny hit targets | Comfortable pointer/touch controls and visible focus |
| 8. No narrow/zoom testing | Narrow width and 200% zoom acceptance |
| 9. Every card moves continuously | Quiet resting state; motion answers actions |
| 10. Header fade hides instant content swap | Actual page/period/disclosure transitions |
| 11. Animations block clicks | Interruptible updates and no snapshot interception |
| 12. Stale request wins | Latest request governs period figures |
| 13. Polling restarts entrances | Passive refresh/typing do not replay motion |
| 14. Reduced motion breaks functionality | Static equivalent, same actions and state |
| 15. Experimental CSS is sole fallback | Cross-browser disclosure behavior verified |
| 16. OAuth developer jargon is setup | Optional plain status; advanced details separated |
| 17. Source quantity sold as verified feeds | Reachability, permission, mode and freshness separated |
| 18. More features masquerade as quality | Compare completion, errors and user hints |
| 19. Green CI masquerades as manual assurance | Distinct browser, package and novice evidence |
| 20. Release copy overclaims security | Specific executed controls and explicit early-beta limits |

## Security review in plain English

For every patch, ask what information crosses a boundary and what can change: browser → local API, imported PDF/XLSX → parser, URL → public website, stored credentials → OAuth/model provider, source/build → downloadable ZIP. Review input validation, URL/SSRF controls, rendering/XSS, origin/session controls, secrets storage, consent, cancellation, dependency vulnerabilities and artifact integrity. Use SAST and SCA plus negative regression tests; document findings privately when disclosure could cause harm. Recheck introduced boundaries and exact package. NIST SSDF, OWASP ASVS and SAMM are frameworks used to organise evidence and improvements, not certificates ASTRA holds. CodeQL, dependency audit, hash-locked requirements, SBOM, provenance and release gates are technical mechanisms whose result counts only when executed on the exact source and artifact. This project is not certified or guaranteed secure.
