/**
 * Comprehensive API Documentation Portal.
 */

import { copyToClipboard, esc, getApiBase, getBrand } from "../api.js";

function buildSnippets(baseUrl, ep) {
  const queryStr =
    ep.sample_query && Object.keys(ep.sample_query).length
      ? "?" + new URLSearchParams(ep.sample_query).toString()
      : "";
  const fullUrl = `${baseUrl.replace(/\/v1$/, "")}${ep.path}${queryStr}`;
  const hasBody = ep.sample_body !== null && ep.sample_body !== undefined;
  const jsonBody = hasBody ? JSON.stringify(ep.sample_body, null, 2) : "";

  const curl = hasBody
    ? `curl -X ${ep.method} "${fullUrl}" \\\n  -H "X-API-Key: YOUR_LILY_API_KEY" \\\n  -H "Content-Type: application/json" \\\n  -d '${JSON.stringify(ep.sample_body)}'`
    : `curl -X ${ep.method} "${fullUrl}" \\\n  -H "X-API-Key: YOUR_LILY_API_KEY"`;

  const python = `import requests\n\nresp = requests.${ep.method.toLowerCase()}(\n    "${fullUrl}",\n    headers={"X-API-Key": "YOUR_LILY_API_KEY"},${hasBody ? `\n    json=${jsonBody.replace(/true/g, "True").replace(/false/g, "False")},` : ""}\n    timeout=10,\n)\nprint(resp.status_code, resp.json())`;

  const javascript = `const res = await fetch("${fullUrl}", {\n  method: "${ep.method}",\n  headers: {\n    "X-API-Key": "YOUR_LILY_API_KEY",${hasBody ? `\n    "Content-Type": "application/json",` : ""}\n  },${hasBody ? `\n  body: JSON.stringify(${JSON.stringify(ep.sample_body)}),` : ""}\n});\nconst data = await res.json();\nconsole.log(res.status, data);`;

  return { curl, python, javascript };
}

