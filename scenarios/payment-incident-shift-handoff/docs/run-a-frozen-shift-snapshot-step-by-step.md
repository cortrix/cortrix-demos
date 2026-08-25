# Run A Manual Runbook: Frozen Shift Snapshot

Run every command from the repository root. This path reconstructs deterministic baseline evidence and replays accepted artifacts without an external model call. Its only write is under the ignored `.runs/` directory.

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

## 3. Inspect the Run A evidence path

```bash
mkdir -p .runs/manual-payment-run-a
./democtl harness baseline --scenario payment-incident-shift-handoff --output .runs/manual-payment-run-a/evidence.json
./democtl harness prompt --scenario payment-incident-shift-handoff --evidence .runs/manual-payment-run-a/evidence.json --output .runs/manual-payment-run-a/answer-prompt.txt
python3 -c 'import json; data=json.load(open(".runs/manual-payment-run-a/evidence.json")); print([(x["document_id"], x["status"]) for x in data["evidence"]])'
```

Clean Room output:

```text
baseline: pass, external_calls=0
prompt: pass, external_calls=0
[('payment-handoff-0100-superseded', 'superseded'), ('payment-capacity-plan', 'current'), ('database-maintenance-notice', 'current'), ('checkout-ui-timeout', 'historical')]
```

The top baseline item is the superseded 01:00 handoff. The current 03:20 handoff is absent from the four-document frozen workspace projection.

## 4. Inspect Run A authority and cleanup

```bash
python3 -c 'import json; p=json.load(open("scenarios/payment-incident-shift-handoff/evidence/accepted-run.json")); r=p["run_id"]; base=f"scenarios/payment-incident-shift-handoff/evidence/runs/{r}"; v=json.load(open(base+"/run-a/resolver.json")); c=json.load(open(base+"/cleanup.json")); print({"execution_pass":v["execution_pass"],"authority_pass":v["authority_pass"],"expected_outcome_observed":v["expected_outcome_observed"],"top_evidence":v["selected_document_ids"][0]}); print({"containers_absent":c["containers_absent"],"runtime_secret_materialized":c["runtime_secret_materialized"]})'
```

Output:

```text
{'execution_pass': True, 'authority_pass': False, 'expected_outcome_observed': True, 'top_evidence': 'payment-handoff-0100-superseded'}
{'containers_absent': True, 'runtime_secret_materialized': False}
```

Run A passes as a negative control, but it does not pass current-source authority.

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

The [accepted comparison screenshot](../evidence/runs/payment-incident-shift-handoff-20260819T080134Z/screenshots/payment-incident-shift-handoff-desktop.png) shows Run A and Run B on the same evidence page.
