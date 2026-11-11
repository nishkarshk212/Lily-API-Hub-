/**
 * Separate Admin Portal: Dedicated Admin Login + Full Colorful Control Center.
 */

import { api, esc, formatDate, formatInr, formatNum, getBrand, openAuthenticatedUrl, setAuthToken, showToast, statusBadge } from "../api.js";
import { bindChartTooltips, renderTrafficChart } from "../components/charts.js";
import { openConfirmModal, openPlanEditorModal } from "../components/modals.js";

const SIDEBAR_TABS = [
  { id: "analytics", label: "Platform Analytics", icon: "◈", accent: "#4f46e5", accentEnd: "#7c3aed", bg: "rgba(79,70,229,0.1)" },
  { id: "users", label: "Users & Roles", icon: "◉", accent: "#059669", accentEnd: "#10b981", bg: "rgba(5,150,105,0.1)" },
  { id: "keys", label: "API Keys Vault", icon: "⚿", accent: "#d97706", accentEnd: "#f59e0b", bg: "rgba(217,119,6,0.12)" },
  { id: "plans", label: "Plans & Pricing", icon: "◆", accent: "#7c3aed", accentEnd: "#a855f7", bg: "rgba(124,58,237,0.11)" },
  { id: "payments", label: "Payments & Webhooks", icon: "₹", accent: "#0891b2", accentEnd: "#06b6d4", bg: "rgba(8,145,178,0.11)" },
  { id: "requests", label: "Request Monitor", icon: "▤", accent: "#e11d48", accentEnd: "#f43f5e", bg: "rgba(225,29,72,0.1)" },
  { id: "master", label: "Master API Config", icon: "⚡", accent: "#2563eb", accentEnd: "#0284c7", bg: "rgba(37,99,235,0.1)" },
  { id: "branding", label: "Site & API Branding", icon: "✦", accent: "#c026d3", accentEnd: "#ec4899", bg: "rgba(192,38,211,0.1)" },
  { id: "governance", label: "Support, Audit & Outbox", icon: "🛡", accent: "#0d9488", accentEnd: "#14b8a6", bg: "rgba(13,148,136,0.1)" },
];

export function renderAdminLoginPage(state, handlers) {
  const root = document.getElementById("app-root");
  if (!root) return;
  const brand = getBrand(state);

  root.innerHTML = `
    <div class="admin-login-shell">
      <div class="admin-login-card">
        <div class="admin-login-banner">
          <span class="admin-pill" style="margin-bottom:12px;">
            <span class="admin-pill-dot"></span>
            ${esc(brand.companyName)} · Restricted Access
          </span>
          <h1 style="margin:0 0 6px;font-size:24px;font-weight:800;">${esc(brand.appName)} Admin Portal</h1>
          <p style="margin:0;font-size:13.5px;color:rgba(226,232,240,0.88);">
            Full platform control for pricing, live API requests, customer accounts, branding & Master Gateway.
          </p>
        </div>
        <div class="admin-login-body">
          <form id="admin-login-form">
            <div id="adm-login-err" style="display:none;margin-bottom:12px;padding:10px 12px;border-radius:10px;background:var(--danger-bg);color:var(--danger);font-size:13px;"></div>
            <div class="field">
              <label>Administrator Email</label>
              <input class="input" type="email" id="adm-email" required placeholder="${esc(brand.supportEmail)}" />
            </div>
            <div class="field">
              <label>Password</label>
              <input class="input" type="password" id="adm-password" required placeholder="••••••••" />
            </div>
            <button type="submit" class="btn btn-primary" style="width:100%;background:linear-gradient(135deg,#4f46e5,#7c3aed);border-color:transparent;" id="adm-login-btn">
              Sign In to Admin Command Center
            </button>
          </form>
        </div>
      </div>
    </div>
  `;

  document.getElementById("admin-login-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const errBox = document.getElementById("adm-login-err");
    const btn = document.getElementById("adm-login-btn");
    errBox.style.display = "none";
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner-sm"></span> Authenticating...`;
    try {
      const res = await api.post("/api/admin/login", {
        email: document.getElementById("adm-email").value,
        password: document.getElementById("adm-password").value,
      });
      if (res.access_token) setAuthToken(res.access_token);
      state.user = res.user;
      showToast("Administrator authenticated.", "success");
      handlers.navigate("#admin");
    } catch (err) {
      errBox.textContent = err.message;
      errBox.style.display = "block";
      btn.disabled = false;
      btn.textContent = "Sign In to Admin Command Center";
    }
  });
}

