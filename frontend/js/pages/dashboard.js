/**
 * Interactive Developer Dashboard:
 * - Dynamic API Credentials & Generate API Key Card (Base URL + Reveal/Copy/Select active key)
 * - Plans Section inside Dashboard (Free Sandbox + all Paid Tiers)
 * - Usage Line+Bar Combo Chart + Animated Horizontal Usage Line-Bars
 * - Live Quick Gateway Test, API Keys Vault, Billing & Receipts, Request Logs, Profile
 */

import {
  api,
  copyToClipboard,
  daysRemaining,
  esc,
  formatDate,
  formatInr,
  formatNum,
  getApiBase,
  getBrand,
  highlightJson,
  openAuthenticatedUrl,
  showToast,
  statusBadge,
} from "../api.js";
import { bindChartTooltips, renderTrafficChart } from "../components/charts.js";
import { openConfirmModal, openCreateKeyModal } from "../components/modals.js";

function animateCounters(root) {
  root.querySelectorAll("[data-count-to]").forEach((el) => {
    const target = Number(el.getAttribute("data-count-to"));
    if (!Number.isFinite(target) || target <= 0) {
      el.textContent = formatNum(target || 0);
      return;
    }
    const duration = 500;
    const start = performance.now();
    const tick = (now) => {
      const progress = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - progress, 3);
      el.textContent = formatNum(Math.round(target * eased));
      if (progress < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}

export async function renderDashboardPage(state, handlers) {
  const root = document.getElementById("app-root");
  if (!root) return;

  root.innerHTML = `<div class="loading-screen"><div class="spinner-lg"></div><p>Loading your Developer Dashboard...</p></div>`;

  let subRes, keysRes, usageRes, paymentsRes, sessionsRes, plansList;
  const loadDashboardData = async () => {
    [subRes, keysRes, usageRes, paymentsRes, sessionsRes, plansList] = await Promise.all([
      api.get("/api/subscriptions/current"),
      api.get("/api/keys"),
      api.get("/api/dashboard/usage?limit=50"),
      api.get("/api/payments/history"),
      api.get("/api/auth/sessions"),
      api.get("/api/plans"),
    ]);
    state.subscription = subRes.subscription;
    state.keys = keysRes.keys || [];
    state.plans = plansList || state.plans || [];
  };

  try {
    await loadDashboardData();
  } catch (err) {
    root.innerHTML = `<div class="container" style="padding:60px 24px;"><div class="glass-card panel-card"><h2>Could not load dashboard</h2><p>${esc(err.message)}</p></div></div>`;
    return;
  }

  const baseUrl = subRes.api_base_url || `${getApiBase() || window.location.origin}/v1`;
  const revealedKeys = {};
  const curlOpenKeys = {};
  let selectedCredKeyId = "";
  let activeTab = state.dashboardTab || "overview";
  let chartMode = "combo"; // 'combo' (Line + Bar) | 'bar' | 'line'
  let logStatusFilter = "all";
  let logSearch = "";
  let quickPingEndpoint = "/v1/status";
  let quickPingResult = null;
  let animateOverviewOnce = true;

  const draw = () => {
    const sub = state.subscription;
    const plan = sub?.plan;
    const plans = state.plans || [];
    const keys = state.keys || [];
    const activeKeys = keys.filter((k) => k.status === "active");
    const activeKeysCount = activeKeys.length;
    const summary = usageRes.summary || {};
    const dailyPct = plan ? Math.min(100, Math.round(((sub.daily_requests_used || 0) / plan.daily_request_limit) * 100)) : 0;
    const cyclePct = plan ? Math.min(100, Math.round(((sub.cycle_requests_used || 0) / plan.monthly_request_limit) * 100)) : 0;
    const successPct = Math.round(Number(summary.success_rate ?? 100));
    const freePlan = plans.find((p) => p.price_paise === 0);

    if (activeKeys.length > 0 && !activeKeys.some((k) => k.id === selectedCredKeyId)) {
      selectedCredKeyId = activeKeys[0].id;
    }
    const credKey = activeKeys.find((k) => k.id === selectedCredKeyId) || activeKeys[0] || null;
    const credKeyDisplay = credKey
      ? revealedKeys[credKey.id] || `${credKey.key_prefix}••••••••••••${credKey.key_last4}`
      : "No active API key yet — click Generate API Key";

    const sidebarItems = [
      { id: "overview", label: "Overview & Usage", icon: "◈" },
      { id: "plans", label: `Plans & Pricing (${plans.length})`, icon: "✦" },
      { id: "keys", label: `API Keys (${activeKeysCount})`, icon: "⚿" },
      { id: "billing", label: "Billing & Receipts", icon: "◆" },
      { id: "logs", label: "Request History", icon: "▤" },
      { id: "profile", label: "Profile & Security", icon: "⚙" },
    ];

    const renderPlansGridHtml = () => `
      <div class="dash-plans-grid">
        ${plans
          .map((p) => {
            const isCurrent = sub?.status === "active" && plan?.id === p.id;
            const isFree = p.price_paise === 0;
            const canAddKeyOnCurrent = isCurrent && activeKeysCount < p.max_api_keys;
            let btnLabel = isFree ? "Activate Free & Generate Key" : "Purchase via Razorpay";
            let btnAttr = `data-dash-plan-action="buy" data-plan-id="${esc(p.id)}"`;
            if (isCurrent) {
              if (canAddKeyOnCurrent) {
                btnLabel = "Generate API Key";
                btnAttr = `data-dash-plan-action="gen-key" data-plan-id="${esc(p.id)}"`;
              } else if (!isFree) {
                btnLabel = "Renew Plan";
                btnAttr = `data-dash-plan-action="renew" data-plan-id="${esc(p.id)}"`;
              } else {
                btnLabel = "Active Plan (Key Ready)";
                btnAttr = `disabled`;
              }
            }

            return `
              <div class="glass-card dash-plan-card ${isCurrent ? "current-plan" : ""}">
                <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;">
                  <strong style="font-size:16px;color:#0a0a0a;">${esc(p.name)}</strong>
                  ${
                    isCurrent
                      ? `<span class="badge badge-success">Active</span>`
                      : p.badge
                      ? `<span class="badge badge-neutral">${esc(p.badge)}</span>`
                      : ""
                  }
                </div>
                <div style="display:flex;align-items:baseline;gap:6px;">
                  <span style="font-size:26px;font-weight:800;color:#0a0a0a;">${isFree ? "Free" : esc(formatInr(p.price_paise))}</span>
                  <span style="font-size:12px;color:var(--text-muted);">/ ${p.billing_cycle_days} days</span>
                </div>
                <p style="margin:0;font-size:12.5px;color:var(--text-muted);min-height:34px;">${esc(p.tagline)}</p>
                <div style="background:#f8fafc;border:1px solid var(--border-subtle);border-radius:10px;padding:10px;font-size:12px;display:grid;grid-template-columns:1fr 1fr;gap:8px;">
                  <div><span style="color:var(--text-muted);">Daily</span><strong style="display:block;color:#0a0a0a;">${formatNum(p.daily_request_limit)}</strong></div>
                  <div><span style="color:var(--text-muted);">Monthly</span><strong style="display:block;color:#0a0a0a;">${formatNum(p.monthly_request_limit)}</strong></div>
                  <div><span style="color:var(--text-muted);">Rate/min</span><strong style="display:block;color:#0a0a0a;">${formatNum(p.rate_limit_per_minute)}</strong></div>
                  <div><span style="color:var(--text-muted);">Max Keys</span><strong style="display:block;color:#0a0a0a;">${p.max_api_keys}</strong></div>
                </div>
                <ul class="plan-features" style="margin:4px 0 8px;font-size:12.5px;">
                  ${(p.features_json || []).slice(0, 3).map((f) => `<li>${esc(f)}</li>`).join("")}
                </ul>
                <button class="btn ${isCurrent || isFree ? "btn-primary" : "btn-secondary"} btn-sm" style="width:100%;margin-top:auto;" ${btnAttr}>
                  ${esc(btnLabel)}
                </button>
              </div>
            `;
          })
          .join("")}
      </div>
    `;

    const renderCredentialsCardHtml = () => `
      <div class="glass-card creds-vault-card">
        <div class="panel-head" style="margin-bottom:6px;">
          <div>
            <div style="font-size:12px;color:var(--text-muted);display:flex;align-items:center;gap:6px;">
              <span class="kpi-dot ${credKey ? "live" : ""}"></span>
              <span>Dynamic API Credentials & Key Generator</span>
            </div>
            <h2 style="margin:4px 0 0;font-size:18px;">
              ${plan ? `${esc(plan.name)} · ${activeKeysCount}/${plan.max_api_keys} Keys` : "Generate Your API Key"}
            </h2>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <button class="btn btn-primary btn-sm" id="dash-generate-key-btn">
              ⚡ Generate API Key
            </button>
            <button class="btn btn-secondary btn-sm" id="dash-open-playground">Open Playground</button>
          </div>
        </div>

        <div class="creds-grid">
          <div class="cred-box">
            <div style="display:flex;justify-content:space-between;align-items:center;">
              <span style="font-size:11.5px;font-weight:700;text-transform:uppercase;color:var(--text-muted);">API Base URL</span>
              <button class="btn btn-ghost btn-sm" id="dash-copy-base">Copy URL</button>
            </div>
            <div class="mono" style="font-size:13.5px;font-weight:700;color:#2563eb;word-break:break-all;">${esc(baseUrl)}</div>
            <div style="font-size:12px;color:var(--text-muted);">
              ${sub ? `Plan Status: ${statusBadge(sub.status)} · Expires ${formatDate(sub.expires_at)}` : "Activate Free Sandbox or any plan below to begin."}
            </div>
          </div>

          <div class="cred-box dark">
            <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap;">
              <span style="font-size:11.5px;font-weight:700;text-transform:uppercase;color:#94a3b8;">Your Active API Key</span>
              ${
                activeKeys.length > 1
                  ? `<select class="select mono" id="dash-cred-key-select" style="width:auto;padding:3px 8px;font-size:11.5px;background:#1e293b;color:#f8fafc;border-color:#334155;">
                      ${activeKeys
                        .map(
                          (k) => `<option value="${esc(k.id)}" ${credKey?.id === k.id ? "selected" : ""}>${esc(k.name)} (${esc(k.key_prefix)}…)</option>`
                        )
                        .join("")}
                    </select>`
                  : ""
              }
            </div>
            <div class="mono" style="font-size:13.5px;color:#ffffff;word-break:break-all;padding:6px 0;">
              ${esc(credKeyDisplay)}
            </div>
            ${
              credKey
                ? `
              <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;justify-content:space-between;">
                <div style="display:flex;gap:6px;flex-wrap:wrap;">
                  <button class="btn btn-secondary btn-sm" data-reveal-key="${esc(credKey.id)}">${revealedKeys[credKey.id] ? "Hide Key" : "Reveal Key"}</button>
                  <button class="btn btn-secondary btn-sm" data-copy-key="${esc(credKey.id)}">Copy Key</button>
                  <button class="btn btn-ghost btn-sm" style="color:#cbd5e1;" id="dash-goto-keys">Manage Keys →</button>
                </div>
                <span style="font-size:11.5px;color:#94a3b8;">Created ${formatDate(credKey.created_at)}</span>
              </div>
            `
                : `<div style="font-size:12px;color:#94a3b8;">Click <strong>⚡ Generate API Key</strong> above to provision a key instantly.</div>`
            }
          </div>
        </div>
      </div>
    `;

    let tabBody = "";

    if (activeTab === "overview") {
      tabBody = `
        <div class="dash-tab-stage">
          ${
            !state.user.is_email_verified
              ? `
            <div class="glass-card" style="padding:14px 18px;margin-bottom:18px;border-color:rgba(217,119,6,0.38);display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:12px;">
              <div>
                <strong style="color:var(--warning);">Email verification pending</strong>
                <span style="color:var(--text-secondary);font-size:13.5px;margin-left:8px;">Verify ${esc(state.user.email)} to secure billing alerts.</span>
              </div>
              <button class="btn btn-secondary btn-sm" id="dash-resend-verify">Resend Verification</button>
            </div>`
              : ""
          }

          ${renderCredentialsCardHtml()}

          <div class="kpi-grid">
            <div class="glass-card kpi-card">
              <div class="kpi-label"><span>Active Plan</span><span class="kpi-dot ${sub?.status === "active" ? "live" : ""}"></span></div>
              <div class="kpi-value" style="font-size:20px;">${plan ? esc(plan.name) : "No Plan"}</div>
              <div class="kpi-sub">${sub ? `${statusBadge(sub.status)} · ${daysRemaining(sub.expires_at)}d left` : "Choose a plan below"}</div>
            </div>
            <div class="glass-card kpi-card">
              <div class="kpi-label"><span>Daily Remaining</span><span class="kpi-dot"></span></div>
              <div class="kpi-value" ${animateOverviewOnce ? `data-count-to="${sub ? sub.daily_remaining : 0}"` : ""}>${sub ? formatNum(sub.daily_remaining) : "0"}</div>
              <div class="kpi-sub">${plan ? `of ${formatNum(plan.daily_request_limit)} / day` : "Resets 00:00 UTC"}</div>
            </div>
            <div class="glass-card kpi-card">
              <div class="kpi-label"><span>Cycle Remaining</span><span class="kpi-dot"></span></div>
              <div class="kpi-value" ${animateOverviewOnce ? `data-count-to="${sub ? sub.monthly_remaining : 0}"` : ""}>${sub ? formatNum(sub.monthly_remaining) : "0"}</div>
              <div class="kpi-sub">${plan ? `of ${formatNum(plan.monthly_request_limit)} total` : "—"}</div>
            </div>
            <div class="glass-card kpi-card">
              <div class="kpi-label"><span>Total API Usage</span><span class="kpi-dot"></span></div>
              <div class="kpi-value" ${animateOverviewOnce ? `data-count-to="${summary.total_requests || 0}"` : ""}>${formatNum(summary.total_requests || 0)}</div>
              <div class="kpi-sub">${summary.success_rate ?? 100}% ok · ${summary.avg_latency_ms || 0} ms avg</div>
            </div>
          </div>

          <div class="two-col">
            <div class="glass-card panel-card">
              <div class="panel-head">
                <h3>Usage Line-Bars & Rate Limits</h3>
                ${plan ? `<span class="badge badge-info">${plan.rate_limit_per_minute} req/min</span>` : ""}
              </div>
              <div class="quota-bar-wrap">
                <div class="quota-bar-top"><span>Daily Usage Line</span><span>${sub ? formatNum(sub.daily_requests_used) : 0} / ${plan ? formatNum(plan.daily_request_limit) : 0} (${dailyPct}%)</span></div>
                <div class="quota-track"><div class="quota-fill" style="width:${dailyPct}%"></div></div>
              </div>
              <div class="quota-bar-wrap">
                <div class="quota-bar-top"><span>Cycle Usage Line</span><span>${sub ? formatNum(sub.cycle_requests_used) : 0} / ${plan ? formatNum(plan.monthly_request_limit) : 0} (${cyclePct}%)</span></div>
                <div class="quota-track"><div class="quota-fill" style="width:${cyclePct}%"></div></div>
              </div>
              <div class="quota-bar-wrap">
                <div class="quota-bar-top"><span>Gateway Health Rate</span><span>${successPct}% (${formatNum(summary.success_requests || 0)} ok)</span></div>
                <div class="quota-track"><div class="quota-fill" style="width:${successPct}%;background:linear-gradient(90deg,#10b981,#0ea5e9);"></div></div>
              </div>
              ${
                sub && plan
                  ? `
                <div style="font-size:12.5px;color:var(--text-muted);margin-top:10px;">
                  Methods: <span class="mono" style="color:#0a0a0a;">${esc(plan.allowed_methods)}</span> · Expires ${formatDate(sub.expires_at)}
                </div>
              `
                  : ""
              }
            </div>

            <div class="glass-card panel-card">
              <div class="panel-head">
                <div>
                  <h3>7-Day Usage (Line + Bar)</h3>
                  <span style="font-size:12px;color:var(--text-muted);">Bars show volume · Line tracks daily trend</span>
                </div>
                <div class="chart-toggle-group">
                  <button type="button" class="chart-toggle-btn ${chartMode === "combo" ? "active" : ""}" data-chart-mode="combo">Line + Bar</button>
                  <button type="button" class="chart-toggle-btn ${chartMode === "bar" ? "active" : ""}" data-chart-mode="bar">Bars</button>
                  <button type="button" class="chart-toggle-btn ${chartMode === "line" ? "active" : ""}" data-chart-mode="line">Line</button>
                </div>
              </div>
              ${renderTrafficChart(usageRes.series, "requests", "errors", 200, chartMode)}
            </div>
          </div>

          ${
            activeKeys.length > 0
              ? `
                <div class="glass-card panel-card">
                  <div class="panel-head">
                    <div>
                      <h3>Live Gateway Quick Test</h3>
                      <p style="margin:3px 0 0;font-size:12.5px;color:var(--text-muted);">
                        Send a real call using <strong>${esc(credKey.name)}</strong> and watch usage bars & line chart update.
                      </p>
                    </div>
                  </div>
                  <div class="quick-ping-bar">
                    <select class="select mono" id="dash-ping-ep" style="flex:1;min-width:220px;">
                      <option value="/v1/status" ${quickPingEndpoint === "/v1/status" ? "selected" : ""}>GET /v1/status — Gateway Health</option>
                      <option value="/v1/crypto/uuid" ${quickPingEndpoint === "/v1/crypto/uuid" ? "selected" : ""}>GET /v1/crypto/uuid — Generate UUID</option>
                      <option value="/v1/utils/timestamp" ${quickPingEndpoint === "/v1/utils/timestamp" ? "selected" : ""}>GET /v1/utils/timestamp — UTC Sync</option>
                      <option value="/v1/geo/ip-parse" ${quickPingEndpoint === "/v1/geo/ip-parse" ? "selected" : ""}>GET /v1/geo/ip-parse — IP Lookup</option>
                    </select>
                    <button class="btn btn-primary btn-sm" id="dash-run-ping">Run Live Test ⚡</button>
                  </div>
                  ${
                    quickPingResult
                      ? `
                    <div class="quick-ping-output">
                      <div style="display:flex;gap:8px;align-items:center;margin-bottom:8px;flex-wrap:wrap;">
                        <span class="badge badge-${quickPingResult.status_code < 400 ? "success" : "danger"}">HTTP ${quickPingResult.status_code}</span>
                        <span class="badge badge-neutral mono">${quickPingResult.latency_ms} ms</span>
                        <span class="badge badge-neutral mono">${esc(quickPingResult.target_endpoint)}</span>
                      </div>
                      <pre class="response-pre" style="min-height:110px;max-height:220px;">${highlightJson(quickPingResult.body)}</pre>
                    </div>
                  `
                      : ""
                  }
                </div>
              `
              : ""
          }

          <div class="glass-card panel-card">
            <div class="panel-head">
              <div>
                <h3>All API Plans (Free & Paid)</h3>
                <p style="margin:3px 0 0;font-size:13px;color:var(--text-muted);">Activate the Free Sandbox or upgrade via Razorpay to generate plan-linked keys.</p>
              </div>
              <button class="btn btn-secondary btn-sm" id="dash-goto-plans">Full Plans View →</button>
            </div>
            ${renderPlansGridHtml()}
          </div>
        </div>
      `;
      animateOverviewOnce = false;
    } else if (activeTab === "plans") {
      tabBody = `
        <div class="dash-tab-stage">
          ${renderCredentialsCardHtml()}
          <div class="glass-card panel-card">
            <div class="panel-head">
              <div>
                <h2>Available API Access Plans</h2>
                <p style="margin:4px 0 0;font-size:13px;color:var(--text-muted);">
                  Compare daily & monthly quotas, rate limits, and key caps. Keys generated are linked to ${esc(getBrand(state).companyName)}'s Master Gateway.
                </p>
              </div>
            </div>
            ${renderPlansGridHtml()}
          </div>
        </div>
      `;
    } else if (activeTab === "keys") {
      const canCreate = sub?.status === "active" && plan && activeKeysCount < plan.max_api_keys;
      tabBody = `
        <div class="dash-tab-stage">
          <div class="base-url-bar">
            <div>
              <div style="font-size:12px;color:var(--text-muted);">API Base URL</div>
              <div class="mono" style="font-size:14.5px;font-weight:700;color:#2563eb;">${esc(baseUrl)}</div>
            </div>
            <button class="btn btn-secondary btn-sm" id="dash-copy-base">Copy Base URL</button>
          </div>
          <div class="glass-card panel-card">
            <div class="panel-head">
              <div>
                <h2>API Keys Vault</h2>
                <p style="margin:4px 0 0;font-size:13px;color:var(--text-muted);">
                  ${plan ? `${activeKeysCount} / ${plan.max_api_keys} active keys used on ${esc(plan.name)}` : "Activate a plan to generate API keys."}
                </p>
              </div>
              <button class="btn btn-primary btn-sm" id="btn-create-key" ${canCreate ? "" : "disabled"}>
                + Generate API Key
              </button>
            </div>

            ${
              keys.length === 0
                ? `<p style="color:var(--text-muted);font-size:14px;">No API keys issued yet. Go to Plans & Pricing or click Generate API Key on Overview.</p>`
                : keys
                    .map((k) => {
                      const revealed = revealedKeys[k.id];
                      const isRevoked = k.status !== "active";
                      const curlShown = Boolean(curlOpenKeys[k.id]);
                      const displayKey = revealed || `${k.key_prefix}••••••••••••${k.key_last4}`;
                      return `
                    <div class="key-card">
                      <div class="key-card-top">
                        <div>
                          <strong style="font-size:15px;">${esc(k.name)}</strong>
                          <span style="margin-left:8px;">${statusBadge(k.status)}</span>
                          <span class="badge badge-neutral mono" style="margin-left:6px;">${esc(k.master_link_tag)}</span>
                        </div>
                        <div style="font-size:12.5px;color:var(--text-muted);">
                          ${formatNum(k.total_requests)} calls · Created ${formatDate(k.created_at)}
                          ${k.last_used_at ? ` · Last used ${formatDate(k.last_used_at)}` : ""}
                        </div>
                      </div>

                      <div class="key-secret-box">
                        <span id="key-display-${esc(k.id)}">${esc(displayKey)}</span>
                        ${
                          !isRevoked
                            ? `<button class="btn btn-ghost btn-sm" data-copy-key="${esc(k.id)}">Copy</button>`
                            : ""
                        }
                      </div>

                      ${
                        !isRevoked
                          ? `
                        <div class="key-actions-row">
                          <button class="btn btn-secondary btn-sm" data-reveal-key="${esc(k.id)}">
                            ${revealed ? "Hide Key" : "Reveal Key"}
                          </button>
                          <button class="btn btn-secondary btn-sm" data-toggle-curl="${esc(k.id)}">${curlShown ? "Hide cURL" : "cURL Snippet"}</button>
                          <button class="btn btn-secondary btn-sm" data-regen-key="${esc(k.id)}">Regenerate</button>
                          <button class="btn btn-secondary btn-sm" data-test-key="${esc(k.id)}">Playground</button>
                          <button class="btn btn-danger btn-sm" data-revoke-key="${esc(k.id)}">Revoke</button>
                        </div>
                        ${
                          curlShown
                            ? `<pre class="response-pre" style="min-height:auto;padding:12px;margin:0;font-size:12px;">curl -s "${esc(baseUrl)}/status" -H "X-API-Key: ${esc(displayKey)}"</pre>`
                            : ""
                        }
                      `
                          : `<div style="font-size:12px;color:var(--danger);">Revoked on ${formatDate(k.revoked_at)}</div>`
                      }
                    </div>
                  `;
                    })
                    .join("")
            }
          </div>
        </div>
      `;
    } else if (activeTab === "billing") {
      const payments = paymentsRes.payments || [];
      tabBody = `
        <div class="dash-tab-stage">
          <div class="glass-card panel-card">
            <div class="panel-head">
              <div>
                <h2>Subscription & Razorpay Billing</h2>
                <p style="margin:4px 0 0;font-size:13px;color:var(--text-muted);">Manage renewals, reconcile pending payments, and download receipts.</p>
              </div>
              <div style="display:flex;gap:8px;flex-wrap:wrap;">
                ${
                  sub && sub.status === "active" && plan && plan.price_paise > 0
                    ? `<button class="btn btn-primary btn-sm" id="billing-renew">Renew ${esc(plan.name)}</button>`
                    : ""
                }
                <button class="btn btn-secondary btn-sm" id="billing-plans">Switch / Upgrade Plan</button>
                ${
                  sub && sub.status === "active"
                    ? `<button class="btn btn-danger btn-sm" id="billing-cancel-sub">Cancel Subscription</button>`
                    : ""
                }
              </div>
            </div>

            <div class="table-wrap">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Receipt</th>
                    <th>Plan</th>
                    <th>Amount</th>
                    <th>Status</th>
                    <th>Method</th>
                    <th>Razorpay References</th>
                    <th>Date</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  ${
                    payments.length === 0
                      ? `<tr><td colspan="8" style="text-align:center;color:var(--text-muted);">No Razorpay transactions recorded yet.</td></tr>`
                      : payments
                          .map(
                            (p) => `
                          <tr>
                            <td class="mono">${esc(p.receipt_number)}</td>
                            <td><strong>${esc(p.plan_name)}</strong><br><span style="font-size:11.5px;color:var(--text-muted);">${esc(p.action)}</span></td>
                            <td><strong>${esc(p.amount_display)}</strong></td>
                            <td>${statusBadge(p.status)}</td>
                            <td>${esc((p.payment_method || "razorpay").toUpperCase())}</td>
                            <td class="mono" style="font-size:11.5px;">
                              Ord: ${esc(p.razorpay_order_id || "—")}<br>
                              Pay: ${esc(p.razorpay_payment_id || "—")}
                            </td>
                            <td style="font-size:12.5px;">${formatDate(p.paid_at || p.created_at)}</td>
                            <td>
                              <div style="display:flex;gap:6px;flex-wrap:wrap;">
                                <button type="button" class="btn btn-secondary btn-sm" data-dash-receipt="${esc(p.id)}">Receipt</button>
                                ${
                                  p.status === "pending"
                                    ? `<button class="btn btn-primary btn-sm" data-reconcile="${esc(p.id)}">Check Status</button>`
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
        </div>
      `;
    } else if (activeTab === "logs") {
      const allLogs = usageRes.logs || [];
      const logs = allLogs.filter((l) => {
        if (logStatusFilter === "2xx" && (l.status_code < 200 || l.status_code >= 400)) return false;
        if (logStatusFilter === "4xx" && (l.status_code < 400 || l.status_code >= 500)) return false;
        if (logStatusFilter === "5xx" && l.status_code < 500) return false;
        if (logSearch.trim()) {
          const q = logSearch.trim().toLowerCase();
          return (
            l.path.toLowerCase().includes(q) ||
            l.method.toLowerCase().includes(q) ||
            (l.error_code || "").toLowerCase().includes(q)
          );
        }
        return true;
      });
      tabBody = `
        <div class="dash-tab-stage">
          <div class="glass-card panel-card">
            <div class="panel-head">
              <div>
                <h2>API Request History</h2>
                <p style="margin:4px 0 0;font-size:13px;color:var(--text-muted);">Live gateway traffic filtered in real time.</p>
              </div>
              <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
                <input class="input" id="logs-search-input" style="width:185px;" placeholder="Filter path/method..." value="${esc(logSearch)}" />
                <select class="select" id="logs-status-filter" style="width:auto;">
                  <option value="all" ${logStatusFilter === "all" ? "selected" : ""}>All Statuses</option>
                  <option value="2xx" ${logStatusFilter === "2xx" ? "selected" : ""}>2xx Success</option>
                  <option value="4xx" ${logStatusFilter === "4xx" ? "selected" : ""}>4xx / 429 Limits</option>
                  <option value="5xx" ${logStatusFilter === "5xx" ? "selected" : ""}>5xx Upstream Errors</option>
                </select>
                <button class="btn btn-secondary btn-sm" id="logs-refresh">Refresh</button>
              </div>
            </div>
            <div class="table-wrap">
              <table class="data-table">
                <thead>
                  <tr>
                    <th>Method</th>
                    <th>Endpoint</th>
                    <th>Status</th>
                    <th>Latency</th>
                    <th>Mode</th>
                    <th>Error Code</th>
                    <th>Timestamp</th>
                  </tr>
                </thead>
                <tbody>
                  ${
                    logs.length === 0
                      ? `<tr><td colspan="7" style="text-align:center;color:var(--text-muted);">No matching API calls yet.</td></tr>`
                      : logs
                          .map(
                            (l) => `
                          <tr>
                            <td><span class="method-pill method-${esc(l.method)}">${esc(l.method)}</span></td>
                            <td class="mono">${esc(l.path)}${l.query_string ? `?${esc(l.query_string)}` : ""}</td>
                            <td><span class="badge badge-${l.status_code < 400 ? "success" : l.status_code === 429 ? "warning" : "danger"}">${l.status_code}</span></td>
                            <td class="mono">${l.latency_ms} ms</td>
                            <td><span class="badge badge-neutral">${esc(l.gateway_mode)}</span></td>
                            <td class="mono" style="font-size:12px;color:var(--danger);">${esc(l.error_code || "—")}</td>
                            <td style="font-size:12.5px;">${formatDate(l.created_at)}</td>
                          </tr>`
                          )
                          .join("")
                  }
                </tbody>
              </table>
            </div>
          </div>
        </div>
      `;
    } else if (activeTab === "profile") {
      const sessions = sessionsRes.sessions || [];
      tabBody = `
        <div class="dash-tab-stage">
          <div class="two-col">
            <div class="glass-card panel-card">
              <div class="panel-head">
                <h3>Profile Information</h3>
                ${state.user.is_email_verified ? `<span class="badge badge-success">Email Verified</span>` : `<span class="badge badge-warning">Unverified</span>`}
              </div>
              <form id="profile-form">
                <div class="field"><label>Email</label><input class="input" disabled value="${esc(state.user.email)}" /></div>
                <div class="field"><label>Full Name</label><input class="input" id="prof-name" required value="${esc(state.user.full_name)}" /></div>
                <div class="field"><label>Company</label><input class="input" id="prof-company" value="${esc(state.user.company)}" /></div>
                <div class="field"><label>Phone (Used for Razorpay prefill)</label><input class="input" id="prof-phone" value="${esc(state.user.phone)}" placeholder="+91 98765 43210" /></div>
                <button class="btn btn-primary btn-sm" type="submit">Save Profile</button>
              </form>
            </div>

            <div class="glass-card panel-card">
              <div class="panel-head"><h3>Security & Password</h3></div>
              <form id="password-form">
                ${
                  state.user.auth_provider !== "google"
                    ? `<div class="field"><label>Current Password</label><input class="input" type="password" id="pwd-current" required /></div>`
                    : `<p style="font-size:12.5px;color:var(--text-muted);margin-top:0;">Signed in via Google. Add a local password below if you also want email/password login.</p>`
                }
                <div class="field"><label>New Password</label><input class="input" type="password" id="pwd-new" required minlength="8" /></div>
                <button class="btn btn-secondary btn-sm" type="submit">Update Password</button>
              </form>
            </div>
          </div>

          <div class="glass-card panel-card">
            <div class="panel-head"><h3>Active Sessions</h3></div>
            <div class="table-wrap">
              <table class="data-table">
                <thead><tr><th>Session</th><th>IP Address</th><th>Last Active</th><th>Action</th></tr></thead>
                <tbody>
                  ${sessions
                    .map(
                      (s) => `
                    <tr>
                      <td style="font-size:12.5px;max-width:340px;">${esc(s.user_agent || "Browser")} ${s.is_current ? `<span class="badge badge-info">Current</span>` : ""}</td>
                      <td class="mono">${esc(s.ip_address)}</td>
                      <td style="font-size:12.5px;">${formatDate(s.last_seen_at)}</td>
                      <td>${
                        s.is_current
                          ? `<span style="font-size:12px;color:var(--text-muted);">Active</span>`
                          : `<button class="btn btn-danger btn-sm" data-revoke-session="${esc(s.id)}">Revoke</button>`
                      }</td>
                    </tr>`
                    )
                    .join("")}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      `;
    }

    root.innerHTML = `
      <div class="container workspace-layout">
        <aside class="glass-card sidebar-panel">
          <div class="sidebar-section-label">Developer Hub</div>
          ${sidebarItems
            .map(
              (item) => `
              <button class="sidebar-btn ${activeTab === item.id ? "active" : ""}" data-tab="${item.id}">
                <span>${item.icon}</span><span>${esc(item.label)}</span>
              </button>`
            )
            .join("")}
        </aside>
        <div>${tabBody}</div>
      </div>
    `;

    animateCounters(root);
    bindChartTooltips(root);

    root.querySelectorAll("[data-tab]").forEach((btn) => {
      btn.addEventListener("click", () => {
        activeTab = btn.getAttribute("data-tab");
        state.dashboardTab = activeTab;
        draw();
      });
    });

    root.querySelectorAll("[data-chart-mode]").forEach((btn) => {
      btn.addEventListener("click", () => {
        chartMode = btn.getAttribute("data-chart-mode");
        draw();
      });
    });

    document.getElementById("dash-cred-key-select")?.addEventListener("change", (e) => {
      selectedCredKeyId = e.target.value;
      draw();
    });

    document.getElementById("dash-copy-base")?.addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      await copyToClipboard(baseUrl, "API Base URL copied!");
      btn.textContent = "Copied ✓";
      setTimeout(() => (btn.textContent = "Copy URL"), 1800);
    });
    document.getElementById("dash-open-playground")?.addEventListener("click", () => handlers.navigate("#playground"));
    document.getElementById("dash-goto-keys")?.addEventListener("click", () => {
      activeTab = "keys";
      state.dashboardTab = "keys";
      draw();
    });
    document.getElementById("dash-goto-plans")?.addEventListener("click", () => {
      activeTab = "plans";
      state.dashboardTab = "plans";
      draw();
    });

    const activateFreeAndReveal = async (btn) => {
      if (!freePlan) {
        activeTab = "plans";
        state.dashboardTab = "plans";
        draw();
        return;
      }
      const orig = btn.textContent;
      btn.disabled = true;
      btn.innerHTML = `<span class="spinner-sm"></span> Generating Key...`;
      try {
        const res = await api.post(`/api/subscriptions/activate-free?plan_id=${encodeURIComponent(freePlan.id)}`, {});
        const rev = await api.get(`/api/keys/${res.api_key.id}/reveal`);
        revealedKeys[res.api_key.id] = rev.api_key;
        selectedCredKeyId = res.api_key.id;
        showToast("Free Sandbox activated & API Key generated!", "success");
        await loadDashboardData();
        animateOverviewOnce = true;
        draw();
      } catch (err) {
        showToast(err.message, "error");
        btn.disabled = false;
        btn.textContent = orig;
      }
    };

    const createKeyAndReveal = () => {
      openCreateKeyModal(async (name) => {
        const res = await api.post("/api/keys", { name });
        const rev = await api.get(`/api/keys/${res.key.id}/reveal`);
        revealedKeys[res.key.id] = rev.api_key;
        selectedCredKeyId = res.key.id;
        showToast("New API key generated!", "success");
        await loadDashboardData();
        draw();
      });
    };

    document.getElementById("dash-generate-key-btn")?.addEventListener("click", async (e) => {
      if (!sub || sub.status !== "active") {
        if (freePlan && activeKeys.length === 0) {
          await activateFreeAndReveal(e.currentTarget);
        } else {
          activeTab = "plans";
          state.dashboardTab = "plans";
          showToast("Select a plan to generate a new API key.", "info");
          draw();
        }
        return;
      }
      if (plan && activeKeysCount >= plan.max_api_keys) {
        showToast(`Your ${plan.name} plan reached its ${plan.max_api_keys} active key limit. Upgrade or revoke an unused key.`, "info");
        activeTab = "plans";
        state.dashboardTab = "plans";
        draw();
        return;
      }
      createKeyAndReveal();
    });

    root.querySelectorAll("[data-dash-plan-action]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const action = btn.getAttribute("data-dash-plan-action");
        const planId = btn.getAttribute("data-plan-id");
        const targetPlan = plans.find((p) => p.id === planId);
        if (!targetPlan) return;

        if (action === "gen-key") {
          createKeyAndReveal();
        } else if (action === "buy" && targetPlan.price_paise === 0) {
          await activateFreeAndReveal(btn);
        } else if (action === "renew") {
          handlers.purchasePlan(planId, "renew");
        } else {
          handlers.purchasePlan(planId, "new");
        }
      });
    });

    document.getElementById("dash-run-ping")?.addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      if (!credKey) return;
      quickPingEndpoint = document.getElementById("dash-ping-ep").value;
      btn.disabled = true;
      btn.innerHTML = `<span class="spinner-sm"></span> Pinging...`;
      try {
        quickPingResult = await api.post("/api/playground/execute", {
          api_key_id: credKey.id,
          method: "GET",
          endpoint: quickPingEndpoint,
          auth_mode: "x_api_key",
          query_params: quickPingEndpoint === "/v1/geo/ip-parse" ? { ip: "8.8.8.8" } : {},
        });
        await loadDashboardData();
        draw();
      } catch (err) {
        showToast(err.message, "error");
        btn.disabled = false;
        btn.textContent = "Run Live Test ⚡";
      }
    });

    document.getElementById("logs-status-filter")?.addEventListener("change", (e) => {
      logStatusFilter = e.target.value;
      draw();
    });
    document.getElementById("logs-search-input")?.addEventListener("input", (e) => {
      logSearch = e.target.value;
      draw();
      const inp = document.getElementById("logs-search-input");
      if (inp) {
        inp.focus();
        inp.setSelectionRange(inp.value.length, inp.value.length);
      }
    });

    document.getElementById("billing-plans")?.addEventListener("click", () => {
      activeTab = "plans";
      state.dashboardTab = "plans";
      draw();
    });
    document.getElementById("billing-renew")?.addEventListener("click", () => {
      if (plan) handlers.purchasePlan(plan.id, "renew");
    });

    document.getElementById("dash-resend-verify")?.addEventListener("click", async (e) => {
      const btn = e.currentTarget;
      btn.disabled = true;
      try {
        const res = await api.post("/api/auth/resend-verification", {});
        showToast(res.message, "success");
        if (res.dev_verification_hint) {
          showToast(`Dev verify URL: ${res.dev_verification_hint}`, "info", 8000);
        }
      } catch (err) {
        showToast(err.message, "error");
      } finally {
        btn.disabled = false;
      }
    });

    document.getElementById("btn-create-key")?.addEventListener("click", createKeyAndReveal);

    root.querySelectorAll("[data-toggle-curl]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-toggle-curl");
        curlOpenKeys[id] = !curlOpenKeys[id];
        draw();
      });
    });

    root.querySelectorAll("[data-reveal-key]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.getAttribute("data-reveal-key");
        if (revealedKeys[id]) {
          delete revealedKeys[id];
          draw();
          return;
        }
        try {
          const res = await api.get(`/api/keys/${id}/reveal`);
          revealedKeys[id] = res.api_key;
          draw();
        } catch (err) {
          showToast(err.message, "error");
        }
      });
    });

    root.querySelectorAll("[data-copy-key]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.getAttribute("data-copy-key");
        try {
          let val = revealedKeys[id];
          if (!val) {
            const res = await api.get(`/api/keys/${id}/reveal`);
            val = res.api_key;
          }
          await copyToClipboard(val, "Full API key copied to clipboard!");
          const orig = btn.textContent;
          btn.textContent = "Copied ✓";
          setTimeout(() => (btn.textContent = orig), 1800);
        } catch (err) {
          showToast(err.message, "error");
        }
      });
    });

    root.querySelectorAll("[data-regen-key]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-regen-key");
        openConfirmModal({
          title: "Regenerate API Key?",
          message: "Your current key will stop working immediately and a brand-new secret linked to your plan will be generated.",
          confirmLabel: "Regenerate Key",
          onConfirm: async () => {
            const res = await api.post(`/api/keys/${id}/regenerate`, {});
            revealedKeys[id] = res.api_key;
            state.keys = state.keys.map((k) => (k.id === id ? res.key : k));
            showToast(res.message, "success");
            draw();
          },
        });
      });
    });

    root.querySelectorAll("[data-revoke-key]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-revoke-key");
        openConfirmModal({
          title: "Revoke API Key?",
          message: "Any applications using this API key will immediately receive HTTP 403 KEY_REVOKED.",
          confirmLabel: "Revoke Key",
          danger: true,
          onConfirm: async () => {
            const res = await api.post(`/api/keys/${id}/revoke`, {});
            delete revealedKeys[id];
            state.keys = state.keys.map((k) => (k.id === id ? res.key : k));
            showToast(res.message, "success");
            draw();
          },
        });
      });
    });

    root.querySelectorAll("[data-test-key]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.playgroundKeyId = btn.getAttribute("data-test-key");
        handlers.navigate("#playground");
      });
    });

    root.querySelectorAll("[data-dash-receipt]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          await openAuthenticatedUrl(`/api/payments/${btn.getAttribute("data-dash-receipt")}/receipt?format=html`);
        } catch (err) {
          showToast(err.message, "error");
        }
      });
    });

    root.querySelectorAll("[data-reconcile]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = btn.getAttribute("data-reconcile");
        btn.disabled = true;
        try {
          const res = await api.post(`/api/payments/reconcile/${id}`, {});
          showToast(`Payment reconciled: ${res.reconciled_status}`, "info");
          await renderDashboardPage(state, handlers);
        } catch (err) {
          showToast(err.message, "error");
          btn.disabled = false;
        }
      });
    });

    document.getElementById("billing-cancel-sub")?.addEventListener("click", () => {
      openConfirmModal({
        title: "Cancel Active Subscription?",
        message: "Cancelling immediately revokes all API keys associated with this subscription.",
        confirmLabel: "Cancel Subscription",
        danger: true,
        onConfirm: async () => {
          const res = await api.post("/api/subscriptions/cancel", {});
          showToast(res.message, "success");
          await renderDashboardPage(state, handlers);
        },
      });
    });

    document.getElementById("logs-refresh")?.addEventListener("click", () => renderDashboardPage(state, handlers));

    document.getElementById("profile-form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const res = await api.patch("/api/auth/profile", {
          full_name: document.getElementById("prof-name").value,
          company: document.getElementById("prof-company").value,
          phone: document.getElementById("prof-phone").value,
        });
        state.user = res.user;
        showToast(res.message, "success");
      } catch (err) {
        showToast(err.message, "error");
      }
    });

    document.getElementById("password-form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const res = await api.post("/api/auth/change-password", {
          current_password: document.getElementById("pwd-current")?.value || null,
          new_password: document.getElementById("pwd-new").value,
        });
        showToast(res.message, "success");
        e.target.reset();
      } catch (err) {
        showToast(err.message, "error");
      }
    });

    root.querySelectorAll("[data-revoke-session]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const sid = btn.getAttribute("data-revoke-session");
        try {
          await api.del(`/api/auth/sessions/${sid}`);
          showToast("Session revoked.", "success");
          await renderDashboardPage(state, handlers);
        } catch (err) {
          showToast(err.message, "error");
        }
      });
    });
  };

  draw();
}
