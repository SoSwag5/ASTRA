# Issue #42: fit-assessment evaluation harness foundation

Answers a different question than issue #41 does. #41 answers "what does
ASTRA think about this job?" This harness answers **"is that judgment
actually useful?"** -- with the primary product risk being **false rejection
of a useful opportunity**, not one headline accuracy number.

This PR supplies the **foundation** for issue #42. The seed corpus and quality
gate remain proposed; issue #42 stays open for independent human/Owner label
adjudication, corpus expansion, gate approval, and any separately approved
production calibration.

This harness is pure, offline, and deterministic: no network, no browser, no
provider API, no LLM, no live/production database. It always calls the real
production engine (`backend.assessment.assess`, `backend.recall.
evaluate_legacy`, `backend.recall.evaluate`) -- it never recomputes a score
or reimplements domain/seniority/geography classification.

## Reference labels are not system buckets

The evaluation-only reference-label vocabulary is deliberately distinct from
`backend.assessment`'s buckets:

| Reference label | Meaning |
|---|---|
| `MUST_SHOW` | A human reviewing this posting for this candidate would expect to see it near the top. |
| `REASONABLE_STRETCH` | Worth showing -- above the candidate's obvious fit, but a real, worthwhile stretch. |
| `LOW_BUT_USEFUL` | Low priority, but a genuine, in-domain opportunity that should stay visible, not be discarded. |
| `GENUINE_REJECTION` | A human would not want to see this at all -- wrong profession, inaccessible geography, or a genuinely different seniority level. |
| `UNCLEAR` | The scenario itself is ambiguous even to a careful human reader; not confidently any of the above. |

`MUST_SHOW` is **not** an alias for `STRONG`; `GENUINE_REJECTION` is **not**
"whatever the classifier happened to reject." The whole point of an
separate label is that ASTRA can eventually be evaluated against independently
adjudicated judgments, rather than graded by its own assumptions.

`UNCLEAR` cases are counted for coverage and reported, but excluded from
every *scored* metric's denominator (`backend.evaluation.scored()`) unless a
metric explicitly says otherwise -- they must never silently become negative
(`GENUINE_REJECTION`-equivalent) examples.

## Label provenance and Owner boundary

The 80 seed scenarios, rationales, and proposed labels were Claude-authored.
They were written from the scenario descriptions rather than mechanically
copied from system buckets, and they deliberately contain label/system
disagreements. That is useful exploratory input, but it is **not independent
human-labelled ground truth** and does not yet satisfy issue #42's final label
adjudication requirement.

`docs/evaluation/FIT_LABEL_REVIEW.md` presents every case for later Owner or
independent-human adjudication. Reviewers may APPROVE the proposal, CHANGE the
label, or MARK UNCLEAR. Any material adjudication requires a new
`human_label_version` and `corpus_content_version`; this foundation does not
record those decisions on the Owner's behalf.

**`reference_status` is `"PROPOSED"` for every case in this corpus.** No
label here is Owner-approved ground truth. Nothing in `backend/evaluation.py`
or `scripts/evaluate_fit.py` may treat a proposed label as approved, and
production defaults are never changed by running this harness.

## Corpus

`tests/fixtures/fit_evaluation_v1.json`: **80 proposed seed cases across 12 query sets**
(a representative subset of the ~120-case target discussed during planning
-- deliberately scoped down so this PR stays reviewable; the corpus is
versioned and designed to grow before gate approval or production calibration). Actual proposed-label
distribution:

| Label | Count |
|---|---|
| MUST_SHOW | 25 |
| REASONABLE_STRETCH | 15 |
| LOW_BUT_USEFUL | 17 |
| GENUINE_REJECTION | 20 |
| UNCLEAR | 3 |

Coverage spans domain (cyber/SOC/IAM/AppSec/DevSecOps/cloud security/
network/NOC/systems/cloud/platform/DevOps/software engineering/technical
support/solutions engineering/physical security/mechanical/civil/
accounting/marketing/sales/healthcare), experience (0-1 through 8+, missing,
preferred-only, multi-clause), seniority (entry through executive,
ambiguous), geography (UAE onsite/remote, global, generic remote, GCC/MENA/
EMEA, US/UK-only, foreign onsite with/without relocation, unknown), data
quality (full/sparse/missing/conflicting), and source shape (Greenhouse/
Lever/Ashby/SmartRecruiters/manual-shaped). `source_kind` is coverage
metadata only -- see "Provider neutrality" below.

Every case uses `.example` employer domains and synthetic candidate/job
text; no real names, CVs, emails, phone numbers, or private content.

