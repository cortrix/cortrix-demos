# Returns buyer reference migration

The Returns service renamed `returns.customer_ref` to `returns.buyer_ref`. It uses a different table, release schedule, and rollback policy from Orders.

Do not apply this migration to `orders`.
