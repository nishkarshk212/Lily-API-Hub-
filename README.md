<div align="center">

<!-- Dynamic Self-Hosted Animated SVG Hero Banner -->
<a href="#-quick-start">
  <img src="./docs/assets/banner-hero.svg" alt="Beta API Hub Dynamic Animated Banner" width="100%" />
</a>

<br />

<!-- Colorful Tech Stack & Status Badges -->
<p>
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Python-3.12%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/SQLAlchemy-2.0-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white" alt="SQLAlchemy" />
  <img src="https://img.shields.io/badge/Razorpay-HMAC--SHA256-072654?style=for-the-badge&logo=razorpay&logoColor=3395FF" alt="Razorpay" />
  <img src="https://img.shields.io/badge/OAuth%202.0-Google-4285F4?style=for-the-badge&logo=google&logoColor=white" alt="Google OAuth" />
  <img src="https://img.shields.io/badge/Pytest-24%2F24%20Passed-10B981?style=for-the-badge&logo=pytest&logoColor=white" alt="Pytest 24/24 Passing" />
  <img src="https://img.shields.io/badge/Compression-GZip%20%2B%20TTL%20Cache-00F2FE?style=for-the-badge&logo=fastapi&logoColor=black" alt="GZip + TTL Cache" />
</p>

<!-- Interactive Quick Navigation Bar -->
<p>
  <a href="#-platform-highlights"><img src="https://img.shields.io/badge/Highlights-6366F1?style=flat-square" /></a>
  <a href="#-gateway-architecture"><img src="https://img.shields.io/badge/Architecture-8B5CF6?style=flat-square" /></a>
  <a href="#-quick-start"><img src="https://img.shields.io/badge/Quick%20Start-10B981?style=flat-square" /></a>
  <a href="#-white-label-branding"><img src="https://img.shields.io/badge/White--Label%20Branding-EC4899?style=flat-square" /></a>
  <a href="#-admin-command-center"><img src="https://img.shields.io/badge/Admin%20Panel-F59E0B?style=flat-square" /></a>
  <a href="#-api-endpoints--quickstart"><img src="https://img.shields.io/badge/API%20Docs-0EA5E9?style=flat-square" /></a>
  <a href="#-cloud-deployment"><img src="https://img.shields.io/badge/Deploy-E11D48?style=flat-square" /></a>
</p>

<h3>
  <strong>Production-Ready API Gateway, Razorpay Monetization Engine, Interactive Developer Dashboard &amp; Colorful Admin Control Center.</strong>
</h3>

<p>
  Issue unique customer API keys · Enforce sliding-window rate limits &amp; daily/monthly quotas · Inject encrypted Master Upstream credentials exclusively server-side · Rebrand the entire platform via <code>.env</code> or the live Admin UI.
</p>

</div>

---

## ✨ Platform Highlights

