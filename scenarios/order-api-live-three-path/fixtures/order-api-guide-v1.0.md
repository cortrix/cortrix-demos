# Order Creation API Integration Guide v1.0

Version: v1.0 historical contract

This guide describes the former Create Order request. A client sends the buyer's account identifier in `account_id`.

```json
{
  "order_no": "SO-10001",
  "account_id": "acct_2048"
}
```

## Troubleshooting an unknown field error

If Create Order rejects the payload with `unknown field account_id`, verify that the request still includes `account_id` exactly as shown above. In the v1.0 contract, `account_id` is the request field for the customer account.

This historical integration guide is retained for v1.0 clients and has been superseded for current integrations.
