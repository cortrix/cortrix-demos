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

function requireAccepted(pointer, manifest, runA, resolver, scenario) {
  if (pointer.status !== "accepted" || manifest.state !== "accepted") {
    throw new Error("The accepted-run pointer and run manifest must both report accepted.");
  }
  if (pointer.run_id !== manifest.run_id || resolver.run_id !== manifest.run_id) {
    throw new Error("Evidence identity mismatch between pointer, manifest, and resolver.");
  }
  if (manifest.scenario_version !== scenario.scenario_version) {
    throw new Error("The accepted run does not match the current scenario contract version.");
  }
  if (resolver.pass !== true || manifest.assertions?.all_passed !== true) {
    throw new Error("The accepted run does not contain passing resolver and run assertions.");
  }
  const requiredAssertions = [
    "selected_expected_document",
    "selected_content_contains_expected_field",
    "required_documents_retrieved",
    "bge_scores_present",
    "final_top1_matches_contract",
    "policy_action_matches_contract",
  ];
  if (resolver.schema_version !== 2 || !requiredAssertions.every((name) => resolver.assertions?.[name] === true)) {
    throw new Error("The accepted resolver does not satisfy the layered-ranking contract.");
  }
  if (runA.pass !== true || runA.top1 !== "order-api-guide-v1.0") {
    throw new Error("The accepted Run A result does not expose the frozen outdated top result.");
  }
  if (manifest.acceptance?.method !== "secondscott_clean_room" || manifest.acceptance?.verdict !== "pass" || manifest.post_screenshot_human_review_required !== true) {
    throw new Error("The accepted run does not preserve the Clean Room and final Human Review gates.");
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
    if (pointer.status !== "accepted") {
      rejectViewer(pointer.reason ?? "No accepted run is available for the current scenario contract.");
      return;
    }
    const manifest = await loadJson(pointer.manifest);
    const runA = await loadJson(pointer.run_a);
    const resolver = await loadJson(pointer.resolver);
    requireAccepted(pointer, manifest, runA, resolver, scenario);

    const runATop = runA.ranking?.[0];
    if (!runATop) {
      throw new Error("The accepted Run A result does not expose a top-ranked document.");
    }
    byId("run-a-title").textContent = runATop.document_id;
    addDefinition(byId("run-a-details"), "Version", runATop.version);
    addDefinition(byId("run-a-details"), "Lifecycle", runATop.lifecycle_status);
    addDefinition(byId("run-a-details"), "Selected field", "account_id");
    addDefinition(byId("run-a-details"), "Cosine similarity", runATop.cosine_similarity);

    const bgeLeader = resolver.layers?.bge_cross_encoder?.leader;
    const finalTop = resolver.layers?.deepseek_listwise_final?.top_result;
    const decision = resolver.decision;
    if (!bgeLeader || !finalTop) {
      throw new Error("The accepted resolver does not expose both ranking layers.");
    }
    byId("bge-title").textContent = bgeLeader.document_id;
    addDefinition(byId("bge-details"), "Version", bgeLeader.version);
    addDefinition(byId("bge-details"), "Lifecycle", bgeLeader.lifecycle_status);
    addDefinition(byId("bge-details"), "BGE rerank rank", bgeLeader.bge_rerank_rank);
    addDefinition(byId("bge-details"), "BGE rerank score", bgeLeader.bge_rerank_score);

    byId("final-title").textContent = finalTop.document_id;
    addDefinition(byId("final-details"), "Version", finalTop.version);
    addDefinition(byId("final-details"), "Lifecycle", finalTop.lifecycle_status);
    addDefinition(byId("final-details"), "Final response rank", finalTop.final_response_rank);
    addDefinition(byId("final-details"), "Selected field", decision.selected_field);
    addDefinition(byId("final-details"), "BGE rerank score", finalTop.bge_rerank_score);

    byId("decision-title").textContent = decision.selected_document_id;
    byId("decision-reason").textContent = decision.reason;
    addDefinition(byId("decision-details"), "Version", decision.selected_version);
    addDefinition(byId("decision-details"), "Selected field", decision.selected_field);
    addDefinition(byId("decision-details"), "Policy action", resolver.layers.application_lifecycle_policy.action);

    addDefinition(byId("run-details"), "Run ID", manifest.run_id);
    addDefinition(byId("run-details"), "Scenario contract", manifest.scenario_version);
    addDefinition(byId("run-details"), "Cortrix release", manifest.target_identity?.release);
    addDefinition(byId("run-details"), "Source revision", manifest.target_identity?.source_revision);
    addDefinition(byId("run-details"), "Demo commit", manifest.target_identity?.demo_commit);
    addDefinition(byId("run-details"), "Provider model", manifest.provider_identity?.model);
    addDefinition(byId("run-details"), "Usage visibility", manifest.cost?.usage_visibility);
    addDefinition(byId("run-details"), "Observable estimated cost (USD)", manifest.cost?.estimated_observable_cost_usd);

    byId("claim-boundary").textContent = resolver.claim_boundary;
    byId("synthetic-disclosure").textContent = scenario.synthetic_disclosure;
    byId("evidence-grid").hidden = false;
    byId("boundary").hidden = false;
    byId("status-panel").classList.add("accepted");
    byId("status-text").textContent = "Clean Room passed · final Human Review pending";
  } catch (error) {
    rejectViewer(error instanceof Error ? error.message : "The accepted evidence contract failed.");
  }
}

render();
