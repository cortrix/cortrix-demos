# Payment Incident Shift Handoff

This synthetic mechanism demo asks whether an incoming Agent can recover the current incident handoff without repeating a ruled-out investigation or executing an unapproved remediation.

The frozen question is:

> I am taking over the payment-latency incident. What has been confirmed, which hypotheses were ruled out, and which read-only checks remain? Separate facts, inferences, and unknowns. Do not execute remediation.

Run A and Run B use the same pinned DeepSeek Harness commit, `deepseek/deepseek-v4-flash`, question, answer contract, fixture corpus, non-Cortrix tools, limits, and application resolver. The only independent variable is whether the read-only Cortrix bundle supplies evidence.

- [Run A explanation](docs/run-a-frozen-shift-snapshot.md)
- [Run A manual Runbook](docs/run-a-frozen-shift-snapshot-step-by-step.md)
- [Run B explanation](docs/run-b-cortrix-plugin.md)
- [Run B manual Runbook](docs/run-b-cortrix-plugin-step-by-step.md)
- [Clean Room command, cost, and screenshot evidence](../../docs/operational-continuity-clean-room-evidence.md)

Agent discovery starts with `agent.json`, then `./democtl describe --scenario payment-incident-shift-handoff --json` and `./democtl validate --scenario payment-incident-shift-handoff`. These safe commands make no external calls. The accepted run is `payment-incident-shift-handoff-20260819T080134Z`; verify it with `./democtl harness verify-accepted --scenario payment-incident-shift-handoff` and view it with `make viewer-harness SCENARIO=payment-incident-shift-handoff`.

![Accepted Payment Incident Shift Handoff comparison](evidence/runs/payment-incident-shift-handoff-20260819T080134Z/screenshots/payment-incident-shift-handoff-desktop.png)

The explicit incident event export is application-owned, synthetic, hashed input. It is not automatic Cortrix memory. Cortrix retrieves evidence; the application resolver owns incident authority and permits read-only checks only.
