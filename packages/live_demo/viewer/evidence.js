"use strict";

(() => {
  const $ = (selector) => document.querySelector(selector);
  const API = window.DemoAPI;
  const items = [];
  let runId = new URLSearchParams(location.search).get("run") || "";
  const pathId = new URLSearchParams(location.search).get("path") || "";
  let selected = "manifest";
  try { selected = decodeURIComponent(location.hash.slice(1)) || "manifest"; } catch { selected = "manifest"; }
  const stringify = (value) => typeof value === "string" ? value : JSON.stringify(value, null, 2);
  const routeQuery = () => `?run=${encodeURIComponent(runId)}${pathId ? `&path=${encodeURIComponent(pathId)}` : ""}`;
  function select(name) {
    const basename = name.replace(/^artifacts\//, "");
    const item = items.find((entry) => entry.name === name || entry.name === basename) || items.find((entry) => entry.name.endsWith(name)) || items[0];
    if (!item) return;
    selected = item.name;
    $("#artifact-title").textContent = item.title || item.name;
    $("#artifact-content").textContent = stringify(item.content) ?? "No content was provided.";
    $("#artifact-content").scrollTop = 0;
    document.querySelectorAll(".artifact-button").forEach((button) => button.setAttribute("aria-selected", String(button.dataset.name === selected)));
    history.replaceState(null, "", `${location.pathname}${routeQuery()}#${encodeURIComponent(selected)}`);
  }
  async function load() {
    $("#refresh-evidence").disabled = true;
    try {
      if (!runId) {
        const workspace = await API.get("/api/workspace");
        runId = workspace.current_run_id || workspace.runs?.[0]?.id || "";
      }
      $("#back-link").href = `index.html${routeQuery()}`;
      const [evidence, code] = await Promise.all([runId ? API.get(`/api/runs/${encodeURIComponent(runId)}/evidence`) : Promise.resolve(null), API.get("/api/code").catch((error) => ({ error: error.message }))]);
      items.length = 0;
      if (evidence) items.push({ name: "manifest", title: "Run manifest", content: evidence.manifest ?? { status: "not_provided" } });
      for (const artifact of evidence?.artifacts || []) items.push({ name: artifact.name, content: artifact.content });
      items.push({ name: "code", title: "Complete source counts and method", content: code });
      const list = $("#artifact-list");
      list.replaceChildren();
      for (const item of items) { const button = document.createElement("button"); button.className = "artifact-button"; button.dataset.name = item.name; button.textContent = item.title || item.name; button.setAttribute("aria-selected", String(item.name === selected)); button.onclick = () => select(item.name); list.append(button); }
      select(selected);
      $("#evidence-status").textContent = `${runId || "No run selected · Static source counts only"} · Read at ${new Date().toLocaleString("en-US", { hour12: false })} · Source records and code can be reviewed independently here`;
    } catch (error) {
      $("#evidence-status").textContent = `Evidence is not available: ${error.message}`;
      $("#artifact-content").textContent = "The selected run remains unchanged. Refresh only reloads evidence; it never starts a run.";
    } finally { $("#refresh-evidence").disabled = false; }
  }
  $("#refresh-evidence").onclick = load;
  window.addEventListener("hashchange", () => { try { select(decodeURIComponent(location.hash.slice(1))); } catch { select("manifest"); } });
  load();
})();
