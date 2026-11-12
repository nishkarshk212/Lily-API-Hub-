/**
 * Next-Gen Developer Platform Landing Page with interactive terminal, media showcase & smooth animations.
 */

import { api, esc, formatInr, formatNum, getApiBase, getBrand, showToast } from "../api.js";

function attachRevealObserver(container) {
  const els = container.querySelectorAll(".reveal");
  if (!("IntersectionObserver" in window)) {
    els.forEach((el) => el.classList.add("in-view"));
    return;
  }
  const io = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("in-view");
          io.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.12, rootMargin: "0px 0px -30px 0px" }
  );
  els.forEach((el) => io.observe(el));
}

export function renderLandingPage(state, handlers) {
  const root = document.getElementById("app-root");
  if (!root) return;

  const plans = state.plans || [];
  const overview = state.overview || {};
  const brand = getBrand(state);
  const baseUrl = overview.api_base_url || `${getApiBase() || window.location.origin}/v1`;
  const faqs = overview.faqs || [];
  const sampleMaskedKey = `${brand.keyPrefixLive}9f3a••••••••c81d`;
  const sampleKey = `${brand.keyPrefixLive}your_key`;

  const features = [
    {
      icon: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>`,
      title: "Master Key Isolation",
      desc: "Upstream master credentials and backends stay securely encrypted server-side with Fernet — never exposed to client browsers.",
    },
    {
      icon: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="1" y="4" width="22" height="16" rx="2" ry="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg>`,
      title: "Razorpay Instant Provisioning",
      desc: "HMAC-SHA256 verified UPI, RuPay, Cards & Indian Netbanking payments automatically activate unique plan-scoped customer keys.",
    },
    {
      icon: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>`,
      title: "YouTube & Media Extractor",
      desc: "Built-in /v1/media/* endpoints to search Hindi songs, download 320kbps MP3s, stream 1080p MP4s, and parse YouTube track metadata.",
    },
    {
      icon: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>`,
      title: "Sliding-Window Quotas & Rate Limits",
      desc: "Thread-safe sliding-window throttling, atomic daily UTC and monthly quota consumption with sub-18ms gateway overhead.",
    },
    {
      icon: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg>`,
      title: "Telegram Bot Companion",
      desc: "1-click @BotFather Telegram pairing with coloured button menus, key inspection, live /v1 calls, and 80%/100% quota alerts.",
    },
    {
      icon: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>`,
      title: "Live Playground & SDKs",
      desc: "Interactive in-browser testing IDE with query builder, headers, binary audio player, and auto-generated cURL, Python & JS code.",
    },
  ];

  const terminalSamples = {
    status: {
      badge: "GET /v1/status",
      code: `<span class="code-cmt"># Call ${esc(brand.appName)} Gateway with your unique API key</span>
curl -s "${esc(baseUrl)}/status" \\
  -H "X-API-Key: ${esc(sampleMaskedKey)}"

{
  <span class="code-key">"service"</span>: <span class="code-str">"${esc(brand.appName)} Gateway"</span>,
  <span class="code-key">"provider"</span>: <span class="code-str">"${esc(brand.companyName)}"</span>,
  <span class="code-key">"status"</span>: <span class="code-str">"operational"</span>,
  <span class="code-key">"plan"</span>: <span class="code-str">"pro-velocity"</span>
}<span class="cursor-blink"></span>`,
    },
    media: {
      badge: "GET /v1/media/search?q=kesariya",
      code: `<span class="code-cmt"># High-speed media extraction & Hindi song downloader</span>
curl -s "${esc(baseUrl)}/media/search?q=kesariya%20hindi%20song&limit=1" \\
  -H "X-API-Key: ${esc(sampleMaskedKey)}"

{
  <span class="code-key">"title"</span>: <span class="code-str">"Kesariya - Brahmāstra | Arijit Singh"</span>,
  <span class="code-key">"duration"</span>: <span class="code-str">"04:28"</span>,
  <span class="code-key">"audio_mp3"</span>: <span class="code-str">"/v1/media/audio?id=BddP6PYo2gs&format=mp3"</span>,
  <span class="code-key">"video_720p"</span>: <span class="code-str">"/v1/media/video?id=BddP6PYo2gs&quality=720p"</span>
}<span class="cursor-blink"></span>`,
    },
    hash: {
      badge: "POST /v1/crypto/hash",
      code: `<span class="code-cmt"># Enforced per-plan rate limit & daily quota</span>
curl -s -X POST "${esc(baseUrl)}/crypto/hash" \\
  -H "X-API-Key: ${esc(sampleMaskedKey)}" \\
  -d '{"text":"sonic","algorithm":"sha256"}'

{
  <span class="code-key">"algorithm"</span>: <span class="code-str">"sha256"</span>,
  <span class="code-key">"digest_hex"</span>: <span class="code-str">"8e4f...b92c"</span>,
  <span class="code-key">"input_bytes"</span>: <span class="code-num">5</span>
}<span class="cursor-blink"></span>`,
    },
    ip: {
      badge: "GET /v1/geo/ip-parse",
      code: `<span class="code-cmt"># Instant telemetry logged in your dashboard</span>
curl -s "${esc(baseUrl)}/geo/ip-parse?ip=8.8.8.8" \\
  -H "X-API-Key: ${esc(sampleMaskedKey)}"

{
  <span class="code-key">"ip"</span>: <span class="code-str">"8.8.8.8"</span>,
  <span class="code-key">"version"</span>: <span class="code-num">4</span>,
  <span class="code-key">"is_global"</span>: <span class="code-num">true</span>
}<span class="cursor-blink"></span>`,
    },
  };

  const pricingHtml = plans
    .map((p, idx) => {
      const priceLabel = p.price_paise === 0 ? "Free" : formatInr(p.price_paise);
      const isCurrentPlan = state.subscription?.plan?.id === p.id && state.subscription?.status === "active";
      const ctaText = isCurrentPlan
        ? "Renew Plan"
        : p.price_paise === 0
        ? "Start Free Trial"
        : "Buy with Razorpay";

      return `
        <div class="glass-card interactive plan-card reveal reveal-d${Math.min(4, idx + 1)} ${p.is_featured ? "featured" : ""}">
          ${p.badge ? `<div class="plan-badge">${esc(p.badge)}</div>` : ""}
          <h3 class="plan-name">${esc(p.name)}</h3>
          <p class="plan-tagline">${esc(p.tagline)}</p>
          <div class="plan-price-row">
            <span class="plan-price">${esc(priceLabel)}</span>
            <span class="plan-cycle">/ ${p.billing_cycle_days} days</span>
          </div>
          <div class="plan-limits-box">
            <div class="plan-limit-item"><span>Daily Limit</span><strong>${formatNum(p.daily_request_limit)}</strong></div>
            <div class="plan-limit-item"><span>Cycle Quota</span><strong>${formatNum(p.monthly_request_limit)}</strong></div>
            <div class="plan-limit-item"><span>Rate Limit</span><strong>${formatNum(p.rate_limit_per_minute)}/m</strong></div>
            <div class="plan-limit-item"><span>API Keys</span><strong>${p.max_api_keys}</strong></div>
          </div>
          <ul class="plan-features">
            ${(p.features_json || []).slice(0, 4).map((f) => `<li>${esc(f)}</li>`).join("")}
          </ul>
          <button
            class="btn ${p.is_featured ? "btn-primary" : "btn-secondary"}"
            style="width:100%;"
            data-buy-plan="${esc(p.id)}"
            data-buy-action="${isCurrentPlan ? "renew" : "new"}"
          >
            ${esc(ctaText)}
          </button>
        </div>
      `;
    })
    .join("");

  root.innerHTML = `
    <section class="hero">
      <div class="container hero-grid">
        <div>
          <div class="hero-eyebrow">
            <span class="pulse-dot"></span>
            <span>${esc(brand.appName)} · ${esc(brand.companyName)}</span>
          </div>
          <h1 class="hero-title">
            Simple, Fast API Access <span class="gradient-text">Built to Scale.</span>
          </h1>
          <p class="hero-desc">
            Purchase an API plan with Razorpay, receive a unique customer key linked to ${esc(brand.companyName)}’s Master Gateway, and start shipping in seconds.
          </p>
          <div class="hero-cta-row">
            <button class="btn btn-primary btn-lg" id="hero-explore-plans">View Pricing</button>
            <button class="btn btn-secondary btn-lg" id="hero-open-docs">API Docs</button>
            <button class="btn btn-ghost btn-lg" id="hero-open-playground">Playground →</button>
          </div>
          <div class="hero-metrics">
            <div>
              <div class="hero-metric-val">99.95%</div>
              <div class="hero-metric-lbl">Gateway Uptime</div>
            </div>
            <div>
              <div class="hero-metric-val">&lt; 18ms</div>
              <div class="hero-metric-lbl">Edge Latency</div>
            </div>
            <div>
              <div class="hero-metric-val">HMAC-256</div>
              <div class="hero-metric-lbl">Razorpay Verified</div>
            </div>
            <div>
              <div class="hero-metric-val">Isolated</div>
              <div class="hero-metric-lbl">Master Key Proxy</div>
            </div>
          </div>
        </div>

        <div class="terminal-card">
          <div class="terminal-top">
            <div class="terminal-dots"><span></span><span></span><span></span></div>
            <span class="mono" id="hero-term-route">${terminalSamples.status.badge}</span>
            <span style="color:#10b981;font-weight:700;display:flex;align-items:center;gap:5px;">
              <span style="width:6px;height:6px;border-radius:50%;background:#10b981;display:inline-block;"></span> 200 OK
            </span>
          </div>
          <div class="terminal-switcher">
            <button type="button" class="term-pill active" data-term="status">/status</button>
            <button type="button" class="term-pill" data-term="media">/media/search</button>
            <button type="button" class="term-pill" data-term="hash">/crypto/hash</button>
            <button type="button" class="term-pill" data-term="ip">/geo/ip-parse</button>
          </div>
          <pre class="terminal-body" id="hero-term-body">${terminalSamples.status.code}</pre>
        </div>
      </div>
    </section>

    <section class="section" style="padding-top:24px;">
      <div class="container">
        <div class="features-grid">
          ${features
            .map(
              (f, idx) => `
              <div class="glass-card interactive feature-card reveal reveal-d${idx + 1}">
                <div class="feature-icon-wrap">${f.icon}</div>
                <h3>${esc(f.title)}</h3>
                <p>${esc(f.desc)}</p>
              </div>`
            )
            .join("")}
        </div>
      </div>
    </section>

    <section class="section" id="section-pricing">
      <div class="container">
        <div class="section-header reveal">
          <span class="section-kicker">Transparent Pricing</span>
          <h2 class="section-title">Choose Your API Plan</h2>
          <p class="section-sub">Instant API key provisioning via Razorpay UPI, Cards & Netbanking with zero manual setup.</p>
        </div>
        <div class="pricing-grid">
          ${pricingHtml}
        </div>
      </div>
    </section>

    <section class="section">
      <div class="container">
        <div class="glass-card reveal two-col" style="padding:32px;gap:32px;align-items:center;">
          <div>
            <span class="section-kicker">Developer Quickstart</span>
            <h2 style="margin:0 0 12px;font-size:25px;color:#ffffff;">One Header. Full Telemetry.</h2>
            <p style="color:var(--text-secondary);font-size:15px;line-height:1.6;margin:0 0 20px;">
              Authenticate requests to <code class="mono" style="color:var(--neon-cyan);">${esc(baseUrl)}</code> using <code>X-API-Key</code> or <code>Authorization: Bearer</code>. Real-time rate limits and remaining daily quotas are returned in every response header.
            </p>
            <div style="display:flex;gap:10px;flex-wrap:wrap;">
              <button class="btn btn-primary btn-sm" id="landing-full-docs">Read Documentation</button>
              <button class="btn btn-secondary btn-sm" id="landing-open-pg">Try in Playground</button>
              <button class="btn btn-secondary btn-sm" id="landing-open-tg">✈ Connect Telegram Bot</button>
            </div>
          </div>
          <div class="code-block-wrap" style="margin:0;width:100%;">
            <div class="code-block-head">
              <span class="mono" style="font-size:12px;color:var(--neon-cyan);">quickstart.py</span>
              <span style="font-size:11px;color:var(--text-muted);">Python 3</span>
            </div>
            <pre class="code-block-pre">import requests

resp = requests.get(
    "${esc(baseUrl)}/status",
    headers={"X-API-Key": "${esc(sampleKey)}"},
    timeout=10,
)
print(resp.status_code, resp.json())</pre>
          </div>
        </div>
      </div>
    </section>

    <section class="section">
      <div class="container">
        <div class="section-header reveal">
          <span class="section-kicker">Frequently Asked</span>
          <h2 class="section-title">Common Questions</h2>
          <p class="section-sub">Everything you need to know about keys, billing, quotas, and upstream proxying.</p>
        </div>
        <div class="faq-list">
          ${faqs
            .slice(0, 5)
            .map(
              (item, idx) => `
              <div class="faq-item reveal ${idx === 0 ? "open" : ""}">
                <button class="faq-btn" type="button">
                  <span>${esc(item.q)}</span>
                  <span style="font-size:18px;font-weight:700;color:var(--neon-cyan);">${idx === 0 ? "−" : "+"}</span>
                </button>
                <div class="faq-answer">${esc(item.a)}</div>
              </div>`
            )
            .join("")}
        </div>
      </div>
    </section>

    <section class="section" id="section-support">
      <div class="container support-grid reveal">
        <div class="glass-card" style="padding:32px;">
          <span class="section-kicker">Support &amp; Inquiries</span>
          <h2 style="margin:0 0 12px;color:#ffffff;">Talk to ${esc(brand.companyName)}</h2>
          <p style="color:var(--text-secondary);font-size:14.5px;line-height:1.6;margin:0 0 24px;">
            Questions about enterprise limits, custom upstreams, high-volume quotas, or Razorpay billing? Reach our engineering team directly.
          </p>
          <div style="display:flex;flex-direction:column;gap:14px;font-size:14px;">
            <div><strong style="color:#ffffff;">Gateway URL:</strong> <span class="mono" style="color:var(--neon-cyan);">${esc(baseUrl)}</span></div>
            <div><strong style="color:#ffffff;">Support Email:</strong> <a href="mailto:${esc(brand.supportEmail)}">${esc(brand.supportEmail)}</a></div>
            <div><strong style="color:#ffffff;">Admin Portal:</strong> <a href="#admin/login" data-nav="#admin/login">Administrator Sign In →</a></div>
          </div>
        </div>

        <div class="glass-card" style="padding:32px;">
          <h3 style="margin:0 0 18px;color:#ffffff;">Send a Message</h3>
          <form id="support-form">
            <div class="two-col">
              <div class="field"><label>Name</label><input class="input" id="sup-name" required value="${esc(state.user?.full_name || "")}" placeholder="Your name" /></div>
              <div class="field"><label>Email</label><input class="input" type="email" id="sup-email" required value="${esc(state.user?.email || "")}" placeholder="you@company.com" /></div>
            </div>
            <div class="field"><label>Subject</label><input class="input" id="sup-subject" required placeholder="Plan upgrade / Media API / Upstream help" /></div>
            <div class="field"><label>Message</label><textarea class="textarea" id="sup-message" required minlength="10" placeholder="How can our gateway team assist you today?"></textarea></div>
            <button type="submit" class="btn btn-primary" id="sup-submit">Send Message</button>
          </form>
        </div>
      </div>
    </section>

    <footer class="footer">
      <div class="container" style="display:flex;flex-wrap:wrap;justify-content:space-between;align-items:center;gap:18px;font-size:13.5px;color:var(--text-muted);">
        <div style="display:flex;align-items:center;gap:10px;">
          <span class="brand-icon" style="width:28px;height:28px;font-size:13px;">${esc(brand.brandLetter || "A")}</span>
          <div><strong style="color:#ffffff;">${esc(brand.appName)}</strong> · ${esc(brand.companyName)}</div>
        </div>
        <div style="display:flex;gap:20px;flex-wrap:wrap;">
          <a href="#pricing" data-nav="#pricing">Pricing</a>
          <a href="#docs" data-nav="#docs">Docs</a>
          <a href="#playground" data-nav="#playground">Playground</a>
          <a href="#dashboard" data-nav="#dashboard">Dashboard</a>
          <a href="#admin/login" data-nav="#admin/login">Admin</a>
        </div>
      </div>
    </footer>
  `;

  attachRevealObserver(root);

  root.querySelectorAll(".term-pill").forEach((pill) => {
    pill.addEventListener("click", () => {
      const key = pill.getAttribute("data-term");
      const sample = terminalSamples[key];
      if (!sample) return;
      root.querySelectorAll(".term-pill").forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
      document.getElementById("hero-term-route").textContent = sample.badge;
      const bodyEl = document.getElementById("hero-term-body");
      bodyEl.style.opacity = "0";
      setTimeout(() => {
        bodyEl.innerHTML = sample.code;
        bodyEl.style.transition = "opacity 0.22s ease";
        bodyEl.style.opacity = "1";
      }, 90);
    });
  });

  document.getElementById("hero-explore-plans")?.addEventListener("click", () => {
    document.getElementById("section-pricing")?.scrollIntoView({ behavior: "smooth" });
  });
  document.getElementById("hero-open-docs")?.addEventListener("click", () => handlers.navigate("#docs"));
  document.getElementById("hero-open-playground")?.addEventListener("click", () => handlers.navigate("#playground"));
  document.getElementById("landing-full-docs")?.addEventListener("click", () => handlers.navigate("#docs"));
  document.getElementById("landing-open-pg")?.addEventListener("click", () => handlers.navigate("#playground"));
  document.getElementById("landing-open-tg")?.addEventListener("click", () => handlers.navigate("#dashboard?tab=telegram"));

  root.querySelectorAll("[data-buy-plan]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const planId = btn.getAttribute("data-buy-plan");
      const action = btn.getAttribute("data-buy-action") || "new";
      handlers.purchasePlan(planId, action);
    });
  });

  root.querySelectorAll(".faq-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const parent = btn.closest(".faq-item");
      const isOpen = parent.classList.toggle("open");
      btn.querySelector("span:last-child").textContent = isOpen ? "−" : "+";
    });
  });

  root.querySelectorAll("[data-nav]").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      handlers.navigate(el.getAttribute("data-nav"));
    });
  });

  document.getElementById("support-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("sup-submit");
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner-sm"></span> Sending...`;
    try {
      const res = await api.post("/api/public/support", {
        name: document.getElementById("sup-name").value,
        email: document.getElementById("sup-email").value,
        subject: document.getElementById("sup-subject").value,
        message: document.getElementById("sup-message").value,
      });
      showToast(res.message, "success");
      e.target.reset();
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Send Message";
    }
  });
}
