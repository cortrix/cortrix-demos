# Run A Manual Runbook: Obsolete Intermediate Conclusion

Run every command from the repository root. This path reconstructs deterministic baseline evidence and replays accepted artifacts without an external model call. Its only writes are under the ignored `.runs/` directory.

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

## 3. Reconstruct the Run A evidence path

```bash
for position in front middle end; do
  mkdir -p ".runs/manual-migration-$position"
  ./democtl harness baseline --scenario migration-decision-recovery --position-variant "$position" --output ".runs/manual-migration-$position/evidence.json"
done
```

Each command returned:

```text
status: pass
scenario: migration-decision-recovery
external_calls: 0
```

## 4. Inspect all three event positions

```bash
python3 -c 'import json; print([(p,json.load(open(f".runs/manual-migration-{p}/evidence.json"))["evidence"][0]["document_id"]) for p in ("front","middle","end")])'
```

Clean Room output:

```text
[('front', 'option-b-recommendation-superseded'), ('middle', 'option-b-recommendation-superseded'), ('end', 'option-b-recommendation-superseded')]
```

Moving the decisive event does not change the frozen Run A top result.

## 5. Inspect Run A authority and cleanup

```bash
python3 -c 'import json; p=json.load(open("scenarios/migration-decision-recovery/evidence/accepted-run.json")); r=p["run_id"]; base=f"scenarios/migration-decision-recovery/evidence/runs/{r}"; variants=f"{base}/position-variants"; print([(v,json.load(open(f"{variants}/{v}/run-a/resolver.json"))["authority_pass"]) for v in ("front","middle","end")]); c=json.load(open(base+"/cleanup.json")); print({"all_variant_namespaces_removed":c["all_variant_namespaces_removed"],"containers_absent":c["containers_absent"],"runtime_secret_materialized":c["runtime_secret_materialized"]})'
```

Output:

```text
[('front', False), ('middle', False), ('end', False)]
{'all_variant_namespaces_removed': True, 'containers_absent': True, 'runtime_secret_materialized': False}
```

Each Run A variant passes as a negative control, but none passes final-decision authority.

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

The [accepted comparison screenshot](../evidence/runs/migration-decision-recovery-20260819T080134Z/screenshots/migration-decision-recovery-desktop.png) shows Run A and Run B on the same evidence page.
