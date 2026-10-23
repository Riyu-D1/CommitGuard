/**
 * CommitGuard backend adapter — the ONLY module allowed to talk to the backend.
 * Vanilla JS, no dependencies. Usable via <script src> (exposes
 * window.CommitGuardAdapter) or importable later.
 *
 * @typedef {Object} Violation
 * @property {string} category
 * @property {"LOW"|"MEDIUM"|"HIGH"|"CRITICAL"} severity
 * @property {string} issue
 * @property {string} correction
 * @property {string|null} suggested_rewrite
 * @property {{brain_key:string, expected:*, found:*}} evidence
 * @property {{text:string, start:number, end:number}} [span]
 *
 * @typedef {Object} VerifyResponse
 * @property {boolean} ok
 * @property {"CLEAN"|"VIOLATION_DETECTED"} status
 * @property {"LOW"|"MEDIUM"|"HIGH"} risk_level
 * @property {Violation[]} violations
 * @property {string|null} suggested_rewrite
 * @property {{engine:string, checks_run:number, latency_ms:number}} meta
 *
 * @typedef {Object} ActionResponse
 * @property {boolean} ok
 * @property {boolean} success
 * @property {string} audit_log_id
 * @property {string} message
 */
(function (global) {
  const BASE_URL = "http://127.0.0.1:8000";

  async function request(path, method, body) {
    try {
      const res = await fetch(BASE_URL + path, {
        method: method || "GET",
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : null,
      });
      if (!res.ok) return { ok: false, error: "HTTP_" + res.status };
      const data = await res.json();
      return Object.assign({ ok: true }, data);
    } catch (e) {
      return { ok: false, error: "BACKEND_OFFLINE" };
    }
  }

  function debounce(fn, ms) {
    let t = null;
    return function (...args) {
      clearTimeout(t);
      t = setTimeout(() => fn.apply(this, args), ms);
    };
  }

  global.CommitGuardAdapter = {
    BASE_URL,
    debounce,
    verifyContext: (text, contextType) =>
      request("/verify-context", "POST", { text, context_type: contextType }),
    executeAction: (actionType, payload) =>
      request("/execute-action", "POST", { action_type: actionType, payload }),
    getBrain: () => request("/brain"),
    getScenarios: () => request("/scenarios"),
    getAuditLog: (limit) => request("/audit-log?limit=" + (limit || 20)),
    getHealth: () => request("/health"),
  };
})(typeof window !== "undefined" ? window : globalThis);
