/**
 * YouTube-Realistic Black & White Theme — Landing Page & Media Extraction Showcase
 */

import { api, esc, formatInr, formatNum, getApiBase, getBrand, showToast } from "../api.js";

// Featured real Hindi YouTube songs for initial realistic shelf
const FEATURED_HINDI_SONGS = [
  {
    id: "Umqb9KENgmk",
    title: "तुम ही हो — आशिकी 2 पूरा गाना (Tum Hi Ho | Arijit Singh)",
    channel: "T-Series",
    avatar: "T",
    views: "512M views",
    time: "1 year ago",
    duration: "4:28",
    thumb: "https://i.ytimg.com/vi/Umqb9KENgmk/hqdefault.jpg",
  },
  {
    id: "BddP6PYo2gs",
    title: "Kesariya — Brahmāstra | Ranbir, Alia | Arijit Singh, Pritam",
    channel: "Sony Music India",
    avatar: "S",
    views: "640M views",
    time: "2 years ago",
    duration: "4:28",
    thumb: "https://i.ytimg.com/vi/BddP6PYo2gs/hqdefault.jpg",
  },
  {
    id: "VAdGW7QDJUI",
    title: "Chaleya — Jawan | Shah Rukh Khan, Nayanthara | Anirudh, Arijit",
    channel: "T-Series",
    avatar: "T",
    views: "410M views",
    time: "1 year ago",
    duration: "3:20",
    thumb: "https://i.ytimg.com/vi/VAdGW7QDJUI/hqdefault.jpg",
  },
  {
    id: "ElZfdU54Cp8",
    title: "Apna Bana Le — Bhediya | Varun Dhawan, Kriti Sanon | Arijit Singh",
    channel: "Zee Music Company",
    avatar: "Z",
    views: "490M views",
    time: "1 year ago",
    duration: "4:21",
    thumb: "https://i.ytimg.com/vi/ElZfdU54Cp8/hqdefault.jpg",
  },
  {
    id: "gvyUuxdRdR4",
    title: "Raataan Lambiyan — Shershaah | Sidharth, Kiara | Jubin Nautiyal",
    channel: "Sony Music India",
    avatar: "S",
    views: "820M views",
    time: "2 years ago",
    duration: "3:50",
    thumb: "https://i.ytimg.com/vi/gvyUuxdRdR4/hqdefault.jpg",
  },
  {
    id: "RLzC55ai0eo",
    title: "Heeriye (Official Video) Jasleen Royal ft Arijit Singh | Dulquer",
    channel: "Jasleen Royal",
    avatar: "J",
    views: "380M views",
    time: "1 year ago",
    duration: "3:19",
    thumb: "https://i.ytimg.com/vi/RLzC55ai0eo/hqdefault.jpg",
  },
];

