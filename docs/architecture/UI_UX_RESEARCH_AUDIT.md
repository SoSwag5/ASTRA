# Research-led UI and motion audit — issue #47

Research date: 2026-10-01. Scope: ASTRA's existing local workspace. This is a
prioritized list of 20 mistakes to avoid in this product, not a claim that an
industry study ranked these as the universal "top 20". Research informed the
work before the changes below were made. Existing controls were retained and
checked rather than replaced just to create a larger diff.

## What makes AI-built interfaces feel considered

The useful part of "vibe coding" is the iteration loop: describe the person,
decision and real data; constrain the visual language; build one coherent
system; inspect it in use; refine specific failures. Vercel's v0 guidance
explicitly structures prompts around the product surface, usage context and
constraints. Its examples are vendor demonstrations, not independent evidence
that generated interfaces are usable. [v0 prompting guide](https://vercel.com/blog/how-to-prompt-v0).

Reusable tokens and components keep generated screens consistent across
iterations. v0 documents this as design-system input. ASTRA already has that
foundation: porcelain and midnight surfaces, indigo actions, warm emphasis,
shared type, space, boundaries and focus treatment. Preserving that system is
more valuable here than copying a landing-page trend. [v0 design systems](https://v0.app/docs/design-systems-legacy).

Motion should reveal a relationship: where a page went, which view is selected,
whether a request is pending, or how a recorded quantity changed. NN/g describes
feedback, orientation and signifiers as productive uses. That supports a
dashboard with deliberate movement and a quiet resting state; it does not
justify perpetual animation on every tile. [NN/g: purpose of motion](https://www.nngroup.com/articles/animation-purpose-ux/).

Timing needs a hierarchy. NN/g's guidance discusses roughly 100–500ms depending
on distance and purpose. ASTRA's chosen values are design decisions, not a
scientifically established optimum: 80ms press, 140ms hover/exit, 200ms state,
260ms page, 280ms dialog, 320ms content entrance and 420ms quantitative fill.
Entrance staggering is capped at 96ms. Nothing waits for a decorative timer
before issuing a request. [NN/g: duration](https://www.nngroup.com/articles/animation-duration/).

Rendering cost matters as much as duration. web.dev recommends transform and
opacity, measuring slow frames, and avoiding speculative layer promotion.
The new surfaces and progress fill use transforms; loading sheen moves a
pseudo-element instead of repainting its background position. The existing
small navigation disclosure and sidebar resize remain bounded layout animations, an explicit
exception. [web.dev: animation performance](https://web.dev/articles/animations-guide).

Native view transitions are progressive enhancement: the DOM change must
succeed even if animation is skipped. Skipping still invokes the update
callback. That distinction exposed a real race in ASTRA's old coordinator;
the new coordinator settles earlier pending updates before the latest update
and prevents stale focus/cleanup. [Chrome: same-document transitions](https://developer.chrome.com/docs/web-platform/view-transitions/same-document).

Reduced motion is a user preference, not a performance mode. W3C explains why
nonessential movement can cause illness and should be disableable. ASTRA keeps
OS and in-app controls, static loading text and unchanged functionality.
This work is not a claim of WCAG certification. [W3C: animation from interactions](https://www.w3.org/WAI/WCAG22/Understanding/animation-from-interactions.html).

Vercel's interface checklist adds practical review criteria: interruption,
focus, labeled controls, state coverage and responsive layouts. Its brand
preferences are not universal rules. ASTRA keeps its own copy and privacy
constraints. [Vercel: interface guidelines](https://vercel.com/design/guidelines).

## The 20 mistakes and their application to ASTRA

| # | Mistake | Applied decision and review point |
|---|---|---|
| 1 | Prompting only for "premium" | Define the task: review opportunities and recorded application evidence, with manual decisions and local data. This document and `VISUAL_MOTION_SYSTEM.md` are the brief. |
| 2 | Mixing unrelated design styles | Retain the shared palette, radii and local font stack in `tokens.css`; no new animation library, external font or decorative asset request. |
| 3 | Giving every element equal emphasis | Keep page heading, section heading, metric and explanatory text distinct. Balance headings and improve paragraph wrapping; primary actions gain restrained hover elevation. |
| 4 | Arbitrary spacing and cramped copy | Use the existing 4px spacing scale and readable text widths. Test narrow layouts and long content rather than shrinking all text to fit. |
| 5 | Treating dark mode as inversion | Retain separately tuned midnight tokens, browser chrome and form colors. Run the existing 156 contrast-pair checks on both palettes. |
| 6 | Styling everything as clickable | Elevation belongs to action buttons. Informational cards enter but do not bounce on hover. Links, press states and row affordances retain their existing semantics. |
| 7 | Abrupt page and sidebar changes | Directional live content entrances, heading exits and a gliding selected marker; desktop navigation resizes over a bounded 260ms. Interactive surfaces are not captured. |
| 8 | Animating a shell while fetched content pops in | Give newly mounted panels and rails a short entrance. Today and Applications receive structured loading placeholders; loaded Progress cards arrive in reading order. |
| 9 | A long cascading entrance on every item | Animate groups and cap the stagger at 96ms. Do not gate content on scrolling, replay on polling, or animate every table row. |
| 10 | Animation blocking the next action | Keep controls and the implicit document root outside named snapshots. Click, keyboard and wheel input interrupt motion; native-browser regressions cover two rapid clicks at four intervals, as well as ordered callbacks. |
| 11 | View tabs changing content without feedback | Today views have distinct keys. Recall groups and Discovery shortlist views get a keyed entrance; controls remain mounted and keep focus. |
| 12 | Layout jumping while the app changes state | Reserve loading structure and stable scrollbar space. Keep existing fixed-width busy labels. Verify the narrow header and Settings cards after adding mobile input sizing. Content length can still change page height. |
| 13 | Fake completion or animated invented numbers | Keep actual values and labels immediate. Determinate rails interpolate their visual scale between recorded values; composition and unavailable states retain their honest meanings. |
| 14 | Indefinite decorative shimmer and costly effects | Loading sheen and active-rail sheen run three cycles, then settle. Static text remains. Busy spinners still identify outstanding requests; there is no idle ambient animation. |
| 15 | Ignoring motion sensitivity | OS and saved reduced motion disable movement, including hover displacement. A live OS change interrupts a running snapshot. No parallax or scroll hijacking. |
| 16 | Mouse-only polish | Preserve skip link, visible focus, navigation focus placement, modal trap/return and inert collapsed tools. A focused surface skips its entrance. |
| 17 | Desktop-only sizing | Keep responsive navigation and stacked layouts; make narrow-screen text inputs at least 16px and account for the bottom safe area on notifications. |
| 18 | Only designing the successful populated state | Keep retry, empty and stale-data explanations. Exercise delayed responses, failed requests and empty records against fictional data. Skeletons announce loading without reading every shape. |
| 19 | Losing context while editing or opening overlays | Preserve unsaved-change prompts and draft retention; contain overlay overscroll. Browser title follows the current page. No routing or persistence rewrite is introduced. |
| 20 | Calling a screenshot "done" | Verify actual in-flight animation, rapid navigation, loading/retry, themes, narrow screens, keyboard and reduced motion. Tie the validation record to the built candidate; preserve any untested platform limits. |

## Deliberate limits

This is a productivity workspace, so marketing effects such as cursor followers,
parallax heroes, automatic carousels and bouncing statistics were rejected.
Research is not a substitute for observing the Owner use the result. Browser
checks establish the exercised behavior, not universal usability or a guaranteed
frame rate on every device. Hash routing, backend behavior, product policy and
third-party submission flows are outside this visual revision.

See `VISUAL_MOTION_VALIDATION.md` for the executed checks and their limits.

Independent review caught a limitation of the initial implementation: disabling
pointer events on the transition overlay does not restore hit testing for
captured elements. The correction removes interactive participants and the
implicit root snapshot; only headings, decorative indicators and departing
overlays are captured. This follows the platform's hit-testing model, documented
by the [view-transition tooling authors](https://vtbag.dev/tips/interactivity/).
Two-click tests replace the inadequate assumption that a passing three-click
sequence proves every intermediate click was delivered.
