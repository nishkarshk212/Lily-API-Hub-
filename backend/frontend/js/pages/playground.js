/**
 * Interactive API Testing Playground.
 */

import { api, copyToClipboard, esc, getBrand, highlightJson, showToast } from "../api.js";

export async function renderPlaygroundPage(state, handlers) {
  const root = document.getElementById("app-root");
  if (!root) return;
  const brand = getBrand(state);

  let keys = state.keys || [];
  if (state.user && keys.length === 0) {
    try {
      const res = await api.get("/api/keys");
      keys = res.keys || [];
      state.keys = keys;
    } catch {
      keys = [];
    }
  }

  const activeKeys = keys.filter((k) => k.status === "active");
  const presets = state.overview?.endpoints || [];
  const seedEp = state.playgroundPreset || presets[0] || {
    method: "GET",
    path: "/v1/status",
    sample_query: {},
    sample_body: null,
  };
  state.playgroundPreset = null;

  let method = seedEp.method || "GET";
  let endpoint = seedEp.path || "/v1/status";
  let selectedKeyId = state.playgroundKeyId || (activeKeys[0]?.id || "");
  let rawCustomKey = "";
  let authMode = "x_api_key";
  let queryRows = Object.entries(seedEp.sample_query || {}).map(([k, v]) => ({ k, v: String(v) }));
  let headerRows = [{ k: "Accept", v: "application/json" }];
  let bodyText = seedEp.sample_body ? JSON.stringify(seedEp.sample_body, null, 2) : "";
  let lastResult = null;

  const draw = () => {
    const respStatusColor = !lastResult
      ? "neutral"
      : lastResult.status_code < 400
      ? "success"
      : lastResult.status_code === 429
      ? "warning"
      : "danger";

    root.innerHTML = `
      <div class="container" style="padding:28px 24px 64px;">
        <div class="panel-head" style="margin-bottom:20px;">
          <div>
            <h1 style="margin:0 0 4px;font-size:24px;">API Testing Playground</h1>
            <p style="margin:0;color:var(--text-muted);font-size:14px;">
              Execute live HTTP requests through the ${esc(brand.companyName)} Gateway with real quota, rate-limit, and upstream proxy enforcement.
            </p>
          </div>
          <button class="btn btn-secondary btn-sm" id="pg-back-dash">← Dashboard</button>
        </div>

        <div class="playground-grid">
          <div class="glass-card panel-card">
            <div class="field">
              <label>Load Preset Endpoint</label>
              <select class="select" id="pg-preset">
                <option value="">Custom Endpoint...</option>
                ${presets
                  .map(
                    (ep, idx) =>
                      `<option value="${idx}" ${ep.path === endpoint && ep.method === method ? "selected" : ""}>${esc(ep.method)} ${esc(ep.path)} — ${esc(ep.title)}</option>`
                  )
                  .join("")}
              </select>
            </div>

            <div class="two-col" style="grid-template-columns:130px 1fr;">
              <div class="field">
                <label>Method</label>
                <select class="select mono" id="pg-method">
                  ${["GET", "POST", "PUT", "PATCH", "DELETE"]
                    .map((m) => `<option value="${m}" ${method === m ? "selected" : ""}>${m}</option>`)
                    .join("")}
                </select>
              </div>
              <div class="field">
                <label>Gateway Endpoint Path</label>
                <input class="input mono" id="pg-endpoint" value="${esc(endpoint)}" placeholder="/v1/status" />
              </div>
            </div>

            <div class="two-col">
              <div class="field">
                <label>API Key Selection</label>
                <select class="select" id="pg-key-select">
                  ${activeKeys
                    .map(
                      (k) =>
                        `<option value="${esc(k.id)}" ${selectedKeyId === k.id ? "selected" : ""}>${esc(k.name)} (${esc(k.key_prefix)}...${esc(k.key_last4)})</option>`
                    )
                    .join("")}
                  <option value="__custom__" ${selectedKeyId === "__custom__" || activeKeys.length === 0 ? "selected" : ""}>Enter Raw Key Manually</option>
                </select>
              </div>
              <div class="field">
                <label>Auth Header Mode</label>
                <select class="select mono" id="pg-auth-mode">
                  <option value="x_api_key" ${authMode === "x_api_key" ? "selected" : ""}>X-API-Key</option>
                  <option value="bearer" ${authMode === "bearer" ? "selected" : ""}>Authorization: Bearer</option>
                </select>
              </div>
            </div>

            ${
              selectedKeyId === "__custom__" || activeKeys.length === 0
                ? `<div class="field"><label>Paste Raw API Key (optional to test 401 behavior)</label><input class="input mono" id="pg-raw-key" value="${esc(rawCustomKey)}" placeholder="${esc(brand.keyPrefixLive)}..." /></div>`
                : ""
            }

            <div style="margin-bottom:14px;">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                <label style="font-size:12.5px;font-weight:600;color:var(--text-secondary);">Query Parameters</label>
                <button type="button" class="btn btn-ghost btn-sm" id="pg-add-query">+ Add Param</button>
              </div>
              <div id="pg-query-rows">
                ${queryRows
                  .map(
                    (row, i) => `
                  <div class="kv-row">
                    <input class="input mono" data-qk="${i}" value="${esc(row.k)}" placeholder="key" />
                    <input class="input mono" data-qv="${i}" value="${esc(row.v)}" placeholder="value" />
                    <button type="button" class="btn btn-danger btn-sm" data-qdel="${i}">×</button>
                  </div>`
                  )
                  .join("")}
              </div>
            </div>

            <div style="margin-bottom:14px;">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                <label style="font-size:12.5px;font-weight:600;color:var(--text-secondary);">Custom Headers</label>
                <button type="button" class="btn btn-ghost btn-sm" id="pg-add-header">+ Add Header</button>
              </div>
              <div id="pg-header-rows">
                ${headerRows
                  .map(
                    (row, i) => `
                  <div class="kv-row">
                    <input class="input mono" data-hk="${i}" value="${esc(row.k)}" placeholder="Header-Name" />
                    <input class="input mono" data-hv="${i}" value="${esc(row.v)}" placeholder="Value" />
                    <button type="button" class="btn btn-danger btn-sm" data-hdel="${i}">×</button>
                  </div>`
                  )
                  .join("")}
              </div>
            </div>

            <div class="field">
              <div style="display:flex;justify-content:space-between;align-items:center;">
                <label>JSON Request Body</label>
                <button type="button" class="btn btn-ghost btn-sm" id="pg-format-json">Format JSON</button>
              </div>
              <textarea class="textarea mono" id="pg-body" placeholder='{"text": "hello sonic"}' ${method === "GET" || method === "DELETE" ? "disabled" : ""}>${esc(bodyText)}</textarea>
            </div>

            <button class="btn btn-primary" style="width:100%;" id="pg-send-btn">Send Live API Request</button>
          </div>

          <div class="glass-card panel-card">
            <div class="panel-head">
              <h3>Response Inspector</h3>
              <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
                ${
                  lastResult
                    ? `
                  <span class="badge badge-${respStatusColor}">HTTP ${lastResult.status_code}</span>
                  <span class="badge badge-info mono">${lastResult.latency_ms} ms</span>
                  <span class="badge badge-neutral mono">${lastResult.size_bytes} B</span>
                  ${
                    lastResult.body?.download_url
                      ? `<a class="btn btn-primary btn-sm" href="${esc(lastResult.body.download_url)}" target="_blank" rel="noopener">Download File</a>`
                      : ""
                  }
                  <button class="btn btn-ghost btn-sm" id="pg-copy-resp">Copy JSON</button>
                `
                    : `<span class="badge badge-neutral">Ready</span>`
                }
              </div>
            </div>

            ${
              lastResult?.body?.binary && lastResult.body.preview_base64
                ? `
              <div style="margin-bottom:14px;padding:12px;border-radius:10px;background:rgba(14,165,233,0.08);border:1px solid rgba(14,165,233,0.25);">
                <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap;">
                  <span class="mono" style="font-size:12.5px;color:var(--neon-cyan);">${esc(lastResult.body.filename)} (${esc(lastResult.body.mime_type)})</span>
                  <a class="btn btn-primary btn-sm" download="${esc(lastResult.body.filename)}" href="data:${esc(lastResult.body.mime_type)};base64,${lastResult.body.preview_base64}">Download ${esc(lastResult.body.filename)}</a>
                </div>
                ${
                  String(lastResult.body.mime_type || "").startsWith("video/")
                    ? `<video controls style="width:100%;max-height:280px;border-radius:8px;" src="data:${esc(lastResult.body.mime_type)};base64,${lastResult.body.preview_base64}"></video>`
                    : `<audio controls style="width:100%;" src="data:${esc(lastResult.body.mime_type)};base64,${lastResult.body.preview_base64}"></audio>`
                }
              </div>`
                : ""
            }

            <pre class="response-pre" id="pg-resp-body">${
              lastResult
                ? highlightJson(
                    lastResult.body?.binary
                      ? { ...lastResult.body, preview_base64: lastResult.body.preview_base64 ? "[omitted base64 preview]" : null }
                      : lastResult.body
                  )
                : `<span style="color:var(--text-muted);">// Click "Send Live API Request" to inspect the formatted JSON response, status code, and ${esc(brand.companyName)} rate-limit headers.</span>`
            }</pre>

            ${
              lastResult
                ? `
              <h4 style="margin:18px 0 8px;font-size:13.5px;color:var(--text-secondary);">Response Headers</h4>
              <div class="table-wrap" style="max-height:200px;overflow-y:auto;">
                <table class="data-table">
                  <tbody>
                    ${Object.entries(lastResult.headers || {})
                      .map(([k, v]) => `<tr><td class="mono" style="color:var(--neon-blue);">${esc(k)}</td><td class="mono">${esc(v)}</td></tr>`)
                      .join("")}
                  </tbody>
                </table>
              </div>
            `
                : ""
            }
          </div>
        </div>
      </div>
    `;

    const syncInputs = () => {
      method = document.getElementById("pg-method").value;
      endpoint = document.getElementById("pg-endpoint").value;
      selectedKeyId = document.getElementById("pg-key-select").value;
      authMode = document.getElementById("pg-auth-mode").value;
      const rawEl = document.getElementById("pg-raw-key");
      if (rawEl) rawCustomKey = rawEl.value;
      bodyText = document.getElementById("pg-body").value;

      queryRows = queryRows.map((_, i) => ({
        k: root.querySelector(`[data-qk="${i}"]`)?.value ?? "",
        v: root.querySelector(`[data-qv="${i}"]`)?.value ?? "",
      }));
      headerRows = headerRows.map((_, i) => ({
        k: root.querySelector(`[data-hk="${i}"]`)?.value ?? "",
        v: root.querySelector(`[data-hv="${i}"]`)?.value ?? "",
      }));
    };

    document.getElementById("pg-back-dash")?.addEventListener("click", () => handlers.navigate("#dashboard"));

    document.getElementById("pg-preset")?.addEventListener("change", (e) => {
      const idx = e.target.value;
      if (idx === "") return;
      const ep = presets[Number(idx)];
      if (!ep) return;
      method = ep.method;
      endpoint = ep.path;
      queryRows = Object.entries(ep.sample_query || {}).map(([k, v]) => ({ k, v: String(v) }));
      bodyText = ep.sample_body ? JSON.stringify(ep.sample_body, null, 2) : "";
      draw();
    });

    document.getElementById("pg-method")?.addEventListener("change", () => {
      syncInputs();
      draw();
    });
    document.getElementById("pg-key-select")?.addEventListener("change", () => {
      syncInputs();
      draw();
    });

    document.getElementById("pg-add-query")?.addEventListener("click", () => {
      syncInputs();
      queryRows.push({ k: "", v: "" });
      draw();
    });
    document.getElementById("pg-add-header")?.addEventListener("click", () => {
      syncInputs();
      headerRows.push({ k: "", v: "" });
      draw();
    });

    root.querySelectorAll("[data-qdel]").forEach((btn) => {
      btn.addEventListener("click", () => {
        syncInputs();
        queryRows.splice(Number(btn.getAttribute("data-qdel")), 1);
        draw();
      });
    });
    root.querySelectorAll("[data-hdel]").forEach((btn) => {
      btn.addEventListener("click", () => {
        syncInputs();
        headerRows.splice(Number(btn.getAttribute("data-hdel")), 1);
        draw();
      });
    });

    document.getElementById("pg-format-json")?.addEventListener("click", () => {
      const el = document.getElementById("pg-body");
      try {
        el.value = JSON.stringify(JSON.parse(el.value), null, 2);
      } catch {
        showToast("Invalid JSON syntax.", "error");
      }
    });

    document.getElementById("pg-copy-resp")?.addEventListener("click", () => {
      if (lastResult) {
        const raw = typeof lastResult.body === "string" ? lastResult.body : JSON.stringify(lastResult.body, null, 2);
        copyToClipboard(raw, "Response JSON copied!");
      }
    });

    document.getElementById("pg-send-btn")?.addEventListener("click", async (e) => {
      syncInputs();
      const btn = e.currentTarget;
      btn.disabled = true;
      btn.innerHTML = `<span class="spinner-sm"></span> Sending Request...`;

      let parsedBody = null;
      if (method !== "GET" && method !== "DELETE" && bodyText.trim()) {
        try {
          parsedBody = JSON.parse(bodyText);
        } catch {
          showToast("Request body must be valid JSON.", "error");
          btn.disabled = false;
          btn.textContent = "Send Live API Request";
          return;
        }
      }

      const qp = {};
      queryRows.forEach((r) => {
        if (r.k.trim()) qp[r.k.trim()] = r.v;
      });
      const hdrs = {};
      headerRows.forEach((r) => {
        if (r.k.trim()) hdrs[r.k.trim()] = r.v;
      });

      try {
        lastResult = await api.post("/api/playground/execute", {
          api_key_id: selectedKeyId && selectedKeyId !== "__custom__" ? selectedKeyId : null,
          raw_api_key: selectedKeyId === "__custom__" || !selectedKeyId ? rawCustomKey : null,
          method,
          endpoint,
          auth_mode: authMode,
          query_params: qp,
          headers: hdrs,
          body: parsedBody,
        });
        draw();
      } catch (err) {
        showToast(err.message, "error");
        btn.disabled = false;
        btn.textContent = "Send Live API Request";
      }
    });
  };

  draw();
}

