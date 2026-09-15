# Issue #41: eligibility + explainable ranking (FitAssessment)

Deterministic, local, explainable ranking. No LLM/network call is authoritative
for any decision described here (Owner Decision 5); optional AI commentary
elsewhere in ASTRA remains non-authoritative and outside this engine.

## Score is a ranking priority, not a probability

`FitAssessment.score_kind` is always `RANKING_PRIORITY`. The score (0-100 for a
rankable job, `null` for a hard-rejected one) means "how this candidate's
confirmed profile and preferences rank this posting relative to others,"
**never** an interview, hiring, or success probability. `Job.match_score`
projects `0` for a rejected row only because that legacy column is a
non-nullable integer; that `0` is a compatibility transport value, not the
FitAssessment score, and must never be read as "0% match."

## Why the old pre-persistence filter was harmful

Before #41, `backend.recall.evaluate()` (now `evaluate_legacy()`) ran
**before** `backend.services.add_job()`, and a hard rejection meant the
posting was never persisted at all:

```
provider result -> recall.evaluate() -> excluded? skip. -> accepted? add_job()
```

That evaluator hard-rejected on `TOO_SENIOR` (any "Senior"/"Lead"/"Manager"/
"Director"/"Architect" word when `career_level == EARLY`), `EXPERIENCE_GAP`
(any gap beyond a small policy-defined allowance), and `ROLE_NOT_RELEVANT`
(a title matching no configured family/adjacent role at all) -- exactly the
false-positive pattern that discarded relevant technical roles before a user
ever saw them, and did so **before persistence**, so there was no durable
record to reassess later.

## New pipeline order

```
validated provider result
    -> add_job() / #40 normalize + conservative dedupe   (unchanged, authoritative)
    -> Job + JobObservation persisted
    -> #41 FitAssessment (backend.assessment.assess())
        - hard incompatibility -> hidden via existing SKIP status
        - otherwise -> STRONG / GOOD / STRETCH / LOW
    -> compatibility projections (Job.match_score, .recommendation, ...) + explanation
```

A structurally invalid record that cannot safely enter #40 (e.g. an unusable
`job_url`) does not need to be forced into a Job row; `backend.main`'s
discover loop catches `add_job()`'s `ValueError` per item and records a
bounded `INVALID_JOB` disposition instead of aborting the whole source scan
(the pre-#41 behavior: one bad row could roll back an entire batch of
otherwise-good results).

**Issue #40 remains untouched and authoritative for identity/dedupe.** #41
never recomputes identity, merges/splits jobs, or uses `normalized_employer_key`
/ provider family as a fit signal.

## Hard-reject taxonomy

A small, bounded set -- six codes, each carrying a bounded human-readable
explanation, evidence references, a confidence, and the ruleset version:

| Code | Meaning |
|---|---|
| `DOMAIN_INCOMPATIBLE` | Strong unrelated-profession evidence (career_tracks.UNRELATED_PROFESSIONS / physical-security signals) **and** no credible enabled-track, custom-role, or contextual technical evidence. |
| `GEO_INCOMPATIBLE` | Workplace geography explicitly incompatible (US/UK-only remote, or a concrete named place outside the UAE with no global/regional remote scope and no relocation evidence). |
| `EXTREME_LEADERSHIP_MISMATCH` | Requires the *conjunction* of a management/executive-shaped title **and** strong organizational/people-leadership evidence, OR a Lead/Principal/Architect title **and** 10+ mandatory years **and** enterprise-wide architecture authority evidence. Title alone is never sufficient. |
| `CONFIRMED_ELIGIBILITY_CONFLICT` | An explicit listing requirement the confirmed candidate profile positively contradicts (never an unconfirmed/unknown declaration). |
| `USER_BLOCKED` | The user's own configured blocked company/domain/excluded-role list -- seniority words inside `excluded_roles` (its legacy default bundles some) are explicitly excluded from this check, since seniority must never hard-reject by itself. |
| `INVALID_JOB` | Run-report-only: a record that failed #40's persistence contract (e.g. bad URL). Never attached to a persisted Job. |

`EXPERIENCE_GAP` and `TOO_SENIOR` are retired as hard-reject reasons.
`ROLE_NOT_RELEVANT` is replaced by `DOMAIN_INCOMPATIBLE`'s stronger,
conjunctive standard. All three remain producible only by `evaluate_legacy()`
for shadow comparison and the `LEGACY` rollback mode.

## Career-track / domain assessment (`backend.assessment.assess_domain`)

