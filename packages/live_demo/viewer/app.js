"use strict";

(() => {
  const $ = (selector) => document.querySelector(selector);
  const API = window.DemoAPI;
  const Presentation = window.DemoPresentation;
  const STAGES = ["input", "write", "search", "result", "code"];
  const ACTIVE = new Set(["queued", "running", "cancelling", "cancel_requested", "cleaning", "cleanup_pending", "waiting_cleanup"]);
  const STATES = { queued: "Queued", pending: "Waiting", waiting: "Waiting", started: "Started", running: "Running", processing: "Processing", completed: "Completed", complete: "Completed", succeeded: "Completed", success: "Completed", ready: "Ready", failed: "Failed", error: "Error", cancelled: "Stopped", canceled: "Stopped", cancelling: "Stopping", cancel_requested: "Stop requested", paused_budget: "Paused: budget reached", paused_limit: "Paused: request limit reached", paused_count: "Paused: request limit reached", paused: "Paused", interrupted: "Reconciliation required", needs_reconciliation: "Reconciliation required", unknown: "Unconfirmed", cleaned: "Generated data cleaned", cleaning: "Cleaning", cleanup_pending: "Cleanup pending", waiting_cleanup: "Cleanup pending", cleanup_failed: "Cleanup incomplete", not_started: "Not started", skipped: "Not run" };
  const STAGE_NAMES = { input: "Freeze input", freeze: "Freeze input", empty_check: "Empty-state check", parse: "Parse documents", parsing: "Parse documents", chunk: "Chunk documents", chunking: "Chunk documents", embed: "Generate vectors", embedding: "Generate vectors", write: "Ingest", ingest: "Ingest source", ingestion: "Ingest source", wait: "Wait for processing", processing: "Process", ready: "Check query readiness", search: "Retrieve", query: "Query", retrieve: "Retrieve", retrieval: "Retrieve", resolve: "Resolve business answer", resolver: "Resolve business answer", filter: "Filter lifecycle", result: "Business result", verify: "Verify result", harness: "Agent tool execution" };
  const QUESTIONS = {};
  Object.assign(STAGE_NAMES, { namespace_ready: "Prepare isolated namespace", document_task_reconciled: "Reconcile document task", document_reconciled: "Reconcile stored document", document_task_accepted: "Accept document task", document_task_progress: "Observe document processing", document_written: "Confirm document write", vectors_exported: "Export actual vectors", pg_write_reconciled: "Reconcile PG write", pg_written: "Commit PG write", enrichment_progress: "Observe semantic processing", enrichment_failed: "Semantic processing failed", enrichment_completed: "Semantic processing complete", ingest_completed: "Ingest complete", pg_query_completed: "PG query complete", cortrix_query_submitting: "Submit Cortrix query", cortrix_query_response: "Receive Cortrix query response", cortrix_query_completed: "Cortrix query complete", namespace_cleanup_receipt: "Verify namespace cleanup receipt", cleanup_completed: "Cleanup complete" });
  const state = { workspace: null, workspaceStatus: "loading", run: null, runId: "", presentedRunId: "", selected: new Set(), stage: "input", previewId: "", code: null, busy: false, refreshing: false, initialized: false, poll: null, pollCount: 0, review: null, identity: "", lastObserved: null };
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));
  const json = (value) => typeof value === "string" ? value : JSON.stringify(value, null, 2);
  const status = (value) => STATES[value] || value || "Not started";
  const languageName = (value) => value === "en" || value === "en-US" ? "English" : value === "zh" || value === "zh-CN" ? "Chinese" : "Uploaded";
  const modeName = (value) => value === "harness" ? "Harness" : "Deterministic";
  function time(value) { if (!value) return "No timestamp"; const date = new Date(value); return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("en-US", { hour12: false }); }
  function duration(value) { return value === null || value === undefined || !Number.isFinite(Number(value)) ? "No duration" : Number(value) < 1000 ? `${Number(value).toFixed(1)} ms` : `${(Number(value) / 1000).toFixed(2)} s`; }
  function money(value) { return value === null || value === undefined || value === "unknown" ? "Unknown" : Number.isFinite(Number(value)) ? `$${Number(value).toFixed(4)}` : String(value); }
  function stored(key) { try { return localStorage.getItem(key); } catch { return null; } }
  function remember(key, value) { try { localStorage.setItem(key, value); } catch { /* Storage is optional; server records remain authoritative. */ } }
  function requestIdentity(body) {
    const signature = JSON.stringify(body);
    let pending;
    try { pending = JSON.parse(sessionStorage.getItem("cortrix.demo.pending_run") || "null"); } catch { pending = null; }
    if (pending?.signature === signature) return pending.key;
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    const key = [...bytes].map((byte) => byte.toString(16).padStart(2, "0")).join("");
    try { sessionStorage.setItem("cortrix.demo.pending_run", JSON.stringify({ signature, key })); } catch { /* The in-flight UI lock still prevents simultaneous submissions. */ }
    return key;
  }
  function notice(message, error = false) { $("#notice").textContent = message; $("#notice").classList.toggle("error", error); $("#notice").title = message; }
  function showError(error) { const sessionExpired = error.status === 401 || error.status === 403; notice(sessionExpired ? "The page session expired. Refresh or try the action again. No request was retried automatically." : `The action did not complete: ${error.message}`, true); }
  function selectedFiles() { return (state.workspace?.files || []).filter((file) => state.selected.has(file.id)); }
  function visibleFiles() { return (state.workspace?.files || []).filter((file) => !file.default || !(file.locale || file.language) || (file.locale || file.language) === $("#language").value); }
  function persistSelection() { remember("cortrix.demo.input_ids", JSON.stringify([...state.selected])); }
  function runFiles() {
    if (!state.run) return selectedFiles();
    const direct = state.run.inputs?.files || state.run.input_files || state.run.files;
    if (Array.isArray(direct) && direct.length && typeof direct[0] === "object") return direct;
    const ids = state.run.input_ids || state.run.inputs?.input_ids || state.run.manifest?.input_ids || [];
    return ids.map((id) => state.workspace?.files.find((file) => file.id === id) || { id, name: id });
  }
  function effectiveMode() { return state.run?.mode || $("#mode").value; }
  function pgAssistEnabled(pathKey) { return state.run?.execution_contract === "demo_h123_v1" && Array.isArray(state.run?.pg_llm_assist_profile?.paths) && state.run.pg_llm_assist_profile.paths.includes(pathKey); }
  function paths() { const deterministicLabel = pgAssistEnabled("a1") ? "A1 · Application rules and LLM assist" : "A1 · Application-managed rules"; const harnessLabel = pgAssistEnabled("pg") ? "A1 · Application rules and LLM assist" : "A1 · Application-managed rules"; return effectiveMode() === "harness" ? [{ key: "a0", label: "A0 · Basic vector retrieval", inactive: true }, { key: "pg", label: harnessLabel }, { key: "b", label: "B · Cortrix processing and retrieval" }] : [{ key: "a0", label: "A0 · Basic vector retrieval" }, { key: "a1", label: deterministicLabel }, { key: "b", label: "B · Cortrix processing and retrieval" }]; }
  function pathData(path) { return state.run?.paths?.[path.key] || state.run?.paths?.[path.key.toUpperCase()] || {}; }
  function allSteps(data) { return Array.isArray(data.steps) ? data.steps : []; }
  function stageTiming(path, data) {
    if (!state.run || path.inactive || state.run.state === "cleaned" || !["write", "search"].includes(state.stage)) return null;
    return window.DemoTiming.summarize(allSteps(data), state.stage === "write" ? "ingest" : "query");
  }
  function timingLabel(timing) {
    return timing.complete ? `${(timing.duration_ms / 1000).toFixed(2)} seconds` : timing.incomplete_attempts ? "Incomplete timing" : "No total duration recorded";
  }
  function timingDescription(timing) {
    const scope = state.stage === "write" ? "From ingest start to processing readiness" : "From query start to retrieval verification";
    const boundary = "Only top-level controller attempts are totaled. Nested work is not counted twice, and the total excludes operator pauses and Agent decisions outside the stage.";
    if (!timing.recorded_attempts && !timing.incomplete_attempts) return `${scope} has no recorded total duration. ${boundary}`;
    return timing.complete ? `${scope}, totaling ${timingLabel(timing)}. ${boundary}` : `Recorded ${(timing.duration_ms / 1000).toFixed(2)} seconds; ${timing.incomplete_attempts} attempts have incomplete timing, so this is not a complete total. ${boundary}`;
  }
  function category(step) { if (step.operation === "query") return "search"; if (step.operation === "ingest") return "write"; const value = String(step.stage || step.name || "").toLowerCase(); if (/search|query|retriev|rank/.test(value)) return "search"; if (/resolv|filter|result|answer|verify/.test(value)) return "result"; if (/input|freeze|source/.test(value)) return "input"; return "write"; }
  function artifactLink(ref, path) { return `evidence.html?run=${encodeURIComponent(state.runId)}${path ? `&path=${encodeURIComponent(path)}` : ""}${ref ? `#${encodeURIComponent(ref)}` : ""}`; }
  function stepRows(steps) {
    if (!steps.length) return '<p class="empty-state">No observations for this stage. The viewer does not invent progress that a component did not report.</p>';
    const labels = { runtime_prepared: "Enable runtime (outside stage)", document_submitting: "Submit source documents", document_task_accepted: "Ingest task accepted", document_task_progress: "Document processing status", document_written: "Document stored", document_reconciled: "Reconcile stored document", namespace_ready: "Namespace ready", vectors_exported: "Actual vectors exported", pg_written: "PostgreSQL write completed", provider_request: "Model request sent", provider_response: "Model response received", enrichment_progress: "Enrichment status", enrichment_completed: "Enrichment completed", enrichment_failed: "Enrichment failed", ingest_started: "Ingest started", ingest_completed: "Ingest completed, including child operations", query_started: "Query started", query_completed: "Query completed, including child operations", pg_query_completed: "Native PG query completed", cortrix_query_submitting: "Submit Cortrix query", cortrix_query_response: "Received raw Cortrix response", cortrix_query_completed: "Cortrix query verification completed" };
    return `<div class="rows">${steps.map((step) => `<div class="data-row"><div class="data-row-top"><span class="data-row-name">${esc(labels[step.stage] || STAGE_NAMES[step.stage] || step.stage || step.name || "Operation")}</span><span class="duration">${esc(duration(step.duration_ms))}</span></div><small>${esc(status(step.state))}${step.observed_at ? ` · ${esc(time(step.observed_at))}` : ""}</small>${step.document_id ? `<small>Document · ${esc(step.document_id)}</small>` : ""}${step.document_count !== undefined ? `<small>Documents ${esc(step.document_count)}${step.chunk_count !== undefined ? ` · source chunks ${esc(step.chunk_count)}` : ""}</small>` : ""}${step.row_count !== undefined ? `<small>Database rows ${esc(step.row_count)}</small>` : ""}${step.artifact_ref ? `<a class="source-button" href="${artifactLink(step.artifact_ref, step.path)}">View step evidence ↗</a>` : ""}</div>`).join("")}</div>`;
  }
  function runtimeSetupNote(steps) {
    const event = [...steps].reverse().find(step => (step.evidence_source || step.source) === "runtime_control" && step.stage === "runtime_prepared" && step.operation === "setup" && step.stage_total_includes_setup === false && typeof step.duration_ms === "number" && Number.isFinite(step.duration_ms) && step.duration_ms >= 0);
    return event ? `<p class="scope-note runtime-setup-note">Runtime setup took ${esc((event.duration_ms / 1000).toFixed(2))} seconds and is excluded from this stage total.</p>` : "";
  }
  function businessStepRows(steps, operation) {
    const rows = window.DemoTiming.summarizeBusinessSteps(steps, operation);
    if (!rows.length) return '<p class="legacy-timing-note">This historical run has no separate business-step boundaries. Aggregate observations remain in execution details and are not relabeled as step duration.</p>';
    const operationNames = { ingest: "Ingest", query: "Query", agent: "Agent" };
    return `<div class="business-steps" aria-label="Measured business-step duration">${rows.map((item) => `<div class="business-step" data-step-id="${esc(item.step_id)}"><div class="data-row-top"><strong>${esc(item.label)}</strong><span class="duration">${esc(item.recorded_attempts ? duration(item.duration_ms) : "Duration unknown")}</span></div><small>${esc(operationNames[item.operation] || item.operation)} · Owner ${esc(item.owner_label)} · state ${esc(status(item.state))}</small>${item.recorded_attempts > 1 ? `<small>${esc(item.recorded_attempts)} completed attempts totaled</small>` : ""}${item.incomplete_attempts ? `<small class="timing-note">Another ${esc(item.incomplete_attempts)} attempts are incomplete, so the total is incomplete.</small>` : ""}</div>`).join("")}</div>`;
  }
  function applicationModelUsage(path) {
    const source = Array.isArray(state.run?.events) && state.run.events.length ? state.run.events : allSteps(pathData(path));
    const events = source.filter(event => event.stage === "application_model_request" && (!event.path || event.path === path.key));
    const requestIds = new Set(events.map(event => event.request_id).filter(Boolean));
    const sessionIds = new Set(events.map(event => event.session_id).filter(Boolean));
    return { requests: requestIds.size, missing_ids: events.filter(event => !event.request_id).length, session_ids: [...sessionIds] };
  }
  function assistNote(path) {
    if (!pgAssistEnabled(path.key)) return "";
    const usage = applicationModelUsage(path);
    const count = usage.missing_ids ? `${usage.requests} deduplicated requests, plus ${usage.missing_ids} records without request_id` : `${usage.requests} requests`;
    const requestLimit = state.run.pg_llm_assist_profile.max_requests_per_path;
    const accounting = effectiveMode() === "harness" ? `Application assistance counts toward the four-request limit for the current native session. The native receipt still reports its own request count${usage.session_ids.length ? `; session ${usage.session_ids.map(value => Presentation.displayValue(value)).join(", ")}` : ""}` : "Application-assistance requests are deduplicated by request_id";
    return `<p class="profile-note">Application model assistance: ${esc(usage.requests)} requests${usage.missing_ids ? " (plus unrecognized records)" : ""}</p><details class="execution-details model-boundary"><summary>Model-call and processing boundary</summary><p>${esc(count)}${Number.isInteger(requestLimit) ? ` / up to ${esc(requestLimit)} requests` : ""}; ${esc(accounting)}. One call expands the query and ranks the existing vector candidates before PG lexical candidates are fused. Newly added lexical candidates are not reranked by the LLM. PG lexical retrieval is not BM25, and this path does not claim equivalence with Cortrix Full Stack.</p></details>`;
  }
  function scoreRows(item) {
    return Object.keys(item).filter((key) => /score|similarity|distance/.test(key)).map((key) => `<small>${esc(item.score_type && key === "score" ? item.score_type : key)}: ${esc(Presentation.displayValue(item[key]))}</small>`).join("");
  }
  function rankingRows(ranking, selectedSource, compact = false) {
    if (!Array.isArray(ranking) || !ranking.length) return '<p class="empty-state">No retrieval candidates yet.</p>';
    const visible = compact ? Presentation.selectRanking(ranking, selectedSource) : ranking;
    const selectedIdentity = selectedSource && typeof selectedSource === "object" ? Presentation.identity(selectedSource) : selectedSource;
    return `<div class="rows">${visible.map((item) => {
      const index = ranking.indexOf(item);
      if (typeof item !== "object" || item === null) return `<div class="data-row">${index + 1}. ${esc(item)}</div>`;
      const lifecycle = item.lifecycle_status || item.lifecycle || item.status || "";
      const adopted = item.adopted === true || item.selected === true || (selectedIdentity && Presentation.identity(item) === selectedIdentity);
      return `<div class="data-row ${lifecycle === "current" ? "current" : ""} ${item.excluded ? "excluded" : ""} ${adopted ? "adopted" : ""}"><div class="data-row-top"><span class="data-row-name">Original rank ${esc(item.rank ?? index + 1)} · ${esc(item.title || item.document_id || item.doc_id || item.id || "candidate source")}</span></div><small>${lifecycle ? esc(lifecycle) : "State not reported"}${adopted ? " · selected" : item.excluded ? " · excluded by the application" : " · comparison item"}</small>${compact ? "" : scoreRows(item)}${item.reason ? `<small>${esc(Presentation.displayValue(item.reason))}</small>` : ""}</div>`;
    }).join("")}</div>`;
  }
  const CODE_CATEGORIES = { application: "Application code", configuration: "Configuration", tests: "Tests" };
  function codeRanges(file, path) {
    const mode = effectiveMode();
    return (file.source_ranges || []).filter((range) => range.included && (range.consumers || []).some((consumer) => consumer.mode === mode && consumer.path === path.key));
  }
  function codeFiles(path) {
    return (state.code?.files || []).filter((file) => (file.modes || []).includes(effectiveMode()) && codeRanges(file, path).length);
  }
  function countedValue(value) { return Number.isInteger(value) && value >= 0 ? String(value) : "Not provided"; }
  function sourceRangeButtons(file, path) {
    return codeRanges(file, path).map((range) => `<button class="source-button range-button" data-code-file="${esc(file.path)}" data-code-path="${path.key}" data-code-start="${esc(range.start_line)}" data-code-end="${esc(range.end_line)}"><span>${esc(range.source_ref || `${file.path}:${range.start_line}`)}–${esc(range.end_line)}</span><small>${esc(range.symbol)} · ${esc(CODE_CATEGORIES[range.category] || range.category)} · ${esc(countedValue(range.code_lines))} lines of code</small></button>`).join("");
  }
  const FALLBACK_RESPONSIBILITIES = {
    a0: [
      ["vector", "Generate and obtain vectors", "The application integrates Cortrix embedding-only and maintains vector export.", ["application", "cortrix"]],
      ["pg", "PG data organization and ranking", "The application maintains vector writes, data organization, and similarity ranking.", ["application", "postgresql"]],
      ["lifecycle", "Current-version rules", "This path does not filter by version; it selects the first vector result.", ["application"]],
      ["business", "Business-field and source verification", "The application extracts the field and verifies its source.", ["application"]],
    ],
    a1: [
      ["vector", "Generate and obtain vectors", "Reuses A0's Cortrix embedding-only and vector foundation.", ["application", "cortrix"]],
      ["pg", "PG data organization and ranking", "Reuses A0's write, organization, and ranking foundation; required shared code remains counted.", ["application", "postgresql"]],
      ["lifecycle", "Current-version rules", "The application adds valid-version filtering and candidate selection.", ["application"]],
      ["business", "Business-field and source verification", "The application extracts the field and verifies its source.", ["application"]],
    ],
    pg: [
      ["vector", "Generate and obtain vectors", "The application integrates Cortrix embedding-only and maintains the PG processing foundation.", ["application", "cortrix"]],
      ["lifecycle", "Application rules and Agent coordination", "The application maintains valid-version rules, tool results, and the final-answer contract.", ["application"]],
      ["business", "Business-field and source verification", "The application extracts the field and verifies its source.", ["application"]],
    ],
    b: [
      ["full-stack", "Processing, retrieval, and enrichment readiness", "The application submits sources and integrates the API; Cortrix performs processing and retrieval.", ["cortrix"]],
      ["lifecycle", "Current-version rules", "The application selects the current version from the candidates returned by Cortrix.", ["application"]],
      ["business", "Business-field and source verification", "The application extracts the field and verifies its source.", ["application"]],
    ],
  };
  function responsibilityConsumers(item) { return item.consumers || item.paths || item.owners || []; }
  function responsibilityApplies(item, path, mode) {
    const consumers = responsibilityConsumers(item);
    return !consumers.length || consumers.some(consumer => typeof consumer === "string" ? consumer === path.key || consumer === `${mode}:${path.key}` : (!consumer.mode || consumer.mode === mode) && (consumer.path === path.key || consumer.id === path.key));
  }
  function responsibilities(path, mode) {
    const supplied = (state.code.responsibilities || []).filter(item => responsibilityApplies(item, path, mode));
    return supplied.length ? supplied : (FALLBACK_RESPONSIBILITIES[path.key] || []).map(([id, label, description, owners]) => ({ id, label, description, owners }));
  }
  function responsibilityCodeLines(item, path) { return Number.isInteger(item.code_lines) ? item.code_lines : Number.isInteger(item.code_lines?.[path.key]) ? item.code_lines[path.key] : null; }
  function responsibilityRangeButtons(item, path) {
    return (item.source_ranges || []).map(range => {
      const filePath = range.path || range.file || range.file_path || range.source_path;
      if (!filePath || !range.start_line || !range.end_line || !state.code.files?.some(file => file.path === filePath)) return "";
      return `<button class="source-button range-button" data-code-file="${esc(filePath)}" data-code-path="${path.key}" data-code-start="${esc(range.start_line)}" data-code-end="${esc(range.end_line)}">${esc(range.source_ref || `${filePath}:${range.start_line}–${range.end_line}`)}</button>`;
    }).join("");
  }
  function responsibilityCard(item, path, compact = false) {
    const lines = responsibilityCodeLines(item, path);
    const ranges = responsibilityRangeButtons(item, path);
    return `<div class="responsibility-card${compact ? " responsibility-card-primary" : ""}" data-responsibility-id="${esc(item.id)}"><div class="data-row-top"><strong>${esc(item.label || item.id)}</strong>${lines !== null ? `<span class="duration">${esc(lines)} lines of code</span>` : ""}</div><p>${esc(item.description || "Responsibility description pending.")}</p>${ranges ? `<details class="responsibility-sources"><summary>View source ranges</summary>${ranges}</details>` : ""}</div>`;
  }
  function codeContent(path) {
    if (!state.code) return '<p class="empty-state">Loading source code and counts.</p>';
    const mode = effectiveMode();
    const files = codeFiles(path);
    const counts = state.code.counts?.by_mode?.[mode]?.[path.key];
    const snapshot = state.run?.code_inventory_snapshot;
    const snapshotCounts = snapshot?.counts?.by_mode?.[mode]?.[path.key];
    const sql = state.code.counts?.by_path?.[path.key]?.sql;
    const comparison = state.code.capabilities_equivalent === false ? "Capability coverage differs, so no savings percentage is calculated." : "Source-line counts do not represent performance or a validated benefit.";
    const reference = `counts.by_mode.${mode}.${path.key}`;
    const methodology = { source_manifest_sha256: state.code.source_manifest_sha256, inventory_implementation_sha256: state.code.inventory_implementation_sha256, methodology: state.code.methodology, warnings: state.code.warnings, excluded: state.code.excluded };
    const applicableResponsibilities = responsibilities(path, mode);
    const groups = Presentation.responsibilityGroups(applicableResponsibilities, path.key);
    const commonResponsibilities = groups.common;
    const distinctResponsibilities = applicableResponsibilities.filter(item => !commonResponsibilities.includes(item));
    const primaryResponsibilities = groups.primary;
    const distinctLines = groups.distinct_lines;
    const commonLines = groups.common_lines;
    const responsibilityCards = primaryResponsibilities.map(item => responsibilityCard(item, path, true)).join("");
    const commonCards = commonResponsibilities.map(item => responsibilityCard(item, path)).join("");
    function countsTableFor(value, label, testIds = false) {
      if (!value) return `<p>${esc(label)} is not available.</p>`;
      return `<h4>${esc(label)}</h4><table class="code-counts" ${testIds ? `data-testid="code-counts-${path.key}"` : ""}><caption class="sr-only">${esc(path.label)}${esc(label)}</caption><thead><tr><th scope="col">Category</th><th scope="col">Exclusive</th><th scope="col">Shared</th><th scope="col">Total</th></tr></thead><tbody>${Object.entries(CODE_CATEGORIES).map(([category, categoryLabel]) => `<tr><th scope="row">${categoryLabel}</th>${["exclusive", "shared", "total"].map(measure => `<td ${testIds ? `data-testid="code-count-${path.key}-${category}-${measure}"` : ""}>${esc(countedValue(value[category]?.[measure]))}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
    }
    const versionNotice = snapshot ? `<p class="version-inline">This run has a frozen code snapshot; details are shown separately from the current implementation.</p>` : state.run ? `<p class="version-inline">Current implementation, not the historical run's version.</p>` : `<p class="version-inline">Current implementation.</p>`;
    const llmNotice = primaryResponsibilities.some(item => item.id === "application_llm_assist") ? `<p class="code-boundary">PG lexical retrieval in the current implementation is not BM25, and this path does not claim equivalence with Cortrix Full Stack.</p>` : "";
    const distinctSummary = distinctResponsibilities.length ? `<p class="difference-total">Differing code: ${esc(distinctLines)} lines <span>· Includes only the path-specific responsibilities below, not all dependencies</span></p>` : "";
    const commonDetails = commonResponsibilities.length ? `<details class="common-dependencies"><summary>Required shared dependencies: ${esc(commonLines)} lines (still included in complete counts)</summary><div class="responsibility-list responsibility-list-common">${commonCards}</div></details>` : "";
    return `<h3>What this path requires the application to maintain</h3>${versionNotice}${distinctSummary}<div class="responsibility-list responsibility-list-primary">${responsibilityCards}</div>${llmNotice}<p class="code-boundary">A0 and A1 use Cortrix embedding-only. In B, the application still owns current-version rules and verification.</p>${commonDetails}<details class="code-details"><summary>Complete counts, configuration, tests, and source evidence</summary>${snapshot ? countsTableFor(snapshotCounts, "Frozen snapshot for this run") : ""}${countsTableFor(counts, "All required dependencies in the current implementation", true)}<p class="code-reference">Reference: <code>${esc(reference)}</code><br>Source: <code>code_inventory.inventory()</code></p><p class="code-boundary">${comparison} Scores and code counts across paths do not establish feature equivalence or a savings percentage.</p>${sql ? `<div class="sql-note" data-testid="sql-note-${path.key}">SQL spans ${esc(countedValue(sql.source_lines))} source lines. These are already included in application code and are not added again.<small>Reference: counts.by_path.${path.key}.sql · non_additive=${esc(sql.non_additive)}</small></div>` : ""}<details class="code-methodology"><summary>Snapshot, counting method, hashes, and exclusions</summary>${state.code.baseline_snapshot ? `<p>A separately supplied comparison snapshot follows.</p><pre class="inline-json">${esc(json(state.code.baseline_snapshot))}</pre>` : '<p>No separate comparison snapshot was supplied.</p>'}${snapshot ? `<pre class="inline-json">${esc(json({ execution_contract: state.run.execution_contract, timing_schema_version: state.run.timing_schema_version, run_source_manifest_sha256: snapshot.source_manifest_sha256, current_source_manifest_sha256: state.code.source_manifest_sha256 }))}</pre>` : ""}<pre class="inline-json">${esc(json(methodology))}</pre></details><h3 class="source-heading">Source references and counted ranges</h3><div class="rows">${files.map(file => `<div class="data-row"><div class="data-row-top"><span>${esc(CODE_CATEGORIES[file.category] || file.category || "Source")}</span><span class="duration">Whole file: ${esc(countedValue(file.lines))} lines</span></div><button class="source-button" data-code-file="${esc(file.path)}" data-code-path="${path.key}">${esc(file.path)}</button><small title="${esc(file.sha256 || "")}">SHA-256 · ${esc(file.sha256 || "Not provided")}</small><details class="source-ranges"><summary>View ranges counted for this path (${codeRanges(file, path).length} ranges)</summary>${sourceRangeButtons(file, path)}</details></div>`).join("") || '<p>No source-file inventory for this path.</p>'}</div><a class="source-button" href="${artifactLink("code")}">Review complete counts and all source independently ↗</a></details>`;
  }
  function openCode(button) {
    const file = state.code?.files.find((item) => item.path === button.dataset.codeFile);
    if (!file) return;
    const path = { key: button.dataset.codePath };
    const start = Number(button.dataset.codeStart);
    const end = Number(button.dataset.codeEnd);
    const ranges = start && end ? [{ start_line: start, end_line: end }] : codeRanges(file, path);
    $("#code-title").textContent = file.path;
    $("#code-meta").textContent = `${CODE_CATEGORIES[file.category] || file.category || "Source"} · ${modeName(effectiveMode())} / ${path.key.toUpperCase()} · Full source; highlights show statically counted ranges, not an execution trace. SHA-256: ${file.sha256 || "Not provided"}`;
    $("#code-content").innerHTML = String(file.content ?? "The server did not provide source text.").split("\n").map((line, index) => { const included = ranges.some((range) => index + 1 >= range.start_line && index + 1 <= range.end_line); return `<span class="code-line ${included ? "code-line-included" : ""}" data-source-line="${index + 1}"><span class="code-line-number">${index + 1}</span>${esc(line)}</span>`; }).join("");
    $("#code-dialog").showModal();
    const first = $("#code-content .code-line-included");
    if (first) $("#code-content").scrollTop = Math.max(0, first.offsetTop - $("#code-content").offsetTop - 24);
    else $("#code-content").scrollTop = 0;
  }
  function content(path, data) {
    if (!state.workspace && state.stage !== "code") return state.workspaceStatus === "failed" ? '<h3>Workspace could not be loaded</h3><p>See the error at the bottom of the page and refresh after the connection recovers.</p>' : '<h3>Loading workspace</h3><p>Loading source documents and saved runs.</p>';
    if (path.inactive) return '<h3>A0 is not run in this mode</h3><p>This Harness comparison runs the application-rules and Cortrix paths. The two Agent tool traces appear in the right columns.</p>';
    if (state.stage === "code") return codeContent(path);
    if (state.stage === "input") {
      const files = runFiles();
      return `<h3>${state.run ? "Frozen inputs for this run" : "Pending input"}</h3><span class="record-label">${state.run ? `${esc(modeName(state.run.mode))} · ${esc(languageName(state.run.locale || state.run.language))}` : "The server freezes the same bytes when the run starts"}</span><div class="rows">${files.map((file) => `<div class="data-row"><div class="data-row-top"><span class="data-row-name">${esc(file.name || file.id)}</span><span class="duration">${file.bytes !== undefined ? `${esc(file.bytes)} B` : ""}</span></div>${file.sha256 ? `<small title="${esc(file.sha256)}">SHA-256 · ${esc(file.sha256.slice(0, 20))}…</small>` : ""}${file.locale || file.language ? `<small>${esc(languageName(file.locale || file.language))}</small>` : ""}</div>`).join("") || '<p class="empty-state">No input manifest yet.</p>'}</div>${state.run?.question ? `<p>Frozen question: ${esc(state.run.question)}</p>` : ""}${state.run ? "" : '<p>Select the documents, question, and mode above, then explicitly start a live run.</p>'}`;
    }
    if (state.run?.state === "cleaned") return '<p class="empty-state">Generated data for this run was cleaned. The original documents remain available for a new run with the same inputs.</p>';
    if (state.stage === "write") {
      const timing = stageTiming(path, data);
      const historical = allSteps(data).filter(step => category(step) === "write" || category(step) === "input");
      return `<h3>Ingest and processing steps</h3>${runtimeSetupNote(allSteps(data))}${timing && !timing.complete ? `<p class="timing-note">${esc(timingDescription(timing))}</p>` : ""}${businessStepRows(allSteps(data), "ingest")}<p class="scope-note">Steps can overlap or run concurrently, so their durations must not be added to the top-level total.</p><details class="execution-details"><summary>Execution details and source receipts</summary>${stepRows(historical)}${data.storage ? `<pre class="inline-json">${esc(json(data.storage))}</pre>` : ""}</details>`;
    }
    if (state.stage === "search") {
      const ranking = data.ranking || data.result?.ranking || data.query?.ranking || [];
      const selectedSource = data.normalized_answer?.decision?.document_id || data.result?.document_id || data.result?.source_document_id || data.result?.resolver?.selected_document_id || data.result?.source;
      const historical = allSteps(data).filter(step => category(step) === "search" || category(step) === "result" || step.stage === "runtime_prepared");
      return `<h3>Selected result and related candidates</h3>${runtimeSetupNote(allSteps(data))}${assistNote(path)}${rankingRows(ranking, selectedSource, true)}<p class="scope-note">Original rankings are preserved. Scores from different algorithms are not compared across paths. Agent work is reported separately and excluded from the top-level query total.</p>${businessStepRows(allSteps(data), ["query", "agent"])}<details class="execution-details"><summary>Complete ranking, scores, and execution details</summary>${rankingRows(ranking, selectedSource)}${stepRows(historical)}</details>`;
    }
    const result = data.result;
    const metrics = data.metrics || data.usage || {};
    const metricNames = { tool_calls: "Agent tool calls", model_rounds: "Model turns", provider_requests: "Provider requests", input_tokens: "Input tokens", output_tokens: "Output tokens", total_tokens: "Total tokens", application_calls: "Application model calls" };
    return `<h3>Basis for this business decision</h3>${assistNote(path)}${result ? `<p>The selected field appears above. The application uses this path's resolver and candidate ranking to select the source.</p>` : '<p class="empty-state">No business result yet.</p>'}${Object.keys(metricNames).some(key => metrics[key] !== undefined) ? `<div class="metric-grid">${Object.entries(metricNames).filter(([key]) => metrics[key] !== undefined).map(([key, label]) => `<div class="metric"><span>${label}</span><strong>${esc(Presentation.displayValue(metrics[key]))}</strong></div>`).join("")}</div>` : ""}<details class="execution-details"><summary>All results, evidence, and scores</summary>${result ? `<pre class="inline-json">${esc(json(result))}</pre>` : ""}${stepRows(allSteps(data).filter(step => category(step) === "result"))}</details>${data.error ? `<p class="error-text">${esc(json(data.error))}</p>` : ""}`;
  }
  function outcome(path) {
    const data = pathData(path);
    const result = state.run?.state === "cleaned" ? null : data.result;
    const normalized = data.normalized_answer?.verified ? data.normalized_answer.decision : null;
    const field = normalized?.selected_field ?? result?.selected_field ?? result?.resolver?.selected_field ?? result?.field;
    const source = normalized?.document_id || result?.document_id || result?.source_document_id || result?.resolver?.selected_document_id || result?.source;
    const ranking = data.ranking || result?.ranking || data.query?.ranking || [];
    const selectedIdentity = source && typeof source === "object" ? Presentation.identity(source) : source;
    const sourceCandidate = ranking.find(candidate => Presentation.identity(candidate) === selectedIdentity);
    const harnessFailed = state.run?.mode === "harness" && data.harness?.business_verdict === "fail";
    const completed = ["completed", "complete", "succeeded", "success", "ready"].includes(data.state);
    return { data, result, normalized, field, source, complete: completed && !harnessFailed, llmAssist: pgAssistEnabled(path.key), lifecycle: result?.lifecycle_status || result?.lifecycle || sourceCandidate?.lifecycle_status || sourceCandidate?.lifecycle || "" };
  }
  function renderLanes() {
    $("#lanes").dataset.mode = state.run?.mode || $("#mode").value;
    const focused = document.activeElement;
    const focusPath = focused?.dataset.path;
    const focusCode = focused?.dataset.codeFile;
    const focusCodePath = focused?.dataset.codePath;
    const focusCodeStart = focused?.dataset.codeStart;
    const focusHref = focused?.closest("#lanes") ? focused.getAttribute("href") : null;
    const focusDetail = focused?.tagName === "SUMMARY" ? `${focused.closest(".lane-content")?.dataset.path}:${focused.textContent}` : null;
    const scroll = new Map([...document.querySelectorAll(".lane-content")].map((node) => [node.dataset.path, node.scrollTop]));
    const openDetails = new Set([...document.querySelectorAll("#lanes details[open]")].map((node) => `${node.closest(".lane-content")?.dataset.path}:${node.querySelector(":scope > summary")?.textContent}:${node.closest(".data-row")?.querySelector("[data-code-file]")?.dataset.codeFile || ""}`));
    const pathList = paths();
    const outcomes = Object.fromEntries(pathList.map(path => [path.key, outcome(path)]));
    $("#lanes").innerHTML = pathList.map((path) => {
      const { data, result, normalized, field, source, lifecycle } = outcomes[path.key];
      const empty = field === null || field === undefined || field === "";
      const pathState = path.inactive ? "Not part of this mode" : state.run?.state === "cleaned" ? "Cleaned" : status(data.state);
      const timing = stageTiming(path, data);
      const displayedState = timing?.last_state === "completed" ? "Completed" : pathState;
      const total = timing ? `<span class="stage-total" data-testid="stage-total-${path.key}" data-duration-ms="${timing.complete ? timing.duration_ms : ""}" tabindex="0" title="${esc(timingDescription(timing))}">${esc(timingLabel(timing))} - </span>` : "";
      const harnessFailure = state.run?.mode === "harness" && data.harness?.business_verdict === "fail";
      const answerLabel = path.inactive ? "Harness experiment scope" : normalized ? "Agent field, citation verified" : state.run?.mode === "harness" ? "Agent output, strict JSON contract" : "Final business field";
      const formatNotice = harnessFailure ? `<small class="agent-validation-note">${normalized ? "The original answer was not JSON-only. The application extracted the single JSON object and verified its citation for display; the original verdict remains preserved." : `The output contract failed. Independent retrieval and rules produced <code>${esc(result?.engine_selected_field || "unconfirmed")}</code>. Review the original answer.`}</small>` : "";
      const explanation = state.stage === "result" && !path.inactive && !empty ? `<p class="answer-explanation">${esc(Presentation.explainResult(path.key, outcomes[path.key], outcomes))}</p>` : "";
      const footer = path.inactive ? "No third Harness trace" : path.key === "a0" ? "The application selects the first vector result" : path.key === "b" ? "Cortrix processing and retrieval · Application-owned business resolver" : "Application-organized processing and retrieval · Application lifecycle rules";
      return `<article class="lane ${path.key === "b" ? "lane-b" : ""}" data-testid="lane-${path.key}"><div class="lane-head"><h2>${path.label}</h2><span class="path-summary">${total}<span class="path-status" data-testid="path-state-${path.key}">${esc(displayedState)}</span></span></div><div class="answer"><span class="answer-label">${answerLabel}</span><strong class="answer-value ${empty ? "empty" : ""}" data-testid="answer-${path.key}">${path.inactive ? "A0 is not run" : harnessFailure && !normalized ? "Output contract failed" : !empty ? esc(Presentation.displayValue(field)) : state.run?.state === "cleaned" ? "Generated data cleaned" : result ? "No field returned" : "Not produced yet"}</strong><span class="answer-source">${source ? `Source · ${esc(Presentation.displayValue(source))}` : path.inactive ? "Select deterministic mode to run all three paths" : "Source pending"}</span>${formatNotice}${lifecycle ? `<span class="answer-lifecycle" data-lifecycle="${esc(lifecycle)}">Lifecycle · ${esc(Presentation.displayValue(lifecycle))}</span>` : ""}${explanation}</div><div class="lane-content" tabindex="0" aria-label="${path.label} stage details" data-path="${path.key}" data-testid="content-${path.key}">${content(path, data)}</div><div class="lane-foot">${footer}</div></article>`;
    }).join("");
    document.querySelectorAll("#lanes details").forEach((node) => { const key = `${node.closest(".lane-content")?.dataset.path}:${node.querySelector(":scope > summary")?.textContent}:${node.closest(".data-row")?.querySelector("[data-code-file]")?.dataset.codeFile || ""}`; node.open = openDetails.has(key); });
    document.querySelectorAll(".lane-content").forEach((node) => { node.scrollTop = scroll.get(node.dataset.path) || 0; });
    const restore = focusPath ? [...document.querySelectorAll(".lane-content")].find((node) => node.dataset.path === focusPath) : focusCode ? [...document.querySelectorAll("[data-code-file]")].find((node) => node.dataset.codeFile === focusCode && node.dataset.codePath === focusCodePath && node.dataset.codeStart === focusCodeStart) : focusHref ? [...document.querySelectorAll("#lanes a")].find((node) => node.getAttribute("href") === focusHref) : focusDetail ? [...document.querySelectorAll("#lanes summary")].find(node => `${node.closest(".lane-content")?.dataset.path}:${node.textContent}` === focusDetail) : null;
    restore?.focus({ preventScroll: true });
  }
  function renderControls() {
    const active = ACTIVE.has(state.run?.state);
    const runtimeReady = state.workspace?.runtime_ready === true;
    const allowance = state.workspace?.run_allowance?.[$("#mode").value];
    const quotaUsed = allowance && allowance.used >= allowance.limit;
    $("#start").disabled = state.busy || !runtimeReady || quotaUsed || !state.selected.size || !$("#question").value.trim();
    $("#start").textContent = !state.workspace ? state.workspaceStatus === "failed" ? "Workspace could not be loaded" : "Loading workspace" : !runtimeReady ? "RC2 runtime is being prepared" : quotaUsed ? "Run allowance exhausted" : state.run ? "New live run" : "Start live run";
    $("#cancel").disabled = state.busy || !state.run || !active;
    $("#resume").disabled = state.busy || !runtimeReady || !state.run || active || ["completed", "complete", "succeeded", "success", "cleaned"].includes(state.run?.state);
    $("#cleanup").disabled = state.busy || !state.run || state.run?.state === "cleaned";
    $("#review").disabled = !state.run || active || !Object.values(state.run.paths || {}).some((path) => path.steps?.length);
    $("#upload").disabled = state.busy || !state.workspace;
    $("#manage-files").disabled = !state.workspace;
    $("#history").disabled = !state.workspace;
    $("#run-state").textContent = state.run ? `${modeName(state.run.mode)} · ${status(state.run.state)}` : "Not run";
    $("#run-state").dataset.state = state.run?.state || "not_started";
    $("#evidence-link").href = artifactLink();
    const selected = selectedFiles();
    $("#selected-files").textContent = !state.workspace ? state.workspaceStatus === "failed" ? "Source documents are not available" : "Loading source documents" : `Selected ${selected.length} documents · ${selected.map((file) => file.name).join(", ") || "Select source documents first"}`;
    $("#selected-files").title = selected.map((file) => file.name).join("\n");
    $("#draft-note").textContent = state.run ? `Viewing ${languageName(state.run.locale || state.run.language)} · ${modeName(state.run.mode)}; the controls above define a new run` : "Pending input";
    const budget = state.workspace?.budget;
    if (budget) { $("#budget").textContent = `${budget.actual_cost === "unknown" ? "Estimated upper bound" : "Spent"} ${money(budget.spent_usd)}${budget.actual_cost === "unknown" ? " · actual charge unknown" : ""} · reserved ${money(budget.reserved_usd)} / limit ${money(budget.total_limit_usd)}`; $("#budget").title = json({ budget, limits: state.workspace.limits }); }
    else $("#budget").textContent = "Budget not loaded";
  }
  function renderHistory() {
    const runs = state.workspace?.runs || [];
    $("#history").innerHTML = '<option value="">Pending input</option>' + runs.map((run) => `<option value="${esc(run.id)}">${esc(time(run.created_at))} · ${esc(languageName(run.locale || run.language))} · ${esc(modeName(run.mode))} · ${esc(status(run.state))}</option>`).join("");
    if (state.runId && !runs.some((run) => run.id === state.runId)) $("#history").insertAdjacentHTML("beforeend", `<option value="${esc(state.runId)}">${esc(state.runId)}</option>`);
    $("#history").value = state.runId;
  }
  function renderFileList() {
    const focusedId = document.activeElement?.dataset.fileId;
    const focusedPreview = document.activeElement?.dataset.previewId;
    const files = visibleFiles();
    $("#file-count").textContent = `${files.length} available documents · ${state.selected.size} selected`;
    $("#file-list").innerHTML = files.map((file) => `<div class="file-item ${state.previewId === file.id ? "active" : ""}"><input type="checkbox" data-file-id="${esc(file.id)}" data-testid="file-checkbox" aria-label="Select ${esc(file.name)}" ${state.selected.has(file.id) ? "checked" : ""}><button data-preview-id="${esc(file.id)}">${esc(file.name)}<small>${esc(languageName(file.locale || file.language))} · ${esc(file.bytes ?? "Unknown")} B · ${file.default ? "Default source" : "Uploaded copy"}</small></button></div>`).join("");
    const restore = focusedId ? [...document.querySelectorAll("[data-file-id]")].find((node) => node.dataset.fileId === focusedId) : focusedPreview ? [...document.querySelectorAll("[data-preview-id]")].find((node) => node.dataset.previewId === focusedPreview) : null;
    restore?.focus({ preventScroll: true });
  }
  function preview(id) {
    const file = state.workspace?.files.find((item) => item.id === id);
    if (!file) return;
    state.previewId = id;
    $("#preview-name").textContent = file.name;
    $("#preview-meta").textContent = `${file.version ? `Version ${file.version} · ` : ""}${file.status ? `Status ${file.status} · ` : ""}SHA-256: ${file.sha256 || "Not provided"}`;
    $("#preview-content").textContent = file.content ?? "The server did not provide document text.";
    renderFileList();
  }
  function setStage(stage, fromReview = false) {
    if (!fromReview) stopReview();
    state.stage = stage;
    document.querySelectorAll("[data-stage]").forEach((button) => { const selected = button.dataset.stage === stage; button.setAttribute("aria-selected", String(selected)); button.tabIndex = selected ? 0 : -1; });
    $("#lanes").setAttribute("aria-labelledby", `tab-${stage}`);
    if (stage === "code" && !state.code) API.get("/api/code").then((code) => { state.code = code; renderLanes(); }).catch(showError);
    renderLanes();
  }
  function stopReview() { if (state.review) clearInterval(state.review); state.review = null; $("#review").textContent = "Replay run stages"; }
  async function loadRun(id) {
    if (!id) { state.runId = ""; state.run = null; renderLanes(); renderControls(); return; }
    const requested = id;
    const firstPresentation = state.presentedRunId !== requested;
    const run = await API.get(`/api/runs/${encodeURIComponent(id)}`);
    if (state.runId !== requested) return;
    state.run = run.run || run;
    state.presentedRunId = requested;
    if (firstPresentation && ["completed", "complete", "succeeded", "success"].includes(state.run.state)) setStage("result");
    state.lastObserved = new Date().toISOString();
    const recorded = state.run.updated_at || state.run.observed_at || state.run.events?.at(-1)?.observed_at;
    $("#observed").textContent = `Last read ${time(state.lastObserved)}${recorded ? ` · record ${time(recorded)}` : ""}`;
    $("#observed").title = $("#observed").textContent;
    const identity = `${state.run.id}:${state.run.state}:${state.run.error ? json(state.run.error) : ""}`;
    if (identity !== state.identity) {
      state.identity = identity;
      const error = state.run.error ? ` · ${json(state.run.error)}` : "";
      notice(`${state.run.id} · ${status(state.run.state)}${error}`, Boolean(state.run.error));
    }
    renderLanes(); renderControls();
  }
  async function loadWorkspace(initial = false) {
    const restoreSelection = initial || !state.initialized;
    state.workspaceStatus = "loading";
    let workspace;
    try { workspace = await API.get("/api/workspace"); } catch (error) { state.workspaceStatus = "failed"; renderControls(); renderLanes(); throw error; }
    state.workspace = workspace;
    state.workspaceStatus = "ready";
    if (typeof workspace.question === "string") { const useTemplate = !$("#question").value.trim() || Object.values(QUESTIONS).includes($("#question").value); QUESTIONS["en-US"] = workspace.question; if (useTemplate) $("#question").value = workspace.question; }
    if (!state.initialized) {
      let selected;
      try { selected = JSON.parse(stored("cortrix.demo.input_ids") || "null"); } catch { selected = null; }
      state.selected = new Set(Array.isArray(selected) ? selected.filter((id) => workspace.files.some((file) => file.id === id)) : workspace.files.filter((file) => file.default && (!(file.locale || file.language) || (file.locale || file.language) === $("#language").value)).map((file) => file.id));
      state.initialized = true;
    }
    if (restoreSelection) {
      const requested = new URLSearchParams(location.search).get("run") || stored("cortrix.demo.run_id");
      state.runId = workspace.runs?.some((run) => run.id === requested) ? requested : workspace.current_run_id || workspace.runs?.[0]?.id || "";
      if (state.runId) await loadRun(state.runId);
      else notice(workspace.runtime_ready ? "Source documents are ready. Select files and start the run to ingest the current input." : "The RC2 runtime is being prepared. You can select, upload, and preview source documents now.");
    }
    renderHistory(); renderControls(); renderLanes();
    if ($("#files-dialog").open) renderFileList();
  }
  async function refresh(initial = false) {
    if (state.refreshing) return;
    state.refreshing = true;
    try { await loadWorkspace(initial); if (!initial && state.runId) await loadRun(state.runId); } catch (error) { showError(error); } finally { state.refreshing = false; }
  }
  function schedulePoll() {
    clearTimeout(state.poll);
    state.poll = setTimeout(async () => {
      if (!state.refreshing) {
        state.refreshing = true;
        try { if (state.runId) await loadRun(state.runId); if (++state.pollCount % 4 === 0) await loadWorkspace(); } catch (error) { showError(error); } finally { state.refreshing = false; }
      }
      schedulePoll();
    }, 1500);
  }
  async function mutate(action) {
    if (state.busy) return;
    state.busy = true; renderControls();
    try { await action(); } catch (error) { showError(error); } finally { state.busy = false; renderControls(); }
  }
  function confirmAction(title, body, label, action) {
    $("#confirm-title").textContent = title;
    $("#confirm-body").innerHTML = body;
    $("#confirm-action").textContent = label;
    $("#confirm-action").onclick = () => { $("#confirm-dialog").close(); mutate(action); };
    $("#confirm-dialog").showModal();
  }
  function encodeFile(file) { return new Promise((resolve, reject) => { const reader = new FileReader(); reader.onload = () => resolve(String(reader.result).split(",", 2)[1]); reader.onerror = () => reject(new Error("Failed to read the selected file")); reader.readAsDataURL(file); }); }
  $("#question").value = "";
  $("#question").addEventListener("input", renderControls);
  $("#refresh").onclick = () => refresh(!state.initialized);
  document.querySelectorAll("[data-close]").forEach((button) => { button.onclick = () => document.getElementById(button.dataset.close).close(); });
  $("#consent-info").onclick = () => { const wrapper = $(".consent-wrapper"); wrapper.classList.toggle("open"); $("#consent-info").setAttribute("aria-expanded", String(wrapper.classList.contains("open"))); };
  $("#consent-info").onkeydown = (event) => { if (event.key === "Escape") { $(".consent-wrapper").classList.remove("open"); $("#consent-info").setAttribute("aria-expanded", "false"); $("#consent-info").blur(); } };
  $("#manage-files").onclick = () => { renderFileList(); if (!state.previewId && visibleFiles().length) preview(visibleFiles()[0].id); $("#files-dialog").showModal(); };
  $("#file-list").addEventListener("change", (event) => { const input = event.target.closest("[data-file-id]"); if (!input) return; input.checked ? state.selected.add(input.dataset.fileId) : state.selected.delete(input.dataset.fileId); persistSelection(); renderFileList(); renderControls(); if (!state.run) renderLanes(); });
  $("#file-list").addEventListener("click", (event) => { const button = event.target.closest("[data-preview-id]"); if (button) preview(button.dataset.previewId); });
  $("#select-visible").onclick = () => { visibleFiles().forEach((file) => state.selected.add(file.id)); persistSelection(); renderFileList(); renderControls(); if (!state.run) renderLanes(); };
  $("#select-none").onclick = () => { state.selected.clear(); persistSelection(); renderFileList(); renderControls(); if (!state.run) renderLanes(); };
  $("#language").onchange = () => { state.workspace?.files.filter((file) => file.default).forEach((file) => { if (!(file.locale || file.language) || (file.locale || file.language) === $("#language").value) state.selected.add(file.id); else state.selected.delete(file.id); }); if (!$("#question").value.trim() || Object.values(QUESTIONS).includes($("#question").value)) $("#question").value = QUESTIONS[$("#language").value] || ""; persistSelection(); renderControls(); if (!state.run) renderLanes(); };
  $("#mode").onchange = () => { renderControls(); if (!state.run) renderLanes(); };
  $("#history").onchange = async () => { stopReview(); state.runId = $("#history").value; state.run = null; remember("cortrix.demo.run_id", state.runId); if (!state.runId) setStage("input"); else { renderLanes(); renderControls(); } try { await loadRun(state.runId); } catch (error) { showError(error); } };
  $("#upload").onchange = () => mutate(async () => {
    const files = [...$("#upload").files];
    for (const file of files) { notice(`Receiving source: ${file.name}`); const response = await API.post("/api/files", { name: file.name, content_base64: await encodeFile(file) }); const saved = response.file || response; if (saved.id) state.selected.add(saved.id); }
    $("#upload").value = ""; persistSelection(); await loadWorkspace(); notice(`Received ${files.length} source documents. Selected content is ingested only after a run starts.`);
  });
  $("#start").onclick = () => mutate(async () => {
    if (state.workspace?.runtime_ready !== true) { notice("The RC2 runtime is being prepared; no run was created."); return; }
    const body = { input_ids: [...state.selected].sort(), question: $("#question").value.trim(), locale: $("#language").value, mode: $("#mode").value, external_call_authorized: true };
    body.idempotency_key = requestIdentity(body);
    const response = await API.post("/api/runs", body);
    const run = response.run || response;
    if (!run.id) throw new Error("Missing run ID in create response");
    try { sessionStorage.removeItem("cortrix.demo.pending_run"); } catch { /* The confirmed response is sufficient for the current page. */ }
    stopReview(); state.runId = run.id; state.run = run; state.presentedRunId = run.id; setStage("input"); remember("cortrix.demo.run_id", run.id); notice(`Created run ${run.id}. Waiting for live execution records.`); await refresh();
  });
  $("#cancel").onclick = () => { const id = state.runId; confirmAction("Stop the current run", `<p>Run: ${esc(id)}</p><p>Stop future scheduling and retain completed steps and source documents. Model requests already sent may still complete and incur charges; the server's reconciliation determines the final state.</p>`, "Confirm stop", async () => { await API.post(`/api/runs/${encodeURIComponent(id)}/cancel`); if (state.runId === id) await loadRun(id); }); };
  $("#resume").onclick = () => mutate(async () => { const id = state.runId; await API.post(`/api/runs/${encodeURIComponent(id)}/resume`); if (state.runId === id) await loadRun(id); });
  $("#cleanup").onclick = () => {
    const id = state.runId;
    confirmAction("Clean up generated data for this run", `<p>Only clean up selected run <strong>${esc(id)}</strong><br>Started: ${esc(time(state.run?.created_at))}</p><ul><li>Remove parsed copies, chunks, vectors, indexes, PG data, and the Cortrix namespace.</li><li>Remove query results, business results, model responses, display caches, and content-bearing logs for this run, including data derived from uploaded source copies.</li><li><strong>Keep default source documents, files on the operator's computer, and uploaded source copies already received by the demo.</strong></li><li>Keep the minimum cleanup receipt and cost ledger. Accumulated cost is not reset, and other runs are unaffected.</li></ul><p>If work is still in progress, the server stops future scheduling, reconciles dispatched work, and then cleans up.</p>`, "Confirm cleanup", async () => { await API.post(`/api/runs/${encodeURIComponent(id)}/cleanup`); if (state.runId === id) await loadRun(id); await loadWorkspace(); });
  };
  document.querySelectorAll("[data-stage]").forEach((button) => { button.onclick = () => setStage(button.dataset.stage); button.onkeydown = (event) => { const current = STAGES.indexOf(button.dataset.stage); const next = event.key === "ArrowRight" ? (current + 1) % STAGES.length : event.key === "ArrowLeft" ? (current + STAGES.length - 1) % STAGES.length : event.key === "Home" ? 0 : event.key === "End" ? STAGES.length - 1 : -1; if (next >= 0) { event.preventDefault(); setStage(STAGES[next]); $(`#tab-${STAGES[next]}`).focus(); } }; });
  $("#review").onclick = () => { if (state.review) { stopReview(); notice("Replay paused. The original run state and records remain unchanged."); return; } let index = 0; setStage(STAGES[index], true); notice("Replaying recorded stages. This only changes the view and does not start a new run."); $("#review").textContent = "Pause replay"; state.review = setInterval(() => { index += 1; if (index >= STAGES.length) { stopReview(); return; } setStage(STAGES[index], true); }, 3500); };
  $("#lanes").addEventListener("click", (event) => { const button = event.target.closest("[data-code-file]"); if (button) openCode(button); });
  renderControls(); renderLanes(); refresh(true).finally(schedulePoll);
})();
