# Changelog

All notable changes to this repository will be documented here after the first accepted local release candidate.

## Unreleased

- Added the private bootstrap for the `order-api-field-migration` scenario.
- Added shared runner, evidence-schema, and read-only viewer contracts.
- Defined scenario contract `1.1.0` with separate dense, BGE cross-encoder, Full Stack final-order, and application-policy evidence.
- Bound candidate and accepted evidence to the tracked scenario version and frozen assertion-contract checksum.
- Extended the review-gated ceiling to a fifth attempt, preserved sixth-attempt denial, and kept the hard Full Stack budget at USD 5.00.
- Persisted ignored query observations before resolver validation so rejected identity failures remain diagnosable.
- Defined scenario contract `1.2.0` with chunk-only query identity and document summaries retained as ingestion-only evidence.
- Defined sealed synthetic scenario contract `2.0.0` with one shared query, an intentionally unfiltered pgvector baseline, a lifecycle-aware application resolver, and an independent four-slot Full Stack campaign.
- Added a no-external-call baseline calibration record and invalidated the current accepted-run pointer until the `2.0.0` candidate passes SecondScott Clean Room review.
- Replaced the pre-screenshot Human Review claim with explicit SecondScott Clean Room acceptance provenance while keeping final Human Review required after screenshot capture.
- Kept licensing, automation, hosting, releases, forks, and public visibility behind separate gates.
- Replaced internal feature identifiers in evidence field names, the Full Stack required-path contract, and documentation with the capability names they describe, and made public-safety validation reject them outside archived evidence. Runs archived before this change keep their recorded spelling; accepted-evidence verification maps the one retired required-path name onto its current name.
