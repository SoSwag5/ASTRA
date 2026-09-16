# Fit assessment evaluation report

_Generated from `backend.evaluation`'s canonical machine-readable output -- not hand-maintained._

- Corpus: `2026-09-15.4` (80 cases, 12 query sets, 3 UNCLEAR)
- Code: assessment schema `fit-assessment-2`, ruleset `fit-rules-2`, taxonomy `career-tracks-1`, experience parser `experience-2`
- Evaluated commit: `f55f645ae5a7a75220c77e8e1f9732424b456a28`
- Evaluated tree: `bed12ffc1916c0d4e25fb27cceb5a56743e443cb`
- Report snapshot: evaluated_commit and evaluated_tree_hash are informational Git diagnostics only; the versioned input manifest and report_payload_sha256 are the authoritative, durable provenance contract.
- Engine/view: `compare` / `BASELINE`
- Input manifest: `docs/evaluation/fit_evaluation_provenance_v1.json` (`006aa38ce2626006d19b2ad29f421853d4d50e61f1197e37a0682a60001f906d`)
- Report payload SHA-256: `1068d32f742c3586bdc54f8aff0aa201de54520535dba9f176a4b39b0f5bba58`

> **Reference labels are Owner-adjudicated (reference_status OWNER_ADJUDICATED); this is the repository Owner's individual review and rationale recorded per case (see docs/evaluation/FIT_LABEL_REVIEW.md), not a multi-human consensus or independently human-labelled benchmark.** Score means ranking priority, never a probability or hiring likelihood. These results measure this corpus only -- not global web recall -- and provider coverage in the corpus is metadata, never a quality signal. Bucket thresholds and component weights remain provisional (issue #41); running this harness changes no production default.

## Coverage

| Reference label | Count |
|---|---|
| MUST_SHOW | 25 |
| REASONABLE_STRETCH | 16 |
| LOW_BUT_USEFUL | 15 |
| GENUINE_REJECTION | 21 |
| UNCLEAR | 3 |

## Primary metrics

| Metric | Value |
|---|---|
| must_show_false_rejection_rate | **0.0000** (0/25) |
| useful_false_rejection_rate | **0.0000** (0/56) |
| new_useful_regression_rate | **0.0000** (0/33) |
| high_priority_irrelevant_leakage | **0.0000** (0/21) |
| broad_irrelevant_leakage | **0.1429** (3/21) |

## Hard-reason precision

| Reason | Precision | Predicted |
|---|---|---|
| DOMAIN_INCOMPATIBLE | **1.0000** (8/8) | 8 |
| GEO_INCOMPATIBLE | **1.0000** (5/5) | 5 |
| EXTREME_LEADERSHIP_MISMATCH | **1.0000** (3/3) | 3 |
| CONFIRMED_ELIGIBILITY_CONFLICT | **1.0000** (1/1) | 1 |
| USER_BLOCKED | **1.0000** (1/1) | 1 |

## Ranking quality

- Precision@10: 0.7504
- Recall@K: 1.0
- nDCG@10: 0.9862
- Pairwise ordering agreement: **0.7902** (113/143)

## Legacy vs new engine

- Category counts: `{'RANKING_CHANGED': 33, 'LEGACY_REJECTED_NEW_STRONG': 16, 'LEGACY_REJECTED_NEW_GOOD': 1, 'CHANGED_REJECTION_REASON': 14, 'NEW_REJECTED': 5, 'LEGACY_REJECTED_NEW_STRETCH': 9, 'LEGACY_REJECTED_NEW_LOW': 2}`
- New regressions (reference-useful, highest review priority): `[]`
- Recovered useful cases: 23

## Duplicate / stale-link

- Dedupe recall (issue #40 corpus, isolated in-memory DB): **1.0000** (6/6)
- False-merge rate: **0.0000** (0/15)
- Stale-link rate (labelled snapshot proxy, no live check): **0.0125** (1/80)

## Calibration candidates (PROPOSED, not adopted)

| Policy | Split | MUST_SHOW FR | Useful FR | HP leakage | nDCG@10 |
|---|---|---|---|---|---|
| current-ruleset | development | **0.0000** (0/15) | **0.0000** (0/42) | **0.0000** (0/9) | **0.9831** |
| current-ruleset | holdout | **0.0000** (0/10) | **0.0000** (0/14) | **0.0000** (0/12) | **1.0000** |
| domain-heavier-v1 | development | **0.0000** (0/15) | **0.0000** (0/42) | **0.0000** (0/9) | **0.9811** |
| domain-heavier-v1 | holdout | **0.0000** (0/10) | **0.0000** (0/14) | **0.0000** (0/12) | **1.0000** |
| geography-heavier-v1 | development | **0.0000** (0/15) | **0.0000** (0/42) | **0.0000** (0/9) | **0.9854** |
| geography-heavier-v1 | holdout | **0.0000** (0/10) | **0.0000** (0/14) | **0.0000** (0/12) | **1.0000** |

Smallest-deviation improving candidate (development split): **geography-heavier-v1**

PROPOSED comparison only. No candidate is adopted into production defaults by this report; Owner review and a code change to backend/assessment.py plus a new ruleset version are required before any candidate can become authoritative.

## PROPOSED quality gate (NOT Owner-approved)

Overall: **INSUFFICIENT_DATA**

| Check | Status | Threshold | Observed |
|---|---|---|---|
| must-show-false-rejection | PASS | <= 0.0 | 0.0 |
| useful-false-rejection | PASS | <= 0.05 | 0.0 |
| high-priority-leakage | PASS | <= 0.02 | 0.0 |
| new-useful-regression | PASS | <= 0.0 | 0.0 |
| domain-hard-reason-sample | PASS | >= 0.0 | 1.0 |
| geography-hard-reason-sample | PASS | >= 0.0 | 1.0 |
| leadership-hard-reason-sample | PASS | >= 0.0 | 1.0 |
| eligibility-hard-reason-sample | INSUFFICIENT_DATA | >= 0.0 | 1.0 (DENOMINATOR_BELOW_MINIMUM; denominator=1, minimum=3) |

## Top failures

- **broad_irrelevant_leakage**: software_engineering-04, systems_infra_cloud_platform_devops-05, technical_support_solutions_engineering-04

---

Report schema `fit-eval-report-3`, metric definitions `metrics-v2`, corpus SHA-256 `19d420c06d4b2dff...`
