-- Executed from project root. No dataframe transformations hidden behind the SQL.
SET TimeZone='UTC';
CREATE OR REPLACE TABLE applications AS
SELECT * FROM read_csv('data/processed/applications.csv', header=true,
 columns={'application_id':'VARCHAR','requested_amount':'DOUBLE','application_type':'VARCHAR','loan_goal':'VARCHAR'});
CREATE OR REPLACE TABLE events AS
SELECT *, row_number() OVER (PARTITION BY application_id ORDER BY event_time,source_sequence) AS event_order
FROM read_csv('data/processed/events.csv',header=true,
 columns={'application_id':'VARCHAR','source_sequence':'INTEGER','event_id':'VARCHAR',
 'activity':'VARCHAR','lifecycle':'VARCHAR','event_time':'TIMESTAMPTZ','origin':'VARCHAR',
 'resource':'VARCHAR','offer_id':'VARCHAR','offered_amount':'DOUBLE','accepted':'BOOLEAN','selected':'BOOLEAN'});
CREATE OR REPLACE TABLE offers AS
SELECT offer_id,application_id,event_time AS created_at,offered_amount
FROM events WHERE activity='O_Create Offer';
