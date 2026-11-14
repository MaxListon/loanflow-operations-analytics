# LoanFlow — executive decision memo

**Decision:** Prioritize investigation of the A_Complete stage and a measured customer-follow-up pilot, subject to verifying state semantics, case mix and intervention cost.

This is a retrospective portfolio analysis of BPI Challenge 2017. No bank intervention was performed.

## What the data shows

- Scope: **31,509 applications**, **1,202,267 events**, and **42,995 offers**.
- Median time to the first operational endpoint: **19.1 calendar days**; 90th percentile: **35.0 days**. These duration summaries include resolved applications only; **98** remain unresolved at the observation cutoff.
- The largest application-state time bucket is **A_Complete**, at **69.8%** of accumulated elapsed time among resolved cases. That's elapsed state time, not employee effort.
- **47.6%** of applications have at least one incomplete-state event. In resolved January–October cohorts, their median duration differs from other resolved cases by **-13.1 days** (application bootstrap 95% interval **-13.5–-10.8**). The pooled incomplete-file group is faster, but the no-incomplete group contains many long cancellation journeys. Within the pending-endpoint group, incomplete cases have a longer median (16.9 vs. 11.2 days). Outcome mix and selection matter; neither comparison is causal.

## Early-warning model

Among applications still open on day seven, a validation-selected model predicts whether they remain unresolved at day 30. The final evaluation uses September–October applications, separate from training and July model selection.

- Test cases: **5,687**; unresolved prevalence: **38.2%**.
- ROC AUC: **0.696**; average precision: **0.539**.
- Brier score: **0.203**, compared with **0.236** for training-prevalence predictions and **0.207** for the stronger state-only baseline. The gain over the logistic reference is small enough that a simpler model may be preferable operationally.
- Reviewing the highest-risk 20% identifies a group with **55.1%** unresolved outcomes, a **1.44×** concentration over the test population, capturing **28.9%** of unresolved outcomes.

These risk scores are meant to prioritize a support-policy experiment — not to approve or deny credit. And flagging risk retrospectively doesn't by itself show that intervening will actually help.

## Size the opportunity without claiming savings

Mechanically compressing A_Complete intervals by 25%, while holding all other intervals and outcomes fixed, changes median time among historically resolved cases from **19.1** to **16.5 days**. The total comes to **119,744 application-days** — a unit of time, not staff-days, money saved, or a causal forecast. Unresolved cases and queue feedback are excluded.

## Recommended pilot

1. Enroll applications still open on day seven that are in the A_Complete state; freeze eligibility before assignment.
2. Randomize by application to existing service or a clear next-step summary plus targeted follow-up. Keep contact cadence, privacy and service policies consistent with the operating institution.
3. Primary outcome: resolved by day 30, evaluated by intention to treat. Report pending, cancellation and denial separately: faster cancellation is not automatically a better customer outcome.
4. Guardrails: support contacts, complaints, completion/acceptance outcomes, and treatment burden. Specify handling for repeat offers and multiple applications if linkage becomes available.
5. Estimate the target segment's baseline from the data; set a meaningful minimum effect and intervention cost with stakeholders before calculating sample size. Do not launch based on the scenario alone.

## Reliability and limits

**24 integrity checks passed.** Source checksum matches the publisher. Missing/zero requested amounts are preserved in raw data and modeled as unknown. First terminal events define endpoints; some applications have later terminal events, retained in raw data. This is a historical dataset from one Dutch institution, with follow-up through early 2017 — it says nothing about current performance or how well it would transfer to another bank.

Source: van Dongen (2017), [BPI Challenge 2017](https://doi.org/10.4121/uuid:5f3067df-f10b-45da-b98b-86ae4c7a310b). See `docs/METHODOLOGY.md`, `reports/data_quality.json` and `reports/model_metrics.json` for definitions and audit evidence.


## Additional validation and the operating recommendation

The frozen context model's AUC declines to **0.671** on **2,466 November cases**. Removing uncertain trace-context fields yields history-only AUC **0.664** in September–October and **0.643** in November. Its Brier score is slightly worse than the transparent state-only baseline in both periods. These diagnostics support a simple state-based support-policy experiment unless context-field immutability and the value of added complexity can be established. One caveat: the November operational aggregates had already been looked at before this extension was built, so this isn't external validation or a claim that the dataset was held out untouched.

The pilot segment contains **23,181** observed A_Complete cases still open on day seven, with baseline 30-day resolution **55.8%**. An **assumed five-percentage-point absolute effect** requires approximately **1,525 applications per arm** under a two-sided normal approximation (alpha=.05, power=.80, equal independent arms, no attrition/clustering adjustment). Historical recruitment volume implies **6.9 weeks**, plus **23 days** after the final day-seven randomization to observe the day-30 horizon. That's planning arithmetic — not a measured treatment effect, and not a forecast of future volume.

Raw data is real observational data; source hashes and original-case event matches are recorded in `reports/source_provenance.json` and the tests. A clean source rebuild reproduced the primary metrics in `reports/reproduction_check.json`. The interactive real-journey examples use original source application IDs and event ordinals.
