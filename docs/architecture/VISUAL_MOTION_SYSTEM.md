# ASTRA visual and motion system

Issue #47 visual follow-up. The implementation preserves the existing React,
Lucide and local-font stack. No new runtime dependency, external asset request,
data flow, endpoint, migration or trust boundary is introduced.

## Direction and semantic tokens

Porcelain is the default for a new browser. Preserve every valid saved light,
dark or system preference, including legacy values. Midnight is a separately
tuned counterpart. `tokens.css` owns colour; legacy CSS names alias it.

| Role | Porcelain | Midnight |
|---|---|---|
| Page / sidebar | `#f6f3ee` / `#efebe4` | `#0d1220` / `#0a0e1a` |
| Surface / raised | `#fffefc` / `#ffffff` | `#141a2a` / `#1d2539` |
| Primary ink / secondary / muted | `#1b2233` / `#414859` / `#5c6272` | `#e9ecf5` / `#bec5d7` / `#9ba4ba` |
| Action / on action | `#3a46c2` / white | `#8f9cff` / `#0c1133` |
| Warm emphasis | `#a44a16` | `#f1b47c` |

Use `--surface-*`, `--ink-*`, `--action-*`, `--status-*`, `--viz-*` and
`--focus-*` by meaning, never by screen. Warm emphasis is sparse; green only
means a recorded successful state. Statuses include labels or icons. Chart
segments have adjacent names and counts; never rely on colour alone.
System typography, a 4px spacing scale, 8/10/16px radii and restrained shadows
keep dense tables and spacious summaries part of one product. Theme swatches
are the deliberate exception to contextual colour: they preview both palettes.

## Motion and control states

Press acknowledgement is 80ms, hover/focus 140ms, ordinary state changes 200ms,
page movement 260ms, dialogs 280ms. Motion finishes after the state change.
Native View Transitions provide page exit/entrance, directional Settings
changes and a moving selected-navigation marker without keeping old React
views alive. Unsupported browsers retain functional navigation and entry
motion. More tools uses a short grid disclosure, rotating chevron and `inert`
while collapsed. Focus enters the new page/section without arbitrary scrolling.

Every shared control uses hover, focus-visible, press, disabled and selected
styles. Asynchronous actions expose busy text immediately and only report
success after the operation returns. Skeletons exist only during requests;
failures show a retry action, preserving previously loaded information when
appropriate. OS reduced motion and the browser-local setting suppress movement;
labels, selected weight, borders and colours retain all state information.

## Progress evidence contract

- Weekly applications: the final entry in the backend's fixed weekly series,
  divided by the explicitly saved Campaign weekly target. Undated submissions
  are excluded and disclosed. Exceeding the target keeps the true text count
  while capping the visual and ARIA value at the target.
- Application composition: canonical recorded current stages; show unavailable
  if state reads are incomplete or totals disagree. This is composition, not
  application completion or probability of employer success.
- Scan: sources done/total from active scan status, otherwise the latest run's
  recorded source outcomes. Missing evidence is unavailable, never an estimate.
  Failed status polling ends the live animation and asks for a refresh.
- No-reply remains a user review cue. No automatic rejection, invented reply,
  streak or badge is introduced.

## References considered

- [Taste existing-project redesign](https://github.com/Leonxlnx/taste-skill/tree/main/skills/redesign-skill): audit existing hierarchy and feedback before changing components.
- [Taste visual guidance](https://github.com/Leonxlnx/taste-skill/tree/main/skills/soft-skill): spacing and depth considered; cinematic effects and new fonts/icons rejected for this data-heavy local app.
- [Vercel Web Interface Guidelines](https://github.com/vercel-labs/web-interface-guidelines/blob/main/command.md): focus, semantics, reduced motion, failure recovery and content overflow.
- [DESIGN.md collection](https://github.com/VoltAgent/awesome-design-md), including its Linear analysis: semantic documentation format only, no copied branding.
- [Microsoft Playwright CLI](https://github.com/microsoft/playwright-cli): real-browser interaction and motion inspection; equivalent installed Playwright browser tooling is used for this candidate.

Verification results belong to the session evidence record, not this design
contract. Token contrast checks cover specified pairs, not an accessibility
certification of the entire application.

## Research-led refinement (2026-10-01)

The [research and 20-point audit](UI_UX_RESEARCH_AUDIT.md) explains the product
decisions and sources. Content surfaces enter in 320ms with at most 96ms of
stagger, including content mounted after a request. They do not replay when
existing data refreshes or when a user types. The sidebar uses a bounded 260ms
resize; tabs retain their controls while the chosen content enters.

New input interrupts snapshots, and superseded update callbacks cannot undo
newer navigation or focus. The document root and interactive surfaces are not
captured, since named participants are excluded from native hit testing.
Heading exits and indicator movement use snapshots; live content supplies the
directional entrance. Theme colors transition on live surfaces. Only the
bounded sidebar/disclosure animations change layout rather than transforms.
Loading sheen uses a moving pseudo-element for three cycles before settling.
Determinate progress fills interpolate their transform between actual recorded
fractions; the text and accessible value update immediately. Browsers without
`@starting-style` still show the correct initial fraction and subsequent updates.
Reduced motion suppresses the new entrances, rail interpolation and hover lift.

Today and Applications use structured loading placeholders. Scrollbar space is
reserved, overlays contain overscroll, mobile fields use at least 16px type,
and browser titles track the current page. These refinements introduce no
new dependency, remote asset, backend behavior or policy change.
