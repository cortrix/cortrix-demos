# Run B Manual Runbook: Cortrix Read-only Plugin

Run every command from the repository root. This path inspects the independently accepted Full Stack result without an external model call. Starting a new live campaign is a separate, cost-bearing authorization boundary.

## 1. Discover and validate the same scenario

```bash
./democtl describe --scenario migration-decision-recovery --json
./democtl validate --scenario migration-decision-recovery
```

Clean Room output:

```text
status: pass
scenario: migration-decision-recovery
external_calls: 0
```

## 2. Print the same exact question

```bash
python3 -c 'from pathlib import Path; print(Path("scenarios/migration-decision-recovery/fixtures/query.txt").read_text().strip())'
```

Output:

```text
Why was option B rejected during this migration? Return the decision, the supporting evidence, the superseded intermediate conclusion, and the constraints that still apply. Cite every material claim.
```

## 3. Inspect the Run B evidence path

```bash
python3 -c 'import json; p=json.load(open("scenarios/migration-decision-recovery/evidence/accepted-run.json")); r=p["run_id"]; base=f"scenarios/migration-decision-recovery/evidence/runs/{r}/run-b"; a=json.load(open(base+"/evidence-01.json")); b=json.load(open(base+"/evidence-02.json")); seq=lambda x:[(i["document_id"],i["source_sha256"]) for i in x["evidence"]]; print(seq(a)); print("identical",seq(a)==seq(b))'
```

Clean Room output begins with:

```text
[('final-decision-option-c-current', '3da938e2b7445aee67adf538fc9933b0b83f878b6e2d94f49ff018bc72872d06'), ('migration-constraints-current', '4cace00b9e23b8e42d444727425133eb542047e30c4c07209c11a7bf2c80ad0b'), ('option-b-recommendation-superseded', 'bdfe61ddabefca32e69038e40dd0788bdc534efb170973e8921f6b2eb3d5d294'), ...]
identical True
```

Both serial queries return the current option C decision first and preserve the same source identity order.

## 4. Inspect all three event positions

```bash
python3 -c 'import json; p=json.load(open("scenarios/migration-decision-recovery/evidence/accepted-run.json")); r=p["run_id"]; path=f"scenarios/migration-decision-recovery/evidence/runs/{r}/position-variants/summary.json"; d=json.load(open(path)); print([(x["variant"],x["run_a_pass"],x["run_b_pass"],x["authority_pass"],x["resolver_pass"],x["cleanup_pass"]) for x in d["variants"]]); print("all_variants_pass",d["all_variants_pass"])'
python3 -c 'import json; p=json.load(open("scenarios/migration-decision-recovery/evidence/accepted-run.json")); r=p["run_id"]; base=f"scenarios/migration-decision-recovery/evidence/runs/{r}/position-variants"; seq=lambda x:[(i["document_id"],i["source_sha256"]) for i in x["evidence"]]; print([(v,seq(json.load(open(f"{base}/{v}/run-b/evidence-01.json")))==seq(json.load(open(f"{base}/{v}/run-b/evidence-02.json")))) for v in ("front","middle","end")])'
```

Output:

```text
[('front', True, True, True, True, True), ('middle', True, True, True, True, True), ('end', True, True, True, True, True)]
all_variants_pass True
[('front', True), ('middle', True), ('end', True)]
```

## 5. Inspect Run B authority and cleanup

```bash
python3 -c 'import json; p=json.load(open("scenarios/migration-decision-recovery/evidence/accepted-run.json")); r=p["run_id"]; base=f"scenarios/migration-decision-recovery/evidence/runs/{r}"; v=json.load(open(base+"/run-b/resolver.json")); c=json.load(open(base+"/cleanup.json")); print({"execution_pass":v["execution_pass"],"authority_pass":v["authority_pass"],"selected_document":v["resolver_selected_document_id"],"action":v["resolver_action"]}); print({"all_variant_namespaces_removed":c["all_variant_namespaces_removed"],"containers_absent":c["containers_absent"],"runtime_secret_materialized":c["runtime_secret_materialized"]})'
```

Output:

```text
{'execution_pass': True, 'authority_pass': True, 'selected_document': 'final-decision-option-c-current', 'action': 'decision_recovery_only'}
{'all_variant_namespaces_removed': True, 'containers_absent': True, 'runtime_secret_materialized': False}
```

## 6. Verify the accepted archive and browser evidence

```bash
./democtl harness verify-accepted --scenario migration-decision-recovery
```

Output:

```text
status: pass
proof_scope: archive_integrity
live_reexecution: false
screenshots: 3
external_calls: 0
```

The [accepted comparison screenshot](../evidence/runs/migration-decision-recovery-20260819T080134Z/screenshots/migration-decision-recovery-desktop.png) binds this Run B result to `run-b/evidence-01.json`.
