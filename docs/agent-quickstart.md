# Agent quick start

This repository is designed so an Agent can discover and inspect a demo without private workspace knowledge.

## Discover

```bash
./democtl list --json
```

The response lists scenario IDs, status, technology-profile path, accepted-evidence pointer, and human guide.

## Describe

```bash
./democtl describe --scenario order-api-field-migration --json
```

The response resolves the business contract, baseline adapter, Cortrix identity, LLM provider/model/roles, required secret name, support status, accepted evidence, and lifecycle endpoints.

## Validate without external calls

```bash
./democtl validate --scenario order-api-field-migration
./democtl public-safety
```

Both commands emit JSON. A failure emits a structured error containing `code`, `category`, `retryable`, `message`, and `structured_data`.

## Agent lifecycle

```text
discover -> describe -> validate -> preflight -> provision -> run -> inspect -> verify -> cleanup
```

The accepted replay requires no external model call. A live Full Stack run is manual, reads its secret only from the named environment variable, and produces a candidate rather than accepted evidence.

## Review boundary

An Agent can discover, validate, run, inspect, verify, and clean up. Independent Clean Run acceptance remains a separate review gate; remote publication remains human-governed. The Web viewer renders the same accepted evidence contract for human readers.