export function renderLandingPage(state, handlers) {
  const root = document.getElementById("app-root");
  if (!root) return;

  const plans = state.plans || [];
  const overview = state.overview || {};
  const brand = getBrand(state);
  const baseUrl = overview.api_base_url || `${getApiBase() || window.location.origin}/v1`;
  const faqs = overview.faqs || [];
  const demoApiKey = "lily_test_CYVhA5u5DI3Ea5zDwm7dgZO--SFukFPEA4bHy1Yqu2U";

  const chips = [
    { label: "All", query: "" },
    { label: "Trending Hindi Songs", query: "trending hindi songs 2026" },
    { label: "Arijit Singh Hits", query: "arijit singh best songs" },
    { label: "Bollywood Party", query: "bollywood dance songs" },
    { label: "Lofi Hindi Chill", query: "hindi lofi songs" },
    { label: "MP3 320kbps Audio", query: "hindi audio songs 320kbps" },
    { label: "1080p HD Videos", query: "latest bollywood 1080p video" },
  ];

  const features = [
    {
      icon: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg>`,
      title: "YouTube & Hindi Song Extractor",
      desc: "Built-in /v1/media/* endpoints to search tracks, extract 320kbps MP3s, stream 1080p video, and parse track metadata with Netscape cookie auth.",
    },
    {
      icon: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="1" y="4" width="22" height="16" rx="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg>`,
      title: "Razorpay Instant Provisioning",
      desc: "HMAC-SHA256 verified UPI, RuPay, and Cards automatically provision unique plan-scoped developer keys linked to your account.",
    },
    {
      icon: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>`,
      title: "Master Key Security & Isolation",
      desc: "Upstream master credentials and backends stay encrypted server-side with Fernet — never exposed to client browsers or network logs.",
    },
    {
      icon: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>`,
      title: "Sliding-Window Rate Limits & Quotas",
      desc: "Thread-safe sliding-window throttling with atomic daily UTC and monthly quota tracking under Neon PostgreSQL.",
    },
    {
      icon: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg>`,
      title: "Telegram Bot Integration",
      desc: "Pair your API account with @BotFather for mobile key lookups, quick audio downloads, and real-time quota threshold alerts.",
    },
    {
      icon: `<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>`,
      title: "Interactive Playground & Code SDKs",
      desc: "Test endpoints live in your browser with built-in audio playback, signed token generation, and one-click cURL / JS / Python snippets.",
    },
  ];

  const terminalSamples = {
    search: {
      badge: "POST /v1/media/search",
      code: `<span class="code-cmt"># 1. Search YouTube Hindi Songs via API</span>
curl -s -X POST "${esc(baseUrl)}/media/search" \\
  -H "X-API-Key: ${esc(demoApiKey)}" \\
  -H "Content-Type: application/json" \\
  -d '{"query":"Tum Hi Ho Arijit Singh","limit":1}'

{
  <span class="code-key">"query"</span>: <span class="code-str">"Tum Hi Ho Arijit Singh"</span>,
  <span class="code-key">"count"</span>: <span class="code-num">1</span>,
  <span class="code-key">"results"</span>: [{
    <span class="code-key">"id"</span>: <span class="code-str">"Umqb9KENgmk"</span>,
    <span class="code-key">"title"</span>: <span class="code-str">"तुम ही हो — आशिकी 2 (Tum Hi Ho)"</span>,
    <span class="code-key">"duration_seconds"</span>: <span class="code-num">268</span>,
    <span class="code-key">"audio_mp3"</span>: <span class="code-str">"${esc(baseUrl)}/media/audio?id=Umqb9KENgmk&format=mp3&bitrate=320"</span>,
    <span class="code-key">"video_1080p"</span>: <span class="code-str">"${esc(baseUrl)}/media/video?id=Umqb9KENgmk&quality=1080p"</span>
  }]
}`,
    },
    audio: {
      badge: "GET /v1/media/audio (320kbps MP3)",
      code: `<span class="code-cmt"># 2. Direct Stream / Download MP3 Audio</span>
curl -L -O "${esc(baseUrl)}/media/audio?id=Umqb9KENgmk&format=mp3&bitrate=320" \\
  -H "X-API-Key: ${esc(demoApiKey)}"

<span class="code-cmt"># Saves: tum_hi_ho_320k.mp3 (Content-Type: audio/mpeg)</span>`,
    },
    status: {
      badge: "GET /v1/status",
      code: `<span class="code-cmt"># 3. Check Gateway & Quota Status</span>
curl -s "${esc(baseUrl)}/status" \\
  -H "X-API-Key: ${esc(demoApiKey)}"

{
  <span class="code-key">"service"</span>: <span class="code-str">"${esc(brand.appName)} Gateway"</span>,
  <span class="code-key">"status"</span>: <span class="code-str">"operational"</span>,
  <span class="code-key">"plan"</span>: {
    <span class="code-key">"name"</span>: <span class="code-str">"Enterprise Nova"</span>,
    <span class="code-key">"daily_limit"</span>: <span class="code-num">500000</span>,
    <span class="code-key">"rate_limit_per_minute"</span>: <span class="code-num">1500</span>
  }
}`,
    },
  };

  root.innerHTML = `
    <!-- Authentic YouTube Category Chips Bar -->
    <div class="yt-chips-container">
      <div class="container">
        <div class="yt-chips-bar" id="yt-chips-bar">
          ${chips
            .map(
              (c, i) => `
            <button class="yt-chip ${i === 0 ? "active" : ""}" data-query="${esc(c.query)}">
              ${esc(c.label)}
            </button>`
            )
            .join("")}
        </div>
      </div>
    </div>

    <!-- YouTube Hero Section with Center Interactive Search -->
    <section class="hero">
      <div class="container hero-content">
        <div class="hero-eyebrow">
          <span class="yt-icon-bullet">▶</span>
          <span>YouTube & Media Extraction API Gateway</span>
        </div>
        <h1 class="hero-title">Stream, Extract & Download Hindi Songs & 4K Video</h1>
        <p class="hero-desc">
          Enterprise YouTube media engine backed by Neon PostgreSQL, ultra-fast yt-dlp, ffmpeg audio conversion, signed ephemeral download tokens, and 1,500 req/min quotas.
        </p>

        <!-- YouTube Realistic Search & Downloader Bar -->
        <div class="hero-search-wrapper">
          <form class="hero-search-box" id="hero-yt-search-form">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#aaaaaa" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:12px;">
              <circle cx="11" cy="11" r="8"></circle>
              <path d="m21 21-4.35-4.35"></path>
            </svg>
            <input
              type="text"
              id="hero-yt-search-input"
              class="hero-search-input"
              placeholder="Search Hindi song name (e.g. Tum Hi Ho, Kesariya, Chaleya) or YouTube URL..."
              autocomplete="off"
            />
            <div class="hero-search-actions">
              <button type="submit" class="btn btn-primary btn-sm" id="hero-btn-search">
                Search & Download
              </button>
            </div>
          </form>
        </div>

        <div class="hero-cta-row">
          <button class="btn btn-primary" data-nav="#pricing">View Access Plans</button>
          <button class="btn btn-secondary" data-nav="#playground">Open Live Playground</button>
          <button class="btn btn-ghost" data-nav="#docs">API Documentation →</button>
        </div>

        <div class="hero-metrics">
          <div>
            <div class="hero-metric-val">500,000</div>
            <div class="hero-metric-lbl">Daily Quota / Key</div>
          </div>
          <div>
            <div class="hero-metric-val">320 kbps</div>
            <div class="hero-metric-lbl">High-Bitrate MP3</div>
          </div>
          <div>
            <div class="hero-metric-val">&lt; 18 ms</div>
            <div class="hero-metric-lbl">Gateway Overhead</div>
          </div>
          <div>
            <div class="hero-metric-val">100%</div>
            <div class="hero-metric-lbl">Netscape Cookie Auth</div>
          </div>
        </div>
      </div>
    </section>

    <!-- Realistic YouTube Video Shelf (Hindi Songs & Videos) -->
    <section class="yt-shelf" id="shelf-featured">
      <div class="container">
        <div class="yt-shelf-header">
          <h2 class="yt-shelf-title" id="shelf-heading">
            <svg width="22" height="18" viewBox="0 0 28 20" fill="none">
              <rect width="28" height="20" rx="5" fill="#FF0000"/>
              <polygon points="11,5.5 19,10 11,14.5" fill="#FFFFFF"/>
            </svg>
            <span>Trending Hindi Songs & Video Downloads</span>
          </h2>
          <span class="yt-shelf-sub">Click any card to play preview or download MP3 / Video</span>
        </div>

        <div class="yt-video-grid" id="yt-video-grid">
          ${FEATURED_HINDI_SONGS.map((song) => renderVideoCardHtml(song, baseUrl, demoApiKey)).join("")}
        </div>
      </div>
    </section>

    <!-- YouTube Studio Developer Terminal Shelf -->
    <section class="yt-shelf" style="background:#141414;border-top:1px solid #272727;border-bottom:1px solid #272727;">
      <div class="container">
        <div class="yt-shelf-header">
          <h2 class="yt-shelf-title">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <polyline points="4 17 10 11 4 5"></polyline>
              <line x1="12" y1="19" x2="20" y2="19"></line>
            </svg>
            <span>Developer Console — Fast Audio & Video Integration</span>
          </h2>
          <span class="yt-shelf-sub">Standard HTTP/2 JSON REST API for any programming language</span>
        </div>

        <div class="terminal-card">
          <div class="terminal-header">
            <div class="terminal-dots">
              <div class="terminal-dot"></div>
              <div class="terminal-dot"></div>
              <div class="terminal-dot"></div>
            </div>
            <div class="terminal-tabs">
              <button class="terminal-tab active" data-tab="search">POST /v1/media/search</button>
              <button class="terminal-tab" data-tab="audio">GET /v1/media/audio</button>
              <button class="terminal-tab" data-tab="status">GET /v1/status</button>
            </div>
          </div>
          <pre class="terminal-body" id="terminal-content">${terminalSamples.search.code}</pre>
        </div>
      </div>
    </section>

    <!-- Core Platform Features Shelf -->
    <section class="yt-shelf">
      <div class="container">
        <div class="yt-shelf-header">
          <h2 class="yt-shelf-title">
            <span>Built for High-Throughput Production Workloads</span>
          </h2>
          <span class="yt-shelf-sub">Reliable cloud architecture powered by Railway, Neon & Vercel</span>
        </div>

        <div class="features-grid">
          ${features
            .map(
              (f) => `
            <div class="feature-card">
              <div class="feature-icon-wrap">${f.icon}</div>
              <h3 class="feature-title">${esc(f.title)}</h3>
              <p class="feature-desc">${esc(f.desc)}</p>
            </div>`
            )
            .join("")}
        </div>
      </div>
    </section>

    <!-- Pricing Plans Shelf (YouTube Premium Style) -->
    <section class="yt-shelf" id="pricing" style="background:#141414;border-top:1px solid #272727;">
      <div class="container">
        <div class="yt-shelf-header" style="text-align:center;display:block;margin-bottom:32px;">
          <h2 class="yt-shelf-title" style="justify-content:center;margin-bottom:8px;">
            <span>Developer Access Plans & Quotas</span>
          </h2>
          <span class="yt-shelf-sub">Instant key activation via Razorpay (UPI, Cards & Netbanking) or Free Tier</span>
        </div>

        <div class="plans-grid">
          ${plans
            .map(
              (p) => `
            <div class="plan-card ${p.slug === "pro-velocity" || p.slug === "enterprise-nova" ? "featured" : ""}">
              ${p.slug === "enterprise-nova" ? `<span class="plan-tag">Most Popular</span>` : ""}
              <h3 class="plan-name">${esc(p.name)}</h3>
              <p class="plan-desc">${esc(p.description || "High-throughput API plan")}</p>
              <div class="plan-price-wrap">
                <span class="plan-price">${p.price_paise === 0 ? "Free" : formatInr(p.price_paise)}</span>
                <span class="plan-cycle">/ ${p.billing_cycle_days} days</span>
              </div>
              <ul class="plan-features-list">
                <li class="plan-feature-item">
                  <span class="plan-feature-icon">✓</span>
                  <span><strong>${formatNum(p.daily_request_limit)}</strong> requests / day</span>
                </li>
                <li class="plan-feature-item">
                  <span class="plan-feature-icon">✓</span>
                  <span><strong>${p.rate_limit_per_minute}</strong> requests / minute</span>
                </li>
                <li class="plan-feature-item">
                  <span class="plan-feature-icon">✓</span>
                  <span>Full /v1/media/* Audio & Video Extractor</span>
                </li>
                <li class="plan-feature-item">
                  <span class="plan-feature-icon">✓</span>
                  <span>Signed 15-Minute Download Tokens</span>
                </li>
                <li class="plan-feature-item">
                  <span class="plan-feature-icon">✓</span>
                  <span>Telegram Bot Access Included</span>
                </li>
              </ul>
              <button class="btn ${p.slug === "enterprise-nova" ? "btn-primary" : "btn-secondary"}" style="width:100%;" data-buy-plan="${esc(p.id)}">
                ${p.price_paise === 0 ? "Activate Free Plan" : `Subscribe with Razorpay`}
              </button>
            </div>`
            )
            .join("")}
        </div>
      </div>
    </section>

    <!-- FAQ Shelf -->
    ${
      faqs.length
        ? `
      <section class="yt-shelf" style="border-top:1px solid #272727;">
        <div class="container" style="max-width:820px;">
          <div class="yt-shelf-header" style="text-align:center;display:block;margin-bottom:28px;">
            <h2 class="yt-shelf-title" style="justify-content:center;margin-bottom:6px;">Frequently Asked Questions</h2>
            <span class="yt-shelf-sub">Everything you need to know about ${esc(brand.appName)}</span>
          </div>
          <div style="display:flex;flex-direction:column;gap:12px;">
            ${faqs
              .map(
                (faq) => `
              <div class="glass-card" style="padding:18px 22px;">
                <h4 style="margin:0 0 8px;font-size:15px;color:#fff;">${esc(faq.q)}</h4>
                <p style="margin:0;font-size:13.5px;color:#aaa;line-height:1.55;">${esc(faq.a)}</p>
              </div>`
              )
              .join("")}
          </div>
        </div>
      </section>`
        : ""
    }

    <!-- Single Audio/Video Download Preview Modal Template -->
    <div id="yt-download-modal-container"></div>
  `;

  // Attach navigation listeners
  root.querySelectorAll("[data-nav]").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      const target = el.getAttribute("data-nav");
      handlers.navigate(target);
    });
  });

  // Attach Buy Plan listeners
  root.querySelectorAll("[data-buy-plan]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const planId = btn.getAttribute("data-buy-plan");
      const targetPlan = plans.find((p) => p.id === planId);
      if (!targetPlan) return;
      if (!state.user) {
        handlers.openAuthModal("signup");
        showToast("Please create an account or sign in to activate your API plan.", "info");
        return;
      }
      handlers.handlePurchase(targetPlan);
    });
  });

  // Terminal tab switching
  root.querySelectorAll(".terminal-tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      root.querySelectorAll(".terminal-tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      const key = tab.getAttribute("data-tab");
      const contentEl = document.getElementById("terminal-content");
      if (contentEl && terminalSamples[key]) {
        contentEl.innerHTML = terminalSamples[key].code;
      }
    });
  });

  // Interactive Live YouTube Search
  const runLiveSearch = async (query) => {
    if (!query) return;
    const grid = document.getElementById("yt-video-grid");
    const heading = document.getElementById("shelf-heading");
    if (heading) {
      heading.innerHTML = `<span>Results for: "${esc(query)}"</span>`;
    }
    if (grid) {
      grid.innerHTML = `
        <div style="grid-column: 1 / -1; padding: 48px; text-align: center; color: #aaa;">
          <div class="spinner-lg" style="margin: 0 auto 16px;"></div>
          <p style="font-size: 15px; color: #fff;">Searching YouTube and extracting media for "${esc(query)}"...</p>
          <span style="font-size: 12px; color: #717171;">Querying /v1/media/search on Railway backend</span>
        </div>
      `;
    }

    // Scroll smoothly to results
    document.getElementById("shelf-featured")?.scrollIntoView({ behavior: "smooth", block: "start" });

    try {
      const data = await api("/v1/media/search", {
        method: "POST",
        headers: {
          "X-API-Key": demoApiKey,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ query: query, limit: 6 }),
      });

      if (data && data.results && data.results.length > 0) {
        const formatted = data.results.map((r) => ({
          id: r.id,
          title: r.title,
          channel: r.channel || r.uploader || "YouTube",
          avatar: (r.channel || r.uploader || "Y")[0].toUpperCase(),
          views: r.view_count ? `${(r.view_count / 1000000).toFixed(1)}M views` : "Trending",
          time: "Recent",
          duration: r.duration_string || "Audio/Video",
          thumb: r.thumbnail || `https://i.ytimg.com/vi/${r.id}/hqdefault.jpg`,
          downloads: r.downloads,
        }));
        if (grid) {
          grid.innerHTML = formatted.map((song) => renderVideoCardHtml(song, baseUrl, demoApiKey)).join("");
          attachCardActionListeners(grid, formatted, baseUrl, demoApiKey);
        }
      } else {
        if (grid) {
          grid.innerHTML = `
            <div style="grid-column: 1 / -1; padding: 40px; text-align: center; color: #aaa;">
              <p style="font-size: 16px; color: #fff;">No YouTube results found for "${esc(query)}".</p>
              <button class="btn btn-secondary btn-sm" id="btn-reset-shelf">Reset to Trending Songs</button>
            </div>
          `;
          document.getElementById("btn-reset-shelf")?.addEventListener("click", () => {
            renderFeaturedDefaults();
          });
        }
      }
    } catch (err) {
      console.warn("Media search fallback:", err);
      showToast(err.message || "Search request encountered an issue.", "warning");
      renderFeaturedDefaults();
    }
  };

  const renderFeaturedDefaults = () => {
    const grid = document.getElementById("yt-video-grid");
    const heading = document.getElementById("shelf-heading");
    if (heading) {
      heading.innerHTML = `
        <svg width="22" height="18" viewBox="0 0 28 20" fill="none">
          <rect width="28" height="20" rx="5" fill="#FF0000"/>
          <polygon points="11,5.5 19,10 11,14.5" fill="#FFFFFF"/>
        </svg>
        <span>Trending Hindi Songs & Video Downloads</span>
      `;
    }
    if (grid) {
      grid.innerHTML = FEATURED_HINDI_SONGS.map((song) => renderVideoCardHtml(song, baseUrl, demoApiKey)).join("");
      attachCardActionListeners(grid, FEATURED_HINDI_SONGS, baseUrl, demoApiKey);
    }
  };

  // Hero search form submit
  document.getElementById("hero-yt-search-form")?.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = document.getElementById("hero-yt-search-input")?.value?.trim();
    if (q) runLiveSearch(q);
  });

  // Top category chips click
  root.querySelectorAll(".yt-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      root.querySelectorAll(".yt-chip").forEach((c) => c.classList.remove("active"));
      chip.classList.add("active");
      const q = chip.getAttribute("data-query");
      if (q) {
        runLiveSearch(q);
      } else {
        renderFeaturedDefaults();
      }
    });
  });

  // Listen for search dispatched from navbar
  const onNavSearch = (e) => {
    if (e.detail?.query) {
      const heroInput = document.getElementById("hero-yt-search-input");
      if (heroInput) heroInput.value = e.detail.query;
      runLiveSearch(e.detail.query);
    }
  };
  window.addEventListener("yt-search-query", onNavSearch);

  // Initial card action listeners
  const gridEl = document.getElementById("yt-video-grid");
  if (gridEl) {
    attachCardActionListeners(gridEl, FEATURED_HINDI_SONGS, baseUrl, demoApiKey);
  }
}

/**
 * Render HTML for an authentic YouTube video card.
 */
function renderVideoCardHtml(song, baseUrl, apiKey) {
  const safeId = esc(song.id);
  const audioUrl = `${baseUrl}/media/audio?id=${safeId}&format=mp3&bitrate=320`;
  const videoUrl = `${baseUrl}/media/video?id=${safeId}&quality=1080p`;

  return `
    <div class="yt-video-card" data-video-id="${safeId}">
      <div class="yt-thumb-frame" data-action="play-preview" data-id="${safeId}">
        <img class="yt-thumb-img" src="${esc(song.thumb)}" alt="${esc(song.title)}" loading="lazy" />
        <span class="yt-duration-badge">${esc(song.duration)}</span>
      </div>
      <div class="yt-card-body">
        <div class="yt-channel-avatar">${esc(song.avatar)}</div>
        <div class="yt-card-info">
          <h4 class="yt-video-title" title="${esc(song.title)}">${esc(song.title)}</h4>
          <div class="yt-channel-name">
            <span>${esc(song.channel)}</span>
            <span class="yt-verified-icon" title="Verified">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 15-5-5 1.41-1.41L10 14.17l7.59-7.59L19 8l-9 9z"/>
              </svg>
            </span>
          </div>
          <div class="yt-video-stats">${esc(song.views)} • ${esc(song.time)}</div>
          <div class="yt-card-actions">
            <button class="yt-action-chip primary" data-action="download-mp3" data-id="${safeId}" data-title="${esc(song.title)}">
              ⬇ MP3 320k
            </button>
            <button class="yt-action-chip" data-action="download-video" data-id="${safeId}" data-title="${esc(song.title)}">
              🎬 Video 1080p
            </button>
            <button class="yt-action-chip" data-action="copy-api" data-url="${esc(audioUrl)}">
              ⚡ API Link
            </button>
          </div>
        </div>
      </div>
    </div>
  `;
}

/**
 * Attach click handlers to YouTube video cards.
 */
function attachCardActionListeners(grid, songList, baseUrl, apiKey) {
  // MP3 Download Action
  grid.querySelectorAll('[data-action="download-mp3"]').forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const id = btn.getAttribute("data-id");
      const title = btn.getAttribute("data-title");
      openDownloadPreviewModal(id, title, "audio", baseUrl, apiKey);
    });
  });

  // Video Download Action
  grid.querySelectorAll('[data-action="download-video"]').forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const id = btn.getAttribute("data-id");
      const title = btn.getAttribute("data-title");
      openDownloadPreviewModal(id, title, "video", baseUrl, apiKey);
    });
  });

  // Play Preview / Card Click Action
  grid.querySelectorAll(".yt-thumb-frame").forEach((frame) => {
    frame.addEventListener("click", () => {
      const id = frame.getAttribute("data-id");
      const song = songList.find((s) => s.id === id);
      openDownloadPreviewModal(id, song ? song.title : "YouTube Media", "preview", baseUrl, apiKey);
    });
  });

  // Copy API Link
  grid.querySelectorAll('[data-action="copy-api"]').forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const url = btn.getAttribute("data-url");
      const curlSnippet = `curl -L "${url}" -H "X-API-Key: ${apiKey}" -O`;
      try {
        await navigator.clipboard.writeText(curlSnippet);
        showToast("cURL command copied to clipboard!", "success");
      } catch (_) {
        showToast(curlSnippet, "info");
      }
    });
  });
}

