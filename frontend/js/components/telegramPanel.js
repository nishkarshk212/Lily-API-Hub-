/**
 * Shared Telegram Bot Management UI Components for Developer Dashboard & Admin Command Center.
 * Includes Platform Bot linking/preferences, @BotFather Bot onboarding, live controls,
 * event logs viewer, and an interactive in-browser Bot Command Simulator.
 */

import { api, copyToClipboard, esc, formatDate, showToast, statusBadge } from "../api.js";
import { closeModal, openConfirmModal } from "./modals.js";

function sanitizeTelegramHtml(raw) {
  let out = esc(raw || "").replace(/\n/g, "<br>");
  const allowedTags = ["b", "i", "code", "pre", "tg-spoiler"];
  for (const tag of allowedTags) {
    out = out
      .replace(new RegExp(`&lt;${tag}&gt;`, "g"), `<${tag}>`)
      .replace(new RegExp(`&lt;/${tag}&gt;`, "g"), `</${tag}>`);
  }
  return out;
}

export function openTelegramSimulatorModal(bot) {
  const root = document.getElementById("modal-root");
  if (!root) return;

  const history = [
    {
      role: "system",
      text: `Interactive simulator for @${bot.bot_username} (${bot.access_mode}). Click a quick command or type below.`,
    },
  ];
  let asOwner = true;

  const renderModal = () => {
    root.innerHTML = `
      <div class="modal-backdrop" id="tg-sim-backdrop">
        <div class="modal-card wide" style="max-width:740px;">
          <div class="modal-header">
            <div>
              <h3 style="margin:0 0 4px;">🧪 Telegram Bot Simulator — @${esc(bot.bot_username)}</h3>
              <p style="margin:0;font-size:13px;color:var(--text-muted);">Test real commands, gateway execution & permissions directly in your browser.</p>
            </div>
            <button class="modal-close" id="tg-sim-close">×</button>
          </div>

          <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:10px;">
            <div style="display:flex;gap:6px;flex-wrap:wrap;">
              ${["/start", "/quota", "/keys", "/status", "/uuid 2", "/dns example.com", "/hash sha256 beta", "/plans"]
                .map((cmd) => `<button type="button" class="btn btn-secondary btn-sm mono" data-sim-quick="${esc(cmd)}">${esc(cmd)}</button>`)
                .join("")}
            </div>
            <label style="display:flex;align-items:center;gap:6px;font-size:12.5px;cursor:pointer;">
              <input type="checkbox" id="tg-sim-owner" ${asOwner ? "checked" : ""} /> Simulate as Paired Owner
            </label>
          </div>

          <div id="tg-sim-feed" style="background:#0b1120;color:#e2e8f0;border:1px solid #1e293b;border-radius:12px;padding:14px;height:330px;overflow-y:auto;display:flex;flex-direction:column;gap:10px;margin-bottom:12px;">
            ${history
              .map((entry) => {
                if (entry.role === "system") {
                  return `<div style="font-size:12px;color:#94a3b8;text-align:center;">${esc(entry.text)}</div>`;
                }
                if (entry.role === "user") {
                  return `<div style="align-self:flex-end;background:#2563eb;color:#fff;padding:8px 12px;border-radius:12px 12px 2px 12px;max-width:85%;font-size:13px;" class="mono">${esc(entry.text)}</div>`;
                }
                const buttons = entry.reply_markup?.inline_keyboard || [];
                return `
                  <div style="align-self:flex-start;background:#1e293b;color:#f8fafc;padding:10px 13px;border-radius:12px 12px 12px 2px;max-width:92%;font-size:13px;line-height:1.5;">
                    <div>${sanitizeTelegramHtml(entry.text)}</div>
                    ${
                      buttons.length
                        ? `<div style="display:flex;flex-direction:column;gap:6px;margin-top:10px;">
                            ${buttons
                              .map(
                                (row) => `
                                <div style="display:flex;gap:6px;flex-wrap:wrap;">
                                  ${row
                                    .map((b) =>
                                      b.url
                                        ? `<a class="btn btn-secondary btn-sm" target="_blank" rel="noopener" href="${esc(b.url)}">${esc(b.text)} ↗</a>`
                                        : `<span style="background:#0f172a;border:1px solid #334155;border-radius:8px;padding:4px 9px;font-size:12px;color:#cbd5e1;">${esc(b.text)}</span>`
                                    )
                                    .join("")}
                                </div>`
                              )
                              .join("")}
                          </div>`
                        : ""
                    }
                  </div>
                `;
              })
              .join("")}
          </div>

          <form id="tg-sim-form" style="display:flex;gap:8px;">
            <input class="input mono" id="tg-sim-input" placeholder="Type command e.g. /call GET /v1/utils/timestamp" autocomplete="off" style="flex:1;" />
            <button type="submit" class="btn btn-primary" id="tg-sim-send">Send</button>
          </form>
        </div>
      </div>
    `;

    const feed = document.getElementById("tg-sim-feed");
    if (feed) feed.scrollTop = feed.scrollHeight;

    document.getElementById("tg-sim-close")?.addEventListener("click", closeModal);
    document.getElementById("tg-sim-backdrop")?.addEventListener("click", (e) => {
      if (e.target.id === "tg-sim-backdrop") closeModal();
    });
    document.getElementById("tg-sim-owner")?.addEventListener("change", (e) => {
      asOwner = e.target.checked;
    });

    const runCmd = async (text) => {
      const cleaned = (text || "").trim();
      if (!cleaned) return;
      history.push({ role: "user", text: cleaned });
      renderModal();
      try {
        const res = await api.post(`/api/telegram/bots/${bot.id}/simulate`, { text: cleaned, as_owner: asOwner });
        for (const rep of res.replies || []) {
          history.push({ role: "bot", text: rep.text || "", reply_markup: rep.reply_markup });
        }
      } catch (err) {
        history.push({ role: "system", text: `Error: ${err.message}` });
      }
      renderModal();
      document.getElementById("tg-sim-input")?.focus();
    };

    root.querySelectorAll("[data-sim-quick]").forEach((btn) => {
      btn.addEventListener("click", () => runCmd(btn.getAttribute("data-sim-quick")));
    });

    document.getElementById("tg-sim-form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const inp = document.getElementById("tg-sim-input");
      await runCmd(inp?.value || "");
    });
  };

  renderModal();
}

