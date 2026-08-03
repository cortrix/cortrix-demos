# Order API Field Migration

## Business question

The order creation API is failing, and the code still sends `account_id`. What should change?

Two synthetic documents are intentionally similar:

- an outdated v1.0 integration guide uses `account_id` and is marked `superseded`;
- a current v2.0 release note requires `buyer_account_id` and is marked `current`.

The outdated guide may rank first. The demo application then applies a separate lifecycle policy and selects the highest-ranked result whose status is current.

## Responsibility boundary

Cortrix provides retrieved content, scores, retrieval paths, source and document identity, and observable evidence. The demo application owns the lifecycle decision. Retrieval rank and LLM output are not business truth.

## Profiles

- `full-stack`: performs a new manual run and requires the pinned runtime, BGE models, and external `deepseek-v4-flash` access.
- `replay`: renders a previously accepted run without making external calls.

No accepted English run is included in the initial scaffold.
