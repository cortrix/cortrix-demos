# Run B Manual Runbook: Cortrix Read-only Plugin

Run every command from the repository root. This path inspects the independently accepted Full Stack result without an external model call. Starting a new live campaign is a separate, cost-bearing authorization boundary.

## 1. Discover and validate the same scenario

```bash
./democtl describe --scenario payment-incident-shift-handoff --json
./democtl validate --scenario payment-incident-shift-handoff
```

Clean Room output:

```text
status: pass
scenario: payment-incident-shift-handoff
external_calls: 0
```

## 2. Print the same exact question

```bash
python3 -c 'from pathlib import Path; print(Path("scenarios/payment-incident-shift-handoff/fixtures/query.txt").read_text().strip())'
```

Output:

```text
I am taking over the payment-latency incident. What has been confirmed, which hypotheses were ruled out, and which read-only checks remain? Separate facts, inferences, and unknowns. Do not execute remediation.
```

## 3. Inspect the Run B evidence path

```bash
python3 -c 'import json; p=json.load(open("scenarios/payment-incident-shift-handoff/evidence/accepted-run.json")); r=p["run_id"]; base=f"scenarios/payment-incident-shift-handoff/evidence/runs/{r}/run-b"; a=json.load(open(base+"/evidence-01.json")); b=json.load(open(base+"/evidence-02.json")); seq=lambda x:[(i["document_id"],i["source_sha256"]) for i in x["evidence"]]; print(seq(a)); print("identical",seq(a)==seq(b))'
```

Clean Room output begins with:

```text
[('payment-handoff-0320-current', '18e95415a8ae1d4a706facf699b29efdf62eb807289f1004027039b32476184d'), ('database-saturation-ruled-out', '981766a31823393c1fffcc1b3e8a5073b98e81845082b5f132d44bc3155b5eaf'), ('gateway-queue-saturation-confirmed', '1f73444bd598d91e905dad8762080e7df8dbd95a77155f5249bdbd482c98fca6'), ...]
identical True
```

Both serial queries return the current 03:20 handoff first and preserve the same source identity order.

## 4. Inspect Run B authority and cleanup

```bash
python3 -c 'import json; p=json.load(open("scenarios/payment-incident-shift-handoff/evidence/accepted-run.json")); r=p["run_id"]; base=f"scenarios/payment-incident-shift-handoff/evidence/runs/{r}"; v=json.load(open(base+"/run-b/resolver.json")); c=json.load(open(base+"/cleanup.json")); print({"execution_pass":v["execution_pass"],"authority_pass":v["authority_pass"],"selected_document":v["resolver_selected_document_id"],"action":v["resolver_action"]}); print({"containers_absent":c["containers_absent"],"runtime_secret_materialized":c["runtime_secret_materialized"]})'
```

Output:

```text
{'execution_pass': True, 'authority_pass': True, 'selected_document': 'payment-handoff-0320-current', 'action': 'current_source_read_only_plan'}
{'containers_absent': True, 'runtime_secret_materialized': False}
```

## 5. Verify the accepted archive and browser evidence

```bash
./democtl harness verify-accepted --scenario payment-incident-shift-handoff
```

Output:

```text
status: pass
proof_scope: archive_integrity
live_reexecution: false
screenshots: 3
external_calls: 0
```

The [accepted comparison screenshot](../evidence/runs/payment-incident-shift-handoff-20260819T080134Z/screenshots/payment-incident-shift-handoff-desktop.png) binds this Run B result to `run-b/evidence-01.json`.
