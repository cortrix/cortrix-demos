# Orders write failure evidence

Observed: 2026-08-17.

The current application log reports `column "account_id" of relation "orders" does not exist`. A read-only catalog snapshot lists `buyer_account_id` and does not list `account_id` on `orders`. The deployed prepared statement still targets `orders(account_id, amount_cents)`.

No database change was executed while collecting this evidence.