export function openTelegramEventsModal(botName, events) {
  const root = document.getElementById("modal-root");
  if (!root) return;

  root.innerHTML = `
    <div class="modal-backdrop" id="tg-ev-backdrop">
      <div class="modal-card wide" style="max-width:780px;">
        <div class="modal-header">
          <div>
            <h3 style="margin:0 0 4px;">📜 Telegram Bot Activity — @${esc(botName)}</h3>
            <p style="margin:0;font-size:13px;color:var(--text-muted);">Latest 50 commands, inline callbacks, alerts & error traces.</p>
          </div>
          <button class="modal-close" id="tg-ev-close">×</button>
        </div>
        <div class="table-wrap" style="max-height:380px;overflow-y:auto;">
          <table class="data-table">
            <thead><tr><th>Type</th><th>Command / Action</th><th>User</th><th>Status</th><th>Latency</th><th>Detail</th><th>Time</th></tr></thead>
            <tbody>
              ${
                events.length === 0
                  ? `<tr><td colspan="7" style="text-align:center;color:var(--text-muted);">No bot activity recorded yet.</td></tr>`
                  : events
                      .map(
                        (ev) => `
                        <tr>
                          <td><span class="badge badge-neutral">${esc(ev.event_type)}</span></td>
                          <td class="mono" style="font-size:12px;">${esc(ev.command_or_action)}</td>
                          <td class="mono" style="font-size:12px;">${esc(ev.telegram_username ? `@${ev.telegram_username}` : ev.telegram_user_id || "-")}</td>
                          <td>${statusBadge(ev.status === "ok" ? "active" : ev.status === "denied" ? "pending" : "failed")}</td>
                          <td class="mono">${ev.latency_ms}ms</td>
                          <td style="font-size:12px;max-width:200px;">${esc(ev.detail || "—")}</td>
                          <td style="font-size:11.5px;">${formatDate(ev.created_at)}</td>
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

  document.getElementById("tg-ev-close")?.addEventListener("click", closeModal);
  document.getElementById("tg-ev-backdrop")?.addEventListener("click", (e) => {
    if (e.target.id === "tg-ev-backdrop") closeModal();
  });
}

