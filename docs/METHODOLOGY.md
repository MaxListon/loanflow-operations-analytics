# Methodology and metric contracts

## Unit of analysis and endpoint

An application is a trace in the original XES. An event is identified by `(application_id, source_sequence)`; source EventID is retained and checked separately. Offers have their own IDs and a many-to-one relationship to applications. Loan amount is never summed over event rows.

Creation is the earliest event timestamp. The endpoint is the **first** A_Pending, A_Denied or A_Cancelled event ordered by timestamp and original trace ordinal. This is an explicit operational definition. A_Accepted is an intermediate application state; it is not used as final acceptance. A_Pending does not prove funding. Later terminal events are retained but do not redefine the endpoint.

The observation cutoff is the maximum timestamp in the downloaded log: 2017-02-01 14:11:03.499 UTC. The publisher's local-time description should not be substituted for this parsed UTC timestamp.

## Time, grain and missingness

All calculations use continuous **calendar days**, not working days. Timezone-aware timestamps are converted to UTC. No unverified working-day calendar, staff hours or service agreement is assumed. The backlog's 14-day age flag is a demonstration threshold, not an actual bank SLA.

Application state intervals use only EventOrigin=Application. LEAD finds the next application state; the final interval ends at the first endpoint or the observation cutoff. Terminal states have no accumulated post-endpoint time. Same-timestamp events retain original trace order. Application-level interval totals reconcile to observed duration within 0.00001 days.

A state can be visited repeatedly. Time is summed within application × state first, then median and P90 are calculated over applications that visit that state. The overall share divides accumulated state time by total elapsed state time for resolved applications. Interval time is elapsed residence in a state, not direct employee effort. A_Complete's name does not mean the application journey has reached its final endpoint; its precise operational cause requires additional domain confirmation.

Raw requested amounts of zero are not silently dropped or accepted as real zero-value requests: the mart uses null with an unknown flag and a distinct amount band. The model uses training-fitted median imputation plus the unknown flag. No other arbitrary event deduplication is performed.

## Metrics

| Metric | Numerator / definition | Population |
|---|---|---|
| Median/P90 resolution | Endpoint time minus creation | Resolved applications only |
| Incomplete-file incidence | Applications with ≥1 A_Incomplete event | All applications in selected cohort |
| Thirty-day resolution | First endpoint ≤ creation + 30 days | Applications with a full observed 30-day window |
| Pending endpoint share | First endpoint A_Pending | All applications in selected group |
| Backlog | Created before next midnight and no endpoint before that boundary | All applications, reconstructed per day |
| Aged backlog | Backlog cases at least 14 calendar days old | Same daily snapshot |
| State elapsed share | State application-days / all state application-days | Resolved cases only |

In the standalone demo, the cohort selector changes cards, outcome mix and state scorecards. Cohort trends and backlog deliberately retain all cohorts and are labeled accordingly. Early-warning results use a fixed test population. Scenarios use all resolved cases. The Streamlit workspace adds loan-purpose/amount filters and a stage selector.

## Censoring

Unresolved cases have no invented resolution duration. They retain observed follow-up to the log cutoff and contribute to a Kaplan–Meier curve until censoring. The curve estimates survival in the unresolved state, not survival of customers. The administrative cutoff is related to application date; cohort differences can make pooled curves difficult to interpret. The fixed 30-day outcome includes only cases with complete follow-up and avoids comparing immature cohorts with mature cohorts.

## Rework association and outcome mix

The main comparison uses resolved January–October applications, split by presence of an incomplete-state event. A seeded, 1,000-replicate application bootstrap estimates the median difference. Bootstrap intervals are descriptive and do not account for calendar clustering.

The pooled median is lower for applications with incomplete events. Looking within the first endpoint reveals a different pattern: pending and denied cases with incomplete events have longer medians than their same-endpoint counterparts without incomplete events. The no-incomplete population contains many long cancellation journeys. This comparison demonstrates a composition problem; conditioning on final outcome is itself retrospective selection and is **not** a causal adjustment. Neither comparison proves that creating or avoiding an incomplete event changes duration.

## Prediction

See MODEL_CARD.md. All time-dependent features use events strictly earlier than day seven. The population is still unresolved at day seven; the label is still unresolved after day 30. Credit scoring variables available only at offer creation or subsequent updates are not automatically used. No applicant approval/denial model is built.

## Scenarios and recommended experiment

The default scenario compresses each resolved application's observed A_Complete time by a user-selected fraction and subtracts that amount from total duration. Other state intervals and outcomes stay fixed. Time cannot be reduced below zero. This ignores downstream queue feedback, reallocation, behavior change and outcome change. Application-days are not staff-days. The scenario cannot support a dollar-savings claim.

The proposed pilot targets eligible day-seven A_Complete cases, randomizes a next-step/follow-up intervention, and measures resolution by day 30 with pending/cancelled/denied outcomes separated. Follow-up must not incentivize early cancellation merely to improve the speed metric. Cost assumptions, meaningful minimum effect and sample size require stakeholder input before launch. No intervention was run in this portfolio project.

## Source

B. van Dongen (2017), [BPI Challenge 2017](https://doi.org/10.4121/uuid:5f3067df-f10b-45da-b98b-86ae4c7a310b). Original bytes verified against publisher MD5. The download mirror is recorded in provenance and accepted only on matching checksum. The institution is historical and anonymous; external validity is untested.


## Version 2 statistical and operational evidence

`04_process_intelligence.sql` adds adjacent application-state transitions, complete journey variants and a mature day-seven A_Complete pilot population. A transition can be visited multiple times; transition counts and distinct-application counts are reported separately. Variant counts sum to the full application population. Transitions out of terminal states are excluded. Illustrative journeys are selected by the first application ID within each documented category and retain source ordinals; they are not representative or treatment examples.

The competing-outcome estimator uses Aalen–Johansen increments for mutually exclusive first pending/cancelled/denied endpoints. At each observed time, incidence increases by unresolved probability immediately before that time times endpoint count divided by the pre-time risk set. Censoring leaves that risk set after tied endpoint increments. The unresolved probability plus all three cumulative incidences sums to one. The chart shows the first 60 days; the CSV retains all observed endpoint times.

Sample-size planning uses the two-sided, equal-arm normal approximation for a difference in independent proportions. The baseline is measured among mature day-seven A_Complete applications. The absolute effect is a user assumption, never fitted to observational outcomes. For p0, p1=p0+effect and pbar=(p0+p1)/2, per-arm size is the ceiling of `(z_(1-alpha/2)*sqrt(2*pbar*(1-pbar)) + z_power*sqrt(p0*(1-p0)+p1*(1-p1)))^2 / effect^2`. No continuity correction, clustering or attrition adjustment is made. Recruitment duration uses historical eligible cases divided by 366/7 weeks in 2016, and is not a prediction of future volume.

The extension's model settings are frozen before evaluating an event-history-only ablation and November temporal audit. Creation-week block bootstrap resamples complete creation-week groups rather than isolated applications. Ten original-test clusters and five November clusters are too few to support strong generalization claims. See the model card for observed deterioration and baseline comparisons.

Every warehouse connection explicitly sets UTC. This matters when a viewer's operating-system timezone would otherwise shift day or month boundaries. Extracted CSVs are accepted from cache only when source and output SHA-256 hashes match the extraction manifest. Synthetic data is used solely for automated edge-case tests; no synthetic records enter analytical tables or dashboard results.
