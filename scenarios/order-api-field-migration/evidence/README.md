# Evidence

Candidate and rejected runs stay in the ignored root `.runs/` directory.

After human acceptance, a sanitized run may be promoted to:

```text
evidence/runs/<run_id>/
```

The promotion must preserve the exact run ID, accepted local commit, review identity, manifests, checksums, resolver output, cleanup receipt, and screenshot manifest. Historical 1.2.0 evidence is retained, but the current 2.0.0 accepted-run pointer remains empty until a new candidate receives Human Review.
