# Warehouse orders regional incident

The `warehouse_orders` ingestion pipeline once reported a missing `shipping_account_id` field in a regional feed. The pipeline is operated separately from the transactional Orders schema. Orders migration 4.0 neither defines nor repairs `warehouse_orders.shipping_account_id`.
