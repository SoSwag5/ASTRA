# #46.2-C v3 blind round: aggregate outcome

**Verdict: FAIL.** The fixed comparison ran once, and the candidate failed one
pre-registered criterion, C3. C stays **NOT VALIDATED**. No candidate is adopted
and nothing in production changed: discovery, ranking, the API and the UI do
not import the candidate, and no AI model is connected to ASTRA.

The candidate is the v3 role-understanding revision that was carried by
[PR #76](https://github.com/SoSwag5/ASTRA/pull/76). That pull request is
**CLOSED and NOT MERGED**, and its candidate is **rejected** after this result.
It must not be merged or adopted on this evidence. No Owner decision remains
about the pull request's fate. Its earlier title and description predate the
result and read "awaiting Owner labels"; that wording is historical only.

## What this page is, and is not

- **Aggregate only.** It publishes counts, criteria and verdicts. It publishes
  no posting identifier, title, employer, posting text, Owner choice for any
  single posting, role reading, prediction or Owner reason.
- **A redacted derivative.** The full output of the fixed comparison, in the
  public-result format the pre-registered plan specified, pairs individual
  postings with the Owner's answers and the candidate's predictions. That is
  private per-posting data, so the file is **retained privately and is not
  published**. This page is a redacted derivative of it.
- **Not reproducible from this repository.** The postings, Owner labels, role
  readings, predictions and full output are private. A reader of this
  repository cannot recompute any row, or check any count below, against them.
  The counts were reported to this closeout as independently verified. This
  documentation-only change did not open the private inputs or results, and it
  could not recompute them.
- **Retained privately, identified by digest.** The digests identify the
  retained files and disclose nothing of their content.
  - Full fixed public-format result, archived privately, not for publication:
    SHA-256 `cc30ffff59e585f6e5c67805343f81adb28018e43461329d0f91aa99643810dd`.
  - Private detailed result:
    SHA-256 `c818342a0c8eda08eedf1c199b8616ab287f9b6ecf4050ab6a92ffc2cec63655`.

## How the round ran

- **Pre-registration.** The
  [blind plan v3](https://github.com/SoSwag5/ASTRA/blob/66c33268e4012ca2d4a192aadc663a0f1e2f23ff/docs/evaluation/DISCOVERY_46_2C_BLIND_PLAN_V3.md)
  (on the branch of the closed, unmerged PR #76, at its pushed head
  `66c3326`) fixed the
  hypotheses, metrics, denominators, exclusion rules and criteria for the
  round. The plan itself notes that code cannot prove it was written before
  the candidate change; the only independent ordering evidence is the seal's
  push record (see Custody facts). A read-only reviewer that did not author C
  approved the frozen
  candidate after seven rounds
  ([review record](https://github.com/SoSwag5/ASTRA/blob/66c33268e4012ca2d4a192aadc663a0f1e2f23ff/docs/evaluation/DISCOVERY_46_2C_BLIND_REVIEW_RECORD.md)).
- **Candidate.** The frozen v3 code, role readings written by a fresh Claude
  Code reader subagent and fixed by hash in the seal commit, and the Owner's
  2026-09-29 preferences: 0–2 required years comfortable, 3–5 shown lower, 6+
  suggested hidden; a confident adjacent-technical reading shown lower; a
  posting worded for UAE nationals shown lower with a warning. The candidate
  never decides eligibility.
- **Comparison path.** The unchanged #41 fit assessment on identical inputs.
  It suggests hiding only on a hard reject.
- **Items.** Twelve employer-separated holdout postings. One had no readable
  description and was excluded by the fixed rule for unreadable sources, so
  **N = 11**. The Owner showed **2** and hid **9**. Labels mean fit assuming the
  vacancy is open; availability was not scored.

## Custody facts

- The Owner-reported label-export SHA-256 matched the exported file.
- The seal commit `4944901b5249cad33a63204316f867ce082a1e80` was pushed to the
  host before the Owner reported that hash. The host's record of that push is
  the only independent ordering evidence in this round.
- The label lock and the fixed comparison each happened once, in local commits
  `0dce1af3c0a1636da2ca2d63eaa8a301fcf0efe2` (lock) and
  `5e9b47342f0ccd3aa0fb26e650bd9b5809455cc8` (comparison). Both are local and
  unpublished. The comparison commit holds the private per-posting output, so
  it, and any commit descended from it, must not be pushed.
- The comparison reported nine integrity checks, all true, and no network
  connection attempt. As pre-registered, it refuses to run if a hash differs,
  if a result already exists, or if the seal does not precede the lock.
- **Not established.** Code cannot prove that the Owner labelled alone, never
  saw candidate output, or labelled at a given time (label and commit times
  come from local clocks). It cannot prove that nobody read holdout text, or
  that no comparison was run privately first.

## Result

| Measure | Candidate | Current path |
|---|---|---|
| M1 exact tier agreement, of 11 | 5 / 11 | 1 / 11 |
| M2 Owner-shown placed hidden, of 2 | 0 / 2 | 0 / 2 |
| M3 Owner-hidden placed prominent, of 9 | 1 / 9 | 1 / 9 |
| M4 Owner-hidden not hidden, of 9 (secondary) | 5 / 9 | 9 / 9 |
| M5 shown-above-hidden pairs ordered correctly, of 2 × 9 = 18 | 16 / 18 | 15 / 18 |

**M6 eligibility wording, as reported:** missed warnings 0, false warnings 0,
assertion errors 0. **No posting was labelled by the Owner as targeting UAE
nationals.**

| Criterion, as pre-registered in the plan | Outcome |
|---|---|
| C0 sample gate: N ≥ 8, at least 2 Owner-shown, at least 2 Owner-hidden (below it the round is INCONCLUSIVE) | pass |
| C1 the candidate hides no Owner-shown posting (M2 = 0) | pass, 0 / 2 |
| C2 candidate M3 ≤ current M3, and candidate M3 ≤ 1 | pass, 1 and 1 |
| C3 candidate M1 ≥ current M1 + 2, and M1 / N ≥ 0.60 | **FAIL.** The margin held (5 ≥ 1 + 2); the rate did not (5 / 11 ≈ 0.45, and 7 of 11 was needed) |
| C4 candidate M5 correct ≥ current M5 correct | pass, 16 ≥ 15 |
| C5 eligibility: missed 0, assertion errors 0, false ≤ 1 | pass, 0 / 0 / 0, with the caveat below |

## Reading the result

- The candidate agreed with more Owner tiers than the current path (5 of 11
  against 1 of 11). It did not reach the pre-registered bar, and the bar is
  not adjusted afterwards.
- **C5 is untested for missed warnings.** With no posting labelled "targets UAE
  nationals", "missed = 0" holds vacuously. The round gives no evidence that
  the warning appears when it should.
- **M2 rests on two Owner-shown postings.** A 0 / 2 result is weak evidence
  that the candidate does not hide relevant roles.
- **M1 and M4 partly reflect the tier mapping.** The current path hides only on
  a hard reject, so it leaves every Owner-hidden posting visible. Pairwise
  ordering (M5) is the fairer comparison, and the candidate led it by one pair.
- **Scope.** Eleven scored postings from a holdout drawn from two employers,
  labelled by one person who also set the policy. No statistical significance
  is claimed, and the result does not show that the candidate is better or
  worse in general.
- **No public post-mortem.** Per-posting explanations of misses would identify
  private postings and Owner choices, so none is published. The revealed
  holdout must not be used to tune the candidate and must never be re-run as
  though blind.

## State after the round

- C is **NOT VALIDATED**. No candidate is adopted, and there is no production,
  ranking, API or UI change.
- The 12-job holdout is **revealed and consumed**. It cannot serve as a blind
  set again.
- The local branch `research/46.2-c-blind-eval` (head `c0b71c3`, three local
  commits ahead of the pushed `66c3326`) is preserved as private audit
  evidence. It was **not pushed** and must not be pushed or merged.
- An independent review found, before the result was pushed, that the
  public-format result carried individual Owner answers and per-posting
  predictions, which repository rules keep out of public commits. The
  repository publication gate's patterns do not target this class of content,
  so a gate PASS would not show that such a file is safe to publish.

## Proposed next step (not started)

A **v4** plan and a fresh evaluation set need an Owner decision. Plan v3 §10
proposed: new employers, readings sealed before labels, at least 30 scored
items, and a second labeller where the Owner agrees. Two suggested additions
for that decision:

- Specify the public result as aggregate-only by design, with per-posting rows
  private from the start.
- Include enough postings with nationality wording that the missed-warning
  check can fail.

See the [C status](DISCOVERY_46_2C_PUBLIC_STATUS.md) and
[project state](../governance/PROJECT_STATE.md).
