# Run B: Cortrix Read-only Plugin

## Purpose

Run B loads the same 21-document synthetic corpus into an isolated Cortrix namespace for each event-position variant. The pinned Harness sees exactly two model tools: `cortrix_search_evidence` and `cortrix_get_source`.

## Processing path

1. Read the same frozen question.
2. Load the front, middle, or end event export without changing any event identity.
3. Search the isolated namespace through the read-only plugin and expand every source in the same session.
4. Preserve the original Cortrix fusion rank, then order the bounded evidence set by the returned BGE reranker score with the fusion score as a deterministic tie-breaker.
5. Repeat the query and require identical document and source-hash order.
6. Give canonical evidence to the same Harness answer stage.
7. Require the application resolver to select option C, bind the replay evidence, identify the superseded option B conclusion, retain current constraints, and prohibit migration execution.
8. Require all three variants and cleanup receipts to pass before the aggregate can pass.