### Development / holdout split

~36% (29/80) reserved as **holdout**, kept as **whole query sets**
(`geography_spectrum`, `unrelated_professions`, `data_quality_and_source_
shape`) rather than a random per-case split, to avoid a candidate
calibration policy leaking information from a query set it was partly tuned
against. This is a larger holdout than the ~20-25% guideline discussed
during planning; the 80-case corpus's small per-query-set sizes made a
whole-query-set split at a smaller fraction impractical without leaving some
splits with too few cases to compute a stable nDCG. Holdout outcomes are
never used to choose a candidate calibration change (Phase 16) --
`backend.evaluation.evaluate_candidate_policies` ranks candidates by their
**development**-split lexicographic key only, and reports holdout
separately for the Owner to inspect.

## Primary metrics

Every ratio metric exposes `numerator`, `denominator`, `value`, `status`, and
`failing_case_ids` where meaningful. **`denominator == 0` produces
`value: null, status: "INSUFFICIENT_DATA"`** -- never a fake 0% or 100%.
New-engine-only metrics in `--engine legacy` runs instead use explicit
`UNAVAILABLE` status and are never calculated from null new-engine outcomes.

- **`must_show_false_rejection_rate`**: among `MUST_SHOW` cases, how many the
  new engine hard-rejects (`bucket == REJECTED`). The highest-severity
  reference failure.
- **`useful_false_rejection_rate`**: among `MUST_SHOW` + `REASONABLE_STRETCH`
  + `LOW_BUT_USEFUL` ("useful") cases, how many are rejected. The primary
  broad product metric.
- **`new_useful_regression_rate`**: useful cases where `evaluate_legacy()`
  accepted the posting and the new engine rejects it. Exact case IDs are
  always exposed; highest review priority.
- **`high_priority_irrelevant_leakage`**: among `GENUINE_REJECTION` cases,
  how many rank `STRONG`/`GOOD`.
- **`broad_irrelevant_leakage`**: among `GENUINE_REJECTION` cases, how many
  remain rankable at all (`STRONG`/`GOOD`/`STRETCH`/`LOW`), with a separate
  `low_only` breakdown since `LOW` leakage is materially less severe.

## Hard-reason precision

A `GENUINE_REJECTION` label does not by itself prove the *emitted* hard
reason was correct. Each case that carries `allowed_hard_reasons` (only
`GENUINE_REJECTION` cases may) declares which code(s) a human would accept.
For `DOMAIN_INCOMPATIBLE`, `GEO_INCOMPATIBLE`, `EXTREME_LEADERSHIP_MISMATCH`,
and `CONFIRMED_ELIGIBILITY_CONFLICT`, the harness reports predicted count,
human-allowed count, a precision-like rate, and the exact case IDs where the
emitted reason wasn't allowed. `USER_BLOCKED` (deterministic user
configuration, not a semantic judgment) is reported the same way but kept
separate. `INVALID_JOB` is ingestion-level, never part of a persisted
`FitAssessment`, and is not evaluated here.

## Ranking / ordinal quality

Precision@K, Recall@K, and nDCG@K (`K = min(10, query-set size)` -- most of
this corpus's query sets are smaller than 10, a direct consequence of the
80-case scope reduction; see "Known limitations" below) use the gain mapping
`MUST_SHOW=3, REASONABLE_STRETCH=2, LOW_BUT_USEFUL=1, GENUINE_REJECTION=0`.
`UNCLEAR` cases are excluded entirely (not gain-0). System ranking within a
query set orders by bucket (`STRONG > GOOD > STRETCH > LOW > REJECTED`, i.e.
`REJECTED` always ranks below `LOW`) then by score, then by case ID for a
fully deterministic tie-break. Pairwise ordering agreement reports the
fraction of comparable pairs (different reference gain) where the system's
relative order agrees with the human gain order, micro-averaged across all
query sets. Bucket-by-reference-label distribution is reported as a
cross-tab for inspection.

If a query set has zero ideal gain (for example, it contains only
`GENUINE_REJECTION` cases), nDCG is `null / INSUFFICIENT_DATA` and is excluded
from the macro average.

## Legacy vs. new comparison

