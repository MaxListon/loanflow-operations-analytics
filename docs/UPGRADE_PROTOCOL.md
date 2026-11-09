# Version 2 evaluation protocol — frozen before running the extension

This extension improves analytical depth and auditability. It does not promise a higher predictive score or claim a real intervention improved operations.

1. Keep the original January–May training, July model selection and September–October evaluation unchanged. Do not tune on its previously inspected test results.
2. Freeze the selected seven-leaf boosting settings. Fit a second version using **event-history features only**, excluding all trace-level amount, purpose and application-type fields whose historical mutability is unknown. Compare it with the original context model and state-only baseline.
3. Evaluate both fixed models in November as an additional temporal audit. November aggregate operational data was previously inspected, so this is not a wholly untouched dataset or external validation. Do not use November to select model settings.
4. Quantify September–October uncertainty by resampling creation-week clusters, in addition to the existing individual-application bootstrap. There are few weeks: show the cluster count and the limitation.
5. Report monthly discrimination, calibration, review-capacity tradeoffs and worst-covered slices. Assess drift descriptively; do not optimize thresholds to test outcomes.
6. Add observed application-state transitions, common journey variants, endpoint-specific cumulative incidence, and deterministic examples traced back to original events.
7. Build a sample-size planning tool using measured day-seven A_Complete baseline and explicitly hypothetical effects. Display pending, cancelled and denied rates separately. No revenue, staffing cost, treatment effect or realized saving is inferred from missing fields.
8. Add provenance hashes, clean-checkout validation, full tests and user-visible metric-scope labels. Keep raw records outside the GitHub publication bundle.

Protocol status: local development decision record written before the extension was run, not a public preregistration or proof of independent validation.
