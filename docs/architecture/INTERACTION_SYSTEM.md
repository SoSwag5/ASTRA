# Interaction system and Settings redesign (#47 follow-up A)

Implementation owner: Claude Code, on `feature/47-followup-interaction-settings`,
stacked on the #47 candidate `4a13fc8` and to be rebased onto the reviewed #47
state before its pull request. Independent assurance: Codex. This is the
visual/interaction rationale, the audit that motivated it, and the rules the
code follows. It changes presentation and interaction only: no settings key,
security rule, endpoint contract or data flow changes.

## 1. What the audit found

An automated pass over every visible control on Today, Progress, Discovery,
Jobs, Applications, Documents, Settings and Privacy & Local Data (isolated
fictional workspace, 1280 px, both themes) plus a stylesheet review found:

| Finding | Where | Effect |
|---|---|---|
| No press (`:active`) state anywhere | all controls | A click gives no immediate acknowledgement |
| No hover state on navigation, icon buttons, text buttons, clickable application rows, disclosure summaries, tabs, links or form fields | all pages | Clickable and static things look alike; NN/g hover guidance unmet |
| Focus styles defined three different ways (global, `.campaign`, `.progress`) | app-wide | Inconsistent ring colour/offset between pages |
| Disabled = opacity only, often with no reason | Privacy (delete, Gmail connect), Discovery, Documents | A control appears available but silently does nothing |
| Permanently disabled "Assisted dry run" / "Automatic submission disabled" buttons | Job detail | Controls that can never act; they are explanations styled as buttons |
| View switches styled as filled/unfilled buttons with no state semantics | Discovery, Recall | Selection is shown by colour only |
| `role="tab"` without the keyboard model tabs need | Today | Screen readers announce tabs that do not behave like tabs |
| Mis-encoded text ("â€¦", "â€”", "â€™s") | Privacy panel | Visible corruption in five strings |
| Gmail "Disconnect" acts immediately | Privacy panel | A consequential, remote-revoking action with no confirmation |
| "Replace master CV" acts on file choice | Settings | Replaces extracted facts with no confirmation |
| Settings fields edit shared app state directly | Settings | No notion of unsaved changes; navigating away silently keeps or loses edits |
| Links and summaries under 24 px tall | Privacy, Discovery | WCAG 2.2 2.5.8 target size |

## 2. Principles and sources

