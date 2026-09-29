# #46.2-C shadow evaluation status

The role-understanding candidate is offline and shadow-only. No AI model is
connected to ASTRA. Production discovery, ranking, the API and the UI do not
import it. **C is not validated.**

## Development evidence (in-sample diagnostics, not accuracy)

The 16 development choices were saved by the Owner after seeing Codex
suggestions. Claude wrote the development role readings after reading those
labels. D09 is excluded: ASTRA's snapshot has no description, and the Owner
asked that it not be scored. Its label is kept. First-saved labels are the
labels of record, and none changed after reveal.

| Development measure (15 scored) | Current path | Candidate v2 (2026-09-22) | Candidate v3 (2026-09-29) |
|---|---|---|---|
| Exact tier agreement | 2 / 15 | 14 / 15 | 11 / 15 |
| Owner-hidden placed prominent | 3 / 9 | 0 / 9 | 0 / 9 |
| Owner-shown placed hidden | 0 / 6 | 0 / 6 | 0 / 6 |
| Shown-above-hidden pairs (6 × 9) | 37 / 54 | 54 / 54 | 52 / 54 |

- **v2 recomputed.** The v2 figures were recomputed exactly on 2026-09-29
  ([v2 report](discovery_46_2c_shadow_eval_v2.json)).
- **v3 inputs.** v3 uses the v3 code, the unchanged v1 readings and the
  Owner's 2026-09-29 preferences ([v3 report](discovery_46_2c_shadow_eval_v3.json)).
- **Why v3 differs.** Under the Owner's decision to hide only at 6+ required
  years, D02, D03 and D15 (5 years each) are shown lower, while their
  first-saved labels say hide. D05 remains a miss because its reading was
  deliberately not rewritten.
- **Current-path caveat.** The current path hides only on a hard reject, so
  its tier agreement partly reflects the tier mapping. Pairwise ordering is
  its fairer measure.

## Blind round v3 (pre-registered and sealed; awaiting Owner labels)

- **Plan.** The [plan v3](DISCOVERY_46_2C_BLIND_PLAN_V3.md) fixes the
  hypotheses, the comparison with the current path, the metrics and
  denominators, the exclusion rules, the success criteria, custody and what
  happens on failure. It was committed before the candidate changed, and it
  records its amendments after independent review.
- **Candidate v3.** The v3 candidate reads preferred and required experience
  from line structure and clauses, falling toward "not required" when a
  posting is ambiguous. It floors year ranges and adds an adjacent-technical
  reading that is shown lower. Its seniority band is the Owner's (0–2 normal,
  3–5 lower, 6+ suggested hidden). Relevant "UAE National" or "Emirati Talent"
  roles are shown lower with a warning; the candidate never infers
  nationality, work authorisation or eligibility.
- **Freeze.** The candidate, evaluation code, dependencies, preferences and
  criteria are frozen in the
  [freeze manifest](discovery_46_2c_blind_freeze_v3.json).
- **Review.** A read-only reviewer that did not author C approved the freeze at
  `bec6546` after seven rounds. The rounds, and the residual ambiguities
  accepted, are in the [review record](DISCOVERY_46_2C_BLIND_REVIEW_RECORD.md).
- **Holdout.** Twelve employer-separated postings. One (H04) has no readable
  description and is excluded by rule.
- **Seal** (commit `4944901`, [record](discovery_46_2c_blind_seal_v3.json)).
  - A fresh Claude Code reader subagent received only the frozen, bounded
    requests and wrote readings for the 11 readable postings.
  - The frozen code computed the candidate and current placements.
  - The record publishes only SHA-256 hashes and counts: 11 readings present,
    0 rejected whole.
  - No reading or prediction has been shown to anyone, and no holdout label
    exists.
- **Remaining steps.**
  - The Owner labels the 11 postings in a private page that shows posting text
    only, then reports the exported file's SHA-256.
  - A lock record is committed.
  - The fixed comparison runs once, and its result is published whether it
    is PASS, FAIL or INCONCLUSIVE.

The Owner's label reasons, the frozen item manifest, posting snapshots,
readings, predictions and the labeling page are private and absent from
this repository.
