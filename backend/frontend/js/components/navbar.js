/**
 * YouTube-Realistic Responsive Navigation Bar component.
 */

import { esc, getBrand } from "../api.js";

export function renderNavbar(state, handlers) {
  const root = document.getElementById("navbar-root");
  if (!root) return;

  const user = state.user;
  const route = state.route;
  const brand = getBrand(state);

  const navItems = [
    { id: "landing", label: "Media Hub", hash: "#/" },
    { id: "pricing", label: "Pricing", hash: "#pricing" },
    { id: "docs", label: "API Docs", hash: "#docs" },
    { id: "playground", label: "Playground", hash: "#playground" },
  ];

  const linksHtml = navItems
    .map(
      (item) => `
      <button class="nav-link ${route === item.id ? "active" : ""}" data-nav="${esc(item.hash)}">
        ${esc(item.label)}
      </button>`
    )
    .join("");

  const authActionsHtml = user
    ? `
      <button class="btn btn-secondary btn-sm desktop-only" data-nav="#dashboard">
        Dashboard
      </button>
      ${
        user.role === "admin"
          ? `<button class="btn btn-secondary btn-sm desktop-only" style="border:1px solid #ff4e45;color:#ff4e45;" data-nav="#admin">Admin Portal</button>`
          : ""
      }
      <button class="btn btn-ghost btn-sm desktop-only" id="btn-nav-logout">Logout</button>
    `
    : `
      <button class="btn btn-ghost btn-sm desktop-only" id="btn-nav-login">Sign In</button>
      <button class="btn btn-primary btn-sm desktop-only" id="btn-nav-signup">Get API Key</button>
    `;

  root.innerHTML = `
    <nav class="navbar">
      <div class="container navbar-inner">
        <a class="brand-mark" data-nav="#/" href="#/">
          <div class="brand-icon-yt">
            <svg width="28" height="20" viewBox="0 0 28 20" fill="none" aria-label="YouTube Play Icon">
              <rect width="28" height="20" rx="5.5" fill="#FF0000"/>
              <polygon points="11,5.5 19,10 11,14.5" fill="#FFFFFF"/>
            </svg>
          </div>
          <div class="brand-text-wrap">
            <span class="brand-name">${esc(brand.appName)}</span>
            <span class="brand-badge-pill">API</span>
          </div>
        </a>

        <!-- YouTube Style Center Search Bar -->
        <div class="yt-nav-search">
          <form class="yt-search-box" id="yt-top-search-form">
            <input
              type="text"
              id="yt-top-search-input"
              class="yt-search-input"
              placeholder="Search Hindi songs, artists, YouTube audio or video..."
              autocomplete="off"
            />
            <button type="submit" class="yt-search-btn" title="Search">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <circle cx="11" cy="11" r="8"></circle>
                <path d="m21 21-4.35-4.35"></path>
              </svg>
            </button>
          </form>
        </div>

        <div class="nav-links">
          ${linksHtml}
        </div>

        <div class="nav-actions">
          ${authActionsHtml}
          <button class="mobile-menu-btn" id="btn-mobile-menu" aria-label="Toggle Menu">☰</button>
        </div>
      </div>

      <div class="mobile-drawer" id="mobile-drawer">
        <form class="yt-search-box" id="yt-mobile-search-form" style="margin-bottom:12px;">
          <input
            type="text"
            id="yt-mobile-search-input"
            class="yt-search-input"
            placeholder="Search Hindi songs..."
          />
          <button type="submit" class="yt-search-btn">🔍</button>
        </form>
        ${linksHtml}
        <button class="nav-link" data-nav="#support">Support</button>
        ${
          user
            ? `
            <button class="btn btn-secondary btn-sm" data-nav="#dashboard">Dashboard (${esc(user.full_name || user.email)})</button>
            ${user.role === "admin" ? `<button class="btn btn-secondary btn-sm" data-nav="#admin">Admin Portal</button>` : ""}
            <button class="btn btn-danger btn-sm" id="btn-mobile-logout">Logout</button>
          `
            : `
            <button class="btn btn-secondary btn-sm" id="btn-mobile-login">Sign In</button>
            <button class="btn btn-primary btn-sm" id="btn-mobile-signup">Get API Key</button>
          `
        }
      </div>
    </nav>
  `;

  root.querySelectorAll("[data-nav]").forEach((el) => {
    el.addEventListener("click", (e) => {
      e.preventDefault();
      const target = el.getAttribute("data-nav");
      document.getElementById("mobile-drawer")?.classList.remove("open");
      handlers.navigate(target);
    });
  });

  const handleSearchSubmit = (inputEl) => {
    const q = inputEl?.value?.trim();
    if (!q) return;
    // Dispatch custom search event for landing page or playground
    window.dispatchEvent(new CustomEvent("yt-search-query", { detail: { query: q } }));
    if (state.route !== "landing") {
      handlers.navigate("#/");
    }
  };

  document.getElementById("yt-top-search-form")?.addEventListener("submit", (e) => {
    e.preventDefault();
    handleSearchSubmit(document.getElementById("yt-top-search-input"));
  });

  document.getElementById("yt-mobile-search-form")?.addEventListener("submit", (e) => {
    e.preventDefault();
    document.getElementById("mobile-drawer")?.classList.remove("open");
    handleSearchSubmit(document.getElementById("yt-mobile-search-input"));
  });

  document.getElementById("btn-mobile-menu")?.addEventListener("click", () => {
    document.getElementById("mobile-drawer")?.classList.toggle("open");
  });

  document.getElementById("btn-nav-login")?.addEventListener("click", () => handlers.openAuthModal("login"));
  document.getElementById("btn-nav-signup")?.addEventListener("click", () => handlers.openAuthModal("signup"));
  document.getElementById("btn-nav-logout")?.addEventListener("click", () => handlers.logout());
  document.getElementById("btn-mobile-login")?.addEventListener("click", () => handlers.openAuthModal("login"));
  document.getElementById("btn-mobile-signup")?.addEventListener("click", () => handlers.openAuthModal("signup"));
  document.getElementById("btn-mobile-logout")?.addEventListener("click", () => handlers.logout());
}
