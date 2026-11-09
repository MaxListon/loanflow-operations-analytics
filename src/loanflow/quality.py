"""Fail the build on metric integrity errors; retain warnings as evidence."""
import json


def run_checks(con, root):
    rules = [
        ("source_application_count", "SELECT abs(count(*)-31509) FROM applications"),
        ("source_event_count", "SELECT abs(count(*)-1202267) FROM events"),
        ("application_primary_key", "SELECT count(*)-count(DISTINCT application_id) FROM applications"),
        ("event_primary_key", "SELECT count(*)-count(DISTINCT (application_id,source_sequence)) FROM events"),
        ("required_event_fields", "SELECT count(*) FROM events WHERE event_time IS NULL OR activity IS NULL OR application_id IS NULL"),
        ("event_references", "SELECT count(*) FROM events e ANTI JOIN applications a USING(application_id)"),
        ("offer_primary_key", "SELECT count(*)-count(DISTINCT offer_id) FROM offers"),
        ("offer_references", "SELECT count(*) FROM events e ANTI JOIN offers o ON e.offer_id=o.offer_id AND e.application_id=o.application_id WHERE e.offer_id IS NOT NULL"),
        ("valid_requested_amounts", "SELECT count(*) FROM applications WHERE requested_amount<0 OR requested_amount IS NULL"),
        ("mart_grain", "SELECT abs((SELECT count(*) FROM application_mart)-(SELECT count(*) FROM applications))"),
        ("event_reconciliation", "SELECT abs((SELECT sum(event_count) FROM application_mart)-(SELECT count(*) FROM events))"),
        ("offer_reconciliation", "SELECT abs((SELECT sum(offer_count) FROM application_mart)-(SELECT count(*) FROM offers))"),
        ("nonnegative_state_time", "SELECT count(*) FROM state_intervals WHERE interval_days<0"),
        ("state_time_reconciliation", "SELECT count(*) FROM (SELECT m.application_id,m.observed_days,sum(s.interval_days) AS days FROM application_mart m JOIN state_intervals s USING(application_id) GROUP BY m.application_id,m.observed_days HAVING abs(days-m.observed_days)>0.00001)"),
        ("feature_time_boundary", "SELECT count(*) FROM landmark_features WHERE latest_feature_at>=landmark_at"),
        ("label_followup", "SELECT count(*) FROM landmark_features WHERE created_at+INTERVAL '30 days'>(SELECT max(event_time) FROM events)"),
        ("valid_target", "SELECT count(*) FROM landmark_features WHERE unresolved_30d NOT IN (0,1)"),
        ("training_labels_precede_validation", "SELECT count(*) FROM landmark_features WHERE split='train' AND created_at+INTERVAL '30 days'>=(SELECT min(landmark_at) FROM landmark_features WHERE split='validation')"),
        ("validation_labels_precede_test", "SELECT count(*) FROM landmark_features WHERE split='validation' AND created_at+INTERVAL '30 days'>=(SELECT min(landmark_at) FROM landmark_features WHERE split='test')"),
    ]
    rules.extend([
        ('nonnegative_transition_time',"SELECT count(*) FROM application_transitions WHERE elapsed_days<0"),
        ('no_transitions_after_endpoint',"SELECT count(*) FROM application_transitions WHERE from_state IN ('A_Pending','A_Denied','A_Cancelled')"),
        ('variant_application_reconciliation',"SELECT abs((SELECT sum(applications) FROM journey_variants)-(SELECT count(*) FROM applications))"),
        ('pilot_population_reconciliation',"SELECT abs((SELECT sum(applications) FROM pilot_baseline)-(SELECT count(*) FROM landmark_features))"),
        ('pilot_outcome_rate_reconciliation',"SELECT count(*) FROM pilot_baseline WHERE abs(resolved_30d_rate-pending_30d_rate-cancelled_30d_rate-denied_30d_rate)>0.0000001")
    ])
    results = [{"check": name,"violations":int(con.execute(sql).fetchone()[0]),"sql":sql} for name,sql in rules]
    warnings = {
        "zero_requested_amount_unknown": int(con.execute("SELECT count(*) FROM applications WHERE requested_amount=0").fetchone()[0]),
        "repeated_source_event_ids": int(con.execute("SELECT count(*)-count(DISTINCT event_id) FROM events").fetchone()[0]),
        "timestamp_inversions_in_source_order": int(con.execute("SELECT count(*) FROM (SELECT event_time,lag(event_time) OVER(PARTITION BY application_id ORDER BY source_sequence) AS prev FROM events) WHERE event_time<prev").fetchone()[0]),
        "applications_with_multiple_terminal_states": int(con.execute("SELECT count(*) FROM (SELECT application_id FROM events WHERE activity IN ('A_Pending','A_Denied','A_Cancelled') GROUP BY 1 HAVING count(*)>1)").fetchone()[0]),
        "unresolved_at_cutoff": int(con.execute("SELECT count(*) FROM application_mart WHERE resolved_at IS NULL").fetchone()[0]),
    }
    report = {"passed": all(x['violations']==0 for x in results), "checks":results,"observations":warnings}
    (root / "reports/data_quality.json").write_text(json.dumps(report,indent=2))
    if not report['passed']:
        raise AssertionError("Data quality failed: " + str([x for x in results if x['violations']]))
    return report
