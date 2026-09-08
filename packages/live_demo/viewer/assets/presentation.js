"use strict";

(() => {
  const COMMON_RESPONSIBILITY_IDS = new Set(["necessary_shared_engine", "shared_business_resolution", "harness_shared_adapter"]);
  const PRIMARY_RESPONSIBILITY_ORDER = {
    a0: ["a0_vector_first_policy", "postgresql_foundation"],
    a1: ["application_llm_assist", "postgresql_foundation", "current_version_pg_filter", "current_version_resolution"],
    pg: ["application_llm_assist", "postgresql_foundation", "current_version_pg_filter", "current_version_resolution"],
    b: ["cortrix_full_stack_adapter", "current_version_resolution"],
  };
  function displayValue(value) {
    if (value === null || value === undefined || value === "") return "Not provided";
    if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
    try { return JSON.stringify(value); } catch { return "Unrenderable structured value"; }
  }

  function identity(item) {
    return item?.document_id ?? item?.doc_id ?? item?.id ?? item?.source_document_id ?? null;
  }

  function selectRanking(ranking, selectedSource) {
    if (!Array.isArray(ranking)) return [];
    const selectedIdentity = selectedSource && typeof selectedSource === "object" ? identity(selectedSource) : selectedSource;
    const selected = ranking.find(item => item && typeof item === "object" && (item.adopted === true || item.selected === true || (selectedIdentity && identity(item) === selectedIdentity)));
    const contrast = ranking.find(item => item !== selected && item && typeof item === "object");
    return [selected, contrast].filter(Boolean);
  }

  function explainResult(pathKey, outcome, peers) {
    if (!outcome || outcome.field === null || outcome.field === undefined || outcome.field === "") return "No explainable business answer is available yet.";
    if (outcome.complete === false) return "This path has a candidate, but verification is still incomplete.";
    const lifecycle = String(outcome.lifecycle || "").toLowerCase();
    const a0Explanation = lifecycle === "current" ? "The first vector result is current; this path did not apply version filtering." : ["superseded", "historical", "outdated"].includes(lifecycle) ? "The first vector result is historical; this path did not apply version filtering." : "The first vector result returned a candidate whose version state is still unconfirmed.";
    const mechanisms = {
      a0: a0Explanation,
      a1: outcome.llmAssist ? "The application applied version rules and LLM assistance, then verified the candidate." : "The application applied current-version rules and verified the candidate.",
      pg: outcome.llmAssist ? "The application applied version rules and LLM assistance, then verified the candidate." : "The application performed retrieval, applied current-version rules, and verified the candidate.",
      b: "Cortrix completed processing and retrieval; the application retained current-version and field selection.",
    };
    const comparable = Object.values(peers || {}).filter(item => item && item.complete !== false && item.field !== null && item.field !== undefined && item.field !== "");
    const same = comparable.length > 1 && comparable.every(item => String(item.field) === String(comparable[0].field));
    const agreement = same ? ` This run's ${comparable.length === 3 ? "three paths" : "comparable paths"} returned the same answer.` : "";
    return `${mechanisms[pathKey] || "The business result was verified."}${agreement}`;
  }

  function responsibilityGroups(items, pathKey) {
    const common = items.filter(item => COMMON_RESPONSIBILITY_IDS.has(item.id));
    const order = PRIMARY_RESPONSIBILITY_ORDER[pathKey] || [];
    const distinct = items.filter(item => !COMMON_RESPONSIBILITY_IDS.has(item.id)).sort((left, right) => {
      const leftIndex = order.indexOf(left.id);
      const rightIndex = order.indexOf(right.id);
      return (leftIndex < 0 ? order.length : leftIndex) - (rightIndex < 0 ? order.length : rightIndex);
    });
    return {
      primary: distinct.length ? distinct : items,
      common,
      distinct_lines: distinct.reduce((total, item) => total + (Number.isInteger(item.code_lines) ? item.code_lines : 0), 0),
      common_lines: common.reduce((total, item) => total + (Number.isInteger(item.code_lines) ? item.code_lines : 0), 0),
    };
  }

  const api = { displayValue, identity, selectRanking, explainResult, responsibilityGroups };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else window.DemoPresentation = api;
})();