function renderAnalyticsTab(analytics) {
  const kpis = analytics.kpis || {};
  const cards = [
    {
      label: "Verified Revenue",
      value: kpis.total_revenue_display || "₹0",
      sub: `${formatNum(kpis.active_subscriptions)} active subscriptions`,
      icon: "₹",
      color: "#059669",
      soft: "rgba(16,185,129,0.14)",
      grad: "linear-gradient(90deg, #059669, #34d399)",
    },
    {
      label: "Registered Users",
      value: formatNum(kpis.total_users),
      sub: `${formatNum(kpis.suspended_users)} suspended accounts`,
      icon: "◉",
      color: "#4f46e5",
      soft: "rgba(99,102,241,0.14)",
      grad: "linear-gradient(90deg, #4f46e5, #818cf8)",
    },
    {
      label: "Active API Keys",
      value: formatNum(kpis.active_api_keys),
      sub: "Linked to Master Gateway",
      icon: "⚿",
      color: "#d97706",
      soft: "rgba(245,158,11,0.15)",
      grad: "linear-gradient(90deg, #d97706, #fbbf24)",
    },
    {
      label: "Gateway Requests (24h)",
      value: formatNum(kpis.requests_24h),
      sub: `${formatNum(kpis.total_requests)} total · ${kpis.avg_latency_ms || 0} ms avg`,
      icon: "⚡",
      color: "#e11d48",
      soft: "rgba(244,63,94,0.14)",
      grad: "linear-gradient(90deg, #e11d48, #fb7185)",
    },
  ];

  return `
    <div class="admin-kpi-grid">
      ${cards
        .map(
          (c) => `
        <div class="admin-kpi-card" style="--kpi-color:${c.color};--kpi-soft:${c.soft};--kpi-gradient:${c.grad};">
          <div class="admin-kpi-top">
            <span class="admin-kpi-label">${esc(c.label)}</span>
            <span class="admin-kpi-badge">${c.icon}</span>
          </div>
          <div class="admin-kpi-value">${esc(c.value)}</div>
          <div class="admin-kpi-sub">${esc(c.sub)}</div>
        </div>`
        )
        .join("")}
    </div>

    <div class="admin-panel" style="--panel-accent:#4f46e5;">
      <div class="admin-panel-head">
        <div>
          <h3>7-Day Gateway Traffic & Error Overview</h3>
          <p style="margin:3px 0 0;font-size:12.5px;color:var(--text-muted);">Live hourly aggregation of authorized calls and blocked/error responses</p>
        </div>
        <button class="btn btn-secondary btn-sm" id="adm-refresh-all">↻ Refresh Data</button>
      </div>
      ${renderTrafficChart(analytics.series, "requests", "errors", 220)}
    </div>

    <div class="two-col">
      <div class="admin-panel" style="--panel-accent:#0ea5e9;">
        <div class="admin-panel-head"><h3>Top Endpoints</h3></div>
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>Endpoint</th><th>Hits</th><th>Avg Latency</th></tr></thead>
            <tbody>
              ${
                (analytics.top_endpoints || []).length === 0
                  ? `<tr><td colspan="3" style="text-align:center;color:var(--text-muted);">No gateway traffic yet.</td></tr>`
                  : (analytics.top_endpoints || [])
                      .map((e) => `<tr><td class="mono">${esc(e.path)}</td><td><strong>${formatNum(e.hits)}</strong></td><td class="mono">${e.avg_ms} ms</td></tr>`)
                      .join("")
              }
            </tbody>
          </table>
        </div>
      </div>

      <div class="admin-panel" style="--panel-accent:#10b981;">
        <div class="admin-panel-head"><h3>Top API Consumers</h3></div>
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>User Email</th><th>Total Calls</th></tr></thead>
            <tbody>
              ${
                (analytics.top_users || []).length === 0
                  ? `<tr><td colspan="2" style="text-align:center;color:var(--text-muted);">No consumer usage yet.</td></tr>`
                  : (analytics.top_users || [])
                      .map((u) => `<tr><td>${esc(u.email)}</td><td><strong>${formatNum(u.hits)}</strong></td></tr>`)
                      .join("")
              }
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;
}

function renderUsersTab(users, currentUserId, userSearch) {
  const q = userSearch.trim().toLowerCase();
  const filtered = users.filter(
    (u) => !q || u.email.toLowerCase().includes(q) || (u.full_name || "").toLowerCase().includes(q)
  );
  return `
    <div class="admin-panel" style="--panel-accent:#059669;">
      <div class="admin-panel-head">
        <div>
          <h2>User & Role Management</h2>
          <p style="margin:3px 0 0;font-size:12.5px;color:var(--text-muted);">Control developer access, email verification, suspensions, and admin roles.</p>
        </div>
        <input class="input" id="adm-user-search" style="max-width:260px;" placeholder="Filter by email or name..." value="${esc(userSearch)}" />
      </div>
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr><th>User</th><th>Role</th><th>Verified</th><th>Plan</th><th>Keys</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>
            ${
              filtered.length === 0
                ? `<tr><td colspan="7" style="text-align:center;color:var(--text-muted);">No matching users found.</td></tr>`
                : filtered
                    .map(
                      (u) => `
                    <tr>
                      <td><strong>${esc(u.full_name || "—")}</strong><br><span style="font-size:12px;color:var(--text-muted);">${esc(u.email)}</span></td>
                      <td><span class="badge badge-${u.role === "admin" ? "info" : "neutral"}">${esc(u.role)}</span></td>
                      <td>${u.is_email_verified ? `<span class="badge badge-success">Verified</span>` : `<span class="badge badge-warning">Pending</span>`}</td>
                      <td>${esc(u.plan_name)} (${esc(u.subscription_status)})</td>
                      <td>${u.active_keys_count}</td>
                      <td>${u.is_suspended ? `<span class="badge badge-danger">Suspended</span>` : `<span class="badge badge-success">Active</span>`}</td>
                      <td>
                        <div style="display:flex;gap:6px;flex-wrap:wrap;">
                          ${
                            u.id !== currentUserId
                              ? `<button class="btn ${u.is_suspended ? "btn-secondary" : "btn-danger"} btn-sm" data-toggle-suspend="${esc(u.id)}" data-suspended="${u.is_suspended}">${u.is_suspended ? "Activate" : "Suspend"}</button>
                                 <button class="btn btn-secondary btn-sm" data-toggle-role="${esc(u.id)}" data-role="${esc(u.role)}">${u.role === "admin" ? "Make User" : "Make Admin"}</button>`
                              : `<span style="font-size:12px;color:var(--text-muted);">Current Admin</span>`
                          }
                          ${
                            !u.is_email_verified
                              ? `<button class="btn btn-secondary btn-sm" data-verify-user="${esc(u.id)}">Verify Email</button>`
                              : ""
                          }
                        </div>
                      </td>
                    </tr>`
                    )
                    .join("")
            }
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function renderKeysTab(keys, keySearch) {
  const q = keySearch.trim().toLowerCase();
  const filtered = keys.filter(
    (k) =>
      !q ||
      (k.user_email || "").toLowerCase().includes(q) ||
      (k.name || "").toLowerCase().includes(q) ||
      (k.masked_key || "").toLowerCase().includes(q)
  );
  return `
    <div class="admin-panel" style="--panel-accent:#d97706;">
      <div class="admin-panel-head">
        <div>
          <h2>Platform API Keys</h2>
          <p style="margin:3px 0 0;font-size:12.5px;color:var(--text-muted);">Inspect customer key prefixes, Master tags, request volumes, and revoke compromised keys.</p>
        </div>
        <input class="input" id="adm-key-search" style="max-width:260px;" placeholder="Filter by owner, label, prefix..." value="${esc(keySearch)}" />
      </div>
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr><th>Owner</th><th>Label</th><th>Key Preview</th><th>Master Tag</th><th>Requests</th><th>Status</th><th>Action</th></tr></thead>
          <tbody>
            ${
              filtered.length === 0
                ? `<tr><td colspan="7" style="text-align:center;color:var(--text-muted);">No matching API keys found.</td></tr>`
                : filtered
                    .map(
                      (k) => `
                    <tr>
                      <td>${esc(k.user_email)}</td>
                      <td>${esc(k.name)}</td>
                      <td class="mono">${esc(k.masked_key)}</td>
                      <td class="mono" style="font-size:12px;">${esc(k.master_link_tag)}</td>
                      <td>${formatNum(k.total_requests)}</td>
                      <td>${statusBadge(k.status)}</td>
                      <td>
                        ${
                          k.status === "active"
                            ? `<button class="btn btn-danger btn-sm" data-adm-revoke-key="${esc(k.id)}">Revoke</button>`
                            : `<span style="font-size:12px;color:var(--text-muted);">Revoked</span>`
                        }
                      </td>
                    </tr>`
                    )
                    .join("")
            }
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function renderPlansTab(plans) {
  return `
    <div class="admin-panel" style="--panel-accent:#7c3aed;">
      <div class="admin-panel-head">
        <div>
          <h2>Subscription Plans & Pricing</h2>
          <p style="margin:3px 0 0;font-size:12.5px;color:var(--text-muted);">Create tiers, adjust INR pricing, edit daily/monthly quotas & HTTP method ACLs live.</p>
        </div>
        <button class="btn btn-primary btn-sm" id="adm-new-plan">+ Create Plan</button>
      </div>
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr><th>Plan</th><th>Price</th><th>Cycle</th><th>Daily / Monthly</th><th>Rate / Min</th><th>Max Keys</th><th>Methods</th><th>Status</th><th>Actions</th></tr></thead>
          <tbody>
            ${plans
              .map(
                (p) => `
              <tr>
                <td>
                  <strong>${esc(p.name)}</strong> ${p.is_featured ? `<span class="badge badge-info">Featured</span>` : ""}
                  <br><span class="mono" style="font-size:11.5px;color:var(--text-muted);">${esc(p.slug)}</span>
                </td>
                <td><strong>${p.price_paise === 0 ? "Free" : formatInr(p.price_paise)}</strong></td>
                <td>${p.billing_cycle_days}d</td>
                <td>${formatNum(p.daily_request_limit)} / ${formatNum(p.monthly_request_limit)}</td>
                <td>${formatNum(p.rate_limit_per_minute)}/min</td>
                <td>${p.max_api_keys}</td>
                <td class="mono" style="font-size:11.5px;">${esc(p.allowed_methods)}</td>
                <td>${p.is_active ? `<span class="badge badge-success">Active</span>` : `<span class="badge badge-neutral">Inactive</span>`}</td>
                <td>
                  <div style="display:flex;gap:6px;">
                    <button class="btn btn-secondary btn-sm" data-edit-plan="${esc(p.id)}">Edit</button>
                    <button class="btn btn-danger btn-sm" data-del-plan="${esc(p.id)}">Archive</button>
                  </div>
                </td>
              </tr>`
              )
              .join("")}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function renderPaymentsTab(paymentsRes, paymentFilter, paymentSearch) {
  const q = paymentSearch.trim().toLowerCase();
  const filtered = (paymentsRes.payments || []).filter((p) => {
    if (paymentFilter && p.status !== paymentFilter) return false;
    if (!q) return true;
    return (
      (p.receipt_number || "").toLowerCase().includes(q) ||
      (p.user_email || "").toLowerCase().includes(q) ||
      (p.razorpay_order_id || "").toLowerCase().includes(q) ||
      (p.razorpay_payment_id || "").toLowerCase().includes(q)
    );
  });
  const webhooks = paymentsRes.webhooks || [];

  return `
    <div class="admin-panel" style="--panel-accent:#0891b2;">
      <div class="admin-panel-head">
        <h2>Razorpay Payment Tracking</h2>
        <div class="admin-toolbar">
          <input class="input" id="adm-pay-search" style="max-width:220px;" placeholder="Search receipt, email, ID..." value="${esc(paymentSearch)}" />
          <select class="select" id="adm-pay-filter" style="max-width:170px;">
            <option value="">All Statuses</option>
            ${["pending", "successful", "failed", "refunded", "cancelled"]
              .map((s) => `<option value="${s}" ${paymentFilter === s ? "selected" : ""}>${s.toUpperCase()}</option>`)
              .join("")}
          </select>
        </div>
      </div>
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr><th>Receipt</th><th>User</th><th>Plan</th><th>Amount</th><th>Status</th><th>Razorpay IDs</th><th>Verified Via</th><th>Actions</th></tr></thead>
          <tbody>
            ${
              filtered.length === 0
                ? `<tr><td colspan="8" style="text-align:center;color:var(--text-muted);">No matching payments.</td></tr>`
                : filtered
                    .map(
                      (p) => `
                    <tr>
                      <td class="mono">${esc(p.receipt_number)}</td>
                      <td>${esc(p.user_email)}</td>
                      <td>${esc(p.plan_name)}</td>
                      <td><strong>${esc(p.amount_display)}</strong></td>
                      <td>${statusBadge(p.status)}</td>
                      <td class="mono" style="font-size:11px;">O: ${esc(p.razorpay_order_id || "—")}<br>P: ${esc(p.razorpay_payment_id || "—")}</td>
                      <td>${esc(p.verified_via || "—")}</td>
                      <td>
                        <div style="display:flex;gap:6px;flex-wrap:wrap;">
                          <button type="button" class="btn btn-secondary btn-sm" data-adm-receipt="${esc(p.id)}">Receipt</button>
                          ${p.status === "pending" ? `<button class="btn btn-primary btn-sm" data-adm-reconcile="${esc(p.id)}">Reconcile</button>` : ""}
                          ${p.status === "successful" ? `<button class="btn btn-danger btn-sm" data-adm-refund="${esc(p.id)}">Mark Refunded</button>` : ""}
                        </div>
                      </td>
                    </tr>`
                    )
                    .join("")
            }
          </tbody>
        </table>
      </div>
    </div>

    <div class="admin-panel" style="--panel-accent:#06b6d4;">
      <div class="admin-panel-head"><h3>Razorpay Webhook Event Log (Idempotent)</h3></div>
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr><th>Event ID</th><th>Type</th><th>Order ID</th><th>Result</th><th>Timestamp</th></tr></thead>
          <tbody>
            ${
              webhooks.length === 0
                ? `<tr><td colspan="5" style="text-align:center;color:var(--text-muted);">No webhooks received yet.</td></tr>`
                : webhooks
                    .map(
                      (w) => `
                    <tr>
                      <td class="mono" style="font-size:11.5px;">${esc(w.event_id)}</td>
                      <td class="mono">${esc(w.event_type)}</td>
                      <td class="mono">${esc(w.razorpay_order_id || "—")}</td>
                      <td><span class="badge badge-info">${esc(w.processing_result)}</span></td>
                      <td style="font-size:12px;">${formatDate(w.created_at)}</td>
                    </tr>`
                    )
                    .join("")
            }
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function renderRequestsTab(reqsRes, requestStatusFilter, requestSearch) {
  const q = requestSearch.trim().toLowerCase();
  const filtered = (reqsRes.requests || []).filter((r) => {
    if (requestStatusFilter && String(r.status_code) !== requestStatusFilter) return false;
    if (!q) return true;
    return (
      (r.user_email || "").toLowerCase().includes(q) ||
      (r.path || "").toLowerCase().includes(q) ||
      (r.key_prefix || "").toLowerCase().includes(q) ||
      (r.error_code || "").toLowerCase().includes(q)
    );
  });

  return `
    <div class="admin-panel" style="--panel-accent:#e11d48;">
      <div class="admin-panel-head">
        <div>
          <h2>Live API Request Monitor</h2>
          <p style="margin:3px 0 0;font-size:12.5px;color:var(--text-muted);">Filter gateway calls by path, customer email, key prefix, error code, or HTTP status.</p>
        </div>
        <div class="admin-toolbar">
          <input class="input" id="adm-req-search" style="max-width:240px;" placeholder="Filter path, email, error..." value="${esc(requestSearch)}" />
          <select class="select" id="adm-req-filter" style="max-width:170px;">
            <option value="">All HTTP Statuses</option>
            ${["200", "401", "403", "404", "429", "502"]
              .map((s) => `<option value="${s}" ${requestStatusFilter === s ? "selected" : ""}>HTTP ${s}</option>`)
              .join("")}
          </select>
        </div>
      </div>
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr><th>User</th><th>Key</th><th>Method</th><th>Path</th><th>Status</th><th>Latency</th><th>Mode</th><th>Error</th><th>Time</th></tr></thead>
          <tbody>
            ${
              filtered.length === 0
                ? `<tr><td colspan="9" style="text-align:center;color:var(--text-muted);">No matching API requests logged.</td></tr>`
                : filtered
                    .map(
                      (r) => `
                    <tr>
                      <td>${esc(r.user_email)}</td>
                      <td class="mono">${esc(r.key_prefix)}</td>
                      <td><span class="method-pill method-${esc(r.method)}">${esc(r.method)}</span></td>
                      <td class="mono">${esc(r.path)}</td>
                      <td><span class="badge badge-${r.status_code < 400 ? "success" : r.status_code === 429 ? "warning" : "danger"}">${r.status_code}</span></td>
                      <td class="mono">${r.latency_ms} ms</td>
                      <td>${esc(r.gateway_mode)}</td>
                      <td class="mono" style="color:var(--danger);font-size:11.5px;">${esc(r.error_code || "—")}</td>
                      <td style="font-size:12px;">${formatDate(r.created_at)}</td>
                    </tr>`
                    )
                    .join("")
            }
          </tbody>
        </table>
      </div>
    </div>
  `;
}

function renderMasterTab(masterCfg, brand) {
  return `
    <div class="admin-panel" style="--panel-accent:#2563eb;">
      <div class="admin-panel-head">
        <div>
          <h2>Master API & Upstream Gateway Configuration</h2>
          <p style="margin:3px 0 0;font-size:12.5px;color:var(--text-muted);">
            Your Master API Key is encrypted at rest with AES/Fernet and injected ONLY server-side when forwarding customer requests.
          </p>
        </div>
        <button class="btn btn-secondary btn-sm" id="adm-test-upstream">Test Upstream Connection</button>
      </div>

      <form id="master-config-form">
        <div class="two-col">
          <div class="field">
            <label>Gateway Routing Mode</label>
            <select class="select" id="mc-mode">
              <option value="hybrid" ${masterCfg.gateway_mode === "hybrid" ? "selected" : ""}>Hybrid (Built-in ${esc(brand.companyName)} APIs + Proxy Fallback)</option>
              <option value="proxy" ${masterCfg.gateway_mode === "proxy" ? "selected" : ""}>Strict Proxy (Forward all /v1/* to Upstream URL)</option>
              <option value="builtin" ${masterCfg.gateway_mode === "builtin" ? "selected" : ""}>Built-in Only (Serve local ${esc(brand.companyName)} APIs)</option>
            </select>
          </div>
          <div class="field">
            <label>Upstream Timeout (ms)</label>
            <input class="input" type="number" id="mc-timeout" min="500" max="60000" value="${masterCfg.timeout_ms || 10000}" />
          </div>
        </div>

        <div class="field">
          <label>Master Backend Upstream API URL</label>
          <input class="input mono" type="url" id="mc-url" value="${esc(masterCfg.upstream_base_url || "")}" placeholder="https://upstream.example.workers.dev" />
        </div>

        <div class="field">
          <label>Rotate / Set Master API Key (Current fingerprint: <span class="mono" style="color:#2563eb;">${esc(masterCfg.master_key_fingerprint || "Not set")}</span>)</label>
          <input class="input mono" type="password" id="mc-key" placeholder="Leave blank to keep existing encrypted Master API Key" />
        </div>

        <div class="two-col">
          <div class="field"><label>Upstream Auth Header Name</label><input class="input mono" id="mc-header" value="${esc(masterCfg.auth_header_name || "Authorization")}" /></div>
          <div class="field"><label>Upstream Auth Scheme (blank for raw header)</label><input class="input mono" id="mc-scheme" value="${esc(masterCfg.auth_scheme || "Bearer")}" /></div>
        </div>

        <label style="display:flex;align-items:center;gap:8px;margin-bottom:18px;font-size:13.5px;cursor:pointer;">
          <input type="checkbox" id="mc-fwd-ctx" ${masterCfg.forward_user_context_headers !== false ? "checked" : ""} />
          Forward non-sensitive customer context headers (<code>X-Beta-User-Id</code>, <code>X-Beta-Plan-Slug</code>, <code>X-Beta-Key-Id</code>)
        </label>

        <button type="submit" class="btn btn-primary" id="mc-save-btn">Save Master Gateway Config</button>
      </form>
    </div>
  `;
}

function renderBrandingTab(b) {
  return `
    <div class="admin-panel" style="--panel-accent:#c026d3;">
      <div class="admin-panel-head">
        <div>
          <h2>Site & API Branding Control</h2>
          <p style="margin:3px 0 0;font-size:12.5px;color:var(--text-muted);">
            Override <code>.env</code> branding live across the navbar, favicon, landing page, emails, receipts & newly minted API keys.
          </p>
        </div>
        <div class="admin-toolbar">
          <span class="badge ${b.has_db_override ? "badge-info" : "badge-neutral"}">
            ${b.has_db_override ? "Live DB Override Active" : "Using .env Defaults"}
          </span>
          <button type="button" class="btn btn-danger btn-sm" id="br-reset-btn">Reset to .env Defaults</button>
        </div>
      </div>

      <div class="brand-preview-card">
        <div class="brand-preview-logo">
          <div class="brand-preview-tile" id="br-prev-tile">${esc(b.brand_letter || "B")}</div>
          <div>
            <div style="font-size:16px;font-weight:800;" id="br-prev-app">${esc(b.app_name)}</div>
            <div style="font-size:12px;color:#94a3b8;" id="br-prev-company">${esc(b.company_name)} · <span id="br-prev-email">${esc(b.support_email)}</span></div>
          </div>
        </div>
        <div class="brand-preview-chips">
          <span class="brand-preview-chip mono">Live: <strong id="br-prev-live">${esc(b.api_key_prefix_live)}</strong>9f3a••••</span>
          <span class="brand-preview-chip mono">Test: <strong id="br-prev-test">${esc(b.api_key_prefix_test)}</strong>4c2d••••</span>
          <span class="brand-preview-chip mono">Receipt: #<strong id="br-prev-receipt">${esc(b.receipt_prefix)}</strong>-2026</span>
        </div>
      </div>

      <form id="branding-config-form">
        <div class="two-col">
          <div class="field">
            <label>Site / Platform Name (<code>APP_NAME</code>)</label>
            <input class="input" id="br-app-name" required minlength="2" maxlength="80" value="${esc(b.app_name || "")}" />
          </div>
          <div class="field">
            <label>Organization / Network Name (<code>COMPANY_NAME</code>)</label>
            <input class="input" id="br-company-name" required minlength="2" maxlength="80" value="${esc(b.company_name || "")}" />
          </div>
        </div>

        <div class="two-col">
          <div class="field">
            <label>Badge / Favicon Letter (1 char)</label>
            <input class="input mono" id="br-letter" maxlength="4" value="${esc(b.brand_letter || "")}" placeholder="B" />
          </div>
          <div class="field">
            <label>Support Email (<code>SUPPORT_EMAIL</code>)</label>
            <input class="input" type="email" id="br-support-email" required maxlength="255" value="${esc(b.support_email || "")}" />
          </div>
        </div>

        <div class="two-col" style="grid-template-columns:repeat(3,minmax(0,1fr));">
          <div class="field">
            <label>Live Key Prefix</label>
            <input class="input mono" id="br-prefix-live" required pattern="^[a-zA-Z0-9_-]+$" value="${esc(b.api_key_prefix_live || "beta_live_")}" />
          </div>
          <div class="field">
            <label>Test Key Prefix</label>
            <input class="input mono" id="br-prefix-test" required pattern="^[a-zA-Z0-9_-]+$" value="${esc(b.api_key_prefix_test || "beta_test_")}" />
          </div>
          <div class="field">
            <label>Receipt Code Prefix</label>
            <input class="input mono" id="br-receipt-prefix" required pattern="^[a-zA-Z0-9_-]+$" value="${esc(b.receipt_prefix || "BETA")}" />
          </div>
        </div>

        <div class="field">
          <label>Site Meta Description (SEO & HTML Meta)</label>
          <textarea class="textarea" id="br-description" rows="2" maxlength="500">${esc(b.site_description || "")}</textarea>
        </div>

        ${b.updated_by_email ? `<p style="font-size:12px;color:var(--text-muted);margin:0 0 14px;">Last updated by <strong>${esc(b.updated_by_email)}</strong> on ${formatDate(b.updated_at)}</p>` : ""}

        <button type="submit" class="btn btn-primary" id="br-save-btn">Save & Apply Branding Live</button>
      </form>
    </div>
  `;
}

function renderGovernanceTab(supportRes, auditRes, outboxRes) {
  const tickets = supportRes.tickets || [];
  const audits = auditRes.logs || [];
  const outbox = outboxRes.emails || [];

  return `
    <div class="admin-panel" style="--panel-accent:#0d9488;">
      <div class="admin-panel-head"><h3>Support Tickets (${tickets.length})</h3></div>
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr><th>From</th><th>Subject & Message</th><th>Status</th><th>Date</th><th>Action</th></tr></thead>
          <tbody>
            ${
              tickets.length === 0
                ? `<tr><td colspan="5" style="text-align:center;color:var(--text-muted);">No support messages yet.</td></tr>`
                : tickets
                    .map(
                      (t) => `
                    <tr>
                      <td><strong>${esc(t.name)}</strong><br><span style="font-size:12px;">${esc(t.email)}</span></td>
                      <td><strong>${esc(t.subject)}</strong><br><span style="font-size:12.5px;color:var(--text-muted);">${esc(t.message)}</span></td>
                      <td>${statusBadge(t.status)}</td>
                      <td style="font-size:12px;">${formatDate(t.created_at)}</td>
                      <td><button class="btn btn-secondary btn-sm" data-toggle-ticket="${esc(t.id)}">${t.status === "open" ? "Mark Resolved" : "Reopen"}</button></td>
                    </tr>`
                    )
                    .join("")
            }
          </tbody>
        </table>
      </div>
    </div>

    <div class="admin-panel" style="--panel-accent:#6366f1;">
      <div class="admin-panel-head"><h3>Security Audit Logs (Latest 100)</h3></div>
      <div class="table-wrap" style="max-height:280px;overflow-y:auto;">
        <table class="data-table">
          <thead><tr><th>Action</th><th>Actor</th><th>Target</th><th>Timestamp</th></tr></thead>
          <tbody>
            ${audits
              .map(
                (a) => `
              <tr>
                <td class="mono" style="color:#4f46e5;">${esc(a.action)}</td>
                <td>${esc(a.actor_email)}</td>
                <td class="mono" style="font-size:12px;">${esc(a.target_type)}:${esc(a.target_id)}</td>
                <td style="font-size:12px;">${formatDate(a.created_at)}</td>
              </tr>`
              )
              .join("")}
          </tbody>
        </table>
      </div>
    </div>

    <div class="admin-panel" style="--panel-accent:#10b981;">
      <div class="admin-panel-head"><h3>Local Email Outbox (Dev Mode Capture)</h3></div>
      <div class="table-wrap" style="max-height:280px;overflow-y:auto;">
        <table class="data-table">
          <thead><tr><th>To</th><th>Subject</th><th>Preview / Link</th><th>Sent Via</th><th>Time</th></tr></thead>
          <tbody>
            ${
              outbox.length === 0
                ? `<tr><td colspan="5" style="text-align:center;color:var(--text-muted);">No captured emails yet.</td></tr>`
                : outbox
                    .map(
                      (e) => `
                    <tr>
                      <td>${esc(e.to_email)}</td>
                      <td>${esc(e.subject)}</td>
                      <td class="mono" style="font-size:11.5px;max-width:340px;word-break:break-all;">${esc(e.text_body)}</td>
                      <td><span class="badge badge-neutral">${esc(e.sent_via)}</span></td>
                      <td style="font-size:12px;">${formatDate(e.created_at)}</td>
                    </tr>`
                    )
                    .join("")
            }
          </tbody>
        </table>
      </div>
    </div>
  `;
}

export async function renderAdminDashboardPage(state, handlers) {
  const root = document.getElementById("app-root");
  if (!root) return;

  if (!state.user || state.user.role !== "admin") {
    handlers.navigate("#admin/login");
    return;
  }

  const brand = getBrand(state);
  root.innerHTML = `<div class="loading-screen"><div class="spinner-lg"></div><p>Loading ${esc(brand.companyName)} Admin Command Center...</p></div>`;

  let analytics, usersRes, keysRes, plansRes, paymentsRes, reqsRes, masterCfg, auditRes, supportRes, outboxRes, brandingCfg;
  try {
    [analytics, usersRes, keysRes, plansRes, paymentsRes, reqsRes, masterCfg, auditRes, supportRes, outboxRes, brandingCfg] =
      await Promise.all([
        api.get("/api/admin/analytics"),
        api.get("/api/admin/users"),
        api.get("/api/admin/keys"),
        api.get("/api/admin/plans"),
        api.get("/api/admin/payments"),
        api.get("/api/admin/requests?limit=100"),
        api.get("/api/admin/master-config"),
        api.get("/api/admin/audit-logs"),
        api.get("/api/admin/support-tickets"),
        api.get("/api/admin/email-outbox"),
        api.get("/api/admin/branding"),
      ]);
  } catch (err) {
    root.innerHTML = `<div class="container" style="padding:60px 24px;"><div class="glass-card panel-card"><h2>Admin Access Error</h2><p>${esc(err.message)}</p><button class="btn btn-primary" id="adm-reauth">Admin Sign In</button></div></div>`;
    document.getElementById("adm-reauth")?.addEventListener("click", () => handlers.navigate("#admin/login"));
    return;
  }

  let activeTab = state.adminTab || "analytics";
  let userSearch = "";
  let keySearch = "";
  let paymentFilter = "";
  let paymentSearch = "";
  let requestStatusFilter = "";
  let requestSearch = "";

  const tabCounts = {
    users: usersRes.users.length,
    keys: keysRes.keys.length,
    plans: plansRes.length,
    requests: (reqsRes.requests || []).length,
  };

  const draw = () => {
    const activeBrand = getBrand(state);
    let tabBody = "";
    if (activeTab === "analytics") tabBody = renderAnalyticsTab(analytics);
    else if (activeTab === "users") tabBody = renderUsersTab(usersRes.users || [], state.user.id, userSearch);
    else if (activeTab === "keys") tabBody = renderKeysTab(keysRes.keys || [], keySearch);
    else if (activeTab === "plans") tabBody = renderPlansTab(plansRes || []);
    else if (activeTab === "payments") tabBody = renderPaymentsTab(paymentsRes, paymentFilter, paymentSearch);
    else if (activeTab === "requests") tabBody = renderRequestsTab(reqsRes, requestStatusFilter, requestSearch);
    else if (activeTab === "master") tabBody = renderMasterTab(masterCfg, activeBrand);
    else if (activeTab === "branding") tabBody = renderBrandingTab(brandingCfg);
    else if (activeTab === "governance") tabBody = renderGovernanceTab(supportRes, auditRes, outboxRes);

    root.innerHTML = `
      <div class="admin-portal">
        <div class="container">
          <div class="admin-hero-bar">
            <div>
              <h1 class="admin-hero-title">
                <span>${esc(activeBrand.appName)}</span>
                <span style="opacity:0.55;font-weight:500;">/</span>
                <span style="color:#a5b4fc;">Admin Command Center</span>
              </h1>
              <p class="admin-hero-sub">Full platform control · Pricing, live API traffic, user permissions, Razorpay billing, branding & Master Gateway.</p>
            </div>
            <div class="admin-hero-pills">
              <span class="admin-pill"><span class="admin-pill-dot"></span>Mode: ${esc((masterCfg.gateway_mode || "hybrid").toUpperCase())}</span>
              <span class="admin-pill">Upstream: ${masterCfg.upstream_base_url ? "Configured" : "Built-in Only"}</span>
              <span class="admin-pill">${esc(activeBrand.companyName)}</span>
              <button type="button" class="btn btn-secondary btn-sm" id="adm-hero-refresh" style="background:rgba(255,255,255,0.14);color:#fff;border-color:rgba(255,255,255,0.22);">↻ Reload</button>
            </div>
          </div>

          <div class="admin-shell-grid">
            <aside class="admin-sidebar">
              <div class="admin-sidebar-label">Platform Controls</div>
              ${SIDEBAR_TABS.map(
                (t) => `
                <button
                  class="admin-nav-btn ${activeTab === t.id ? "active" : ""}"
                  style="--tab-accent:${t.accent};--tab-accent-end:${t.accentEnd};--tab-bg:${t.bg};"
                  data-adm-tab="${t.id}"
                >
                  <span style="display:flex;align-items:center;gap:10px;">
                    <span class="admin-nav-icon">${t.icon}</span>
                    <span>${esc(t.label)}</span>
                  </span>
                  ${tabCounts[t.id] !== undefined ? `<span class="admin-nav-count">${tabCounts[t.id]}</span>` : ""}
                </button>`
              ).join("")}
            </aside>
            <div class="admin-stage">${tabBody}</div>
          </div>
        </div>
      </div>
    `;

    root.querySelectorAll("[data-adm-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        activeTab = btn.getAttribute("data-adm-tab");
        state.adminTab = activeTab;
        draw();
      });
    });
    bindChartTooltips(root);

    document.getElementById("adm-hero-refresh")?.addEventListener("click", () => renderAdminDashboardPage(state, handlers));
    document.getElementById("adm-refresh-all")?.addEventListener("click", () => renderAdminDashboardPage(state, handlers));

    document.getElementById("adm-user-search")?.addEventListener("input", (e) => {
      userSearch = e.target.value;
      draw();
      document.getElementById("adm-user-search")?.focus();
    });

    document.getElementById("adm-key-search")?.addEventListener("input", (e) => {
      keySearch = e.target.value;
      draw();
      document.getElementById("adm-key-search")?.focus();
    });

    root.querySelectorAll("[data-toggle-suspend]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const uid = btn.getAttribute("data-toggle-suspend");
        const isSuspended = btn.getAttribute("data-suspended") === "true";
        openConfirmModal({
          title: isSuspended ? "Reactivate User Account?" : "Suspend User Account?",
          message: isSuspended
            ? "User will regain access to the portal and active non-revoked keys."
            : "Suspending immediately blocks all API keys owned by this user at the Gateway.",
          confirmLabel: isSuspended ? "Activate User" : "Suspend User",
          danger: !isSuspended,
          onConfirm: async () => {
            await api.patch(`/api/admin/users/${uid}`, {
              is_suspended: !isSuspended,
              suspension_reason: isSuspended ? null : "Suspended by administrator",
            });
            showToast("User status updated.", "success");
            await renderAdminDashboardPage(state, handlers);
          },
        });
      });
    });

    root.querySelectorAll("[data-toggle-role]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const uid = btn.getAttribute("data-toggle-role");
        const currentRole = btn.getAttribute("data-role");
        const nextRole = currentRole === "admin" ? "user" : "admin";
        openConfirmModal({
          title: nextRole === "admin" ? "Promote User to Administrator?" : "Demote Administrator to User?",
          message:
            nextRole === "admin"
              ? "This account will gain full access to pricing, branding, payments, and Master API controls."
              : "This account will lose administrator privileges and only retain normal developer access.",
          confirmLabel: nextRole === "admin" ? "Promote to Admin" : "Set Role to User",
          danger: nextRole !== "admin",
          onConfirm: async () => {
            await api.patch(`/api/admin/users/${uid}`, { role: nextRole });
            showToast(`Role changed to ${nextRole}.`, "success");
            await renderAdminDashboardPage(state, handlers);
          },
        });
      });
    });

    root.querySelectorAll("[data-verify-user]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await api.patch(`/api/admin/users/${btn.getAttribute("data-verify-user")}`, { is_email_verified: true });
        showToast("User email verified.", "success");
        await renderAdminDashboardPage(state, handlers);
      });
    });

    root.querySelectorAll("[data-adm-revoke-key]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const kid = btn.getAttribute("data-adm-revoke-key");
        openConfirmModal({
          title: "Revoke User API Key?",
          message: "This key will immediately fail validation with HTTP 403.",
          confirmLabel: "Revoke Key",
          danger: true,
          onConfirm: async () => {
            await api.post(`/api/admin/keys/${kid}/revoke`, {});
            showToast("API key revoked.", "success");
            await renderAdminDashboardPage(state, handlers);
          },
        });
      });
    });

    document.getElementById("adm-new-plan")?.addEventListener("click", () => {
      openPlanEditorModal(null, async () => {
        await handlers.refreshPublicPlans();
        await renderAdminDashboardPage(state, handlers);
      });
    });

    root.querySelectorAll("[data-edit-plan]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const plan = plansRes.find((p) => p.id === btn.getAttribute("data-edit-plan"));
        openPlanEditorModal(plan, async () => {
          await handlers.refreshPublicPlans();
          await renderAdminDashboardPage(state, handlers);
        });
      });
    });

    root.querySelectorAll("[data-del-plan]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const pid = btn.getAttribute("data-del-plan");
        openConfirmModal({
          title: "Archive / Delete Plan?",
          message: "Plans with existing subscriptions will be archived (inactive); unused plans will be deleted.",
          confirmLabel: "Proceed",
          danger: true,
          onConfirm: async () => {
            const res = await api.del(`/api/admin/plans/${pid}`);
            showToast(res.message, "success");
            await handlers.refreshPublicPlans();
            await renderAdminDashboardPage(state, handlers);
          },
        });
      });
    });

    document.getElementById("adm-pay-filter")?.addEventListener("change", (e) => {
      paymentFilter = e.target.value;
      draw();
    });
    document.getElementById("adm-pay-search")?.addEventListener("input", (e) => {
      paymentSearch = e.target.value;
      draw();
      document.getElementById("adm-pay-search")?.focus();
    });

    root.querySelectorAll("[data-adm-receipt]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          await openAuthenticatedUrl(`/api/payments/${btn.getAttribute("data-adm-receipt")}/receipt?format=html`);
        } catch (err) {
          showToast(err.message, "error");
        }
      });
    });

    root.querySelectorAll("[data-adm-reconcile]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          const res = await api.post(`/api/admin/payments/${btn.getAttribute("data-adm-reconcile")}/reconcile`, {});
          showToast(`Reconciled status: ${res.reconciled_status}`, "info");
          await renderAdminDashboardPage(state, handlers);
        } catch (err) {
          showToast(err.message, "error");
        }
      });
    });

    root.querySelectorAll("[data-adm-refund]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const pid = btn.getAttribute("data-adm-refund");
        openConfirmModal({
          title: "Mark Order as Refunded?",
          message: "This marks the Razorpay payment as refunded and immediately revokes the linked subscription and API keys.",
          confirmLabel: "Confirm Refund Status",
          danger: true,
          onConfirm: async () => {
            const res = await api.post(`/api/admin/payments/${pid}/mark-refunded`, {});
            showToast(res.message, "success");
            await renderAdminDashboardPage(state, handlers);
          },
        });
      });
    });

    document.getElementById("adm-req-filter")?.addEventListener("change", (e) => {
      requestStatusFilter = e.target.value;
      draw();
    });
    document.getElementById("adm-req-search")?.addEventListener("input", (e) => {
      requestSearch = e.target.value;
      draw();
      document.getElementById("adm-req-search")?.focus();
    });

    document.getElementById("master-config-form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const btn = document.getElementById("mc-save-btn");
      btn.disabled = true;
      try {
        const res = await api.put("/api/admin/master-config", {
          gateway_mode: document.getElementById("mc-mode").value,
          upstream_base_url: document.getElementById("mc-url").value.trim(),
          master_api_key: document.getElementById("mc-key").value.trim() || null,
          auth_header_name: document.getElementById("mc-header").value.trim(),
          auth_scheme: document.getElementById("mc-scheme").value.trim(),
          timeout_ms: Number(document.getElementById("mc-timeout").value || 10000),
          forward_user_context_headers: document.getElementById("mc-fwd-ctx").checked,
        });
        showToast(res.message, "success");
        await renderAdminDashboardPage(state, handlers);
      } catch (err) {
        showToast(err.message, "error");
        btn.disabled = false;
      }
    });

    document.getElementById("adm-test-upstream")?.addEventListener("click", async () => {
      try {
        const res = await api.post("/api/admin/master-config/test", {});
        showToast(res.detail, res.ok ? "success" : "error", 5000);
      } catch (err) {
        showToast(err.message, "error");
      }
    });

    const syncBrandPreview = () => {
      const appVal = document.getElementById("br-app-name")?.value.trim() || "Brand Name";
      const compVal = document.getElementById("br-company-name")?.value.trim() || "Company";
      const letVal = (document.getElementById("br-letter")?.value.trim() || appVal[0] || "A").slice(0, 1).toUpperCase();
      const mailVal = document.getElementById("br-support-email")?.value.trim() || "support@example.com";
      const liveVal = document.getElementById("br-prefix-live")?.value.trim() || "api_live_";
      const testVal = document.getElementById("br-prefix-test")?.value.trim() || "api_test_";
      const recVal = (document.getElementById("br-receipt-prefix")?.value.trim() || "API").toUpperCase();

      const setTxt = (id, v) => {
        const el = document.getElementById(id);
        if (el) el.textContent = v;
      };
      setTxt("br-prev-app", appVal);
      const prevComp = document.getElementById("br-prev-company");
      if (prevComp) prevComp.innerHTML = `${esc(compVal)} · <span id="br-prev-email">${esc(mailVal)}</span>`;
      setTxt("br-prev-tile", letVal);
      setTxt("br-prev-live", liveVal);
      setTxt("br-prev-test", testVal);
      setTxt("br-prev-receipt", recVal);
    };

    ["br-app-name", "br-company-name", "br-letter", "br-support-email", "br-prefix-live", "br-prefix-test", "br-receipt-prefix"].forEach(
      (id) => document.getElementById(id)?.addEventListener("input", syncBrandPreview)
    );

    document.getElementById("branding-config-form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const btn = document.getElementById("br-save-btn");
      btn.disabled = true;
      try {
        const res = await api.put("/api/admin/branding", {
          app_name: document.getElementById("br-app-name").value.trim(),
          company_name: document.getElementById("br-company-name").value.trim(),
          brand_badge_letter: document.getElementById("br-letter").value.trim(),
          support_email: document.getElementById("br-support-email").value.trim(),
          api_key_prefix_live: document.getElementById("br-prefix-live").value.trim(),
          api_key_prefix_test: document.getElementById("br-prefix-test").value.trim(),
          receipt_prefix: document.getElementById("br-receipt-prefix").value.trim(),
          site_description: document.getElementById("br-description").value.trim(),
        });
        showToast(res.message, "success");
        await handlers.refreshPublicData();
        handlers.refreshChrome();
        await renderAdminDashboardPage(state, handlers);
      } catch (err) {
        showToast(err.message, "error");
        btn.disabled = false;
      }
    });

    document.getElementById("br-reset-btn")?.addEventListener("click", () => {
      openConfirmModal({
        title: "Reset Branding to .env Defaults?",
        message: "This removes database branding overrides and restores APP_NAME, COMPANY_NAME, prefixes, and email from your .env file.",
        confirmLabel: "Reset Branding",
        danger: true,
        onConfirm: async () => {
          const res = await api.post("/api/admin/branding/reset", {});
          showToast(res.message, "success");
          await handlers.refreshPublicData();
          handlers.refreshChrome();
          await renderAdminDashboardPage(state, handlers);
        },
      });
    });

    root.querySelectorAll("[data-toggle-ticket]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await api.patch(`/api/admin/support-tickets/${btn.getAttribute("data-toggle-ticket")}`, {});
        await renderAdminDashboardPage(state, handlers);
      });
    });
  };

  draw();
}