- **Feedback must be immediate and truthful.** A press acknowledges within
  ~100 ms (NN/g button states; NN/g animation duration: ~100 ms "feels
  immediate"). Success is shown only when the server said so; failures keep the
  user's work and say what to do.
- **Motion explains a change, then gets out of the way.** Durations stay in
  NN/g's 100–500 ms band and mostly under 250 ms; entering uses ease-out,
  leaving uses ease-in (NN/g). Curves are Material 3's `standard`
  `cubic-bezier(0.2, 0, 0, 1)`, `emphasized-decelerate`
  `cubic-bezier(0.05, 0.7, 0.1, 1)` and `standard-accelerate`
  `cubic-bezier(0.3, 0, 1, 1)`. Fluent 2's "functional, natural, consistent"
  principles rule out decoration: no perpetual pulses, count-ups, confetti or
  animation library.
- **Reduced motion is a first-class mode** (WCAG 2.2 2.3.3). The OS
  `prefers-reduced-motion` setting and an in-app "Reduce motion" choice both set
  every motion token to 0; feedback stays visible through colour, icon and text.
- **Confirm only consequential actions, and say what will happen** (NN/g
  confirmation dialogs): specific titles, action-named buttons ("Disconnect
  Gmail", "Keep connected"), typed confirmation only for irreversible deletion.
- **Unsaved changes are always visible and never silently lost** (Cloudscape
  unsaved-changes pattern; save-bar pattern used by Mirakl and Grafana): a
  save bar appears as soon as a section differs from what is saved, and leaving
  that section or page asks to keep editing or discard.
- **Recognition over recall** (NN/g): Settings is organised by what a person
  is trying to do, each section says what it affects, and every value shows
  its current saved state.

Reference galleries (Mobbin, Awwwards, Behance, Dribbble, Figma Community,
Pttrns) were used only for ideas about section navigation and save feedback.
Mobbin returned 403 without an account, so no flow from it was studied in
detail. No asset, font, icon or illustration was imported; Lucide remains the
only icon family, so no licence review was needed.

## 3. Tokens

Added to `frontend/src/tokens.css` (both themes):

| Token | Value | Use |
|---|---|---|
| `--motion-instant` | 80 ms | press acknowledgement |
| `--motion-fast` | 120 ms | hover, focus, colour |
| `--motion-base` | 180 ms | disclosure, receipts, save bar |
| `--motion-slow` | 240 ms | dialogs and the detail drawer entering |
| `--ease-standard` | `cubic-bezier(0.2, 0, 0, 1)` | state changes |
| `--ease-enter` | `cubic-bezier(0.05, 0.7, 0.1, 1)` | things appearing |
| `--ease-exit` | `cubic-bezier(0.3, 0, 1, 1)` | things leaving |
| `--state-hover` / `--state-press` | theme-specific tints | hover and press layers |
| `--danger-fg` / `--danger-bg` / `--danger-border` | theme-specific | consequential actions |

All motion tokens are 0 when `prefers-reduced-motion: reduce` or when the
in-app "Reduce motion" setting is on (`html[data-motion="reduced"]`).

## 4. State rules (`frontend/src/interaction.css`)

| State | Rule |
|---|---|
| Hover | Background/border tint within `--motion-fast`; clickable rows also nudge their arrow 2 px. Never the only cue: every hover has a keyboard focus equivalent. |
| Focus | One ring everywhere: `--focus-width` solid `--focus-ring`, offset `--focus-offset`, `:focus-visible` only. |
| Press | `translateY(1px)` and the press tint within `--motion-instant`; transform only, so nothing reflows. |
| Loading | `aria-busy="true"` on the control; label changes to the action in progress ("Saving…"); a small spinner only while real work runs, static under reduced motion. The control keeps its size. |
| Disabled | Reduced contrast, `not-allowed` cursor, and a visible or `aria-describedby` reason wherever the reason is not self-evident. |
| Selected | `aria-pressed`/`aria-current`/`aria-selected` drive an accent border and tint; colour is never the only cue (weight or a check icon too). |
| Success | Inline status with a check icon, announced politely, stating what was saved and when. |
| Error | Inline callout with the server's message, announced assertively; the user's input is kept. |

## 5. Settings structure

One Settings page with a section list (a sidebar at desktop widths, a select at
narrow widths). Each section says what it affects.

| Section | Contents | Saved by |
|---|---|---|
| Career focus | Career tracks, custom roles, target/excluded roles, locations, blocked employers/domains, thresholds, scoring weights | `/api/settings/career-focus`, `/api/settings` |
| Profile & CV | Candidate profile, confirmation, extracted facts and corrections, application profile answers, replace master CV | `/api/profile`, `/api/profile/facts/*`, `/api/privacy/application-profile`, `/api/import/cv` |
| Discovery sources | Configured company boards, enable/pause, add | `/api/records/sources`, `/api/search/sources` |
| Gmail & permissions | Gmail connection, AI provider and key, daily AI limit, preparation mode, legacy domain permissions | existing Gmail, privacy and settings routes |
| Appearance | Theme (ink, light, match system), reduce motion | this browser only (`localStorage`) |
| Privacy & local data | Security check, storage location, export, backups, legacy Windows task, delete local data | existing privacy and campaign routes |
| Workspace | Setup wizard, tracker download, Excel sync, application limits | `/api/settings`, `/api/files/tracker.xlsx` |

The "Privacy & Local Data" navigation item opens this page at its privacy
section, so there is one home for each setting.

## 6. Known limits

- Appearance choices are per browser, like the existing theme toggle; they are
  not stored in the local database.
- Unsaved-change protection covers in-app navigation, section switches and tab
  close/reload (`beforeunload`, which shows the browser's own wording).
- Automation (schedule, run history) and Discovery's per-source scan controls
  stay on their pages; Settings links to them.
