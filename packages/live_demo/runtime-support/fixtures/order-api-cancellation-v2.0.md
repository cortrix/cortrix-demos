# Order API v2 Cancellation

Status: Current

Effective date: July 1, 2026

Cancel an existing order by sending its immutable `order_id` and a machine-readable `reason_code`.

```json
{
  "order_id": "ord_8091",
  "reason_code": "customer_request"
}
```

Cancellation fields apply after an order exists. They do not define the buyer identifier used by Create Order.