Reuses `backend.recall.evaluate()`'s own real `assessment_shadow` comparison
(`LEGACY_REJECTED_NEW_<bucket>`, `NEW_REJECTED`, `SAME_REJECTION`,
`CHANGED_REJECTION_REASON`, `SAME_RANKABLE`, `RANKING_CHANGED`) -- this
harness never recomputes that categorization. Recovered cases
(`LEGACY_REJECTED_NEW_*`) are cross-referenced against reference-useful
labels; new regressions (`NEW_REJECTED`) are surfaced the same way, with
reference-useful new regressions being the single highest-priority failure
list in the report. Live shadow-mode data from production is never used as
ground truth here -- only this offline corpus.

## Duplicate rate and stale-link rate

- **`duplicate_rate`** (`backend.evaluation.duplicate_rate`) reuses issue
  #40's own labelled corpus (`tests/fixtures/job_dedupe_corpus.json`)
  against an **isolated in-memory SQLite database** (never the live/
  production database) and reports `dedupe_recall_rate` (fraction of
  `MUST_COLLAPSE` groups where every observation correctly resolves onto one
  `Job`) and `false_merge_rate` (fraction of `MUST_NOT_COLLAPSE` pairs that
  incorrectly collapse). This is a bounded summary metric for this report --
  it does not replace #40's own certification suite
  (`tests/test_job_deduplication.py`, `tests/test_issue40_remediation.py`).
- **`stale_link_rate`** is an **offline proxy only**: the fraction of corpus
  cases whose `reference_link_state` (a labelled snapshot judgment written
  into the corpus, not a live check) is `LIKELY_STALE`. This harness
  performs **no network link validation** of any kind.

## Bounded candidate calibration

`backend.evaluation.CandidatePolicy` / `apply_candidate_policy` recompose
the **same already-computed, already-normalized per-component contributions**
(`FitAssessment.components`, each already 0..its `WEIGHTS[component]`) under
alternate component weights and (optionally) alternate bucket floors. A hard
reject is **never** recomposed -- it stays authoritative from the real
engine regardless of candidate weights. This is deliberately the *only*
safely-externally-evaluable surface: the current `#41` implementation
computes each component's semantic classification (domain match type,
seniority level, geography compatibility, etc.) internally and does not
expose a way to vary that classification without risking semantic drift, so
`#42` does not attempt it. **Any point-table or hard-rule change requires a
code change to `backend/assessment.py` and a new ruleset version -- never a
candidate-policy file alone.**

`backend.evaluation.evaluate_candidate_policies` runs each predeclared
candidate against the **real** current-ruleset `new_bucket/new_score` baseline
on both splits and reports
the comparison; it **never** auto-adopts a "best" candidate. Preference
order when comparing candidates (development split only): (1) eliminate
`MUST_SHOW` rejection, (2) minimize useful false rejection, (3) avoid useful
legacy-accepted -> new-rejected regressions, (4) control `STRONG`/`GOOD`
irrelevant leakage, (5) improve nDCG, (6) prefer the smallest deviation from
the current ruleset. A candidate is called improving only when its development
lexicographic key beats that real baseline; deviation is the final tie-break.
No ML optimizer, no opaque search, no LLM tuning, no
protected-demographic or provider-prestige signal, no inference from missing
facts.

## PROPOSED quality gate

`tests/fixtures/quality_gate_proposed_v1.json` and `backend.evaluation.
evaluate_quality_gate` implement the *mechanism* for evaluating explicit,
versioned quality-gate checks against one named engine/view. Every check names
a supported metric, operator, threshold, minimum denominator, and whether it
is required or optional. A required check whose metric is insufficient makes
the overall gate `INSUFFICIENT_DATA`; an empty gate is invalid and can never
PASS. Optional checks may be explicitly skipped. The
shipped gate file's specific threshold values are a **starting proposal
only**, derived from this baseline's own evidence; see the Owner Review
section of the PR for the reasoning. **No gate in this repository is
Owner-approved.**

## Determinism and report provenance

The same git commit + corpus + ruleset + candidate policy + fixed
assessment clock (`corpus['fixed_assessment_clock']`, never wall-clock time)
produces byte-identical JSON: fixed key ordering (`sort_keys=True`), stable
case/query ordering, no absolute local paths, no random values. Verified by
`tests/test_fit_evaluation.py::test_determinism_byte_identical_output`.
Machine output records both `provenance.evaluated_commit` and
`provenance.evaluated_tree_hash`. A committed report is generated from a clean
evaluated commit and may be stored by a later report-only commit; the snapshot
note states that relationship rather than pretending the report contains its
own future commit SHA.

## Running the harness