export function renderUserTelegramTab({ tgStatus, keys, editingBotId }) {
  const activeKeys = (keys || []).filter((k) => k.status === "active");
  const pbot = tgStatus?.platform_bot || { configured: false };
  const bots = tgStatus?.bots || [];
  const recommendedMode = tgStatus?.recommended_mode || "polling";

  const platformCardHtml = pbot.configured
    ? `
      <div class="glass-card panel-card" style="border-color:rgba(14,165,233,0.35);">
        <div class="panel-head">
          <div>
            <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
              <h3 style="margin:0;">✈ Official Platform Telegram Bot (@${esc(pbot.bot_username)})</h3>
              ${pbot.linked ? `<span class="badge badge-success">Account Linked</span>` : `<span class="badge badge-warning">Not Linked</span>`}
            </div>
            <p style="margin:4px 0 0;font-size:13px;color:var(--text-muted);">
              Connect your personal Telegram chat in 1 click to manage keys, check quotas &amp; receive real-time alerts.
            </p>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap;">
            <a class="btn btn-primary btn-sm" href="${esc(pbot.connect_deep_link)}" target="_blank" rel="noopener">
              ${pbot.linked ? "Open @"+esc(pbot.bot_username) : "Connect in Telegram ↗"}
            </a>
            <button type="button" class="btn btn-secondary btn-sm" id="tg-copy-platform-cmd">Copy /link Code</button>
          </div>
        </div>

        ${
          pbot.linked && pbot.link
            ? `
            <div style="background:#f8fafc;border:1px solid var(--border-subtle);border-radius:12px;padding:14px;display:flex;flex-direction:column;gap:12px;">
              <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
                <span style="font-size:13px;">Linked Telegram: <strong class="mono">${esc(pbot.link.telegram_username ? `@${pbot.link.telegram_username}` : pbot.link.telegram_first_name)}</strong> (ID: <span class="mono">${esc(pbot.link.telegram_user_id)}</span>)</span>
                <div style="display:flex;gap:8px;">
                  <button type="button" class="btn btn-secondary btn-sm" id="tg-platform-test-alert">🔔 Send Test Alert</button>
                  <button type="button" class="btn btn-danger btn-sm" id="tg-platform-unlink">Unlink</button>
                </div>
              </div>
              <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;font-size:13px;">
                <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
                  <input type="checkbox" class="tg-pref-cb" data-pref="notify_quota_alerts" ${pbot.link.notify_quota_alerts ? "checked" : ""} /> Quota Warnings (80% / 100%)
                </label>
                <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
                  <input type="checkbox" class="tg-pref-cb" data-pref="notify_security_alerts" ${pbot.link.notify_security_alerts ? "checked" : ""} /> Key Security Alerts
                </label>
                <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
                  <input type="checkbox" class="tg-pref-cb" data-pref="notify_payment_alerts" ${pbot.link.notify_payment_alerts ? "checked" : ""} /> Razorpay Payment Alerts
                </label>
                <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
                  <input type="checkbox" class="tg-pref-cb" data-pref="notify_gateway_errors" ${pbot.link.notify_gateway_errors ? "checked" : ""} /> Upstream 5xx Error Alerts
                </label>
              </div>
            </div>
          `
            : `
            <div style="background:#f8fafc;border:1px solid var(--border-subtle);border-radius:12px;padding:12px 14px;font-size:13px;color:var(--text-secondary);">
              Click <strong>Connect in Telegram ↗</strong> and tap <strong>Start</strong> in Telegram — or send <code class="mono">${esc(pbot.manual_link_command)}</code> to <a href="${esc(pbot.bot_url)}" target="_blank" rel="noopener">@${esc(pbot.bot_username)}</a>.
            </div>
          `
        }
      </div>
    `
    : "";

  const botsListHtml =
    bots.length === 0
      ? `<p style="color:var(--text-muted);font-size:13.5px;margin:0;">No custom Telegram bots connected yet. Paste your <code>@BotFather</code> token above to launch your first bot.</p>`
      : bots
          .map((bot) => {
            const isEditing = editingBotId === bot.id;
            return `
              <div class="key-card" style="margin-bottom:14px;">
                <div class="key-card-top">
                  <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                    <strong style="font-size:15.5px;">${esc(bot.bot_name)}</strong>
                    <a class="mono" href="${esc(bot.bot_url)}" target="_blank" rel="noopener" style="font-size:13px;color:#2563eb;font-weight:600;">@${esc(bot.bot_username)}</a>
                    ${bot.is_active ? `<span class="badge badge-success">Active</span>` : `<span class="badge badge-warning">Paused</span>`}
                    <span class="badge badge-neutral">${esc(bot.connection_mode === "webhook" ? (bot.webhook_active ? "Webhook Live" : "Webhook") : "Polling")}</span>
                    <span class="badge badge-info">${esc(bot.access_mode === "public_gateway" ? "Public Gateway" : "Owner Only")}</span>
                  </div>
                  <div style="font-size:12.5px;color:var(--text-muted);">
                    ${bot.total_messages_handled || 0} msgs handled · Token: <span class="mono">${esc(bot.token_fingerprint)}</span>
                  </div>
                </div>

                <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;background:#f8fafc;border:1px solid var(--border-subtle);border-radius:10px;padding:10px 12px;font-size:12.5px;">
                  <div>
                    <span style="color:var(--text-muted);display:block;">Owner Pairing</span>
                    <strong>${bot.is_paired ? `Paired (${esc(bot.paired_telegram_username ? `@${bot.paired_telegram_username}` : bot.paired_telegram_user_id)})` : "Pending — Click Pair in Telegram"}</strong>
                  </div>
                  <div>
                    <span style="color:var(--text-muted);display:block;">Bound API Key</span>
                    <strong class="mono">${bot.bound_key ? `${esc(bot.bound_key.name)} (${esc(bot.bound_key.masked_key)})` : "Auto (Latest Active Key)"}</strong>
                  </div>
                  <div>
                    <span style="color:var(--text-muted);display:block;">Custom /ask Proxy Route</span>
                    <strong class="mono">${bot.custom_proxy_path ? `${esc(bot.custom_proxy_method)} ${esc(bot.custom_proxy_path)}` : "Built-in Gateway Tools"}</strong>
                  </div>
                </div>

                ${
                  bot.webhook_url
                    ? `<div style="font-size:11.5px;color:var(--text-muted);" class="mono">Webhook: ${esc(bot.webhook_url)}</div>`
                    : ""
                }
                ${
                  bot.last_error
                    ? `<div style="font-size:12px;color:var(--danger);background:var(--danger-bg);padding:8px 10px;border-radius:8px;">Last Notice: ${esc(bot.last_error)}</div>`
                    : ""
                }

                <div class="key-actions-row">
                  <a class="btn btn-primary btn-sm" href="${esc(bot.pair_deep_link)}" target="_blank" rel="noopener">🔗 ${bot.is_paired ? "Open Bot" : "Pair in Telegram"} ↗</a>
                  <button type="button" class="btn btn-secondary btn-sm" data-tg-sim="${esc(bot.id)}">🧪 Test Simulator</button>
                  <button type="button" class="btn btn-secondary btn-sm" data-tg-events="${esc(bot.id)}">📜 Bot Logs</button>
                  <button type="button" class="btn btn-secondary btn-sm" data-tg-sync="${esc(bot.id)}">⚡ Sync Webhook</button>
                  ${
                    bot.connection_mode === "polling"
                      ? `<button type="button" class="btn btn-secondary btn-sm" data-tg-poll="${esc(bot.id)}">↻ Pull Updates</button>`
                      : ""
                  }
                  ${
                    bot.is_paired
                      ? `<button type="button" class="btn btn-secondary btn-sm" data-tg-ping="${esc(bot.id)}">🔔 Test Ping</button>`
                      : ""
                  }
                  <button type="button" class="btn btn-secondary btn-sm" data-tg-edit="${esc(bot.id)}">${isEditing ? "Close Settings" : "⚙ Configure"}</button>
                  <button type="button" class="btn btn-danger btn-sm" data-tg-del="${esc(bot.id)}">Disconnect</button>
                </div>

                ${
                  isEditing
                    ? `
                    <form class="tg-edit-form" data-tg-edit-form="${esc(bot.id)}" style="margin-top:8px;padding-top:12px;border-top:1px solid var(--border-subtle);display:flex;flex-direction:column;gap:10px;">
                      <div class="two-col">
                        <div class="field" style="margin:0;"><label>Bot Display Name</label><input class="input" name="bot_name" value="${esc(bot.bot_name)}" required /></div>
                        <div class="field" style="margin:0;">
                          <label>Bound API Key</label>
                          <select class="select" name="api_key_id">
                            <option value="">Auto (Latest Active Key)</option>
                            ${activeKeys
                              .map((k) => `<option value="${esc(k.id)}" ${bot.api_key_id === k.id ? "selected" : ""}>${esc(k.name)} (${esc(k.masked_key)})</option>`)
                              .join("")}
                          </select>
                        </div>
                      </div>
                      <div class="two-col">
                        <div class="field" style="margin:0;">
                          <label>Access Mode</label>
                          <select class="select" name="access_mode">
                            <option value="owner_only" ${bot.access_mode === "owner_only" ? "selected" : ""}>Owner Only (Private Keys, Quotas &amp; Gateway)</option>
                            <option value="public_gateway" ${bot.access_mode === "public_gateway" ? "selected" : ""}>Public Gateway Bot (Public /status, /hash, /ask; Keys stay Owner-Only)</option>
                          </select>
                        </div>
                        <div class="field" style="margin:0;">
                          <label>Connection Transport</label>
                          <select class="select" name="connection_mode">
                            <option value="webhook" ${bot.connection_mode === "webhook" ? "selected" : ""}>Webhook (Recommended on HTTPS)</option>
                            <option value="polling" ${bot.connection_mode === "polling" ? "selected" : ""}>Long Polling (Works on Local HTTP)</option>
                          </select>
                        </div>
                      </div>
                      <div class="two-col">
                        <div class="field" style="margin:0;"><label>Custom /ask Gateway Path (Optional)</label><input class="input mono" name="custom_proxy_path" value="${esc(bot.custom_proxy_path)}" placeholder="/v1/network/echo" /></div>
                        <div class="field" style="margin:0;">
                          <label>Custom Route Method</label>
                          <select class="select" name="custom_proxy_method">
                            <option value="POST" ${bot.custom_proxy_method === "POST" ? "selected" : ""}>POST</option>
                            <option value="GET" ${bot.custom_proxy_method === "GET" ? "selected" : ""}>GET</option>
                          </select>
                        </div>
                      </div>
                      <div class="field" style="margin:0;"><label>Custom Welcome Message (Optional)</label><textarea class="textarea" name="welcome_message" rows="2">${esc(bot.welcome_message)}</textarea></div>
                      <div style="display:flex;gap:16px;flex-wrap:wrap;font-size:13px;">
                        <label style="display:flex;align-items:center;gap:6px;cursor:pointer;"><input type="checkbox" name="is_active" ${bot.is_active ? "checked" : ""} /> Bot Active</label>
                        <label style="display:flex;align-items:center;gap:6px;cursor:pointer;"><input type="checkbox" name="forward_plain_text" ${bot.forward_plain_text ? "checked" : ""} /> Auto-forward plain text to Custom Route</label>
                        <label style="display:flex;align-items:center;gap:6px;cursor:pointer;"><input type="checkbox" name="notify_owner_alerts" ${bot.notify_owner_alerts ? "checked" : ""} /> Send Key/Quota/Billing Alerts to Owner</label>
                      </div>
                      <div><button type="submit" class="btn btn-primary btn-sm">Save Bot Configuration</button></div>
                    </form>
                  `
                    : ""
                }
              </div>
            `;
          })
          .join("");

  return `
    <div class="dash-tab-stage">
      ${platformCardHtml}

      <div class="glass-card panel-card">
        <div class="panel-head">
          <div>
            <h2>✈ Connect Your Telegram Bot from Website</h2>
            <p style="margin:4px 0 0;font-size:13px;color:var(--text-muted);">
              Create a bot with <code>@BotFather</code> in Telegram (<code>/newbot</code>), paste its Bot Token below, and Beta auto-configures commands, interactive inline menus &amp; live gateway execution.
            </p>
          </div>
          <span class="badge ${tgStatus?.public_https_ready ? "badge-success" : "badge-info"}">
            ${tgStatus?.public_https_ready ? "HTTPS Webhook Ready" : "Local Polling Mode Ready"}
          </span>
        </div>

        <form id="tg-connect-form">
          <div class="two-col">
            <div class="field">
              <label>Telegram Bot Token (from @BotFather)</label>
              <input class="input mono" type="password" id="tg-new-token" required minlength="20" placeholder="7123456789:AAF_your_botfather_token" />
            </div>
            <div class="field">
              <label>Bot Label (Optional — defaults to Telegram name)</label>
              <input class="input" type="text" id="tg-new-name" maxlength="120" placeholder="Sonic Network Assistant" />
            </div>
          </div>

          <div class="two-col">
            <div class="field">
              <label>Bind to API Key (Used for /status, /hash, /dns, /call, /ask)</label>
              <select class="select" id="tg-new-key">
                <option value="">Auto-select my active API key</option>
                ${activeKeys
                  .map((k) => `<option value="${esc(k.id)}">${esc(k.name)} (${esc(k.masked_key)})</option>`)
                  .join("")}
              </select>
            </div>
            <div class="field">
              <label>Bot Access Scope</label>
              <select class="select" id="tg-new-access">
                <option value="owner_only">Owner Only (Private DevOps + Keys + Alerts)</option>
                <option value="public_gateway">Public Gateway Bot (Public /v1 Tools; Keys Owner-Only)</option>
              </select>
            </div>
          </div>

          <div class="two-col">
            <div class="field">
              <label>Custom /ask Upstream Endpoint (Optional)</label>
              <input class="input mono" id="tg-new-proxy" placeholder="/v1/network/echo (or your upstream route)" />
            </div>
            <div class="field">
              <label>Connection Mode</label>
              <select class="select" id="tg-new-mode">
                <option value="${esc(recommendedMode)}">Auto (${recommendedMode === "webhook" ? "Webhook on HTTPS" : "Long Polling"})</option>
                <option value="webhook">Webhook (HTTPS Server)</option>
                <option value="polling">Polling (Works without HTTPS)</option>
              </select>
            </div>
          </div>

          <div class="field">
            <label>Custom Bot Welcome Message (Optional)</label>
            <textarea class="textarea" id="tg-new-welcome" rows="2" placeholder="Welcome to our Beta-powered Telegram Bot! Tap a button or run /help."></textarea>
          </div>

          <div style="display:flex;gap:18px;flex-wrap:wrap;margin-bottom:14px;font-size:13px;">
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
              <input type="checkbox" id="tg-new-fwd-text" /> Forward plain non-command messages to Custom /ask Route
            </label>
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
              <input type="checkbox" id="tg-new-owner-alerts" checked /> Send API Key, Quota (80%/100%) &amp; Billing Alerts via this bot
            </label>
          </div>

          <button type="submit" class="btn btn-primary" id="tg-connect-btn">Connect &amp; Activate Telegram Bot</button>
        </form>
      </div>

      <div class="glass-card panel-card">
        <div class="panel-head">
          <div>
            <h3>Connected Telegram Bots (${bots.length})</h3>
            <p style="margin:3px 0 0;font-size:13px;color:var(--text-muted);">
              Includes built-in <code>/start</code>, <code>/menu</code>, <code>/quota</code>, <code>/keys</code>, <code>/logs</code>, <code>/plans</code>, <code>/alerts</code>, <code>/status</code>, <code>/uuid</code>, <code>/hash</code>, <code>/ip</code>, <code>/dns</code>, <code>/time</code>, <code>/json</code>, <code>/call</code>, and <code>/ask</code>.
            </p>
          </div>
          <button type="button" class="btn btn-secondary btn-sm" id="tg-refresh-btn">↻ Refresh Status</button>
        </div>
        ${botsListHtml}
      </div>
    </div>
  `;
}

