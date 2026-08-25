# Run B: Cortrix Read-only Plugin

## Purpose

Run B loads the same 16-document synthetic corpus into an isolated Cortrix namespace. The pinned Harness sees exactly two model tools: `cortrix_search_evidence` and `cortrix_get_source`.

## Processing path

1. Read the same frozen question.
2. Search the isolated namespace through the read-only plugin.
3. Expand every returned source in the same tool session.
4. Preserve the original Cortrix fusion rank, then order the bounded evidence set by the returned BGE reranker score with the fusion score as a deterministic tie-breaker.
5. Repeat the query and require identical document and source-hash order.
6. Give the canonical evidence to the same Harness answer stage.
7. Require the application resolver to select the current handoff, bind the confirmed and ruled-out findings, and prohibit remediation.
8. Remove the namespace and verify campaign cleanup.

Cortrix supplies evidence. The application resolver remains the authority boundary.
