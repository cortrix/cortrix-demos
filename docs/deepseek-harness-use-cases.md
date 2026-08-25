# DeepSeek Harness Use Cases

The four synthetic scenarios demonstrate a narrow capability: an Agent can request source-bound semantic evidence before it explains a technical situation, while an application-owned resolver remains responsible for authority and allowed actions.

| Scenario | Evidence problem | Demonstrated result |
| --- | --- | --- |
| Database Change Conflict Guardian | A prominent runbook conflicts with the approved schema migration | Cortrix returns current migration evidence and the resolver permits only a read-only diagnostic plan |
| API Version Drift Coding Agent | An obsolete SDK example conflicts with the current API | Cortrix returns the current API, deprecation notice, migration guide, and maintained tests |
| Payment Incident Shift Handoff | A superseded shift snapshot hides the current incident state | Cortrix returns the current handoff, confirmed facts, ruled-out hypotheses, pending remediation, and read-only checks |
| Migration Decision Recovery | A long event stream preserves a superseded intermediate recommendation | Cortrix recovers the final decision, supporting evidence, rejected conclusion, and still-valid constraints across three event positions |

## Reasonable extensions

The same read-only pattern can support dependency upgrade evidence, CI failure triage, release-risk review, data contract drift, infrastructure runbook review, security advisory evidence, and cross-Agent engineering handoffs when all of the following are true:

- the source material is explicitly imported into a trusted namespace;
- each source has stable identity, content integrity, version, status, scope, and validity metadata;
- the application defines an authority resolver;
- the desired output is an explanation, recommendation, or read-only check rather than an action;
- scenario-specific validation and an independent clean-room review prove the claim.

These extensions are design candidates, not capabilities already validated by the four demos.
