/**
 * Responsive Navigation Bar component.
 */

import { esc, getBrand } from "../api.js";

export function renderNavbar(state, handlers) {
  const root = document.getElementById("navbar-root");
  if (!root) return;

  const user = state.user;
  const route = state.route;
  const brand = getBrand(state);

  const navItems = [
    { id: "landing", label: "Platform", hash: "#/" },
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
          ? `<button class="btn btn-secondary btn-sm desktop-only" style="border-color:#0a0a0a;font-weight:700;" data-nav="#admin">Admin Portal</button>`
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
          <div class="brand-icon">${esc(brand.brandLetter)}</div>
          <div class="brand-text-wrap">
            <span class="brand-name">${esc(brand.appName)}</span>
            <span class="brand-sub">by ${esc(brand.companyName)}</span>
          </div>
        </a>

        <div class="nav-links">
          ${linksHtml}
          <button class="nav-link ${route === "support" ? "active" : ""}" data-nav="#support">Support</button>
        </div>

        <div class="nav-actions">
          ${authActionsHtml}
          <button class="mobile-menu-btn" id="btn-mobile-menu" aria-label="Toggle Menu">☰</button>
        </div>
      </div>

      <div class="mobile-drawer" id="mobile-drawer">
        ${linksHtml}
        <button class="nav-link" data-nav="#support">Support</button>
        ${
          user
            ? `
            <button class="btn btn-secondary btn-sm" data-nav="#dashboard">Developer Dashboard (${esc(user.full_name || user.email)})</button>
            ${user.role === "admin" ? `<button class="btn btn-secondary btn-sm" data-nav="#admin">Admin Portal</button>` : ""}
            <button class="btn btn-danger btn-sm" id="btn-mobile-logout">Logout</button>
          `
            : `
            <button class="btn btn-secondary btn-sm" id="btn-mobile-login">Sign In</button>
            <button class="btn btn-primary btn-sm" id="btn-mobile-signup">Create Account</button>
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

  document.getElementById("btn-mobile-menu")?.addEventListener("click", () => {
    document.getElementById("mobile-drawer")?.classList.toggle("open");
  });

  document.getElementById("btn-nav-login")?.addEventListener("click", () => handlers.openAuth("login"));
  document.getElementById("btn-nav-signup")?.addEventListener("click", () => handlers.openAuth("register"));
  document.getElementById("btn-mobile-login")?.addEventListener("click", () => {
    document.getElementById("mobile-drawer")?.classList.remove("open");
    handlers.openAuth("login");
  });
  document.getElementById("btn-mobile-signup")?.addEventListener("click", () => {
    document.getElementById("mobile-drawer")?.classList.remove("open");
    handlers.openAuth("register");
  });

  document.getElementById("btn-nav-logout")?.addEventListener("click", handlers.logout);
  document.getElementById("btn-mobile-logout")?.addEventListener("click", handlers.logout);
}

