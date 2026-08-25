# Confirmed cause for the payment-latency incident shift handoff

For an engineer taking over this incident, the confirmed cause is payment gateway queue saturation after the regional failover. Queue depth reached 18,400 messages and oldest-message age reached 47 seconds while database metrics stayed within the established baseline. The timing preceded the p95 authorization latency increase by four minutes. This is a confirmed fact, not permission to remediate.
