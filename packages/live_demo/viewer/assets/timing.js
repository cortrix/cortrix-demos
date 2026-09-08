"use strict";

(() => {
  const TERMINAL_SUFFIXES = ["completed", "failed", "cancelled", "canceled", "paused", "interrupted"];
  const STEP_LABELS = {
    namespace_prepare: "Prepare isolated namespace",
    documents_ingest: "Receive and process sources",
    query_anchor_ingest: "Generate question anchor",
    vectors_export: "Export source and question vectors",
    pg_write: "Write to PostgreSQL and confirm readiness",
    enrichment_wait: "Wait for enrichment readiness",
    query_vector_read: "Read the stored question vector",
    hybrid_retrieve: "Fuse vector and lexical candidates",
    pg_search: "PostgreSQL ranking and filtering",
    business_resolve: "Application selects business answer",
    cortrix_search: "Call Cortrix retrieval",
    evidence_verify: "Application verifies evidence",
    llm_plan_rerank: "LLM expansion and candidate ranking",
    llm_expand: "LLM-assisted query expansion",
    llm_rerank: "LLM-assisted reranking",
  };
  const OWNER_LABELS = { application: "Application", cortrix: "Cortrix", postgresql: "PostgreSQL" };

  function sourceOf(step) { return step.evidence_source || step.source; }
  function terminalState(stage, state) {
    const suffix = TERMINAL_SUFFIXES.find(value => stage.endsWith(`_${value}`));
    return suffix || (TERMINAL_SUFFIXES.includes(state) ? state : null);
  }
  function validDuration(value) { return typeof value === "number" && Number.isFinite(value) && value >= 0; }
  function legacyStart(step) {
    const value = step.started_monotonic_ns;
    return typeof value === "string" && /^\d+$/.test(value) ? value : null;
  }
  function attemptKey(step) {
    if (step.attempt_id !== undefined && step.attempt_id !== null && String(step.attempt_id)) {
      return `id:${String(step.process_instance_id ?? "legacy-process")}:${String(step.attempt_id)}`;
    }
    const started = legacyStart(step);
    return started ? `start:${started}` : null;
  }

  function summarize(steps, operation) {
    const attempts = new Map();
    let invalidRecords = 0;
    let lastState = null;
    for (const step of steps) {
      if (sourceOf(step) !== "controller") continue;
      const terminal = terminalState(String(step.stage || ""), String(step.state || ""));
      if (step.stage !== `${operation}_started` && (!terminal || !String(step.stage || "").startsWith(`${operation}_`))) continue;
      const key = attemptKey(step);
      if (!key) { invalidRecords += 1; continue; }
      if (!attempts.has(key)) attempts.set(key, { started: false, ended: false, duration: null, conflict: false });
      const attempt = attempts.get(key);
      if (step.stage.endsWith("_started")) {
        attempt.started = true;
        lastState = "started";
        continue;
      }
      lastState = terminal;
      const duration = step.duration_ms;
      if (!validDuration(duration)) { attempt.conflict = true; continue; }
      if (attempt.ended && (attempt.duration !== duration || attempt.state !== terminal)) attempt.conflict = true;
      attempt.ended = true;
      attempt.duration = duration;
      attempt.state = terminal;
    }
    const recorded = [...attempts.values()].filter(attempt => attempt.started && attempt.ended && !attempt.conflict);
    const incompleteAttempts = attempts.size - recorded.length + invalidRecords;
    return {
      duration_ms: recorded.reduce((total, attempt) => total + attempt.duration, 0),
      complete: recorded.length > 0 && incompleteAttempts === 0,
      recorded_attempts: recorded.length,
      incomplete_attempts: incompleteAttempts,
      last_state: lastState,
      source: "controller_top_level_attempts",
    };
  }

  function summarizeBusinessSteps(steps, operation) {
    const attempts = new Map();
    const operations = Array.isArray(operation) ? operation : [operation];
    for (const step of steps) {
      if (sourceOf(step) !== "business_step" || step.timing_scope !== "step" || !operations.includes(step.operation)) continue;
      const stage = String(step.stage || "");
      if (stage !== "business_step_started" && !terminalState(stage, String(step.state || ""))) continue;
      const stepId = String(step.step_id || "");
      const key = attemptKey(step);
      if (!stepId || !key) continue;
      const compound = `${step.operation}|${stepId}|${key}`;
      if (!attempts.has(compound)) attempts.set(compound, { step_id: stepId, operation: step.operation, owner: step.owner, started: false, ended: false, duration_ms: null, state: "unknown", conflict: false });
      const attempt = attempts.get(compound);
      if (stage === "business_step_started") {
        attempt.started = true;
        attempt.state = step.state || "running";
      } else {
        const terminal = terminalState(stage, String(step.state || ""));
        if (!validDuration(step.duration_ms)) attempt.conflict = true;
        if (attempt.ended && (attempt.duration_ms !== step.duration_ms || attempt.state !== terminal)) attempt.conflict = true;
        attempt.ended = true;
        attempt.duration_ms = step.duration_ms;
        attempt.state = terminal;
      }
    }
    const grouped = new Map();
    for (const attempt of attempts.values()) {
      const groupKey = `${attempt.operation}|${attempt.step_id}`;
      if (!grouped.has(groupKey)) grouped.set(groupKey, { step_id: attempt.step_id, operation: attempt.operation, label: STEP_LABELS[attempt.step_id] || attempt.step_id, owner: attempt.owner, owner_label: OWNER_LABELS[attempt.owner] || attempt.owner || "Unspecified", duration_ms: 0, recorded_attempts: 0, incomplete_attempts: 0, state: attempt.state });
      const item = grouped.get(groupKey);
      item.state = attempt.state;
      if (attempt.started && attempt.ended && !attempt.conflict && validDuration(attempt.duration_ms)) {
        item.duration_ms += attempt.duration_ms;
        item.recorded_attempts += 1;
      } else item.incomplete_attempts += 1;
    }
    return [...grouped.values()].map(item => ({ ...item, complete: item.recorded_attempts > 0 && item.incomplete_attempts === 0 }));
  }
  const api = { summarize, summarizeBusinessSteps, STEP_LABELS, OWNER_LABELS };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else window.DemoTiming = api;
})();
