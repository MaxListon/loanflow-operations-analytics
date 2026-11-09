# Data dictionary

All timestamps are UTC; elapsed durations are calendar days. Raw zeros remain untouched in `applications`; analytical amounts use null plus an unknown flag. The source fields are anonymized historical records, not live customer accounts.

| Table | Grain | Purpose |
|---|---|---|
| applications | One row per source trace | Original requested amount, type and purpose |
| events | One row per application × source sequence | All source lifecycle events with timestamps, identities and offer references |
| offers | One row per offer creation | Separate offer grain; joined after aggregation |
| application_mart | One row per application | Endpoint, observed follow-up, outcome, counts and cohort |
| state_intervals | One row per nonterminal application-state visit | Nonoverlapping elapsed intervals capped at endpoint/cutoff |
| state_case_durations | One row per application × state | Sum across repeated visits before summary statistics |
| daily_backlog | One row per completed calendar day | Historical end-of-day open and aged counts |
| monthly_cohorts | One row per creation month | Equal-definition cohort reporting |
| landmark_features | One row per day-seven eligible application | Point-in-time features and 30-day label |
| test_predictions | One row per eligible final-test application | Retrospective probability and outcome for evaluation |

## Important fields and contracts

| Field | Definition |
|---|---|
| application_id | Source trace name; anonymized case identifier |
| source_sequence | Zero-based original event ordinal within its trace |
| event_order | One-based event rank by timestamp then source ordinal |
| event_id | Original EventID; not used as a substitute for source ordinal |
| activity | Source concept:name; surrounding whitespace trimmed |
| lifecycle | Source lifecycle transition; schedule/start/suspend/complete etc. remain distinct |
| origin | Source EventOrigin: Application, Offer or Workflow |
| resource | Anonymized source resource identifier; not a verified staffing role |
| offer_id | OfferID; for O_Create Offer, populated from the offer's EventID |
| accepted / selected | Source event attributes, retained for audit; not final application outcome labels |
| requested_amount | Raw requested amount in source table; zero becomes null in the mart |
| requested_amount_unknown | True for raw amount zero; analytic assumption documented in methodology |
| created_at | Earliest event time in the application |
| resolved_at | First A_Pending, A_Denied or A_Cancelled timestamp, or null |
| outcome | First terminal application state; ties use source sequence |
| observed_until | resolved_at if available; otherwise global source cutoff |
| observed_days | observed_until minus creation, in days |
| resolution_days | resolved_at minus creation, or null for censored applications |
| incomplete_count / validation_count | Number of source A_Incomplete / A_Validating events |
| offer_count | Number of offer creation rows, aggregated before application join |
| interval_end / interval_days | Next application state or observation endpoint; elapsed state duration |
| days_in_state | Sum of intervals in a state per application |
| cohort_month | UTC creation month, independent of resolution month |
| report_date | Calendar day whose end-of-day backlog is reported |
| aged_14d | Open applications at least 14 days old; a demo threshold, not a known bank SLA |
| resolved_within_30d | Rate among applications with complete 30-day follow-up |
| landmark_at | Creation + seven days; future feature events excluded strictly |
| events_7d | Number of all-origin events before the landmark |
| incomplete_7d / validation_7d / offers_7d | Corresponding activity counts observed before the landmark |
| resources_7d | Distinct observed anonymized resources before the landmark |
| state_7d | Last application state observed before the landmark |
| days_since_event | Landmark minus latest observed event, calendar days |
| latest_feature_at | Maximum contributing event timestamp; used to audit timing |
| unresolved_30d | 1 if no first endpoint by creation + 30 days; else 0 |
| split | train, validation, test or unused, determined by creation time |
| risk | Selected model's estimated probability of unresolved_30d=1 |

## Generated database schema

This inventory is captured from the actual built database. See the SQL files for full derivations.

### applications

| Column | Type |
|---|---|
| application_id | VARCHAR |
| requested_amount | DOUBLE |
| application_type | VARCHAR |
| loan_goal | VARCHAR |

### events

| Column | Type |
|---|---|
| application_id | VARCHAR |
| source_sequence | INTEGER |
| event_id | VARCHAR |
| activity | VARCHAR |
| lifecycle | VARCHAR |
| event_time | TIMESTAMP WITH TIME ZONE |
| origin | VARCHAR |
| resource | VARCHAR |
| offer_id | VARCHAR |
| offered_amount | DOUBLE |
| accepted | BOOLEAN |
| selected | BOOLEAN |
| event_order | BIGINT |

### offers

| Column | Type |
|---|---|
| offer_id | VARCHAR |
| application_id | VARCHAR |
| created_at | TIMESTAMP WITH TIME ZONE |
| offered_amount | DOUBLE |

### application_mart

