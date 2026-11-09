# Resume and interview materials

## Project title

**LoanFlow | Loan Operations Analytics & Early-Warning System**

**Stack:** Python, SQL, DuckDB, pandas, scikit-learn, Plotly, Streamlit, pytest.

## Resume bullets

Use only the bullets you can explain and reproduce. Link the interactive demo and repository when you publish them.

- Built a Python/SQL analytics pipeline for **1.2M loan-process events across 31,509 applications**, reconciling application, offer and elapsed-time metrics with **24 automated integrity checks**.
- Developed an interactive operations dashboard that identified **69.8% of resolved-case elapsed state time in one process stage**, with cohort analysis, historical backlog reconstruction and outcome-specific rework comparisons.
- Evaluated day-seven delay models on **5,687 later applications**, achieving **0.696 ROC AUC and 1.44× top-quintile lift**; compared calibration and Brier scores against constant-risk, state-only and logistic baselines.

For analytics roles, prioritize the first two. For roles requesting machine learning, include the third. Describe the improvement tool as a scenario analysis, not a delivered reduction. Do not claim savings, production deployment, bank employment, intervention success or two months of work unless independently true.

## A 60-second project explanation

“I built LoanFlow to answer where an operations manager should investigate delays in a loan application process. The source had over a million events, including multiple offers and repeated workflow lifecycles, so the first challenge was defining a trustworthy application-level dataset. I built SQL reporting tables and reconciliation checks, then created a dashboard of turnaround time, backlog and process states. The analysis changed my initial hypothesis: incomplete-file cases looked faster overall, but the outcome mix explained why that comparison was misleading. The largest time concentration was in A_Complete. I also tested an early-warning model using only information observed by day seven and evaluated it on later applications. Finally, I built a transparent improvement scenario and proposed a randomized follow-up pilot, without claiming that historical associations prove an intervention would work.”

## Interview questions to prepare

1. Why does joining offers directly to events inflate counts? Show the aggregated offer join.
2. Why isn't A_Accepted your final success event? Explain the declared endpoint contract and domain uncertainty.
3. What happens to the 98 unresolved applications? Show null resolution durations, censoring and the fixed-horizon denominator.
4. Why can incomplete-file cases look faster overall? Show the endpoint-mix table; explain why conditioning on final outcomes is not causal adjustment.
5. How do you know the model cannot read events after day seven? Show the SQL predicate and future-event regression test.
6. Why use validation log loss? Explain probability quality and why model choice cannot be driven by the final test.
7. Why might you choose logistic regression anyway? The boosting gain is small; explain maintenance and interpretation costs.
8. Does 1.44× lift mean the bank would save 44% more time? No: it measures concentration of unresolved outcomes, not time savings or treatment response.
9. What would change for deployment? Point-in-time field history, agreed endpoints, fresh validation, monitoring and a tested support intervention.
10. What decision changed because of your analysis? Prioritize investigating A_Complete rather than assuming incomplete-file handling is the largest opportunity.

## Recruiter walkthrough (three minutes)

- **0:00–0:30:** Open the standalone dashboard. State the business decision and dataset size.
- **0:30–1:15:** Change the creation-quarter filter. Explain median vs P90 and backlog.
- **1:15–2:00:** Show process analysis and the outcome-mix reversal. Explain a metric pitfall you prevented.
- **2:00–2:30:** Show early warning, the simple baseline and honest performance limits.
- **2:30–3:00:** Move the scenario slider. Distinguish a hypothetical opportunity from a proven improvement; describe the pilot.

## Publication checklist

The repository and dashboard links are provided in the project README after publication. Before sharing a public repository, use `.gitignore` to omit raw records, extracted files, the database and fitted binary model. Keep the dashboard, source code, tests, reports and dataset attribution. The portable ZIP already omits source records and processed data. Review the dataset terms before any redistribution or commercial reuse. Replace this guide's instructions with links to your actual hosted demo/repository when those exist.


## Version 2 additions to defend

Explain why the November audit is additional temporal evidence rather than an untouched dataset, why the history-only model loses information, and why the state-only rule can be preferable on Brier score despite lower AUC. Show the measured pilot baseline and change the assumed effect to explain why smaller effects need larger samples. Trace one real application from the journey explorer back to its source ordinal. Explain the UTC boundary test and the cached-data corruption test.

An additional optional resume bullet: “Extended model validation with a 2,466-application temporal audit, event-history-only sensitivity analysis and calendar-block uncertainty; designed a pilot-planning tool using observed outcome baselines and explicit effect assumptions.”


## Service engineering resume option

“Implemented an authenticated historical-replay API with point-in-time input validation, immutable checksummed JSON releases, atomic activation/rollback and aggregate monitoring; verified SQL-to-API parity on real source events and exercised concurrent requests against an actual server process.”

Describe the Docker/CI setup as provided configuration until the container and hosted checks actually pass. Explain why the serving model is deliberately simpler than the retrospective context benchmark, why new cohorts are rejected, and why predictive accuracy does not establish intervention benefit.
