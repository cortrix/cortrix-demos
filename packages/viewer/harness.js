const byId = (id) => document.getElementById(id);
const CONFIG = "/__cortrix_harness_viewer_config__.json";

function addDefinition(list, term, value) {
  const dt = document.createElement("dt");
  const dd = document.createElement("dd");
  dt.textContent = term;
  dd.textContent = String(value ?? "not reported");
  list.append(dt, dd);
}

async function loadJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) throw new Error(`Unable to load accepted evidence (${response.status})`);
  return response.json();
}

function requireAccepted(config, manifest, runA, resolverA, runB, resolverB, scenario, technology, review) {
  const sameRun = [runA, runB, review].every((value) => value.run_id === manifest.run_id);
  const sameScenario = [resolverA, resolverB].every((value) => value.scenario_id === manifest.scenario_id);
  if (config.mode !== "accepted_harness" || config.run_id !== manifest.run_id || !sameRun || !sameScenario) throw new Error("Accepted evidence identity is inconsistent.");
  if (manifest.state !== "accepted" || manifest.screenshot_eligible !== true || manifest.human_review_required !== false) throw new Error("The Harness run has not passed the accepted evidence gate.");
  if (manifest.acceptance?.method !== "independent_clean_room" || manifest.acceptance?.verdict !== "pass" || review.verdict !== "pass") throw new Error("The Harness run has no passing independent Clean Room review.");
  if (scenario.scenario_id !== manifest.scenario_id || technology.scenario_id !== manifest.scenario_id) throw new Error("Scenario and technology profile identity is inconsistent.");
  if (runA.pass !== true || runA.authority_pass !== false || resolverA.expected_outcome_observed !== true) throw new Error("Run A does not preserve the expected negative control.");
  if (runB.pass !== true || runB.authority_pass !== true || runB.serial_query_count !== 2 || runB.serial_source_order_identical !== true || resolverB.pass !== true || resolverB.authority_pass !== true) throw new Error("Run B does not preserve the accepted two-query resolver contract.");
  if (manifest.provider?.provider !== "deepseek" || manifest.provider?.model !== "deepseek-v4-flash" || manifest.provider?.local_generative_llm !== false || manifest.provider?.fallback_used !== false) throw new Error("Provider identity or fallback boundary is invalid.");
  if (technology.plugin?.tools?.join(",") !== "cortrix_search_evidence,cortrix_get_source" || technology.plugin?.write_tools !== 0) throw new Error("Plugin tool surface is invalid.");
}

function renderSteps() {
  const steps = ["Discover scenario", "Validate frozen contract", "Search evidence", "Expand same-session sources", "Answer in Harness", "Apply authority policy", "Verify and clean"];
  for (const [index, step] of steps.entries()) {
    const item = document.createElement("li");
    const marker = document.createElement("span");
    marker.setAttribute("aria-hidden", "true");
    marker.textContent = String(index + 1).padStart(2, "0");
    item.append(marker, document.createTextNode(step));
    byId("agent-steps").append(item);
  }
}

