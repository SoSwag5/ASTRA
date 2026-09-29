# #46.2-C shadow evaluation status

**C is NOT VALIDATED.** The v3 blind round ran once and **FAILED** its pre-registered criteria (criterion C3). No candidate is adopted and production is unchanged. The aggregate result is in the [v3 blind outcome](DISCOVERY_46_2C_V3_BLIND_OUTCOME.md).

The role-understanding candidate is offline and shadow-only. No AI model is connected, and production discovery and ranking do not import it.

## Blind round v3: FAIL

- **Result.** Eleven postings were scored: 2 the Owner showed and 9 the Owner hid. One more had no readable description and was excluded by the fixed rule. Exact tier agreement was 5 of 11 for the candidate against 1 of 11 for the current path. Criterion C3 needed a margin of at least 2 over the current path (met) and agreement of at least 0.60, which is 7 of 11 (not met). C0, C1, C2, C4 and C5 passed.
- **Untested check.** No posting was labelled as targeting UAE nationals, so the eligibility-warning check for missed warnings passed vacuously and the round is no evidence that the warning appears when it should.
- **Consequences.** The candidate is rejected. [PR #76](https://github.com/SoSwag5/ASTRA/pull/76), which carried it, is **CLOSED and NOT MERGED**. The 12-job holdout is revealed and consumed, so it must never be reused as blind or used to tune the candidate.
- **Private retention.** The full fixed comparison output is retained privately and is not published. The outcome page is a redacted derivative, so a reader cannot reproduce individual rows from this repository. The local branch that holds the private output is preserved as audit evidence and is not pushed.
- **Next.** A v4 plan with a fresh evaluation set is proposed and not started. It needs an Owner decision.

## Historical v2 development evidence (assisted, in-sample)

These figures describe the earlier v2 candidate on assisted development labels. They are not blind results, and they are not the v3 candidate that the blind round tested.

The first development round has 16 saved Owner choices. The Owner saw Codex suggestions before saving them, so these choices are assisted feedback rather than blind ground truth. Fifteen items were scored; one was excluded for the recorded availability conflict. On those 15 development items, the shadow placement agreed with 14 Owner tiers and ordered all 54 shown-versus-hidden pairs correctly. D05 remains the disagreement: the Owner chose `LOWER`, while the candidate chose `PROMINENT`. These are in-sample results and do not establish improvement on unseen jobs.

The [development report](discovery_46_2c_shadow_eval_v2.json) contains development rows and aggregate holdout-boundary counts. The Owner's free-text label reasons, the frozen holdout manifest, and posting snapshots remain private and are intentionally absent from this publication branch. The offline evaluation script needs those private inputs to reproduce the report, so a public checkout cannot rerun that particular 15-item evaluation. The 12-job holdout was later used for the v3 blind round above and is now revealed.

The candidate design retains relevant UAE-national-worded roles lower with an eligibility warning. It makes no eligibility decision and performs no application action. The blind round could not test that behaviour, because no posting was labelled as targeting UAE nationals. The policy choice for the development disagreement, the seniority thresholds and model selection remain unvalidated.
