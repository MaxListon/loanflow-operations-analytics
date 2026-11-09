# Technical and analytical decisions

| Choice | Reason | Tradeoff |
|---|---|---|
| DuckDB rather than a hosted database | Runs real analytical SQL over a million events locally and remains easy to reproduce | Single-machine prototype; no multiuser warehouse claims |
| Streaming XML parsing | Avoid loading the entire expanded event log into memory | Sequential extraction; CSV staging consumes disk |
| Original trace ordinal retained | Stable tie-breaking for same-timestamp events | Source ordinal is not proof of a real sub-millisecond causal order |
| Source checksum required | A mirror can be verified against publisher bytes | Published MD5 is an integrity check, not a cryptographic authenticity guarantee |
| First terminal application event | Explicit, reproducible definition robust to a later contradictory endpoint | Other business endpoint definitions can produce different results |
| Application-state intervals | Prevents mixing overlapping workflow lifecycles and offer histories | Less detail about active work and customer-vs-bank waiting |
| Censored cases retained | Prevents inventing completion timestamps | Resolved-only summaries still have selection bias; labeled accordingly |
| Zero amounts treated as unknown | Avoids asserting that zero is meaningful loan value | An assumption; original value remains auditable |
| Fixed day-seven landmark | Simple feature availability rule and operationally explainable queue | Excludes applications already resolved by day seven and does not score dynamic daily risk |
| Temporal split with gaps | Labels used for selection are observed before later scoring periods | Less training data than random splits |
| Log loss for model selection | Rewards probability quality and penalizes confident errors | Highest validation AUC does not necessarily win |
| Simple baselines and logistic reference | Measures incremental complexity benefit | Boosting wins selection narrowly; operational preference may still favor simplicity |
| Self-contained HTML plus Streamlit | Recruiter can inspect instantly; analyst can filter detailed database-backed views | Two interfaces; their metric contracts must remain consistent |
| Mechanical scenario | Quantifies explicit assumptions without causal claims | No queue feedback, treatment response or realized savings |

The analysis started with incomplete-file handling as a plausible focus. The observed state-time concentration and outcome-mix comparison changed the recommended investigation priority. The final dashboard and memo follow the findings.
