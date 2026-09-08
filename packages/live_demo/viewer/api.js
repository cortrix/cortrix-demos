"use strict";

(() => {
  for (const key of ["cortrix.demo.token", "cortrix.demo.csrf"]) {
    try { sessionStorage.removeItem(key); } catch { /* Legacy credentials are never read or reused. */ }
  }
  let csrf = "";
  let sessionRequest = null;
  async function ensureCsrf() {
    if (csrf) return csrf;
    if (!sessionRequest) {
      sessionRequest = request("/api/session").then((body) => {
        if (body.access_mode !== "loopback_operator" || typeof body.csrf !== "string" || !body.csrf) throw new Error("Invalid local session response");
        csrf = body.csrf;
        return csrf;
      }).finally(() => { sessionRequest = null; });
    }
    return sessionRequest;
  }
  async function request(path, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set("Accept", "application/json");
    if (options.method === "POST") {
      headers.set("Content-Type", "application/json");
      headers.set("X-CSRF-Token", await ensureCsrf());
    }
    const response = await fetch(path, { ...options, headers, cache: "no-store", credentials: "same-origin" });
    const body = await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) csrf = "";
      const detail = body.error?.message || body.error || body.detail || body.message || `HTTP ${response.status}`;
      const error = new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      error.status = response.status;
      error.detail = body;
      error.method = options.method || "GET";
      throw error;
    }
    return body;
  }
  window.DemoAPI = {
    get: (path) => request(path),
    post: (path, body = {}) => request(path, { method: "POST", body: JSON.stringify(body) }),
  };
})();
