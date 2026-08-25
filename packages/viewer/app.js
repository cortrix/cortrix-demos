const byId = (id) => document.getElementById(id);
const CANDIDATE_QA_ROUTE = "/packages/viewer/candidate-qa.html";
const CANDIDATE_QA_CONFIG = "/__cortrix_candidate_qa_config__.json";

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
  byId("status-text").textContent = "No valid evidence";
  byId("failure-message").textContent = message;
  byId("failure").hidden = false;
}

function requireSharedEvidence(manifest, runA, resolver, scenario, technology) {
  if (resolver.run_id !== manifest.run_id) {
    throw new Error("Evidence identity mismatch between manifest and resolver.");
  }
  if (manifest.scenario_version !== scenario.scenario_version || technology.scenario_id !== scenario.scenario_id) {
    throw new Error("The run and technology profile do not match the scenario contract.");
  }
  if (resolver.pass !== true || manifest.assertions?.all_passed !== true) {
    throw new Error("The run does not contain passing resolver and run assertions.");
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
    throw new Error("The resolver does not satisfy the layered-ranking contract.");
  }
  if (runA.pass !== true || runA.top1 !== "order-api-guide-v1.0") {
    throw new Error("Run A does not expose the frozen outdated top result.");
  }
  if (technology.baseline?.adapter_id !== "postgresql-pgvector" || technology.llm?.adapter_id !== "deepseek-openai-compatible") {
    throw new Error("The viewer technology profile is not the profile used by the evidence.");
  }
}

function requireAccepted(pointer, manifest, runA, resolver, scenario, technology) {
  if (pointer.status !== "accepted" || manifest.state !== "accepted") {
    throw new Error("The accepted-run pointer and run manifest must both report accepted.");
  }
  if (pointer.run_id !== manifest.run_id || resolver.run_id !== manifest.run_id) {
    throw new Error("Evidence identity mismatch between pointer, manifest, and resolver.");
  }
  requireSharedEvidence(manifest, runA, resolver, scenario, technology);
  const acceptedMethod = manifest.acceptance?.method === "independent_clean_room" || pointer.acceptance_contract === "legacy_published_v1";
  if (!acceptedMethod || manifest.acceptance?.verdict !== "pass" || manifest.post_screenshot_human_review_required !== true) {
    throw new Error("The accepted run does not preserve the Clean Room and publication-review gates.");
  }
}

function requireCandidate(candidate, manifest, runA, resolver, scenario, technology) {
  if (candidate.run_id !== manifest.run_id || resolver.run_id !== manifest.run_id) {
    throw new Error("Candidate evidence identity mismatch.");
  }
  if (manifest.state !== "candidate" || manifest.screenshot_eligible !== false || manifest.human_review_required !== true) {
    throw new Error("Candidate QA requires a non-screenshot-eligible candidate that still requires human review.");
  }
  if (manifest.acceptance !== undefined || manifest.post_screenshot_human_review_required !== undefined) {
    throw new Error("Candidate QA refuses evidence that contains acceptance or post-screenshot review metadata.");
  }
  requireSharedEvidence(manifest, runA, resolver, scenario, technology);
}

function renderAgentPath() {
  const steps = ["Discover", "Describe", "Validate", "Preflight", "Provision", "Run", "Inspect", "Verify", "Cleanup"];
  for (const step of steps) {
    const item = document.createElement("li");
    const marker = document.createElement("span");
    marker.setAttribute("aria-hidden", "true");
    marker.textContent = String(steps.indexOf(step) + 1).padStart(2, "0");
    item.append(marker, document.createTextNode(step));
    byId("agent-steps").append(item);
  }
}

function initializeTheme() {
  const saved = localStorage.getItem("cortrix-demo-theme");
  const dark = saved ? saved === "dark" : window.matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  byId("theme-toggle").setAttribute("aria-pressed", String(dark));
  byId("theme-toggle").addEventListener("click", () => {
    const nextDark = document.documentElement.dataset.theme !== "dark";
    document.documentElement.dataset.theme = nextDark ? "dark" : "light";
    localStorage.setItem("cortrix-demo-theme", nextDark ? "dark" : "light");
    byId("theme-toggle").setAttribute("aria-pressed", String(nextDark));
  });
}

