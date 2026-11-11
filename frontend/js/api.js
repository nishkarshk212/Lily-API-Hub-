/**
 * Core HTTP API client, cross-origin URL/token helpers, XSS escaping, formatting, and toast utilities.
 */

const TOKEN_STORAGE_KEY = "beta_session_token";
const API_OVERRIDE_KEY = "beta_api_base_override";

export function getApiBase() {
  const configured = String(window.__APP_CONFIG__?.API_BASE_URL || "").trim().replace(/\/+$/, "");
  if (configured) return configured;
  try {
    const override = String(sessionStorage.getItem(API_OVERRIDE_KEY) || "").trim().replace(/\/+$/, "");
    if (override) return override;
  } catch {
    // Ignore storage access errors in restricted contexts
  }
  return "";
}

export function setApiBaseOverride(url) {
  try {
    if (!url) {
      sessionStorage.removeItem(API_OVERRIDE_KEY);
      return;
    }
    const parsed = new URL(url);
    if (parsed.protocol === "https:" || parsed.protocol === "http:") {
      sessionStorage.setItem(API_OVERRIDE_KEY, parsed.origin);
    }
  } catch {
    // Ignore invalid URL overrides
  }
}

export function apiUrl(path) {
  if (!path) return getApiBase() || "";
  if (/^https?:\/\//i.test(path)) return path;
  const base = getApiBase();
  return base ? `${base}${path.startsWith("/") ? path : "/" + path}` : path;
}

export function getAuthToken() {
  try {
    return sessionStorage.getItem(TOKEN_STORAGE_KEY) || "";
  } catch {
    return "";
  }
}

export function setAuthToken(token) {
  try {
    if (token) sessionStorage.setItem(TOKEN_STORAGE_KEY, token);
  } catch {
    // Ignore
  }
}

export function clearAuthToken() {
  try {
    sessionStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    // Ignore
  }
}

export function getBrand(state) {
  const ov = state?.overview || {};
  const appName = ov.brand || "Beta API Hub";
  const companyName = ov.company || "Sonic Network";
  const brandLetter = (ov.brand_letter || appName.slice(0, 1) || "A").toUpperCase();
  const supportEmail = ov.support_email || "support@sonicnetwork.dev";
  const keyPrefixLive = ov.key_prefix_live || "beta_live_";
  const keyPrefixTest = ov.key_prefix_test || "beta_test_";
  return { appName, companyName, brandLetter, supportEmail, keyPrefixLive, keyPrefixTest };
}

export function esc(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

export function formatInr(paise) {
  const num = Number(paise || 0) / 100;
  if (num === 0) return "₹0";
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: num % 1 === 0 ? 0 : 2,
  }).format(num);
}

export function formatNum(n) {
  return new Intl.NumberFormat("en-IN").format(Number(n || 0));
}

export function formatDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function daysRemaining(expiresIso) {
  if (!expiresIso) return 0;
  const diff = new Date(expiresIso).getTime() - Date.now();
  return Math.max(0, Math.ceil(diff / (1000 * 60 * 60 * 24)));
}

export function showToast(message, type = "info", duration = 4200) {
  const root = document.getElementById("toast-root");
  if (!root) return;
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  const icon = type === "success" ? "✓" : type === "error" ? "!" : "i";
  el.innerHTML = `<span class="badge badge-${type === "error" ? "danger" : type === "success" ? "success" : "info"}">${icon}</span><div style="flex:1">${esc(message)}</div>`;
  root.appendChild(el);
  setTimeout(() => {
    el.style.opacity = "0";
    el.style.transform = "translateY(8px)";
    el.style.transition = "all 0.2s ease";
    setTimeout(() => el.remove(), 220);
  }, duration);
}

export async function copyToClipboard(text, label = "Copied to clipboard") {
  try {
    await navigator.clipboard.writeText(text);
    showToast(label, "success", 2400);
  } catch {
    showToast("Copy failed — select and copy manually.", "error");
  }
}

export function highlightJson(data) {
  const raw = typeof data === "string" ? data : JSON.stringify(data, null, 2);
  const safe = esc(raw);
  return safe.replace(
    /(&quot;(?:\\.|[^&])*?&quot;)(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?/g,
    (match, quoted, colon, boolOrNull) => {
      if (quoted) {
        if (colon) return `<span class="json-key">${quoted}</span>${colon}`;
        return `<span class="json-str">${quoted}</span>`;
      }
      if (boolOrNull === "null") return `<span class="json-null">${match}</span>`;
      if (boolOrNull) return `<span class="json-bool">${match}</span>`;
      return `<span class="json-num">${match}</span>`;
    }
  );
}

export function statusBadge(status) {
  const s = String(status || "").toLowerCase();
  if (["active", "successful", "resolved", "operational"].includes(s)) {
    return `<span class="badge badge-success">${esc(status)}</span>`;
  }
  if (["pending", "open"].includes(s)) {
    return `<span class="badge badge-warning">${esc(status)}</span>`;
  }
  if (["failed", "revoked", "expired", "suspended", "cancelled", "refunded"].includes(s)) {
    return `<span class="badge badge-danger">${esc(status)}</span>`;
  }
  return `<span class="badge badge-neutral">${esc(status)}</span>`;
}

async function request(method, url, body = undefined) {
  const opts = {
    method,
    credentials: "include",
    headers: {},
  };
  const token = getAuthToken();
  if (token) {
    opts.headers["Authorization"] = `Bearer ${token}`;
  }
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const resp = await fetch(apiUrl(url), opts);
  const contentType = resp.headers.get("content-type") || "";
  const data = contentType.includes("application/json") ? await resp.json() : await resp.text();
  if (!resp.ok) {
    const errMsg =
      typeof data === "object" && data !== null
        ? data.detail || data.message || JSON.stringify(data)
        : String(data || `Request failed (${resp.status})`);
    const err = new Error(errMsg);
    err.status = resp.status;
    err.data = data;
    throw err;
  }
  return data;
}

export async function openAuthenticatedUrl(path) {
  const opts = { method: "GET", credentials: "include", headers: {} };
  const token = getAuthToken();
  if (token) {
    opts.headers["Authorization"] = `Bearer ${token}`;
  }
  const resp = await fetch(apiUrl(path), opts);
  if (!resp.ok) {
    throw new Error(`Unable to open receipt (HTTP ${resp.status})`);
  }
  const html = await resp.text();
  const blob = new Blob([html], { type: "text/html" });
  const blobUrl = URL.createObjectURL(blob);
  window.open(blobUrl, "_blank", "noopener");
  setTimeout(() => URL.revokeObjectURL(blobUrl), 60000);
}

export const api = {
  get: (url) => request("GET", url),
  post: (url, body) => request("POST", url, body),
  put: (url, body) => request("PUT", url, body),
  patch: (url, body) => request("PATCH", url, body),
  del: (url) => request("DELETE", url),
};

