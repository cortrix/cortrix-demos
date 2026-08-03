const byId = (id) => document.getElementById(id);

function addDefinition(list, term, value) {
  const dt = document.createElement("dt");
  const dd = document.createElement("dd");
  dt.textContent = term;
  dd.textContent = String(value ?? "not reported");
  list.append(dt, dd);
}

async function loadJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Unable to load ${path} (${response.status})`);
  }
  return response.json();
}

function rejectViewer(message) {
  byId("status-panel").classList.add("rejected");
  byId("status-text").textContent = "No accepted evidence";
  byId("failure-message").textContent = message;
  byId("failure").hidden = false;
}

function requireAccepted(pointer, manifest, resolver) {
  if (pointer.status !== "accepted" || manifest.state !== "accepted") {
    throw new Error("The accepted-run pointer and run manifest must both report accepted.");
  }
  if (pointer.run_id !== manifest.run_id || resolver.run_id !== manifest.run_id) {
    throw new Error("Evidence identity mismatch between pointer, manifest, and resolver.");
  }
  if (resolver.pass !== true || manifest.assertions?.all_passed !== true) {
    throw new Error("The accepted run does not contain passing resolver and run assertions.");
  }
}

async function render() {
  try {
    const config = await loadJson("./viewer-config.json");
    const scenario = await loadJson(config.scenario_metadata);
    byId("scenario-id").textContent = scenario.display_name;
    byId("scenario-title").textContent = scenario.title;
    byId("scenario-summary").textContent = scenario.summary;

    const pointer = await loadJson(config.accepted_pointer);
    const manifest = await loadJson(pointer.manifest);
    const resolver = await loadJson(pointer.resolver);
    requireAccepted(pointer, manifest, resolver);

    const first = resolver.candidates[0];
    const decision = resolver.decision;
    byId("retrieval-title").textContent = first.document_id;
    addDefinition(byId("retrieval-details"), "Version", first.version);
    addDefinition(byId("retrieval-details"), "Lifecycle", first.lifecycle_status);
    addDefinition(byId("retrieval-details"), "Retrieval rank", first.retrieval_rank);
    addDefinition(byId("retrieval-details"), "Rerank score", first.rerank_score);

    byId("decision-title").textContent = decision.selected_document_id;
    byId("decision-reason").textContent = decision.reason;
    addDefinition(byId("decision-details"), "Version", decision.selected_version);
    addDefinition(byId("decision-details"), "Selected field", decision.selected_field);

    addDefinition(byId("run-details"), "Run ID", manifest.run_id);
    addDefinition(byId("run-details"), "Cortrix release", manifest.target_identity?.release);
    addDefinition(byId("run-details"), "Source revision", manifest.target_identity?.source_revision);
    addDefinition(byId("run-details"), "Demo commit", manifest.target_identity?.demo_commit);
    addDefinition(byId("run-details"), "Provider model", manifest.provider_identity?.model);
    addDefinition(byId("run-details"), "Usage visibility", manifest.cost?.usage_visibility);
    addDefinition(byId("run-details"), "Observable estimated cost (USD)", manifest.cost?.estimated_observable_cost_usd);

    byId("claim-boundary").textContent = resolver.claim_boundary;
    byId("evidence-grid").hidden = false;
    byId("boundary").hidden = false;
    byId("status-panel").classList.add("accepted");
    byId("status-text").textContent = "Accepted local evidence";
  } catch (error) {
    rejectViewer(error instanceof Error ? error.message : "The accepted evidence contract failed.");
  }
}

render();
