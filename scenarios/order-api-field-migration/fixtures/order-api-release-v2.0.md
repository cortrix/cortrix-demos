# Order Creation API Release Note v2.0

Status: Current

Effective date: July 1, 2026

Starting with v2.0, the order creation API requires `buyer_account_id`. The previous `account_id` field is no longer accepted as the current request field.

```json
{
  "order_no": "SO-10001",
  "buyer_account_id": "acct_2048"
}
```

This release note supersedes the field guidance in the v1.0 integration guide.