Match types, strongest first: `CUSTOM` (a user's own custom target role --
first-class, never flattened into a fallback), `CORE` (an enabled built-in
track family/alias), `ADJACENT` (an enabled adjacent role title plus >=2
core-skill body hits), `CONTEXTUAL` (ambiguous title, but the description
carries real technical context, e.g. "Security Officer" + SIEM/IAM/SOC
wording), `AMBIGUOUS` (some body evidence, no clear match), `OUTSIDE` (no
technical evidence at all). Only `OUTSIDE` combined with strong
unrelated-profession/physical-security evidence is `hard_incompatible`; a
sparse/ambiguous out-of-track role (e.g. "Backend Engineer" with no
description) ranks LOW/uncertain instead of being hard-rejected.

**Custom-only fix**: `backend.career_tracks.active_tracks()` used to treat an
explicitly empty `career_tracks` list the same as "not configured yet" and
silently fall back to every built-in track. It now checks
`search_focus_confirmed` (an existing setting): unconfirmed/fresh installs
still get every built-in track as a sane default, but once a user has
confirmed their search focus, an explicitly empty `career_tracks` list is
respected -- custom target roles stand on their own.

## Experience (`backend/experience.py`)

`ExperienceRequirement`/`ExperienceClause` preserve every scoped clause
separately -- `"7+ years overall, 2+ years in cloud"` stays two clauses
(`effective_required_minimum` prefers the `OVERALL` one), never summed into
"9 years" or collapsed into "7 years of cloud." Supported syntax: numeric and
written (zero-ten) numbers, hyphen/en-dash/em-dash/"to" ranges, `+`/"or
more", "minimum"/"at least", required/preferred/desirable/bonus/advantage/"a
plus"/"preferred but not required", "no experience required"/"graduate"/
"entry level", and "or equivalent". Company-history ("founded 25 years ago")
and training-duration ("3-year training program") text is excluded from
candidate-experience parsing by the same relevance gate the legacy parser
used, refined to stop the bare word "experience" from defeating its own
company-history exclusion (a real bug found and fixed while porting it).

Candidate years are read from the same `verified_relevant_experience_years`
+ `..._confirmed` declaration pair ASTRA already required; unconfirmed or
missing candidate experience is `None` (UNKNOWN) and is **never** treated as
`0`.

## Seniority (`backend.assessment.assess_seniority`)

`title_level` (ENTRY/MID/SENIOR_IC/LEAD/MANAGER/EXECUTIVE/UNKNOWN) and
`leadership_scope` (NONE_EVIDENCED/TECHNICAL/TEAM/MULTI_TEAM/ORGANIZATIONAL/
UNKNOWN) are assessed independently from title and description-responsibility
signals (direct reports, budget/department ownership, hiring/performance
management, enterprise-wide architecture authority). `EXTREME_LEADERSHIP_
MISMATCH` requires the conjunction described above; a management-shaped title
with no responsibility evidence only lowers the seniority *score component*
(a ranking penalty), matching non-negotiable outcomes #3/#4.

## Geography / eligibility (`backend.assessment.assess_geography` +
`backend.recall.eligibility`)

Geography, nationality/eligibility, and work authorization/sponsorship/
relocation are kept as separate concepts. Geography: UAE or a stated
global/regional remote scope is `COMPATIBLE`; an explicit US/UK-only
restriction or any other concrete named place with no global scope is
`INCOMPATIBLE` (relocation evidence downgrades this to `UNKNOWN` rather than
a hard rejection); a bare workplace-type word with no place name ("Remote",
"Hybrid", "On-site") or a missing location is `UNKNOWN`. Work authorization
and sponsorship are always `UNKNOWN` here -- never inferred from absence.
`CONFIRMED_ELIGIBILITY_CONFLICT` (reusing the existing, unchanged
`backend.recall.eligibility()` nationality check) fires only when the
listing has an explicit requirement **and** the candidate profile explicitly
contradicts it; an unconfirmed/unknown declaration is never a hard conflict.

## Scoring (provisional -- #42 owns calibration)

Seven components, maximum points:

| Component | Max |
|---|---|
| Domain / role alignment | 25 |
| Enabled career-track priority | 15 |
| Confirmed profile skill/responsibility evidence | 20 |
| Experience fit | 15 |
| Seniority / leadership fit | 10 |
| Geography quality | 10 |
| Freshness / source-evidence quality | 5 |
| **Total** | **100** |

