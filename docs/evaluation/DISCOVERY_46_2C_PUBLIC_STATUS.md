# #46.2-C shadow evaluation status

The role-understanding candidate in this branch is offline and shadow-only. No AI model is connected, and production discovery and ranking do not import it.

The first development round has 16 saved Owner choices. The Owner saw Codex suggestions before saving them, so these choices are assisted feedback rather than blind ground truth. Fifteen items were scored; one was excluded for the recorded availability conflict. On those 15 development items, the shadow placement agreed with 14 Owner tiers and ordered all 54 shown-versus-hidden pairs correctly. D05 remains the disagreement: the Owner chose `LOWER`, while the candidate chose `PROMINENT`. These are in-sample results and do not establish improvement on unseen jobs.

The [development report](discovery_46_2c_shadow_eval_v2.json) contains development rows and aggregate holdout-boundary counts. The Owner's free-text label reasons, the frozen holdout manifest, and posting snapshots remain private and are intentionally absent from this publication branch. The offline evaluation script needs those private inputs to reproduce the report, so a public checkout cannot rerun that particular 15-item evaluation. The 12-job holdout remains reserved for a later blind round.

The candidate retains relevant UAE-national-worded roles lower with an eligibility warning. It makes no eligibility decision and performs no application action. The D05 policy choice, seniority thresholds, model selection, and blind evaluation remain open.
