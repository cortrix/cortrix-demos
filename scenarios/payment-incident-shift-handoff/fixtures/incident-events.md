{"event_id":"pay-001","at":"2026-08-18T00:46:00Z","kind":"signal","subject":"payment-p95","state":"above-threshold"}
{"event_id":"pay-002","at":"2026-08-18T00:53:00Z","kind":"hypothesis","subject":"db-primary","state":"open","confidence":"low"}
{"event_id":"pay-003","at":"2026-08-18T01:18:00Z","kind":"observation","subject":"db-primary","metrics":"cpu-locks-connections-commit","state":"baseline"}
{"event_id":"pay-004","at":"2026-08-18T01:31:00Z","kind":"hypothesis_update","subject":"db-primary","state":"closed","evidence_ref":"db-metrics-0118"}
{"event_id":"pay-005","at":"2026-08-18T01:42:00Z","kind":"observation","subject":"gw-payments-east","metrics":"queue-depth-oldest-age","state":"rising-after-failover"}
{"event_id":"pay-006","at":"2026-08-18T02:02:00Z","kind":"cause_update","subject":"gw-payments-east","state":"confirmed","evidence_ref":"queue-correlation"}
{"event_id":"pay-007","at":"2026-08-18T02:18:00Z","kind":"change_request","subject":"worker-concurrency","state":"awaiting-approval"}
{"event_id":"pay-008","at":"2026-08-18T03:20:00Z","kind":"shift_boundary","subject":"incoming-operator","state":"inspect-only","checks_ref":"readonly-register"}
