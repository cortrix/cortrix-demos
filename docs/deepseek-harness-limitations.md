# DeepSeek Harness Integration Limitations

- The integration is Preview and fixed to one reviewed DeepSeek Harness commit and package family.
- Only top-level Native tool calls are supported because that surface durably persists the source ledger used by `cortrix_get_source`.
- The model can use only two read-only tools. It cannot write, upload, delete, administer, execute a shell, browse arbitrary URLs, or run remediation.
- The operator fixes the endpoint, namespace, credential reference, timeout, retry policy, and result limits. The model cannot change them.
- `cortrix_get_source` is not a general object reader. It accepts only a source reference returned by a successful search in the same Native session.
- Cortrix retrieves candidate evidence; it does not determine business authority. Each application needs explicit currentness, scope, approval, and action rules.
- The scenarios use synthetic, deliberately constructed corpora. They are mechanism demonstrations, not retrieval benchmarks or general accuracy claims.
- Accepted archive verification checks tracked integrity and reports `live_reexecution=false`. It does not call the model or rerun Cortrix.
- Provider usage visibility is partial. Recorded cost is not a complete bill or a general cost claim.
- The integration has not completed production multi-tenant authorization, enterprise RBAC, regulatory certification, penetration testing, or long-term upgrade validation.
- A new integration source commit invalidates the source identity bound into existing accepted evidence. New public-source attribution may require a new live candidate and Clean Room.
