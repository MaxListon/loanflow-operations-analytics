-- Landmark prediction: among applications still open on day 7, identify
-- those not resolved by day 30. Use events STRICTLY BEFORE day 7.
CREATE OR REPLACE TABLE landmark_features AS
WITH eligible AS (
 SELECT *,created_at+INTERVAL '7 days' AS landmark_at
 FROM application_mart
 WHERE (resolved_at IS NULL OR resolved_at>created_at+INTERVAL '7 days')
 AND created_at+INTERVAL '30 days'<=(SELECT max(event_time) FROM events)
), history AS (
 SELECT m.application_id,count(*) AS events_7d,
 count(*) FILTER(WHERE e.activity='A_Incomplete') AS incomplete_7d,
 count(*) FILTER(WHERE e.activity='A_Validating') AS validation_7d,
 count(*) FILTER(WHERE e.activity='O_Create Offer') AS offers_7d,
 count(DISTINCT e.resource) AS resources_7d,
 arg_max(e.activity,struct_pack(t:=e.event_time,s:=e.source_sequence)) FILTER(WHERE e.origin='Application') AS state_7d,
 epoch(m.landmark_at-max(e.event_time))/86400 AS days_since_event,
 max(e.event_time) AS latest_feature_at
 FROM eligible m JOIN events e ON m.application_id=e.application_id AND e.event_time<m.landmark_at
 GROUP BY m.application_id,m.landmark_at
)
SELECT m.application_id,m.created_at,m.landmark_at,m.requested_amount,m.requested_amount_unknown,m.application_type,m.loan_goal,
 h.* EXCLUDE(application_id),
 (m.resolved_at IS NULL OR m.resolved_at>m.created_at+INTERVAL '30 days')::INT AS unresolved_30d,
 CASE WHEN m.created_at<TIMESTAMPTZ '2016-06-01' THEN 'train'
 WHEN m.created_at>=TIMESTAMPTZ '2016-07-01' AND m.created_at<TIMESTAMPTZ '2016-08-01' THEN 'validation'
 WHEN m.created_at>=TIMESTAMPTZ '2016-09-01' AND m.created_at<TIMESTAMPTZ '2016-11-01' THEN 'test'
 ELSE 'unused' END AS split
FROM eligible m JOIN history h USING(application_id);