export function renderDocsPage(state, handlers) {
  const root = document.getElementById("app-root");
  if (!root) return;

  const brand = getBrand(state);
  const sampleDocsKey = `${brand.keyPrefixLive}your_unique_customer_key`;
  const baseUrl = state.overview?.api_base_url || `${getApiBase() || window.location.origin}/v1`;
  const endpoints = state.overview?.endpoints || [];

  const errorCodes = [
    ["401", "MISSING_API_KEY / INVALID_API_KEY", "No key supplied or the key hash does not exist."],
    ["403", "KEY_REVOKED", "The API key was revoked by the owner or administrator."],
    ["403", "ACCOUNT_SUSPENDED", "Owning account has been suspended."],
    ["403", "SUBSCRIPTION_EXPIRED", "Subscription passed its expiry timestamp; renew to restore access."],
    ["403", "METHOD_NOT_ALLOWED_FOR_PLAN", "HTTP verb is restricted on the purchased plan tier."],
    ["429", "RATE_LIMIT_EXCEEDED", "Exceeded per-minute sliding-window ceiling. Respect Retry-After header."],
    ["429", "DAILY_QUOTA_EXCEEDED / MONTHLY_QUOTA_EXCEEDED", "Plan daily (UTC) or cycle quota exhausted."],
    ["502", "UPSTREAM_UNREACHABLE", "Configured Master Upstream API could not be reached."],
  ];

  root.innerHTML = `
    <div class="container docs-layout">
      <aside class="glass-card docs-sidebar">
        <div style="font-size:12px;font-weight:700;text-transform:uppercase;color:var(--neon-cyan);letter-spacing:0.08em;margin-bottom:10px;">
          Documentation
        </div>
        <button class="docs-nav-item active" data-doc-jump="doc-auth">Authentication</button>
        <button class="docs-nav-item" data-doc-jump="doc-headers">Rate Limit & Quota Headers</button>
        <button class="docs-nav-item" data-doc-jump="doc-endpoints">Endpoints Reference</button>
        <button class="docs-nav-item" data-doc-jump="doc-errors">Error Codes</button>
        <button class="docs-nav-item" data-doc-jump="doc-guides">Integration Guide</button>
        <hr style="border:none;border-top:1px solid var(--border-subtle);margin:14px 0;" />
        <button class="btn btn-primary btn-sm" style="width:100%;" id="docs-goto-playground">Open Playground</button>
      </aside>

      <div>
        <div class="base-url-bar">
          <div>
            <div style="font-size:12px;color:var(--text-muted);">Production API Gateway Base URL</div>
            <div class="mono" style="font-size:15px;font-weight:600;color:var(--neon-cyan);">${esc(baseUrl)}</div>
          </div>
          <button class="btn btn-secondary btn-sm" id="docs-copy-base">Copy Base URL</button>
        </div>

        <section id="doc-auth" class="glass-card panel-card">
          <h1 style="margin:0 0 10px;font-size:26px;">${esc(brand.appName)} Documentation</h1>
          <p style="color:var(--text-secondary);margin:0 0 16px;">
            Every request to <code>${esc(baseUrl)}/*</code> must present a valid customer API key issued by ${esc(brand.appName)}. The gateway verifies your key, checks plan expiry and quotas, and forwards authorized calls through ${esc(brand.companyName)}'s isolated Master Gateway.
          </p>
          <h3 style="margin:18px 0 8px;">Authentication Headers (Choose Either)</h3>
          <div class="code-block-wrap">
            <pre class="code-block-pre">X-API-Key: ${esc(sampleDocsKey)}
# OR standard Bearer token header:
Authorization: Bearer ${esc(sampleDocsKey)}</pre>
          </div>
        </section>

        <section id="doc-headers" class="glass-card panel-card">
          <h2 style="margin:0 0 12px;">Rate-Limit & Quota Response Headers</h2>
          <p style="color:var(--text-muted);font-size:14px;margin:0 0 14px;">Every gateway response includes live quota counters so your client apps can throttle or alert gracefully.</p>
          <div class="table-wrap">
            <table class="data-table">
              <thead><tr><th>Header</th><th>Description</th></tr></thead>
              <tbody>
                <tr><td class="mono">X-RateLimit-Limit</td><td>Maximum requests per 60-second sliding window for your plan</td></tr>
                <tr><td class="mono">X-RateLimit-Remaining</td><td>Remaining calls inside the current 60-second window</td></tr>
                <tr><td class="mono">X-Quota-Daily-Remaining</td><td>Remaining daily requests before 00:00 UTC reset</td></tr>
                <tr><td class="mono">X-Quota-Monthly-Remaining</td><td>Remaining requests in your active billing cycle</td></tr>
                <tr><td class="mono">X-Lily-Plan</td><td>Active subscription plan slug applied to this request</td></tr>
                <tr><td class="mono">X-Gateway-Mode</td><td><code>builtin</code> or <code>proxy</code> (upstream master forwarding)</td></tr>
              </tbody>
            </table>
          </div>
        </section>

        <section id="doc-endpoints" class="glass-card panel-card">
          <div class="panel-head">
            <div>
              <h2>API Endpoints Reference</h2>
              <p style="margin:4px 0 0;color:var(--text-muted);font-size:13.5px;">Built-in ${esc(brand.companyName)} APIs plus any custom routes configured on the Master Upstream API.</p>
            </div>
          </div>

          ${endpoints
            .map((ep, idx) => {
              const snippets = buildSnippets(baseUrl, ep);
              return `
                <div class="key-card" style="margin-bottom:16px;">
                  <div class="key-card-top">
                    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
                      <span class="method-pill method-${esc(ep.method)}">${esc(ep.method)}</span>
                      <span class="mono" style="font-size:14.5px;color:var(--text-primary);font-weight:600;">${esc(ep.path)}</span>
                      <span style="color:var(--text-muted);font-size:13px;">— ${esc(ep.title)}</span>
                    </div>
                    <button class="btn btn-secondary btn-sm" data-try-ep="${idx}">Try in Playground →</button>
                  </div>
                  <p style="margin:0;color:var(--text-muted);font-size:13.5px;">${esc(ep.description)}</p>
                  <div class="code-block-wrap" data-snippet-box="${idx}">
                    <div class="code-block-head">
                      <div class="code-tabs">
                        <button class="code-tab active" data-lang="curl" data-idx="${idx}">cURL</button>
                        <button class="code-tab" data-lang="python" data-idx="${idx}">Python</button>
                        <button class="code-tab" data-lang="javascript" data-idx="${idx}">JavaScript</button>
                      </div>
                      <button class="btn btn-ghost btn-sm" data-copy-snippet="${idx}">Copy</button>
                    </div>
                    <pre class="code-block-pre" id="snippet-pre-${idx}">${esc(snippets.curl)}</pre>
                  </div>
                </div>
              `;
            })
            .join("")}
        </section>

        <section id="doc-errors" class="glass-card panel-card">
          <h2 style="margin:0 0 12px;">Error Codes Reference</h2>
          <div class="table-wrap">
            <table class="data-table">
              <thead><tr><th>HTTP</th><th>Error Code</th><th>Meaning</th></tr></thead>
              <tbody>
                ${errorCodes
                  .map(
                    ([code, name, desc]) => `
                    <tr>
                      <td><span class="badge badge-${code.startsWith("429") ? "warning" : "danger"}">${code}</span></td>
                      <td class="mono">${esc(name)}</td>
                      <td>${esc(desc)}</td>
                    </tr>`
                  )
                  .join("")}
              </tbody>
            </table>
          </div>
        </section>

        <section id="doc-guides" class="glass-card panel-card">
          <h2 style="margin:0 0 10px;">Production Integration Best Practices</h2>
          <ul style="margin:0;padding-left:20px;color:var(--text-secondary);display:flex;flex-direction:column;gap:8px;font-size:14.5px;">
            <li>Store your <code>${esc(brand.keyPrefixLive)}*</code> key in server-side environment variables — never commit keys to client-side frontend code.</li>
            <li>Create separate API keys per environment (<code>Production</code>, <code>Staging</code>, <code>Worker</code>) up to your plan's limit so you can rotate or revoke individually.</li>
            <li>Handle <code>HTTP 429</code> responses with exponential backoff respecting the <code>Retry-After</code> header.</li>
            <li>Monitor <code>X-Quota-Daily-Remaining</code> and upgrade or renew early in your Dashboard before hitting cycle expiry.</li>
          </ul>
        </section>
      </div>
    </div>
  `;

  document.getElementById("docs-copy-base")?.addEventListener("click", () => copyToClipboard(baseUrl, "Base URL copied!"));
  document.getElementById("docs-goto-playground")?.addEventListener("click", () => handlers.navigate("#playground"));

  root.querySelectorAll("[data-doc-jump]").forEach((btn) => {
    btn.addEventListener("click", () => {
      root.querySelectorAll(".docs-nav-item").forEach((n) => n.classList.remove("active"));
      btn.classList.add("active");
      document.getElementById(btn.getAttribute("data-doc-jump"))?.scrollIntoView({ behavior: "smooth" });
    });
  });

  const activeSnippets = endpoints.map((ep) => buildSnippets(baseUrl, ep));

  root.querySelectorAll("[data-lang]").forEach((tab) => {
    tab.addEventListener("click", () => {
      const idx = Number(tab.getAttribute("data-idx"));
      const lang = tab.getAttribute("data-lang");
      const box = root.querySelector(`[data-snippet-box="${idx}"]`);
      box.querySelectorAll(".code-tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById(`snippet-pre-${idx}`).textContent = activeSnippets[idx][lang];
    });
  });

  root.querySelectorAll("[data-copy-snippet]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const idx = Number(btn.getAttribute("data-copy-snippet"));
      const text = document.getElementById(`snippet-pre-${idx}`).textContent;
      copyToClipboard(text, "Code snippet copied!");
    });
  });

  root.querySelectorAll("[data-try-ep]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const ep = endpoints[Number(btn.getAttribute("data-try-ep"))];
      handlers.openInPlayground(ep);
    });
  });
}