| Column | Type |
|---|---|
| application_id | VARCHAR |
| application_type | VARCHAR |
| loan_goal | VARCHAR |
| requested_amount | DOUBLE |
| requested_amount_unknown | BOOLEAN |
| created_at | TIMESTAMP WITH TIME ZONE |
| last_event_at | TIMESTAMP WITH TIME ZONE |
| resolved_at | TIMESTAMP WITH TIME ZONE |
| outcome | VARCHAR |
| event_count | BIGINT |
| incomplete_count | BIGINT |
| validation_count | BIGINT |
| offer_count | BIGINT |
| observed_until | TIMESTAMP WITH TIME ZONE |
| observed_days | DOUBLE |
| resolution_days | DOUBLE |
| cohort_month | DATE |
| amount_band | VARCHAR |
| outcome_label | VARCHAR |

### state_intervals

| Column | Type |
|---|---|
| application_id | VARCHAR |
| source_sequence | INTEGER |
| activity | VARCHAR |
| event_time | TIMESTAMP WITH TIME ZONE |
| next_at | TIMESTAMP WITH TIME ZONE |
| created_at | TIMESTAMP WITH TIME ZONE |
| observed_until | TIMESTAMP WITH TIME ZONE |
| resolved_at | TIMESTAMP WITH TIME ZONE |
| cohort_month | DATE |
| loan_goal | VARCHAR |
| amount_band | VARCHAR |
| interval_end | TIMESTAMP WITH TIME ZONE |
| interval_days | DOUBLE |

### state_case_durations

| Column | Type |
|---|---|
| application_id | VARCHAR |
| activity | VARCHAR |
| days_in_state | DOUBLE |

### daily_backlog

| Column | Type |
|---|---|
| report_date | DATE |
| open_applications | BIGINT |
| aged_14d | BIGINT |
| median_age_days | DOUBLE |

### monthly_cohorts

| Column | Type |
|---|---|
| cohort_month | DATE |
| applications | BIGINT |
| pending_endpoint | BIGINT |
| denied | BIGINT |
| cancelled | BIGINT |
| unresolved | BIGINT |
| median_resolution_days | DOUBLE |
| p90_resolution_days | DOUBLE |
| rework_rate | DOUBLE |
| resolved_within_30d | DOUBLE |

### landmark_features

| Column | Type |
|---|---|
| application_id | VARCHAR |
| created_at | TIMESTAMP WITH TIME ZONE |
| landmark_at | TIMESTAMP WITH TIME ZONE |
| requested_amount | DOUBLE |
| requested_amount_unknown | BOOLEAN |
| application_type | VARCHAR |
| loan_goal | VARCHAR |
| events_7d | BIGINT |
| incomplete_7d | BIGINT |
| validation_7d | BIGINT |
| offers_7d | BIGINT |
| resources_7d | BIGINT |
| state_7d | VARCHAR |
| days_since_event | DOUBLE |
| latest_feature_at | TIMESTAMP WITH TIME ZONE |
| unresolved_30d | INTEGER |
| split | VARCHAR |

### test_predictions

| Column | Type |
|---|---|
| application_id | VARCHAR |
| created_at | TIMESTAMP WITH TIME ZONE |
| landmark_at | TIMESTAMP WITH TIME ZONE |
| state_7d | VARCHAR |
| loan_goal | VARCHAR |
| requested_amount | DOUBLE |
| unresolved_30d | INTEGER |
| risk | DOUBLE |


## Version 2 tables and outputs

| Table / report | Grain | Meaning |
|---|---|---|
| application_transitions | Adjacent application-state event pair | Elapsed time between state changes before the first endpoint |
| transition_summary | State pair | Transition occurrences, distinct applications and duration summaries |
| journey_variants | Full application-state sequence | Observed case counts and endpoint/duration summaries |
| pilot_baseline | Day-seven application state | Mature case count and separate 30-day outcome rates; unresolved cases remain in every denominator |
| robustness_predictions | Application × evaluation period | Fixed context, history-only and state-only retrospective probabilities |
| competing_outcomes.csv | Observed endpoint time | Censoring-aware cumulative incidence of pending, cancelled and denied first endpoints |
| example_journeys.json | Deterministically selected source case | Original application-state events and trace-level counts |
| source_provenance.json | Downloaded source version | Publisher checksum, measured source SHA-256, record counts and real-versus-assumed distinction |
| extraction_manifest.json | Source extraction | Source SHA-256 plus cached-CSV hashes; stored only in processed data |
| artifact_hashes.json | Generated source/report file | SHA-256 snapshot for build audit; publication packaging must verify it again |

The original model remains a retrospective context benchmark. The additional history-only model excludes requested amount, amount-missing flag, application type and loan purpose. Creation-week block intervals and November results are diagnostics, not new parameter-selection criteria.