```
python scripts/evaluate_fit.py                                    # full corpus, text output
python scripts/evaluate_fit.py --case <id>                        # one case
python scripts/evaluate_fit.py --query <query_id>                 # one query set
python scripts/evaluate_fit.py --slice domain=cloud_security       # one tag slice
python scripts/evaluate_fit.py --split holdout                    # holdout only
python scripts/evaluate_fit.py --engine new|legacy|compare        # legacy marks new-only metrics UNAVAILABLE
python scripts/evaluate_fit.py --format json|text|markdown
python scripts/evaluate_fit.py --dedupe                           # add duplicate/stale-link metrics
python scripts/evaluate_fit.py --candidate-policy path.json       # candidate becomes the headline metric view
python scripts/evaluate_fit.py --calibration a.json --calibration b.json --gate gate.json
```

Unsupported corpus/label/metric versions, malformed governance fields,
candidate policies, and quality gates fail clearly
(`backend.evaluation.CorpusError`), never silently fall back. Candidate policy
and quality-gate JSON files carry explicit schema versions.

## Adding a new case to the corpus

1. Write the job/candidate/config scenario first.
2. Propose the `reference_label` and write `human_reason` **before** running
   the classifier against it; record it as `PROPOSED`.
3. Pick a stable, never-reused `id` (`kebab-case`, prefixed with its
   `query_id`).
4. If the label is `GENUINE_REJECTION`, declare `allowed_hard_reasons`.
5. Run `python scripts/evaluate_fit.py --case <id>` to sanity-check the
   engine actually runs on it; if the label and the engine's output
   disagree, that disagreement is the point -- do not "fix" the label to
   match the engine unless the *scenario itself* (not the label) turns out
   to be wrong (see "Bugs found while building this harness").
6. Run the full corpus test (`pytest tests/test_fit_evaluation.py`) to
   confirm the corpus still validates.
7. Add the case to `FIT_LABEL_REVIEW.md`; independent human/Owner adjudication
   is a later explicit step, not something the harness infers.

## Re-running before/after a ranking change

```
git stash                                    # or checkout the pre-change commit
python scripts/evaluate_fit.py --format json --dedupe > before.json
git stash pop                                # or checkout the post-change commit
python scripts/evaluate_fit.py --format json --dedupe > after.json
```

Compare `primary_metrics`, `hard_reason_precision`, and `ranking_metrics`
between the two files -- per issue #42's acceptance criteria, no ranking
change should ship as an improvement without this before/after measurement.

## Bugs found while building this harness

Running the harness against its own corpus surfaced three real bugs before
this PR was opened, all fixed in this branch (not the corpus's fault, and
not the classifier's fault either -- genuine harness bugs):

1. Two corpus cases meant to represent a generic "Remote" location left the
   default `remote_status` (`"On-site"`) unset, producing a nonsensical
   combined `"Remote On-site"` geography string that the engine correctly
   refused to treat as the ambiguous workplace type it was meant to be.
   Fixed in the corpus generator.
2. `duplicate_rate()`'s `MUST_NOT_COLLAPSE` loop reused one observation's
   `job_source_id` for both observations in a pair, even for pairs
   deliberately built from two *different* source instances -- defeating
   exactly the case being tested and producing a false "false merge." Fixed
   by resolving each observation's own source independently.
3. `duplicate_rate()` passed the corpus's lowercase `provider_family`
   (`"greenhouse"`) straight through as `add_job()`'s `source` field, which
   `backend.services._PROVIDER_FAMILY_FOR_SOURCE` only recognizes in its
   capitalized display form (`"Greenhouse"`) -- the mismatch silently forced
   every observation to `identity_kind='manual'`, colliding two distinct
   native IDs onto the same uniqueness tuple and raising a spurious
   `IntegrityError`. Fixed by mapping to the expected capitalized label.

## Known limitations

- 80 cases / 12 query sets is a deliberate reduction from the ~120-case,
  ~10-per-query-set target discussed during planning; several query sets
  here have as few as 4 cases, so `Precision@10`/`Recall@10`/`nDCG@10` use
  `K = min(10, pool size)` and should be read as directional, not a fully
  powered top-10 evaluation. The corpus is versioned so it can grow without
  breaking existing case IDs.
- Labels are Claude-authored proposals, not independent human labelling;
  `reference_status: PROPOSED` reflects this throughout. Issue #42 remains
  open for adjudication, gate approval, and any later production calibration.
- `stale_link_rate` is a labelled-snapshot proxy; it says nothing about
  whether a link is *actually* dead today.
- `CONFIRMED_ELIGIBILITY_CONFLICT` has only 1 corpus example; its precision
  and the proposed gate's `min_hard_reason_sample_size` check both flag this
  as under-covered rather than hiding it.
