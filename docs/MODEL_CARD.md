# Model card — day-seven unresolved-application risk

**Purpose:** Prioritize investigation of potentially long-running applications. This is a retrospective prototype, not a lending eligibility system or a deployed support policy.

## Target and population

Among applications without a pending, cancelled or denied endpoint by creation + seven days, predict whether the first endpoint occurs after day 30 or remains unobserved at that horizon. Cases require at least 30 calendar days of source observation. A case resolved exactly at day seven is excluded; a case resolved exactly at day 30 is labeled resolved. Events at the landmark itself are excluded from features.

The target deliberately counts cancellation and denial as resolution. It measures operational delay, not a desirable customer outcome, successful lending or profitable lending.

## Inputs

Requested amount and unknown flag; application type; loan purpose; counts of observed events, incomplete-state events, validating events, offers and distinct observed resource IDs; most recent application state; days since last observed event. Resource IDs are counted, not one-hot encoded as individual staff predictors. Loan purpose and requested amount are source trace attributes treated as creation-time context. A live deployment would need to verify they are truly available and immutable at scoring time, since the historical trace does not provide field-level revisions. Re-run without them if that cannot be established.

No eventual outcome, full-journey event count, later credit score, final offer count or future state duration is included.

## Chronological development

| Role | Application creation dates | Eligible cases | What is learned |
|---|---|---:|---|
| Training | January–May 2016 | 10,452 | Imputation, scaling, category vocabulary and model parameters |
| Gap | June | Excluded | Separates training outcome windows from validation |
| Validation | July 2016 | 2,817 | Select lowest log loss from five preset candidates |
| Gap | August | Excluded | Separates validation outcome windows from testing |
| Final test | September–October 2016 | 5,687 | Report selected-model and preset baseline performance |

Other months are not used for model selection/testing. The selected model remains fit on training only; it is not refit on validation. All preprocessing is inside the fitted pipeline. Tree early stopping is disabled, avoiding a random internal validation split.

Candidates are logistic regression with C=0.1, 1 or 10 and histogram gradient boosting with 7 or 15 leaves, 150 iterations, learning rate 0.05 and L2 regularization 10. Model selection uses validation log loss, rather than trying to maximize test AUC. See the actual trial log in `reports/model_metrics.json`.

Baselines: constant training prevalence, and current-application-state rates smoothed toward training prevalence with 20 pseudo-observations. Smoothing is a preset demonstration choice, not a test-tuned setting. The best validation logistic regression is also retained as an interpretable reference.

## Delivered results

Selected: histogram gradient boosting with seven leaves. Test unresolved prevalence is 38.21%.

| Metric | Constant prevalence | State-only baseline | Logistic reference | Selected boosting |
|---|---:|---:|---:|---:|
| ROC AUC | 0.500 | 0.652 | 0.691 | 0.696 |
| Average precision | 0.382 | 0.475 | 0.533 | 0.539 |
| Brier score | 0.2362 | 0.2068 | 0.2031 | 0.2027 |
| Log loss | 0.6654 | 0.5856 | 0.5770 | 0.5750 |

A 500-replicate seeded application bootstrap gives selected-model AUC 95% interval approximately **0.681–0.709**, and Brier improvement over the state-only baseline approximately **0.0024–0.0054**. Intervals do not incorporate temporal clustering, model-selection uncertainty or another institution's distribution. They do not establish that boosting meaningfully beats logistic regression.

At exactly the top ceil(20% × N) cases, 1,138 applications are selected. Precision is 55.10%, recall is 28.85%, and concentration over prevalence is 1.44×. Ties are broken by existing application-ID order, without reading outcomes. A constant-score baseline's top-capacity metrics reflect this arbitrary tie order; expected lift under random selection is 1.

Calibration plots use eight test probability-quantile bins. Small subgroup results are excluded from the slice report below 100 cases. This is a calibration diagnostic, not a comprehensive fairness audit. Protected attributes and complete underwriting context are unavailable.

## Limitations and operating decision

The incremental gain over logistic regression is small. An operations team could reasonably prefer logistic regression for explanation and maintenance even though the declared selection criterion picks boosting. Operational utility requires intervention cost and treatment-effect evidence, neither of which is provided by these data.

The prototype is not deployed. A live implementation would need immutable point-in-time source fields, monitoring by calendar cohort, recalibration evaluation, domain-approved endpoints and a controlled support-policy experiment. Logistic coefficients in `reports/logistic_coefficients.csv` describe the logistic reference only; they are not explanations of the boosted model.


## Version 2: fixed-model robustness and temporal extension

The [extension protocol](UPGRADE_PROTOCOL.md) was recorded before running these diagnostics. It does not alter the original model-selection split. November operational aggregates had already been viewed; the additional November evaluation is not a claim of an entirely untouched dataset or external validation.

| Evaluation | Cases | Context model AUC / Brier | History-only AUC / Brier | State-only AUC / Brier |
|---|---:|---|---|---|
| September–October | 5,687 | 0.696 / 0.2027 | 0.664 / 0.2072 | 0.652 / 0.2068 |
| November | 2,466 | 0.671 / 0.2040 | 0.643 / 0.2065 | 0.637 / 0.2058 |

The history-only model uses six timestamped event-history measures plus current application state, with the same frozen seven-leaf boosting settings. It removes requested amount, unknown-amount flag, application type and loan purpose. That addresses uncertain trace-field history, but loses predictive information. Its Brier score is slightly worse than the state-only baseline in both evaluations; more complexity is not automatically warranted.

Creation-week cluster bootstrap gives the context model September–October AUC interval **0.679–0.713** across **10 clusters**. In November there are only **five clusters**, and the Brier-improvement interval over the state baseline crosses zero. These are sensitivity diagnostics with limited temporal support.

**Operating recommendation:** keep the context model as a retrospective benchmark until creation-time availability is verified. If immutable context cannot be established, start a support-policy pilot with the transparent state-only rule; the history-only challenger has not demonstrated consistent probability-quality improvement. No model is deployed for lending decisions. All target outcomes and score-based policies require experimental evaluation before claiming customer benefit.