async function render() {
  try {
    const candidateMode = window.location.pathname === CANDIDATE_QA_ROUTE;
    const config = await loadJson(candidateMode ? CANDIDATE_QA_CONFIG : "./viewer-config.json");
    if ((candidateMode && config.mode !== "candidate_qa") || (!candidateMode && config.mode === "candidate_qa")) {
      throw new Error("The requested viewer route does not match its evidence mode.");
    }
    const [scenario, technology] = await Promise.all([
      loadJson(config.scenario_metadata),
      loadJson(config.technology_profile),
    ]);
    byId("scenario-id").textContent = scenario.display_name;
    byId("scenario-title").textContent = scenario.title;
    byId("scenario-summary").textContent = scenario.summary;

    let manifest;
    let runA;
    let resolver;
    if (candidateMode) {
      const candidate = config.candidate;
      if (!candidate) {
        throw new Error("Candidate QA configuration is missing its evidence pointer.");
      }
      [manifest, runA, resolver] = await Promise.all([
        loadJson(candidate.manifest),
        loadJson(candidate.run_a),
        loadJson(candidate.resolver),
      ]);
      requireCandidate(candidate, manifest, runA, resolver, scenario, technology);
      byId("viewer-eyebrow").textContent = "Candidate QA viewer";
      byId("agent-support").textContent = "This local QA projection renders candidate evidence without accepting or promoting it.";
      byId("evidence-policy-label").textContent = "Candidate QA · not accepted evidence";
    } else {
      const pointer = await loadJson(config.accepted_pointer);
      if (pointer.status !== "accepted") {
        rejectViewer(pointer.reason ?? "No accepted run is available for the current scenario contract.");
        return;
      }
      [manifest, runA, resolver] = await Promise.all([
        loadJson(pointer.manifest),
        loadJson(pointer.run_a),
        loadJson(pointer.resolver),
      ]);
      requireAccepted(pointer, manifest, runA, resolver, scenario, technology);
    }

    const runATop = runA.ranking?.[0];
    if (!runATop) {
      throw new Error("The evidence does not expose a top-ranked Run A document.");
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
      throw new Error("The resolver does not expose both ranking layers.");
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

    addDefinition(byId("technology-details"), "Profile", technology.id);
    addDefinition(byId("technology-details"), "Run A baseline", technology.baseline.adapter_id);
    addDefinition(byId("technology-details"), "Baseline version", technology.baseline.version);
    addDefinition(byId("technology-details"), "Run B Cortrix", `${technology.cortrix.release} @ ${technology.cortrix.source_revision.slice(0, 12)}`);
    addDefinition(byId("technology-details"), "Embedding", technology.cortrix.embedding_model);
    addDefinition(byId("technology-details"), "Reranker", technology.cortrix.reranker_model);
    addDefinition(byId("technology-details"), "LLM", `${technology.llm.provider}/${technology.llm.model}`);
    addDefinition(byId("technology-details"), "LLM roles", technology.llm.roles.join(", "));

    addDefinition(byId("run-details"), "Run ID", manifest.run_id);
    addDefinition(byId("run-details"), "Scenario contract", manifest.scenario_version);
    addDefinition(byId("run-details"), "Cortrix release", manifest.target_identity?.release);
    addDefinition(byId("run-details"), "Source revision", manifest.target_identity?.source_revision);
    addDefinition(byId("run-details"), "Demo commit", manifest.target_identity?.demo_commit);
    addDefinition(byId("run-details"), "Provider model", manifest.provider_identity?.model);
    addDefinition(byId("run-details"), "Usage visibility", manifest.cost?.usage_visibility);
    addDefinition(byId("run-details"), "Observable estimated cost (USD)", manifest.cost?.estimated_observable_cost_usd);

    renderAgentPath();
    byId("claim-boundary").textContent = resolver.claim_boundary;
    byId("synthetic-disclosure").textContent = scenario.synthetic_disclosure;
    byId("evidence-grid").hidden = false;
    byId("boundary").hidden = false;
    byId("status-panel").classList.add(candidateMode ? "candidate" : "accepted");
    byId("status-text").textContent = candidateMode
      ? "Candidate QA · Clean Room review · not accepted evidence"
      : "Clean Run accepted · local evidence";
  } catch (error) {
    rejectViewer(error instanceof Error ? error.message : "The evidence contract failed.");
  }
}

initializeTheme();
render();
