# Known Limitations

- This scenario demonstrates responsibility boundaries, not performance or retrieval-quality superiority.
- The corpus and query are synthetic and constructed to isolate an API version-conflict failure mode. They are not a held-out evaluation set.
- PostgreSQL and pgvector support metadata filtering. Run A intentionally measures dense-only exact cosine without a lifecycle filter.
- The application resolver independently validates lifecycle metadata and preserves the current Full Stack result in the reviewed contract.
- The BGE cross-encoder leader is recorded but is not a frozen business outcome or a currentness judgment.
- The pinned Cortrix source may expose known observability gaps. A run must disclose them rather than silently treating them as successful product claims.
- Cost reporting may be partial when internal provider usage is not observable. Partial visibility must not become a public cost claim.
- `democtl verify-accepted` checks the integrity and internal consistency of the tracked accepted evidence. It does not rerun PostgreSQL, Cortrix, or the external provider and reports `live_reexecution=false`.
- A pricing snapshot is a dated manual attestation against the official provider page. It is not an automated proof that pricing is still current.
- Repository-authored source, documentation, schemas, and visual assets are licensed under Apache-2.0. Runtime dependencies and referenced third-party services retain their own licenses and terms.
- The DeepSeek Harness integration is Preview and fixed to one reviewed source and package family.
- The four Harness scenarios validate two explicit read-only tools. They do not validate automatic memory capture, writes, remediation, arbitrary source browsing, or Code Mode nested tool persistence.
- Existing Harness accepted evidence binds the original local integration commit. A future public integration commit requires new live evidence for complete source attribution.
- The exact public export or distribution path for the required Cortrix-compatible BGE model files is not yet documented. Accepted replay works, but a new public live run remains blocked on model provenance.
- Historical accepted evidence may retain reviewer-specific or campaign-specific identifiers that were already public. New runs use generic public-neutral identities; the project does not rewrite historical observations.
