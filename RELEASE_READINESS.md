# Monday release readiness

## What was found

The working core was already strong: local FastAPI + SQLite, explainable scoring, public-board discovery, preparation-only safeguards, a queue, document generation, application events and follow-ups. The main release risks were a ten-step first-run wizard, eleven equally weighted navigation destinations, no fictional public demo, weak mobile presentation, server errors that could leave a blank screen, and missing favicon/social metadata.

## What changed

- Added a safe fictional-data launch demo at `/demo`. It is fully client-side and never reads the private CV, tracker or database.
- Added a product-specific favicon, title, description, Open Graph/Twitter image metadata and a branded preview image.
- Added a compact navigation control and a responsive sidebar mode while preserving the existing destinations.
- Added offline-aware API errors with a visible retry action instead of silent failures.
- Kept discovery, saved jobs, source health, application notes and follow-up workflows intact.
- Added a direct `/demo` server fallback so refreshes work in the production build.

## User journey

Before: a first-time user could be sent through a long setup flow before seeing the workspace, then had to infer which screen mattered.

After: the public demo immediately shows Discover → Review evidence → Track progress with fictional roles. The private workspace opens on Discovery, where the next scan, shortlist, source health and filters are visible. Applications provides status, notes and follow-up actions in one view.

## Remaining risks

- The app is still a local single-user service. It is not ready to expose to the public internet without authentication, TLS, protected runtime storage and an operational backup plan.
- Automatic scans require the local server to stay running and the computer to remain awake.
- The generated social preview is a square image; social platforms may crop it differently from a wide card.
- Browser/ATS support remains site-specific and review-first. LinkedIn stays manual.

## Test results

- Frontend production build passes.
- 45 automated tests pass.
- The fictional demo loads after a direct refresh.
- The local API serves the favicon and social preview assets.
- The live discovery workflow previously verified 518 listings across eight enabled sources, producing three reviewable roles without touching existing applications.

## Deployment status

The app is running locally at http://localhost:8787. The public-safe demo is http://localhost:8787/demo. No public deployment was attempted because no production host or account was configured.

## Recommended screenshots

1. `/demo` hero plus shortlist and evidence panel.
2. Private Discovery page showing source health and scan results.
3. A job detail drawer showing score, matching evidence and review flags.
4. Applications showing status, notes and follow-up date.

## 20–30 second demo

Open `/demo`, select “Cybersecurity Analyst” in the shortlist, point out the 86/100 evidence score and the missing experience item, click Save, then click Prepare application. Close by showing the two trust statements: review stays with the user and nothing is submitted automatically.

## Monday release blocker

For a LinkedIn launch, use `/demo` with fictional data. Do not publish the private workspace until a hosting owner, authentication model, TLS and backup plan are in place.
