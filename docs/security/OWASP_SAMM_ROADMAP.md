# SAMM improvement roadmap
Owner: Maintainer. Target maturity 1 for every practice; no target date implies achievement.

| Horizon | Priority and actions | Exit evidence |
|---|---|---|
| Before public v1.0 | Close private-report leak and manually review release content; remediate/verify applicable L1 gaps; real CI/CodeQL/dependency review; clean Windows install; signed provenance/independent verification; protected repository | Release Security Gate plus source/artifact-bound assurance report, no mandatory skipped checks |
| First 30 days after authorized activation | Test private reporting; train against top recurring weakness classes; review threat model on one real change; run Scorecard and triage | Intake test, exercise record, threat-review diff, reviewed Scorecard JSON |
| Within 90 days | Record dependency/update cadence, closure lead times, synthetic backup recovery and incident tabletop; review global availability, AI response limits and logging coverage | Dated recovery/triage records, regression evidence and risk decisions |
| Quarterly | Complete both streams' SAMM quality-criteria questionnaire for all 15 practices; review root-cause patterns and assess whether level 1 is actually met | Evidence-linked questionnaire and revised assessment; no unsupported averaging |

Practice-specific next actions and weaknesses are in OWASP_SAMM_V2_ASSESSMENT.md. Reassess on contributor growth, public/network hosting, changed data flows or incidents. Do not add impossible external-review rules for a solo maintainer; document absence honestly and use technical controls.