/**
 * Realistic YouTube Stream & Download Modal Dialog.
 */
function openDownloadPreviewModal(videoId, title, initialMode, baseUrl, apiKey) {
  const container = document.getElementById("yt-download-modal-container");
  if (!container) return;

  const audio320 = `${baseUrl}/media/audio?id=${videoId}&format=mp3&bitrate=320`;
  const audio192 = `${baseUrl}/media/audio?id=${videoId}&format=mp3&bitrate=192`;
  const audioM4a = `${baseUrl}/media/audio?id=${videoId}&format=m4a`;
  const video1080 = `${baseUrl}/media/video?id=${videoId}&quality=1080p`;
  const video720 = `${baseUrl}/media/video?id=${videoId}&quality=720p`;

  container.innerHTML = `
    <div class="modal-backdrop" id="yt-modal-backdrop">
      <div class="modal-card wide" id="yt-modal-card">
        <div class="modal-header">
          <div style="display:flex;align-items:center;gap:10px;">
            <svg width="24" height="17" viewBox="0 0 28 20" fill="none">
              <rect width="28" height="20" rx="5" fill="#FF0000"/>
              <polygon points="11,5.5 19,10 11,14.5" fill="#FFFFFF"/>
            </svg>
            <h3 style="margin:0;font-size:16px;color:#fff;">YouTube Media Download & Stream Console</h3>
          </div>
          <button class="modal-close" id="btn-close-yt-modal">✕</button>
        </div>

        <div style="display:flex;gap:20px;flex-wrap:wrap;margin-bottom:20px;">
          <div style="flex:1;min-width:280px;">
            <div style="position:relative;aspect-ratio:16/9;border-radius:8px;overflow:hidden;background:#000;margin-bottom:12px;">
              <img src="https://i.ytimg.com/vi/${esc(videoId)}/hqdefault.jpg" style="width:100%;height:100%;object-fit:cover;" />
              <div style="position:absolute;inset:0;background:rgba(0,0,0,0.3);display:flex;align-items:center;justify-content:center;">
                <div style="width:52px;height:52px;border-radius:50%;background:#ff0000;display:flex;align-items:center;justify-content:center;box-shadow:0 4px 16px rgba(0,0,0,0.6);">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="#fff"><polygon points="6,4 20,12 6,20"/></svg>
                </div>
              </div>
            </div>
            <h4 style="margin:0 0 6px;font-size:15px;color:#fff;">${esc(title)}</h4>
            <p style="margin:0;font-size:12.5px;color:#aaa;">YouTube ID: <code style="color:#f1f1f1;">${esc(videoId)}</code></p>
          </div>

          <div style="flex:1;min-width:280px;display:flex;flex-direction:column;gap:14px;">
            <div style="background:#141414;border:1px solid #272727;border-radius:8px;padding:14px;">
              <span style="font-size:11.5px;font-weight:700;color:#aaa;text-transform:uppercase;letter-spacing:0.05em;display:block;margin-bottom:8px;">
                🎵 High-Bitrate Audio Downloads (MP3 / M4A)
              </span>
              <div style="display:flex;flex-direction:column;gap:8px;">
                <a href="${esc(audio320)}" target="_blank" class="btn btn-primary btn-sm" style="justify-content:space-between;text-decoration:none;">
                  <span>⬇ Download MP3 (320kbps Studio)</span>
                  <span style="font-size:11px;opacity:0.8;">Best Audio</span>
                </a>
                <a href="${esc(audio192)}" target="_blank" class="btn btn-secondary btn-sm" style="justify-content:space-between;text-decoration:none;">
                  <span>⬇ Download MP3 (192kbps Standard)</span>
                  <span style="font-size:11px;opacity:0.8;">Fast Download</span>
                </a>
                <a href="${esc(audioM4a)}" target="_blank" class="btn btn-secondary btn-sm" style="justify-content:space-between;text-decoration:none;">
                  <span>⬇ Download M4A (AAC Audio)</span>
                  <span style="font-size:11px;opacity:0.8;">Apple & Mobile</span>
                </a>
              </div>
            </div>

            <div style="background:#141414;border:1px solid #272727;border-radius:8px;padding:14px;">
              <span style="font-size:11.5px;font-weight:700;color:#aaa;text-transform:uppercase;letter-spacing:0.05em;display:block;margin-bottom:8px;">
                🎬 Video Downloads (MP4 Stream)
              </span>
              <div style="display:flex;flex-direction:column;gap:8px;">
                <a href="${esc(video1080)}" target="_blank" class="btn btn-secondary btn-sm" style="justify-content:space-between;text-decoration:none;">
                  <span>⬇ Download Video (1080p Full HD)</span>
                  <span style="font-size:11px;opacity:0.8;">MP4 Video</span>
                </a>
                <a href="${esc(video720)}" target="_blank" class="btn btn-secondary btn-sm" style="justify-content:space-between;text-decoration:none;">
                  <span>⬇ Download Video (720p HD)</span>
                  <span style="font-size:11px;opacity:0.8;">MP4 Video</span>
                </a>
              </div>
            </div>
          </div>
        </div>

        <div style="background:#000;border:1px solid #272727;border-radius:8px;padding:12px;">
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
            <span style="font-size:11.5px;color:#aaa;font-weight:600;">Direct cURL Command (Ready to Run):</span>
            <button class="btn btn-ghost btn-sm" id="btn-copy-modal-curl" style="padding:2px 8px;font-size:11px;">Copy cURL</button>
          </div>
          <pre style="margin:0;font-size:12px;color:#3ea6ff;overflow-x:auto;padding:4px 0;">curl -L "${esc(audio320)}" -H "X-API-Key: ${esc(apiKey)}" -o "${esc(videoId)}.mp3"</pre>
        </div>
      </div>
    </div>
  `;

  document.getElementById("btn-close-yt-modal")?.addEventListener("click", () => {
    container.innerHTML = "";
  });
  document.getElementById("yt-modal-backdrop")?.addEventListener("click", (e) => {
    if (e.target.id === "yt-modal-backdrop") container.innerHTML = "";
  });
  document.getElementById("btn-copy-modal-curl")?.addEventListener("click", async () => {
    const cmd = `curl -L "${audio320}" -H "X-API-Key: ${apiKey}" -o "${videoId}.mp3"`;
    try {
      await navigator.clipboard.writeText(cmd);
      showToast("cURL command copied to clipboard!", "success");
    } catch (_) {
      showToast(cmd, "info");
    }
  });
}