Experience uses a progressive tier on the *listing's* required years
(<=3: full marks; <=5: moderate penalty; <=7: substantial penalty; higher:
low but never zero), applied even when the candidate's own years are
unconfirmed (an explicit uncertainty note is attached instead of a silent
zero). A preferred-only shortfall reduces the experience component by at
most 2 points. Freshness uses only a documented `posted_at` with
authority `documented_provider_field`/`legacy_carried_forward` -- never
`retrieved_at` -- and an unknown posted date is neutral (3/5), not 0.
Provider family never earns a "prestige" bonus.

No soft component can produce a hard rejection; hard compatibility is a
wholly separate layer evaluated first, and the score is simply the clamped
sum of the seven components.

## Buckets (provisional)

`STRONG` 80-100, `GOOD` 65-79, `STRETCH` 45-64, `LOW` 0-44, `REJECTED` (hard
incompatibility only, `score=null`). `LOW` is a normal rankable/visible bucket
-- it must never be treated as a hidden/SKIP disposition; only `REJECTED` is.
Compatibility recommendation mapping: STRONG->HIGH_PRIORITY, GOOD->APPLY,
STRETCH->MAYBE, LOW->NEEDS_REVIEW (via the existing recommendation gate, which
now only downgrades to NEEDS_REVIEW for a real actionable review item --
routine uncertainty notes like "posted date unknown" are informational only
and never withhold a confident recommendation), REJECTED->SKIP.

## Query provenance

`query_expansion_match` is always `"UNKNOWN"` and contributes `0` weight --
#41 does not plumb real query-planner provenance (a future issue may), and
never infers a query match from title similarity, career track, or provider
board name.

## Persistence (Owner Decision 3: no new table/column)

The authoritative derived assessment lives at `Job.analysis['fit_assessment']`
(set by `backend.services.analyze()`), holding the full structured record
(components, experience/seniority/geography evidence, positives, penalties,
uncertainty, versions, input digest, explanation). `#40`'s `JobObservation`
remains the raw source-provenance layer; existing `Job` columns
(`match_score`, `recommendation`, `priority`, `matching_skills`,
`missing_skills`, `red_flags`, `requirements`) are compatibility projections
of the same FitAssessment, computed once in `services.score()` -- never a
second, independently recalculated score (the pre-#41 code computed a
weighted total and then discarded it in favor of `recall.evaluate()`'s
priority; that dead computation is removed).

### Hard-rejected retention (Owner Decision 1)

A structurally valid posting that is hard-rejected still gets its `Job` +
`JobObservation` persisted; it is hidden purely via the existing `SKIP`
status (`services.analyze()`'s existing guard: only set when the job has no
Application and isn't already in a terminal status), so no Application,
document, or artifact is ever created for it, and an existing saved/applied
job's workflow state is **never** overwritten by a later reassessment.

## Assessment modes (`Settings.assessment_mode`, default `NEW`)

- **NEW** (default): `backend.assessment` is authoritative;
  `evaluate_legacy()` still runs and is attached as `legacy_shadow` on every
  decision for #42 comparison, never for a product decision.
- **SHADOW**: `evaluate_legacy()` is authoritative; the new engine still runs
  non-authoritatively and is attached as `fit_assessment` for diagnostics.
- **LEGACY**: rollback path -- `evaluate_legacy()` only. Existing
  `fit_assessment` data already persisted is never deleted.

## Input digest / reassessment

`backend.assessment.input_digest()` hashes only assessment-relevant state:
canonical Job fields, observation authority/provenance, confirmed candidate
declarations, enabled career tracks/custom roles, and the schema/ruleset/
taxonomy/parser versions. It deliberately excludes `assessed_at`, wall-clock
time, `Job.updated_at`, UI state, and Application status, so identical inputs
always produce an identical digest regardless of when they were assessed.

## Security

All job text is treated as inert, attacker-controlled data: no network call,
no markup execution, no instruction-following from descriptions, bounded
regexes, and no raw CV/profile text placed in run reports (only bounded
skill/keyword references). No new dependency; no provider transport change.

## Not done in #41 (explicitly out of scope)

- Score/threshold calibration (#42).
- Discovery telemetry/analytics beyond bounded per-run counts (#43).
- A full rewrite of `backend/discovery.py`/`backend/campaign.py`'s own
  relevance/coverage helpers -- `campaign.fit()` already delegates to
  `Job.analysis['recall']` (and therefore to the new engine) when present;
  `campaign.py`'s employer-coverage metric still calls the legacy
  `discovery_reason()` independently, a narrow analytics-only inconsistency
  left as a residual item rather than expanding this PR's surface.
- The full ~80-case synthetic corpus described during planning; this PR
  ships a representative subset (`tests/fixtures/job_fit_corpus.json`)
  covering every non-negotiable outcome, not an exhaustive one.