export function bindUserTelegramEvents(root, { tgStatus, bots, reloadTelegramTab, setEditingBotId }) {
  const pbot = tgStatus?.platform_bot || {};

  document.getElementById("tg-copy-platform-cmd")?.addEventListener("click", () => {
    if (pbot.manual_link_command) copyToClipboard(pbot.manual_link_command, "Copied /link command!");
  });

  document.getElementById("tg-platform-test-alert")?.addEventListener("click", async () => {
    try {
      const res = await api.post("/api/telegram/platform/test-alert", {});
      showToast(res.message, "success");
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  document.getElementById("tg-platform-unlink")?.addEventListener("click", () => {
    openConfirmModal({
      title: "Unlink Telegram Account?",
      message: "You will stop receiving platform bot notifications until reconnected.",
      confirmLabel: "Unlink",
      danger: true,
      onConfirm: async () => {
        const res = await api.del("/api/telegram/platform/unlink");
        showToast(res.message, "success");
        await reloadTelegramTab();
      },
    });
  });

  root.querySelectorAll(".tg-pref-cb").forEach((cb) => {
    cb.addEventListener("change", async () => {
      const pref = cb.getAttribute("data-pref");
      try {
        await api.patch("/api/telegram/platform/preferences", { [pref]: cb.checked });
        showToast("Alert preference saved.", "success", 2000);
      } catch (err) {
        cb.checked = !cb.checked;
        showToast(err.message, "error");
      }
    });
  });

  document.getElementById("tg-connect-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("tg-connect-btn");
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner-sm"></span> Connecting Bot...`;
    try {
      const res = await api.post("/api/telegram/bots", {
        bot_token: document.getElementById("tg-new-token").value.trim(),
        bot_name: document.getElementById("tg-new-name").value.trim() || null,
        api_key_id: document.getElementById("tg-new-key").value || null,
        access_mode: document.getElementById("tg-new-access").value,
        connection_mode: document.getElementById("tg-new-mode").value,
        custom_proxy_path: document.getElementById("tg-new-proxy").value.trim(),
        welcome_message: document.getElementById("tg-new-welcome").value.trim(),
        forward_plain_text: document.getElementById("tg-new-fwd-text").checked,
        notify_owner_alerts: document.getElementById("tg-new-owner-alerts").checked,
      });
      showToast(`${res.message} Click "Pair in Telegram" to complete linking.`, "success", 5500);
      await reloadTelegramTab();
    } catch (err) {
      showToast(err.message, "error", 6000);
      btn.disabled = false;
      btn.textContent = "Connect & Activate Telegram Bot";
    }
  });

  document.getElementById("tg-refresh-btn")?.addEventListener("click", reloadTelegramTab);

  root.querySelectorAll("[data-tg-sim]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const bot = bots.find((b) => b.id === btn.getAttribute("data-tg-sim"));
      if (bot) openTelegramSimulatorModal(bot);
    });
  });

  root.querySelectorAll("[data-tg-events]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.getAttribute("data-tg-events");
      const bot = bots.find((b) => b.id === id);
      try {
        const res = await api.get(`/api/telegram/bots/${id}/events`);
        openTelegramEventsModal(bot?.bot_username || "bot", res.events || []);
      } catch (err) {
        showToast(err.message, "error");
      }
    });
  });

  root.querySelectorAll("[data-tg-sync]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.getAttribute("data-tg-sync");
      btn.disabled = true;
      try {
        const res = await api.post(`/api/telegram/bots/${id}/sync`, {});
        showToast(res.message, "success");
        await reloadTelegramTab();
      } catch (err) {
        showToast(err.message, "error");
        btn.disabled = false;
      }
    });
  });

  root.querySelectorAll("[data-tg-poll]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.getAttribute("data-tg-poll");
      btn.disabled = true;
      try {
        const res = await api.post(`/api/telegram/bots/${id}/poll`, {});
        showToast(res.message, "info");
        await reloadTelegramTab();
      } catch (err) {
        showToast(err.message, "error");
        btn.disabled = false;
      }
    });
  });

  root.querySelectorAll("[data-tg-ping]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.getAttribute("data-tg-ping");
      try {
        const res = await api.post(`/api/telegram/bots/${id}/test-message`, {});
        showToast(res.message, "success");
      } catch (err) {
        showToast(err.message, "error");
      }
    });
  });

  root.querySelectorAll("[data-tg-edit]").forEach((btn) => {
    btn.addEventListener("click", () => {
      setEditingBotId(btn.getAttribute("data-tg-edit"));
    });
  });

  root.querySelectorAll("[data-tg-edit-form]").forEach((form) => {
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const id = form.getAttribute("data-tg-edit-form");
      const fd = new FormData(form);
      try {
        const res = await api.patch(`/api/telegram/bots/${id}`, {
          bot_name: fd.get("bot_name"),
          api_key_id: fd.get("api_key_id") || "",
          access_mode: fd.get("access_mode"),
          connection_mode: fd.get("connection_mode"),
          custom_proxy_path: fd.get("custom_proxy_path") || "",
          custom_proxy_method: fd.get("custom_proxy_method"),
          welcome_message: fd.get("welcome_message") || "",
          is_active: form.querySelector('[name="is_active"]').checked,
          forward_plain_text: form.querySelector('[name="forward_plain_text"]').checked,
          notify_owner_alerts: form.querySelector('[name="notify_owner_alerts"]').checked,
        });
        showToast(res.message, "success");
        setEditingBotId("");
        await reloadTelegramTab();
      } catch (err) {
        showToast(err.message, "error");
      }
    });
  });

  root.querySelectorAll("[data-tg-del]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-tg-del");
      openConfirmModal({
        title: "Disconnect Telegram Bot?",
        message: "This removes the Telegram webhook and deletes the stored bot credentials from this website.",
        confirmLabel: "Disconnect Bot",
        danger: true,
        onConfirm: async () => {
          const res = await api.del(`/api/telegram/bots/${id}`);
          showToast(res.message, "success");
          await reloadTelegramTab();
        },
      });
    });
  });
}

