/**
 * Main SPA Router, Session Bootstrap, and Razorpay Checkout Orchestrator.
 */

import { api, getBrand, showToast } from "./api.js";
import { openAuthModal } from "./components/modals.js";
import { renderNavbar } from "./components/navbar.js";
import { renderAdminDashboardPage, renderAdminLoginPage } from "./pages/admin.js";
import { renderDashboardPage } from "./pages/dashboard.js";
import { renderDocsPage } from "./pages/docs.js";
import { renderLandingPage } from "./pages/landing.js";
import { renderPlaygroundPage } from "./pages/playground.js";

const state = {
  user: null,
  subscription: null,
  keys: [],
  plans: [],
  overview: null,
  route: "landing",
  dashboardTab: "overview",
  adminTab: "analytics",
  playgroundPreset: null,
  playgroundKeyId: null,
};

function parseRoute() {
  const hash = window.location.hash || "";
  const path = window.location.pathname;
  if (hash) {
    const clean = hash.replace(/^#\/?/, "");
    const [routePart, queryPart] = clean.split("?");
    return { route: routePart || "landing", params: new URLSearchParams(queryPart || "") };
  }
  const cleanPath = path.replace(/^\/+/, "");
  if (cleanPath === "docs-portal") return { route: "docs", params: new URLSearchParams() };
  if (cleanPath) return { route: cleanPath, params: new URLSearchParams(window.location.search) };
  return { route: "landing", params: new URLSearchParams() };
}

async function refreshSession() {
  try {
    const me = await api.get("/api/auth/session");
    state.user = me.authenticated ? me.user : null;
    state.subscription = me.authenticated ? me.subscription : null;
  } catch {
    state.user = null;
    state.subscription = null;
  }
}

async function refreshPublicData() {
  const [overview, plans] = await Promise.all([api.get("/api/public/overview"), api.get("/api/plans")]);
  state.overview = overview;
  state.plans = plans;
  document.title = `${overview.brand || "Lily API Hub"} by ${overview.company || "Sonic Network"}`;
}

const handlers = {
  refreshPublicData,
  refreshChrome() {
    renderNavbar(state, handlers);
    const brand = getBrand(state);
    document.title = `${brand.appName} by ${brand.companyName}`;
    const fav = document.querySelector('link[rel="icon"]');
    if (fav) fav.href = `/favicon.svg?v=${Date.now()}`;
  },
  navigate(target) {
    if (target === "#pricing" || target === "#support") {
      const sectionId = target === "#pricing" ? "section-pricing" : "section-support";
      if (state.route !== "landing") {
        window.location.hash = "#/";
        setTimeout(() => document.getElementById(sectionId)?.scrollIntoView({ behavior: "smooth" }), 90);
      } else {
        document.getElementById(sectionId)?.scrollIntoView({ behavior: "smooth" });
      }
      return;
    }
    window.location.hash = target;
  },

  openAuth(mode = "login", resetToken = "", onSuccess = null) {
    const brand = getBrand(state);
    openAuthModal({
      mode,
      brand,
      googleEnabled: Boolean(state.overview?.google_oauth_enabled),
      resetToken,
      onAuthSuccess: async (user) => {
        state.user = user;
        await refreshSession();
        if (onSuccess) {
          await onSuccess();
        } else {
          await renderCurrentRoute();
        }
      },
    });
  },

  async logout() {
    try {
      await api.post("/api/auth/logout", {});
    } catch {
      // Ignore if session already expired
    }
    state.user = null;
    state.subscription = null;
    state.keys = [];
    showToast("Signed out safely.", "info");
    window.location.hash = "#/";
    await renderCurrentRoute();
  },

  async refreshPublicPlans() {
    state.plans = await api.get("/api/plans");
  },

  openInPlayground(ep) {
    state.playgroundPreset = ep;
    window.location.hash = "#playground";
  },

  async purchasePlan(planId, action = "new") {
    const plan = state.plans.find((p) => p.id === planId);
    if (!plan) return;

    if (!state.user) {
      handlers.openAuth("register", "", () => handlers.purchasePlan(planId, action));
      return;
    }

    if (plan.price_paise === 0) {
      try {
        const res = await api.post(`/api/subscriptions/activate-free?plan_id=${encodeURIComponent(planId)}`, {});
        showToast(res.message, "success");
        await refreshSession();
        state.dashboardTab = "keys";
        window.location.hash = "#dashboard";
      } catch (err) {
        showToast(err.message, "error");
      }
      return;
    }

    if (typeof window.Razorpay === "undefined") {
      showToast("Razorpay Checkout script failed to load. Check internet connectivity.", "error");
      return;
    }

    let orderData;
    try {
      orderData = await api.post("/api/payments/create-order", { plan_id: planId, action });
    } catch (err) {
      showToast(err.message, "error", 6000);
      return;
    }

    const brand = getBrand(state);
    const rzp = new window.Razorpay({
      key: orderData.key_id,
      amount: orderData.amount_paise,
      currency: orderData.currency,
      name: brand.appName,
      description: orderData.plan_description,
      order_id: orderData.razorpay_order_id,
      prefill: orderData.prefill,
      theme: { color: "#0a0a0a" },
      handler: async (response) => {
        try {
          const verified = await api.post("/api/payments/verify", {
            razorpay_order_id: response.razorpay_order_id,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature: response.razorpay_signature,
          });
          showToast(verified.message || "Payment verified & API key activated!", "success", 6000);
          await refreshSession();
          state.dashboardTab = "keys";
          window.location.hash = "#dashboard";
        } catch (err) {
          showToast(`Verification error: ${err.message}`, "error", 6500);
        }
      },
      modal: {
        ondismiss: async () => {
          try {
            await api.post("/api/payments/cancel", {
              razorpay_order_id: orderData.razorpay_order_id,
              reason: "Checkout closed before payment completion",
            });
            showToast("Checkout cancelled.", "info");
          } catch {
            // Non-blocking
          }
        },
      },
    });

    rzp.on("payment.failed", async (failResp) => {
      try {
        await api.post("/api/payments/mark-failed", {
          razorpay_order_id: orderData.razorpay_order_id,
          razorpay_payment_id: failResp?.error?.metadata?.payment_id || null,
          reason: failResp?.error?.description || "Payment failed at Razorpay",
        });
      } catch {
        // Non-blocking
      }
      showToast(failResp?.error?.description || "Payment failed.", "error", 6000);
    });

    rzp.open();
  },
};

async function renderCurrentRoute() {
  const { route, params } = parseRoute();

  // Handle email verification deep link
  if (route === "verify-email" && params.get("token")) {
    try {
      const res = await api.post("/api/auth/verify-email", { token: params.get("token") });
      showToast(res.message, "success", 5500);
      await refreshSession();
    } catch (err) {
      showToast(err.message, "error", 5500);
    }
    window.location.hash = state.user ? "#dashboard" : "#/";
    return;
  }

  // Handle password reset deep link
  if (route === "reset-password" && params.get("token")) {
    state.route = "landing";
    renderNavbar(state, handlers);
    renderLandingPage(state, handlers);
    handlers.openAuth("reset", params.get("token"));
    return;
  }

  if (route === "login") {
    state.route = "landing";
    renderNavbar(state, handlers);
    renderLandingPage(state, handlers);
    handlers.openAuth("login");
    return;
  }

  // Protected user routes
  if (route === "dashboard" || route === "playground") {
    if (!state.user) {
      state.route = "landing";
      renderNavbar(state, handlers);
      renderLandingPage(state, handlers);
      showToast("Please sign in to access your Developer Workspace.", "info");
      handlers.openAuth("login", "", async () => {
        window.location.hash = `#${route}`;
      });
      return;
    }
  }

  state.route = route;
  renderNavbar(state, handlers);

  if (route === "docs") {
    renderDocsPage(state, handlers);
  } else if (route === "dashboard") {
    await renderDashboardPage(state, handlers);
  } else if (route === "playground") {
    await renderPlaygroundPage(state, handlers);
  } else if (route === "admin/login") {
    renderAdminLoginPage(state, handlers);
  } else if (route === "admin") {
    await renderAdminDashboardPage(state, handlers);
  } else {
    state.route = "landing";
    renderLandingPage(state, handlers);
  }
}

async function boot() {
  const queryParams = new URLSearchParams(window.location.search);
  if (queryParams.get("auth_error")) {
    showToast(`Authentication notice: ${queryParams.get("auth_error")}`, "error", 6000);
  }

  await Promise.all([refreshPublicData(), refreshSession()]);
  await renderCurrentRoute();
}

window.addEventListener("hashchange", renderCurrentRoute);
boot();

