# Orders audit column reference

The `orders_audit` table retains `account_id_snapshot` for historical reporting. That audit field is not accepted by the active `orders` write path and does not replace `orders.buyer_account_id`.
