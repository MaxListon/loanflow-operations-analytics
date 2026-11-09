-- An application reaches the operational endpoint at its FIRST A_Pending,
-- A_Denied or A_Cancelled event. A_Pending is not proven disbursement.
CREATE OR REPLACE TABLE application_mart AS
WITH summary AS (
 SELECT application_id, min(event_time) AS created_at, max(event_time) AS last_event_at,
 min(event_time) FILTER(WHERE activity IN ('A_Pending','A_Denied','A_Cancelled')) AS resolved_at,
 arg_min(activity,struct_pack(t:=event_time,s:=source_sequence))
   FILTER(WHERE activity IN ('A_Pending','A_Denied','A_Cancelled')) AS outcome,
 count(*) AS event_count,
 count(*) FILTER(WHERE activity='A_Incomplete') AS incomplete_count,
 count(*) FILTER(WHERE activity='A_Validating') AS validation_count
 FROM events GROUP BY application_id
), offer_summary AS (
 SELECT application_id,count(*) AS offer_count FROM offers GROUP BY application_id
)
SELECT a.* EXCLUDE(requested_amount),nullif(a.requested_amount,0) AS requested_amount,
 (a.requested_amount=0) AS requested_amount_unknown,s.* EXCLUDE(application_id), coalesce(o.offer_count,0) AS offer_count,
 coalesce(s.resolved_at,(SELECT max(event_time) FROM events)) AS observed_until,
 epoch(coalesce(s.resolved_at,(SELECT max(event_time) FROM events))-s.created_at)/86400.0 AS observed_days,
 CASE WHEN resolved_at IS NOT NULL THEN epoch(resolved_at-created_at)/86400.0 END AS resolution_days,
 date_trunc('month',created_at)::DATE AS cohort_month,
 CASE WHEN a.requested_amount=0 THEN 'Unknown' WHEN a.requested_amount<10000 THEN '<10k' WHEN a.requested_amount<25000 THEN '10–25k' ELSE '25k+' END AS amount_band,
 coalesce(outcome,'Unresolved at cutoff') AS outcome_label
FROM applications a JOIN summary s USING(application_id)
LEFT JOIN offer_summary o USING(application_id);

-- Use APPLICATION state events only; mixing offer and workflow lifecycles
-- would create misleading double-counted intervals. Cap at the first endpoint.
CREATE OR REPLACE TABLE state_intervals AS
WITH ordered AS (
 SELECT e.application_id,e.source_sequence,e.activity,e.event_time,
 lead(e.event_time) OVER(PARTITION BY e.application_id ORDER BY e.event_time,e.source_sequence) AS next_at,
 m.created_at,m.observed_until,m.resolved_at,m.cohort_month,m.loan_goal,m.amount_band
 FROM events e JOIN application_mart m USING(application_id)
 WHERE e.origin='Application' AND e.event_time<=m.observed_until
)
SELECT *, coalesce(next_at,observed_until) AS interval_end,
 epoch(coalesce(next_at,observed_until)-event_time)/86400.0 AS interval_days
FROM ordered WHERE activity NOT IN ('A_Pending','A_Denied','A_Cancelled');

CREATE OR REPLACE TABLE state_case_durations AS
SELECT application_id,activity,sum(interval_days) AS days_in_state
FROM state_intervals GROUP BY application_id,activity;

-- Daily end-of-day backlog reconstructed using only events before the snapshot.
CREATE OR REPLACE TABLE daily_backlog AS
WITH dates AS (
 SELECT snapshot FROM generate_series(TIMESTAMPTZ '2016-01-02',TIMESTAMPTZ '2017-02-01', INTERVAL '1 day') t(snapshot)
)
SELECT d.snapshot::DATE-1 AS report_date,
 count(*) AS open_applications,
 count(*) FILTER(WHERE epoch(d.snapshot-m.created_at)/86400>=14) AS aged_14d,
 median(epoch(d.snapshot-m.created_at)/86400) AS median_age_days
FROM dates d JOIN application_mart m
 ON m.created_at<d.snapshot AND (m.resolved_at IS NULL OR m.resolved_at>=d.snapshot)
GROUP BY d.snapshot ORDER BY report_date;

CREATE OR REPLACE TABLE monthly_cohorts AS
SELECT cohort_month,count(*) AS applications,
 count(*) FILTER(WHERE outcome='A_Pending') AS pending_endpoint,
 count(*) FILTER(WHERE outcome='A_Denied') AS denied,
 count(*) FILTER(WHERE outcome='A_Cancelled') AS cancelled,
 count(*) FILTER(WHERE resolved_at IS NULL) AS unresolved,
 median(resolution_days) AS median_resolution_days,
 quantile_cont(resolution_days,0.9) AS p90_resolution_days,
 avg((incomplete_count>0)::INT) AS rework_rate,
 -- Fixed horizon gives cohorts equal follow-up. Null for immature cohorts.
 avg(CASE WHEN created_at+INTERVAL '30 days'<=(SELECT max(event_time) FROM events)
   THEN (resolved_at IS NOT NULL AND resolved_at<=created_at+INTERVAL '30 days')::INT END) AS resolved_within_30d
FROM application_mart GROUP BY cohort_month ORDER BY cohort_month;
