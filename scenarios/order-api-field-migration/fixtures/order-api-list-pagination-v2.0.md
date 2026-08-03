# Order API v2 List Pagination

Status: Current

Effective date: July 1, 2026

The List Orders endpoint uses cursor pagination. Send `page_after` with the previous response cursor and set `page_size` between 1 and 100.

```json
{
  "page_after": "ord_cursor_7f3a",
  "page_size": 50
}
```

Pagination fields apply only to listing orders. They do not define the buyer identifier used by Create Order.
