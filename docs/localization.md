# Localization

The canonical repository ships only `en-US`.

A presentation-only locale may change labels, explanations, tutorial links, and annotations. It must not change fixtures, queries, prompts, embedding inputs, raw requests or responses, traces, scores, source IDs, result identities, or checksums.

The viewer hides its locale switcher when only one locale is installed. Missing keys fall back to `en-US` in the viewer and fail validation during development.

Any localized semantic input is a new scenario profile and requires its own Full Stack run, manifest, screenshots, and human acceptance.