export function renderAdminTelegramTab(tgAdmin) {
  const pbot = tgAdmin?.platform_bot;
  const links = tgAdmin?.linked_users || [];
  const events = tgAdmin?.events || [];
  const recMode = tgAdmin?.recommended_mode || "polling";

  return `
    <div class="admin-panel" style="--panel-accent:#0284c7;">
      <div class="admin-panel-head">
        <div>
          <h2>✈ Official Platform Telegram Bot</h2>
          <p style="margin:3px 0 0;font-size:12.5px;color:var(--text-muted);">
            Configure a platform-wide Telegram bot so every signed-in user gets 1-click account linking, push alerts &amp; admin telemetry.
          </p>
        </div>
        <div class="admin-toolbar">
          ${pbot ? `<span class="badge ${pbot.is_active ? "badge-success" : "badge-warning"}">@${esc(pbot.bot_username)}</span>` : `<span class="badge badge-neutral">Not Configured</span>`}
          ${pbot ? `<button type="button" class="btn btn-secondary btn-sm" id="adm-tg-sync">⚡ Sync Webhook</button>` : ""}
          ${pbot && pbot.connection_mode === "polling" ? `<button type="button" class="btn btn-secondary btn-sm" id="adm-tg-poll">↻ Poll Now</button>` : ""}
          ${pbot ? `<button type="button" class="btn btn-danger btn-sm" id="adm-tg-remove">Disconnect</button>` : ""}
        </div>
      </div>

      ${
        pbot
          ? `
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-bottom:16px;">
            <div style="background:#f8fafc;border:1px solid var(--border-subtle);border-radius:10px;padding:10px 12px;">
              <div style="font-size:11.5px;color:var(--text-muted);">Bot Handle</div>
              <a class="mono" style="font-weight:700;color:#2563eb;" href="${esc(pbot.bot_url)}" target="_blank" rel="noopener">@${esc(pbot.bot_username)}</a>
            </div>
            <div style="background:#f8fafc;border:1px solid var(--border-subtle);border-radius:10px;padding:10px 12px;">
              <div style="font-size:11.5px;color:var(--text-muted);">Transport Status</div>
              <strong>${esc(pbot.connection_mode === "webhook" ? (pbot.webhook_active ? "Webhook Live ✓" : "Webhook") : "Polling")}</strong>
            </div>
            <div style="background:#f8fafc;border:1px solid var(--border-subtle);border-radius:10px;padding:10px 12px;">
              <div style="font-size:11.5px;color:var(--text-muted);">Linked Users / Custom Bots</div>
              <strong>${links.length} users · ${tgAdmin.custom_bots_count || 0} custom bots</strong>
            </div>
            <div style="background:#f8fafc;border:1px solid var(--border-subtle);border-radius:10px;padding:10px 12px;">
              <div style="font-size:11.5px;color:var(--text-muted);">Token Fingerprint</div>
              <strong class="mono">${esc(pbot.token_fingerprint)}</strong>
            </div>
          </div>
        `
          : ""
      }

      <form id="adm-tg-form">
        <div class="two-col">
          <div class="field">
            <label>${pbot ? "Rotate @BotFather Token (leave blank to keep current)" : "Official BotFather Token"}</label>
            <input class="input mono" type="password" id="adm-tg-token" ${pbot ? "" : "required"} placeholder="7123456789:AAF..." />
          </div>
          <div class="field">
            <label>Bot Display Name</label>
            <input class="input" id="adm-tg-name" value="${esc(pbot?.bot_name || "Beta Official Bot")}" />
          </div>
        </div>

        <div class="two-col">
          <div class="field">
            <label>Connection Mode</label>
            <select class="select" id="adm-tg-mode">
              <option value="webhook" ${(pbot?.connection_mode || recMode) === "webhook" ? "selected" : ""}>Webhook (HTTPS)</option>
              <option value="polling" ${(pbot?.connection_mode || recMode) === "polling" ? "selected" : ""}>Polling (Local HTTP)</option>
            </select>
          </div>
          <div class="field">
            <label>Custom /ask Gateway Path (Optional)</label>
            <input class="input mono" id="adm-tg-proxy" value="${esc(pbot?.custom_proxy_path || "")}" placeholder="/v1/network/echo" />
          </div>
        </div>

        <div class="field">
          <label>Welcome Message</label>
          <textarea class="textarea" id="adm-tg-welcome" rows="2">${esc(pbot?.welcome_message || "")}</textarea>
        </div>

        <div style="display:flex;gap:18px;flex-wrap:wrap;margin-bottom:14px;font-size:13px;">
          <label style="display:flex;align-items:center;gap:6px;cursor:pointer;"><input type="checkbox" id="adm-tg-active" ${pbot?.is_active !== false ? "checked" : ""} /> Bot Active</label>
          <label style="display:flex;align-items:center;gap:6px;cursor:pointer;"><input type="checkbox" id="adm-tg-fwd" ${pbot?.forward_plain_text ? "checked" : ""} /> Forward plain messages to /ask path</label>
        </div>

        <button type="submit" class="btn btn-primary" id="adm-tg-save">${pbot ? "Update Official Telegram Bot" : "Connect Official Telegram Bot"}</button>
      </form>
    </div>

    ${
      pbot
        ? `
        <div class="admin-panel" style="--panel-accent:#10b981;">
          <div class="admin-panel-head"><h3>📢 Broadcast Announcement to Linked Users</h3></div>
          <form id="adm-tg-broadcast-form" style="display:flex;flex-direction:column;gap:10px;">
            <textarea class="textarea" id="adm-tg-broadcast-msg" rows="2" required placeholder="Scheduled maintenance tonight at 02:00 UTC or new /v1 endpoint launched!"></textarea>
            <div style="display:flex;gap:10px;flex-wrap:wrap;">
              <button type="submit" class="btn btn-primary btn-sm">Send to All Linked Chats (${links.filter((l) => l.is_active).length})</button>
              <button type="button" class="btn btn-secondary btn-sm" id="adm-tg-test-broadcast">Test Send to My Linked Chat</button>
            </div>
          </form>
        </div>
      `
        : ""
    }

    <div class="admin-panel" style="--panel-accent:#6366f1;">
      <div class="admin-panel-head"><h3>Linked User Telegram Chats (${links.length})</h3></div>
      <div class="table-wrap" style="max-height:240px;overflow-y:auto;">
        <table class="data-table">
          <thead><tr><th>Website User</th><th>Telegram</th><th>Alert Subscriptions</th><th>Status</th><th>Updated</th></tr></thead>
          <tbody>
            ${
              links.length === 0
                ? `<tr><td colspan="5" style="text-align:center;color:var(--text-muted);">No users have linked Telegram yet.</td></tr>`
                : links
                    .map(
                      (l) => `
                      <tr>
                        <td>${esc(l.user_email)}</td>
                        <td class="mono">${esc(l.telegram_username ? `@${l.telegram_username}` : l.telegram_first_name)} (${esc(l.telegram_user_id)})</td>
                        <td style="font-size:12px;">
                          ${l.notify_quota_alerts ? "Quota " : ""}${l.notify_security_alerts ? "Keys " : ""}${l.notify_payment_alerts ? "Billing " : ""}${l.notify_gateway_errors ? "5xx" : ""}
                        </td>
                        <td>${statusBadge(l.is_active ? "active" : "revoked")}</td>
                        <td style="font-size:12px;">${formatDate(l.updated_at)}</td>
                      </tr>`
                    )
                    .join("")
            }
          </tbody>
        </table>
      </div>
    </div>

    <div class="admin-panel" style="--panel-accent:#ec4899;">
      <div class="admin-panel-head"><h3>Platform-Wide Telegram Events (Latest 60)</h3></div>
      <div class="table-wrap" style="max-height:280px;overflow-y:auto;">
        <table class="data-table">
          <thead><tr><th>Bot</th><th>Type</th><th>Action</th><th>Status</th><th>Latency</th><th>Detail</th><th>Time</th></tr></thead>
          <tbody>
            ${
              events.length === 0
                ? `<tr><td colspan="7" style="text-align:center;color:var(--text-muted);">No Telegram events yet.</td></tr>`
                : events
                    .map(
                      (ev) => `
                      <tr>
                        <td class="mono">${esc(ev.bot_username)}</td>
                        <td><span class="badge badge-neutral">${esc(ev.event_type)}</span></td>
                        <td class="mono" style="font-size:12px;">${esc(ev.command_or_action)}</td>
                        <td>${statusBadge(ev.status === "ok" ? "active" : ev.status === "denied" ? "pending" : "failed")}</td>
                        <td class="mono">${ev.latency_ms}ms</td>
                        <td style="font-size:12px;">${esc(ev.detail || "—")}</td>
                        <td style="font-size:11.5px;">${formatDate(ev.created_at)}</td>
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

export function bindAdminTelegramEvents({ reloadAdmin }) {
  document.getElementById("adm-tg-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("adm-tg-save");
    btn.disabled = true;
    try {
      const res = await api.put("/api/admin/telegram/platform-bot", {
        bot_token: document.getElementById("adm-tg-token").value.trim() || null,
        bot_name: document.getElementById("adm-tg-name").value.trim() || null,
        connection_mode: document.getElementById("adm-tg-mode").value,
        custom_proxy_path: document.getElementById("adm-tg-proxy").value.trim(),
        welcome_message: document.getElementById("adm-tg-welcome").value.trim(),
        is_active: document.getElementById("adm-tg-active").checked,
        forward_plain_text: document.getElementById("adm-tg-fwd").checked,
      });
      showToast(res.message, "success");
      await reloadAdmin();
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
    }
  });

  document.getElementById("adm-tg-sync")?.addEventListener("click", async () => {
    try {
      const res = await api.post("/api/admin/telegram/platform-bot/sync", {});
      showToast(res.message, "success");
      await reloadAdmin();
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  document.getElementById("adm-tg-poll")?.addEventListener("click", async () => {
    try {
      const res = await api.post("/api/admin/telegram/platform-bot/poll", {});
      showToast(res.message, "info");
      await reloadAdmin();
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  document.getElementById("adm-tg-remove")?.addEventListener("click", () => {
    openConfirmModal({
      title: "Disconnect Official Platform Bot?",
      message: "Removes the webhook and deletes the stored platform Telegram bot configuration.",
      confirmLabel: "Disconnect",
      danger: true,
      onConfirm: async () => {
        const res = await api.del("/api/admin/telegram/platform-bot");
        showToast(res.message, "success");
        await reloadAdmin();
      },
    });
  });

  const sendBroadcast = async (testOnly) => {
    const msg = document.getElementById("adm-tg-broadcast-msg")?.value.trim();
    if (!msg) return;
    try {
      const res = await api.post("/api/admin/telegram/platform-bot/broadcast", { message: msg, test_only: testOnly });
      showToast(res.message, "success");
      await reloadAdmin();
    } catch (err) {
      showToast(err.message, "error");
    }
  };

  document.getElementById("adm-tg-broadcast-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    await sendBroadcast(false);
  });
  document.getElementById("adm-tg-test-broadcast")?.addEventListener("click", () => sendBroadcast(true));
}