<table>
  <tr>
    <td width="50%" valign="top">
      <h3>🔐 Isolated Master API Proxy</h3>
      <ul>
        <li>Supports <code>hybrid</code>, strict <code>proxy</code>, and <code>builtin</code> routing modes.</li>
        <li>Encrypts <code>MASTER_API_KEY</code> at rest with Fernet/AES; decrypted only in server RAM.</li>
        <li>Validates customer keys via <code>SHA-256</code> hash with instant revoke &amp; rotation.</li>
        <li>Supports configurable headers (e.g. <code>X-API-Key</code> or <code>Authorization: Bearer</code>) for Cloudflare Workers &amp; REST backends.</li>
      </ul>
    </td>
    <td width="50%" valign="top">
      <h3>📊 Interactive Developer Dashboard</h3>
      <ul>
        <li>Dynamic <strong>Credentials &amp; Base URL</strong> card with one-click Reveal, Copy, and Generate Key actions.</li>
        <li>Built-in <strong>Plans Section</strong> displaying Free Sandbox &amp; paid tiers with instant activation/upgrade.</li>
        <li>Animated <strong>Line + Bar Usage Charts</strong> and real-time quota progress bars.</li>
        <li>Built-in <strong>API Playground</strong> for testing live requests with latency &amp; header inspection.</li>
      </ul>
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <h3>💳 Razorpay Checkout &amp; Webhooks</h3>
      <ul>
        <li>Server-authoritative pricing (<code>price_paise</code> read directly from DB).</li>
        <li>Constant-time <strong>HMAC-SHA256</strong> signature verification &amp; Razorpay order cross-check.</li>
        <li>Idempotent webhook processing (<code>webhook_events</code>) prevents duplicate provisioning.</li>
        <li>Automated HTML/JSON receipts, pending-order reconciliation, and refund revocation.</li>
      </ul>
    </td>
    <td width="50%" valign="top">
      <h3>🎨 White-Label &amp; Colorful Admin UI</h3>
      <ul>
        <li>Full 10-tab <strong>Admin Command Center</strong> (<code>#admin</code>) with color-coded KPIs &amp; Telegram Bot Console.</li>
        <li>Manage users, promote/demote roles, revoke keys, edit plan pricing &amp; quotas live.</li>
        <li>Connect <strong>@BotFather Telegram Bots</strong> straight from Dashboard &amp; Admin Panel (Webhooks + Polling).</li>
        <li>Live <strong>Site &amp; API Branding Editor</strong> with real-time preview &amp; one-click <code>.env</code> reset.</li>
        <li>Custom <code>APP_NAME</code>, <code>COMPANY_NAME</code>, key prefixes, receipt codes &amp; dynamic SVG favicon.</li>
      </ul>
    </td>
  </tr>
  <tr>
    <td width="50%" valign="top">
      <h3>⚡ High-Throughput &amp; Latency Optimization</h3>
      <ul>
        <li><strong>In-Memory TTL Cache</strong>: Thread-safe caching for hot public endpoints (<code>/api/public/overview</code>, <code>/api/plans</code>, branding) with instant cache invalidation on admin edits.</li>
        <li><strong>GZip Compression Middleware</strong>: Automatic gzip compression for all payloads > 1KB (media search & metadata results).</li>
        <li><strong>Persistent Connection Pooling</strong>: Reusable <code>httpx.AsyncClient</code> pool with keep-alive across concurrent proxy requests to prevent socket churn.</li>
        <li><strong>Composite DB Indexes</strong>: Fast analytics queries via composite indexes on <code>api_request_logs</code> (<code>user_id + created_at</code>, <code>api_key_id + created_at</code>).</li>
      </ul>
    </td>
    <td width="50%" valign="top">
      <h3>🎵 Built-In YouTube &amp; Media Downloader</h3>
      <ul>
        <li>Direct <code>/v1/media/search</code>, <code>/v1/media/info</code>, <code>/v1/media/audio</code>, and <code>/v1/media/video</code> endpoints.</li>
        <li>High-speed audio transcode (MP3/M4A up to 320kbps) &amp; video muxing (1080p/720p/360p MP4).</li>
        <li>Encrypted Netscape YouTube cookies with automatic rotation and bot verification bypass.</li>
        <li>Signed binary token downloads with one-time verification.</li>
      </ul>
    </td>
  </tr>
</table>

---

## 🔀 Gateway Architecture

<div align="center">
  <img src="./docs/assets/banner-architecture.svg" alt="Beta API Hub Isolated Master Gateway Lifecycle" width="100%" />
</div>

<details>
<summary><b>🔭 Click to expand Interactive Mermaid System Flowchart (Zoom &amp; Pan)</b></summary>

```mermaid
flowchart LR
    Dev["👩‍💻 Developer App / Playground"] -->|"X-API-Key or Bearer Token"| Auth["🛡️ Key & Subscription Guard<br/>(SHA-256 · Expiry · Method ACL)"]
    Auth -->|"Pass"| Quota["⏱️ Atomic Quota & Rate Limiter<br/>(Sliding 60s Window · Daily UTC · Cycle)"]
    Auth -->|"Invalid / Expired / Suspended"| Err4xx["🚫 HTTP 401 / 403 / 429 JSON"]
    Quota -->|"Built-in Route"| Builtin["⚙️ FastAPI Built-in Utilities<br/>(/status, /hash, /uuid, /dns, /ip-parse)"]
    Quota -->|"Proxy Fallback / Strict Proxy"| Vault["🔑 Fernet Key Vault<br/>(Decrypts MASTER_API_KEY in RAM)"]
    Vault -->|"Injects Auth Header + Context"| Origin["☁️ Upstream Master API<br/>(Cloudflare Worker / Origin Backend)"]
    Builtin --> Log["📈 Request Telemetry & Charts DB"]
    Origin --> Log
```

</details>

---

## ⚡ Quick Start

<details open>
<summary><b>🚀 Run Locally in 60 Seconds (SQLite Zero-Config)</b></summary>

### 1. Configure Backend Environment
```bash
cd backend
cp .env.example .env
# Edit backend/.env to customize APP_NAME, SECRET_KEY, FRONTEND_URL, RAZORPAY_*, UPSTREAM_API_BASE_URL, and MASTER_API_KEY
```

### 2. Install Dependencies & Start Backend Server
```bash
python3 -m venv ../.venv
source ../.venv/bin/activate
pip install -r requirements.txt

uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

*(Optional) Run Frontend Independently on Port `3000` (Cross-Origin Decoupled Test):*
```bash
cd ../frontend
API_BASE_URL="http://127.0.0.1:8000" sh build-config.sh
python3 -m http.server 3000
```

### 3. Explore Portal Routes
| Surface | URL | Purpose |
| :--- | :--- | :--- |
| **Landing & Pricing** | `http://127.0.0.1:8000/` | Hero terminal, live plans, quickstart & support |
| **Developer Dashboard** | `http://127.0.0.1:8000/#dashboard` | Generate/reveal API keys, view line+bar usage & billing |
| **API Playground** | `http://127.0.0.1:8000/#playground` | Execute live `GET/POST/PUT/DELETE` calls with telemetry |
| **Documentation** | `http://127.0.0.1:8000/#docs` | Auto-generated endpoint docs, headers & code snippets |
| **Admin Command Center** | `http://127.0.0.1:8000/#admin/login` | Full management UI (seed creds configured in `.env`) |
| **OpenAPI / Health** | `http://127.0.0.1:8000/docs` · `/healthz` | Interactive Swagger schema & JSON health probe |

</details>

---

## 🏷️ White-Label Branding

Rename **Beta API Hub** and **Sonic Network** to any brand in seconds—no code edits needed.

<details>
<summary><b>✨ Click to view all `.env` Branding Variables &amp; Live Admin Override Behavior</b></summary>

Update `.env` (or edit live inside **Admin Portal → Site & API Branding**, stored in `site_branding_config` and cleanly resettable to `.env` defaults):

| Environment Variable | Default Example | Controls |
| :--- | :--- | :--- |
| `APP_NAME` | `Beta API Hub` | Navbar title, page `<title>`, emails, Hero/Docs copy & `/v1/status` |
| `COMPANY_NAME` | `Sonic Network` | Subtitle, footer, support section, gateway provider metadata |
| `BRAND_BADGE_LETTER` | `""` *(auto first char)* | Navbar brand square icon & dynamic SVG `/favicon.svg` |
| `SUPPORT_EMAIL` | `support@sonicnetwork.dev` | Public support block, email templates & admin login hint |
| `SITE_META_DESCRIPTION` | `Purchase API access plans...` | HTML `<meta name="description">` injected server-side |
| `API_KEY_PREFIX_LIVE` | `beta_live_` | Prefix used when minting new live customer API keys |
| `API_KEY_PREFIX_TEST` | `beta_test_` | Prefix used for test API keys *(legacy prefixes stay valid)* |
| `RECEIPT_PREFIX` | `BETA` | Prefix on generated Razorpay payment receipt numbers |

</details>

---

## 🎛️ Admin Command Center

Sign in at **`/#admin/login`** using `INITIAL_ADMIN_EMAIL` & `INITIAL_ADMIN_PASSWORD` from `.env` to unlock 9 colorful management workspaces:

<details>
<summary><b>🧩 Click to explore all 9 Admin Control Modules</b></summary>

| Tab | Accent | Capabilities |
| :--- | :---: | :--- |
| **Platform Analytics** | 🟣 Indigo | Verified revenue, active subscriptions, 24h traffic, avg latency, 7-day chart & top endpoints |
| **Users & Roles** | 🟢 Emerald | Filter developers, suspend/reactivate accounts, verify emails & promote/demote `user` / `admin` roles |
| **API Keys Vault** | 🟠 Amber | Search across all customer keys by owner, label, or masked preview & revoke keys with 403 cutoff |
| **Plans & Pricing** | 🟣 Violet | Create, edit & archive plans (INR price, cycle days, daily/monthly quotas, RPM, max keys, HTTP verbs) |
| **Payments & Webhooks** | 🔵 Cyan | Search Razorpay orders, inspect IDs, download receipts, reconcile pending orders & mark refunded |
| **Request Monitor** | 🔴 Rose | Filter real-time gateway request logs by HTTP status (`200`–`502`), user email, path, or error code |
| **Master API Config** | 🔷 Cobalt | Switch `hybrid` / `proxy` / `builtin`, rotate encrypted `MASTER_API_KEY`, configure headers & test upstream |
| **Site & API Branding** | 💖 Fuchsia | Edit site/company names, key prefixes, support email & description with **live preview** or reset to `.env` |
| **Support, Audit & Outbox** | 🩵 Teal | Resolve/reopen support tickets, audit admin actions & inspect dev-mode captured emails |

</details>

---

## 🔌 API Endpoints & Quickstart

<details>
<summary><b>📡 Click for Built-in Gateway Routes, Response Headers &amp; Copy-Ready Code Snippets</b></summary>

### Built-in Gateway Routes (`/v1/*`)
*(In `hybrid` mode, any route not listed below is automatically proxied to your configured `UPSTREAM_API_BASE_URL`)*

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/v1/status` | Authenticated gateway health, plan status, and provider info |
| `ALL` | `/v1/network/echo` | Mirrors method, query params, sanitized headers, client IP & JSON payload |
| `GET` | `/v1/network/dns?domain=example.com` | Real-time A / AAAA DNS resolution |
| `GET` | `/v1/geo/ip-parse?ip=8.8.8.8` | IPv4/IPv6 inspection, range classification & PTR pointer |
| `POST` | `/v1/crypto/hash` | Compute `sha256` / `sha512` / `blake2b` / `md5` digests |
| `GET` | `/v1/crypto/uuid` | Generate cryptographically random UUIDv4 tokens |
| `GET` | `/v1/utils/timestamp` | Synchronized ISO-8601 UTC & Unix timestamps |
| `POST` | `/v1/utils/json-validate` | Validate JSON syntax and report object size & key count |
| `GET/POST` | `/v1/media/search` (`/v1/yt/search`) | Search songs & videos with metadata, thumbnails & signed download URLs |
| `GET/POST` | `/v1/media/info` (`/v1/yt/info`) | Full track/video metadata, music tags, channel stats, chapters, captions & all formats |
| `GET/POST` | `/v1/media/audio` (`/v1/media/song`) | Download/stream audio (`mp3`, `m4a`, `opus`, `webm`, `original`) or `mode=json` |
| `GET/POST` | `/v1/media/video` (`/v1/yt/video`) | Download/stream muxed video (`1080p`, `720p`, `480p`, `360p`, `best`) in `mp4`/`webm` |
| `GET/POST` | `/v1/media/download` | Unified media downloader (`type=audio\|video\|info`) |
| `GET` | `/v1/media/file?token=...` | 15-minute HMAC-signed download URL without exposing raw API keys |

### Quickstart Snippets

**cURL**
```bash
curl -s -X POST "http://127.0.0.1:8000/v1/crypto/hash" \
  -H "X-API-Key: YOUR_CUSTOMER_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"text":"hello gateway","algorithm":"sha256"}'
```

**Python (`requests`)**
```python
import requests

resp = requests.get(
    "http://127.0.0.1:8000/v1/status",
    headers={"X-API-Key": "YOUR_CUSTOMER_API_KEY"},
    timeout=10,
)
print(resp.status_code, resp.json())
```

**JavaScript (`fetch`)**
```js
const res = await fetch("http://127.0.0.1:8000/v1/status", {
  headers: { "Authorization": "Bearer YOUR_CUSTOMER_API_KEY" },
});
console.log(res.status, await res.json());
```

### Standard Gateway Telemetry Headers
Every `/v1/*` response returns:
`X-Request-Id` · `X-RateLimit-Limit` · `X-RateLimit-Remaining` · `X-Quota-Daily-Remaining` · `X-Quota-Monthly-Remaining` · `X-Beta-Plan` · `X-Gateway-Mode`

</details>

---

## ☁️ Cloud Deployment

Production blueprints are included out of the box—see [**`DEPLOYMENT_GUIDE.md`**](./DEPLOYMENT_GUIDE.md) and [**`RAZORPAY_GUIDE.md`**](./RAZORPAY_GUIDE.md) for full checklists.

<details open>
<summary><b>🌐 Decoupled Architecture: Frontend (Vercel / Cloudflare Pages) + Backend (Render / Railway)</b></summary>

| Component | Recommended Host | Root / Config | Why It Fits Best |
| :--- | :--- | :--- | :--- |
| **Frontend (`frontend/`)** | **Vercel** or **Cloudflare Pages** | Root Directory: `frontend` (`vercel.json`, `_redirects`) | Pure static HTML/CSS/ES6 CDN — zero cold starts, global edge cache, free SSL |
| **Backend (`backend/`)** | **Render** (`render.yaml`) or **Railway** (`railway.toml`) | Root Directory: `backend` (`Dockerfile`) | Stateful persistent Python container for rate limits, webhooks, PostgreSQL & upstream proxying |
| **Upstream API** | **Cloudflare Workers** | Linked via `UPSTREAM_API_BASE_URL` + `MASTER_API_KEY` | Low-latency edge API origin protected behind Beta Gateway |
| **VPS All-in-One** | **Ubuntu VPS (Docker + Nginx TLS)** | [`docker-compose.yml`](./docker-compose.yml) · [`deploy/nginx.conf`](./deploy/nginx.conf) | Runs PostgreSQL 15 + FastAPI (`:8000`) + Same-Origin Nginx Proxy (`:3000`) cleanly together |

> **Connecting Split Frontend → Backend:** Set `API_BASE_URL=https://your-backend-url` in Vercel/Cloudflare Pages (`sh build-config.sh`), and set `FRONTEND_URL=https://your-frontend-url` + `CORS_ORIGINS` on your Backend so cookies, Bearer sessions, Google OAuth redirects, email links & receipts work seamlessly.

> **VPS Quick Launch:** `cp backend/.env.example backend/.env && export POSTGRES_PASSWORD="strong_password" && docker compose up -d --build` (see [`DEPLOYMENT_GUIDE.md`](./DEPLOYMENT_GUIDE.md) Section 3 for Nginx + Certbot HTTPS setup).

</details>

---

## 🧪 Testing & Repository Layout

<details>
<summary><b>🧪 Click to view Test Coverage (21/21 Passing) &amp; Two-Part Project Structure</b></summary>

Run the full automated suite from `backend/`:
```bash
cd backend
source ../.venv/bin/activate
pytest -v
```

| Test Module | Coverage |
| :--- | :--- |
| [`backend/tests/test_auth.py`](./backend/tests/test_auth.py) | Registration, login, email verification, password reset & Google OAuth CSRF state validation |
| [`backend/tests/test_gateway_quotas.py`](./backend/tests/test_gateway_quotas.py) | Key reveal/rotate/revoke, max-key caps, built-in endpoints, rate limits, expiry & Master proxy injection |
| [`backend/tests/test_media_api.py`](./backend/tests/test_media_api.py) | Media search, full details, SSRF validation, MP3/MP4 streaming, signed URLs & Admin cookies config |
| [`backend/tests/test_razorpay.py`](./backend/tests/test_razorpay.py) | Razorpay order creation, HMAC verification, webhook idempotency, cancellation & reconciliation |
| [`backend/tests/test_admin.py`](./backend/tests/test_admin.py) | Admin RBAC isolation, user suspension, plan CRUD, Vercel fallback, cross-origin Bearer auth & live branding |
| [`backend/tests/test_telegram.py`](./backend/tests/test_telegram.py) | @BotFather onboarding, coloured `ButtonStyle` menus, per-key usage analytics, webhooks, polling & alerts |

```text
.
├── frontend/                        # Part 1 — Standalone Static Web App (Vercel / Cloudflare Pages / Netlify)
│   ├── index.html                   # SPA shell
│   ├── config.js                    # Runtime API_BASE_URL injection target
│   ├── build-config.sh              # Env var -> config.js script for static hosts
│   ├── vercel.json · _redirects · _headers
│   ├── css/                         # tokens.css, base.css, landing.css, dashboard.css, admin.css
│   └── js/                          # api.js (Bearer + Cookie), app router, charts, modals, telegramPanel & 5 pages
├── backend/                         # Part 2 — FastAPI API, Gateway, Razorpay, Telegram Bot & DB
│   ├── app/
│   │   ├── main.py                  # FastAPI app, dynamic SVG favicon, CORS & Telegram polling lifecycle
│   │   ├── core/                    # Config (.env), SQLAlchemy engine, Fernet security, email & seed
│   │   ├── models/                  # User, Plan, ApiKey, Payment, MasterGateway, MediaGatewayConfig, SiteBranding, TelegramBot
│   │   ├── routers/                 # Auth, Public, Plans, Keys, Payments, Playground, Telegram, Admin, Gateway (/v1)
│   │   ├── schemas/                 # Pydantic v2 validation schemas
│   │   └── services/                # Auth, Branding, Key minting, Gateway proxy, Media extractor, Razorpay & Telegram engine
│   ├── telegram_bot_worker.py       # Optional standalone long-polling CLI worker
│   ├── tests/                       # 21 end-to-end automated integration tests
│   ├── Dockerfile · .dockerignore · railway.toml
│   └── requirements.txt · pyproject.toml · .env.example
├── docs/assets/                     # Custom animated SVG banners & architecture visuals
├── deploy/nginx.conf                # Unified Nginx proxy config for VPS / Docker Compose
├── docker-compose.yml               # VPS / Local 3-container stack (Postgres + Backend + Nginx Frontend)
├── render.yaml                      # Root Render Blueprint targeting backend/Dockerfile
├── vercel.json                      # Static frontend Vercel deploy config
├── DEPLOYMENT_GUIDE.md              # Cloud deployment checklist
└── RAZORPAY_GUIDE.md                # Test/Live Razorpay setup & webhook security guide
```

</details>

---

<div align="center">

<img src="./docs/assets/footer-wave.svg" alt="Beta API Hub Animated Footer" width="100%" />

</div>
