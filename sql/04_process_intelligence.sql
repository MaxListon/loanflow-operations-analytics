-- Adjacent application-state transitions, capped at the first endpoint.
CREATE OR REPLACE TABLE application_transitions AS
WITH sequenced AS (
 SELECT e.application_id,e.activity AS to_state,e.event_time AS entered_at,
 lag(e.activity) OVER w AS from_state,
 lag(e.event_time) OVER w AS left_at
 FROM events e JOIN application_mart m USING(application_id)
 WHERE e.origin='Application' AND e.event_time<=m.observed_until
 WINDOW w AS(PARTITION BY e.application_id ORDER BY e.event_time,e.source_sequence)
)
SELECT *,epoch(entered_at-left_at)/86400.0 AS elapsed_days
FROM sequenced WHERE from_state IS NOT NULL
AND from_state NOT IN ('A_Pending','A_Denied','A_Cancelled');

CREATE OR REPLACE TABLE transition_summary AS
SELECT from_state,to_state,count(*) AS transitions,count(DISTINCT application_id) AS applications,
 median(elapsed_days) AS median_days,quantile_cont(elapsed_days,0.9) AS p90_days
FROM application_transitions GROUP BY 1,2;

CREATE OR REPLACE TABLE journey_variants AS
WITH paths AS (
 SELECT e.application_id,string_agg(e.activity,' → ' ORDER BY e.event_time,e.source_sequence) AS path
 FROM events e JOIN application_mart m USING(application_id)
 WHERE e.origin='Application' AND e.event_time<=m.observed_until
 GROUP BY e.application_id
)
SELECT p.path,count(*) AS applications,median(m.resolution_days) AS median_days,
 avg((m.outcome='A_Pending')::INT) AS pending_endpoint_share
FROM paths p JOIN application_mart m USING(application_id) GROUP BY p.path ORDER BY applications DESC;

-- Mature, genuinely observed day-seven segment for pilot planning.
CREATE OR REPLACE TABLE pilot_baseline AS
SELECT f.state_7d,count(*) AS applications,
 avg((f.unresolved_30d=0)::INT) AS resolved_30d_rate,
 avg(coalesce((m.outcome='A_Pending' AND m.resolution_days<=30),false)::INT) AS pending_30d_rate,
 avg(coalesce((m.outcome='A_Cancelled' AND m.resolution_days<=30),false)::INT) AS cancelled_30d_rate,
 avg(coalesce((m.outcome='A_Denied' AND m.resolution_days<=30),false)::INT) AS denied_30d_rate
FROM landmark_features f JOIN application_mart m USING(application_id)
GROUP BY f.state_7d ORDER BY applications DESC;
