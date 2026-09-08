# Order API v2 Buyer Identity Migration

Status: Current

Effective date: July 1, 2026

For Create Order requests under the v2 contract, set the buyer identifier in `buyer_account_id`. This field is required for all current integrations.

```json
{
  "order_no": "SO-10001",
  "buyer_account_id": "acct_2048"
}
```

Requests that use the retired v1 customer-identifier key fail schema validation. This bulletin supersedes the buyer field guidance in the historical v1.0 integration guide.
