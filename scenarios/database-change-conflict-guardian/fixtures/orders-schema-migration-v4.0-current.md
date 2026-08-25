# Orders schema migration 4.0

Status: current and approved. Effective: 2026-07-12.

The active Orders schema renamed `orders.account_id` to `orders.buyer_account_id`. Writers must use `buyer_account_id`; `account_id` is no longer present on `orders`.

Approved read-only diagnosis:

1. Inspect `information_schema.columns` or `pg_catalog` for the deployed `orders` table.
2. Inspect the application statement captured in deployment or incident telemetry.
3. Run `EXPLAIN` without `ANALYZE` inside a read-only transaction if a query plan is needed.
4. Compare the deployed statement with this approved migration and the current rollback-window notice.

This document does not authorize DDL, DML, rollback, configuration changes, or traffic changes.
