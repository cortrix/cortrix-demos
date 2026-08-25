# Acceptance and screenshot runbook

The Full Stack runner can produce only a candidate or a rejected run. This procedure begins only after an independent clean room returns `PASS` for the exact candidate run ID and its `demo_commit`. Final human review occurs after the screenshot-backed local package is complete.

## 1. Stage curated accepted evidence

Keep `main` on a clean commit that descends from the candidate's recorded commit without changing the frozen scenario inputs. Pass the private Clean Room review identifier to the command; the identifier is used as an execution gate and is not copied into the future-public evidence.

```bash
./democtl stage-accepted \
  --run-id <accepted-run-id> \
  --clean-room-review-id <private-review-id>
```

The command copies only the curated manifest, target identity, sanitized runtime identity, provider contract-smoke identity and usage, pricing snapshot, fixture manifest, frozen assertion contract, model checksums, Run A result, Run B summary and resolvers, run assertions, cleanup receipt, and state history. It writes the accepted pointer last. Raw requests, raw responses, metrics, runtime logs, private paths, provider response content, and the private review identifier stay out of tracked evidence.

## 2. Capture the accepted viewer

Run `make viewer`, open `/packages/viewer/index.html`, and capture the rendered accepted evidence with a real browser. Do not generate or edit the image. Record each browser-captured PNG:

```bash
./democtl record-screenshot \
  --run-id <accepted-run-id> \
  --file <browser-captured.png> \
  --route /packages/viewer/index.html \
  --evidence-path run-b/resolver-01.json
```

The recorder rejects non-PNG files, images below 800x450, non-viewer routes, and evidence paths outside the accepted run. It records the SHA-256 digest, dimensions, capture time, route, run ID, evidence path, and accepted code commit.

## 3. Verify and commit

```bash
./democtl verify-accepted --run-id <accepted-run-id>
```

The verifier requires at least one screenshot, an exact curated file allowlist, complete checksums, matching pointer/manifest/resolver/screenshot identity, passing assertions, a reachable demo commit, and public-safe English text. Commit the accepted evidence only after this command passes.

If a later viewer-only correction changes the meaning or trust-boundary labels shown in an existing screenshot, recapture the same accepted route and use `./democtl harness record-screenshot --replace` for each existing filename. Replacement is allowed only when exactly one matching screenshot binding already exists. It does not change the accepted answer or source identity, and it requires a new independent Clean Room review of the resulting commit.

## 4. Verify a fresh clone

After committing the accepted package, run:

```bash
./democtl fresh-clone-verify --run-id <accepted-run-id>
```

The verifier creates an isolated temporary local clone, finds `See the result`, `Run it locally`, and `Inspect the evidence` in order, runs `make validate`, confirms Apache License 2.0 plus `NOTICE`, confirms the absence of GitHub Actions workflows, and revalidates the accepted run and screenshots. The temporary clone is removed when verification ends.
