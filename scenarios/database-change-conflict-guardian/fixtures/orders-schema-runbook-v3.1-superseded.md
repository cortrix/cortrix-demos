# Orders schema migration runbook 3.1

Status: superseded on 2026-07-12 by Orders schema migration 4.0.

For the retired 3.1 schema, application writes used `orders.account_id`. Operators diagnosed write failures by checking that column and could roll back while the 3.1 deployment window remained open.

This runbook is retained for incident history. It does not describe the active 4.0 schema and must not authorize a rollback or any database change.