function summarizeDecision(decision) {
  return Object.entries(decision ?? {}).map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(", ") : value}`).join(" · ");
}

async function render() {
  try {
    const config = await loadJson(CONFIG);
    const requested = new URLSearchParams(window.location.search).get("scenario");
    if (requested !== config.scenario_id) throw new Error("Requested scenario does not match the server-validated accepted run.");
    const [manifest, runA, answerA, resolverA, evidenceA, runB, answerB, resolverB, evidenceB, runtime, cleanup, review, scenario, locale, technology] = await Promise.all([
      config.manifest, config.run_a_summary, config.run_a_answer, config.run_a_resolver, config.run_a_evidence,
      config.run_b_summary, config.run_b_answer, config.run_b_resolver, config.run_b_evidence, config.runtime,
      config.cleanup, config.review, config.scenario_metadata, config.locale, config.technology_profile,
    ].map(loadJson));
    requireAccepted(config, manifest, runA, resolverA, runB, resolverB, scenario, technology, review);
    const positionVariants = config.position_variants ? await loadJson(config.position_variants) : null;
    const messages = locale.messages ?? {};
    const firstA = evidenceA.evidence?.[0] ?? {};
    const firstB = evidenceB.evidence?.[0] ?? {};
    byId("scenario-id").textContent = scenario.scenario_id;
    byId("scenario-title").textContent = messages["scenario.title"] ?? scenario.display_name;
    byId("scenario-summary").textContent = scenario.summary;
    byId("question-text").textContent = evidenceA.query;
    byId("run-a-title").textContent = messages["runA.title"] ?? "Run A: frozen workspace evidence";
    byId("run-b-title").textContent = messages["runB.title"] ?? "Run B: Cortrix read-only plugin";
    byId("run-a-verdict").textContent = messages["runA.verdict"] ?? "Current authority unavailable";
    byId("run-b-verdict").textContent = messages["runB.verdict"] ?? "Current authority recovered";
    addDefinition(byId("run-a-details"), "Top evidence", firstA.document_id);
    addDefinition(byId("run-a-details"), "Lifecycle status", firstA.status);
    addDefinition(byId("run-a-details"), "Authority pass", resolverA.authority_pass);
    addDefinition(byId("run-a-details"), "Expected control", resolverA.expected_outcome_observed);
    addDefinition(byId("run-a-details"), "Decision", summarizeDecision(resolverA.decision));
    byId("run-a-answer").textContent = answerA.answer;
    addDefinition(byId("run-b-details"), "Top evidence", firstB.document_id);
    addDefinition(byId("run-b-details"), "Lifecycle status", firstB.status);
    addDefinition(byId("run-b-details"), "Authority pass", resolverB.authority_pass);
    addDefinition(byId("run-b-details"), "Serial queries", `${runB.serial_query_count}, identical source order`);
    addDefinition(byId("run-b-details"), "Decision", summarizeDecision(resolverB.decision));
    byId("run-b-answer").textContent = answerB.answer;
    addDefinition(byId("comparison-details"), "Harness", `${technology.harness.mode} @ ${technology.harness.commit.slice(0, 12)}`);
    addDefinition(byId("comparison-details"), "Model", `${manifest.provider.provider}/${manifest.provider.model}`);
    addDefinition(byId("comparison-details"), "Question and corpus", "identical");
    addDefinition(byId("comparison-details"), "Answer contract", "identical");
    addDefinition(byId("comparison-details"), "Only independent variable", manifest.comparison.only_independent_variable);
    addDefinition(byId("comparison-details"), "Run A evidence provider", evidenceA.provider);
    addDefinition(byId("comparison-details"), "Run B evidence provider", evidenceB.provider);
    addDefinition(byId("resolver-details"), "Selected document", resolverB.resolver_selected_document_id);
    addDefinition(byId("resolver-details"), "Allowed action", resolverB.resolver_action);
    addDefinition(byId("resolver-details"), "Execution pass", resolverB.execution_pass);
    addDefinition(byId("resolver-details"), "Authority pass", resolverB.authority_pass);
    addDefinition(byId("runtime-details"), "Observable provider calls", manifest.usage.observable_calls);
    addDefinition(byId("runtime-details"), "Observable input tokens", manifest.usage.observable_input_tokens);
    addDefinition(byId("runtime-details"), "Observable output tokens", manifest.usage.observable_output_tokens);
    addDefinition(byId("runtime-details"), "Observable cost", `$${Number(manifest.usage.observable_cost_usd).toFixed(6)} USD`);
    addDefinition(byId("runtime-details"), "Usage visibility", manifest.usage.visibility);
    addDefinition(byId("runtime-details"), "Model cache", `${runtime.model_cache_action}; checksums ${runtime.model_checksums.all_match ? "match" : "failed"}`);
    if (positionVariants) {
      if (positionVariants.all_variants_pass !== true || positionVariants.variants?.length !== 3) throw new Error("Position variant aggregate is invalid.");
      for (const item of positionVariants.variants) addDefinition(byId("variant-details"), item.variant, `Run A ${item.run_a_pass ? "pass" : "fail"}; Run B ${item.run_b_pass ? "pass" : "fail"}; authority ${item.authority_pass ? "pass" : "fail"}`);
      byId("position-variants").hidden = false;
    }
    addDefinition(byId("identity-details"), "Run ID", manifest.run_id);
    addDefinition(byId("identity-details"), "Demo commit", manifest.source_identity.demo_commit);
    addDefinition(byId("identity-details"), "Plugin commit", manifest.source_identity.plugin_commit);
    addDefinition(byId("identity-details"), "Cortrix commit", manifest.source_identity.cortrix_commit);
    addDefinition(byId("identity-details"), "Clean Room review", manifest.acceptance.review_id);
    addDefinition(byId("identity-details"), "Namespace cleanup", cleanup.removed_or_absent);
    addDefinition(byId("identity-details"), "Containers absent", cleanup.containers_absent);
    addDefinition(byId("identity-details"), "Secret persisted", manifest.provider.secret_value_recorded);
    byId("resolver-title").textContent = messages["resolver.title"] ?? "Application authority and action validation";
    byId("claim-boundary").textContent = messages.boundary ?? resolverB.claim_boundary;
    byId("synthetic-disclosure").textContent = scenario.synthetic_disclosure;
    renderSteps();
    byId("status-panel").classList.add("accepted");
    byId("status-text").textContent = "Independent Clean Room accepted";
    byId("question-panel").hidden = false;
    byId("evidence-grid").hidden = false;
    byId("boundary").hidden = false;
  } catch (error) {
    byId("status-panel").classList.add("rejected");
    byId("status-text").textContent = "No valid accepted evidence";
    byId("failure-message").textContent = error instanceof Error ? error.message : String(error);
    byId("failure").hidden = false;
  }
}

const theme = window.localStorage.getItem("cortrix-theme");
if (theme === "dark" || theme === "light") document.documentElement.dataset.theme = theme;
byId("theme-toggle").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  window.localStorage.setItem("cortrix-theme", next);
  byId("theme-toggle").setAttribute("aria-pressed", String(next === "dark"));
});

render();
