/**
 * Reusable Modal dialogs: Authentication, Confirm, New Key, Admin Plan Editor.
 */

import { api, apiUrl, esc, setAuthToken, showToast } from "../api.js";

export function closeModal() {
  const root = document.getElementById("modal-root");
  if (root) root.innerHTML = "";
}

export function openConfirmModal({ title, message, confirmLabel = "Confirm", danger = false, onConfirm }) {
  const root = document.getElementById("modal-root");
  if (!root) return;

  root.innerHTML = `
    <div class="modal-backdrop" id="confirm-backdrop">
      <div class="modal-card">
        <div class="modal-header">
          <div>
            <h3 style="margin:0 0 6px;">${esc(title)}</h3>
            <p style="margin:0;font-size:14px;color:var(--text-muted);">${esc(message)}</p>
          </div>
          <button class="modal-close" id="confirm-close">×</button>
        </div>
        <div style="display:flex;justify-content:flex-end;gap:10px;margin-top:20px;">
          <button class="btn btn-secondary" id="confirm-cancel">Cancel</button>
          <button class="btn ${danger ? "btn-danger" : "btn-primary"}" id="confirm-ok">${esc(confirmLabel)}</button>
        </div>
      </div>
    </div>
  `;

  document.getElementById("confirm-close")?.addEventListener("click", closeModal);
  document.getElementById("confirm-cancel")?.addEventListener("click", closeModal);
  document.getElementById("confirm-backdrop")?.addEventListener("click", (e) => {
    if (e.target.id === "confirm-backdrop") closeModal();
  });
  document.getElementById("confirm-ok")?.addEventListener("click", async (e) => {
    const btn = e.currentTarget;
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner-sm"></span> Working...`;
    try {
      await onConfirm();
      closeModal();
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
      btn.textContent = confirmLabel;
    }
  });
}

export function openAuthModal({
  mode = "login",
  brand = { appName: "Lily API Hub", companyName: "Sonic Network" },
  googleEnabled = false,
  resetToken = "",
  onAuthSuccess,
}) {
  const root = document.getElementById("modal-root");
  if (!root) return;

  let currentMode = mode;

  const render = () => {
    const titles = {
      login: [`Sign In to ${brand.appName}`, "Access your developer keys, quotas, and Razorpay billing."],
      register: [`Create Your ${brand.companyName} Account`, "Start with a free sandbox key or unlock production scale."],
      forgot: ["Reset Password", "Enter your account email to receive a password reset link."],
      reset: ["Choose a New Password", "Set a strong password with at least 8 characters, letters, and numbers."],
    };
    const [title, subtitle] = titles[currentMode] || titles.login;

    const googleButtonHtml =
      currentMode === "login" || currentMode === "register"
        ? `
        <button type="button" class="btn btn-secondary" style="width:100%;margin-bottom:14px;" id="btn-google-oauth">
          <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
            <path fill="#EA4335" d="M12 10.2v3.9h5.4c-.2 1.3-1.5 3.9-5.4 3.9-3.3 0-6-2.7-6-6s2.7-6 6-6c1.9 0 3.1.8 3.8 1.5l2.6-2.5C16.8 3.5 14.6 2.5 12 2.5 6.8 2.5 2.5 6.8 2.5 12s4.3 9.5 9.5 9.5c5.5 0 9.1-3.9 9.1-9.3 0-.6-.1-1.1-.2-1.6H12z"/>
          </svg>
          Continue with Google
        </button>
        <div style="display:flex;align-items:center;gap:12px;margin:12px 0;color:var(--text-dim);font-size:12px;">
          <div style="flex:1;height:1px;background:var(--border-subtle);"></div>
          <span>OR WITH EMAIL</span>
          <div style="flex:1;height:1px;background:var(--border-subtle);"></div>
        </div>
      `
        : "";

    let formFields = "";
    if (currentMode === "login") {
      formFields = `
        <div class="field"><label>Email Address</label><input class="input" type="email" id="auth-email" required placeholder="dev@company.com" /></div>
        <div class="field"><label>Password</label><input class="input" type="password" id="auth-password" required placeholder="••••••••" /></div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;font-size:13px;">
          <a href="#" id="link-forgot">Forgot password?</a>
          <a href="#" id="link-to-register">Need an account? Sign up</a>
        </div>
        <button class="btn btn-primary" style="width:100%;" type="submit" id="auth-submit-btn">Sign In</button>
      `;
    } else if (currentMode === "register") {
      formFields = `
        <div class="field"><label>Full Name</label><input class="input" type="text" id="auth-name" required minlength="2" placeholder="Aarav Mehta" /></div>
        <div class="field"><label>Company / Project (Optional)</label><input class="input" type="text" id="auth-company" placeholder="${esc(brand.companyName)}" /></div>
        <div class="field"><label>Email Address</label><input class="input" type="email" id="auth-email" required placeholder="dev@company.com" /></div>
        <div class="field"><label>Password (min 8 chars, letters + numbers)</label><input class="input" type="password" id="auth-password" required minlength="8" placeholder="Create strong password" /></div>
        <div style="text-align:right;margin-bottom:16px;font-size:13px;">
          <a href="#" id="link-to-login">Already registered? Sign in</a>
        </div>
        <button class="btn btn-primary" style="width:100%;" type="submit" id="auth-submit-btn">Create Account</button>
      `;
    } else if (currentMode === "forgot") {
      formFields = `
        <div class="field"><label>Registered Email</label><input class="input" type="email" id="auth-email" required placeholder="dev@company.com" /></div>
        <div style="text-align:right;margin-bottom:16px;font-size:13px;">
          <a href="#" id="link-to-login">Back to sign in</a>
        </div>
        <button class="btn btn-primary" style="width:100%;" type="submit" id="auth-submit-btn">Send Reset Link</button>
      `;
    } else if (currentMode === "reset") {
      formFields = `
        <div class="field"><label>Reset Token</label><input class="input mono" type="text" id="auth-reset-token" required value="${esc(resetToken)}" /></div>
        <div class="field"><label>New Password (min 8 chars, letters + numbers)</label><input class="input" type="password" id="auth-new-password" required minlength="8" /></div>
        <button class="btn btn-primary" style="width:100%;" type="submit" id="auth-submit-btn">Update Password</button>
      `;
    }

    root.innerHTML = `
      <div class="modal-backdrop" id="auth-backdrop">
        <div class="modal-card">
          <div class="modal-header">
            <div>
              <h2 style="margin:0 0 6px;font-size:20px;">${esc(title)}</h2>
              <p style="margin:0;font-size:13.5px;color:var(--text-muted);">${esc(subtitle)}</p>
            </div>
            <button class="modal-close" id="auth-close">×</button>
          </div>
          ${googleButtonHtml}
          <form id="auth-form">
            <div id="auth-error-box" style="display:none;margin-bottom:12px;padding:10px 12px;border-radius:10px;background:var(--danger-bg);border:1px solid rgba(225,29,72,0.32);color:var(--danger);font-size:13px;"></div>
            ${formFields}
          </form>
        </div>
      </div>
    `;

    document.getElementById("auth-close")?.addEventListener("click", closeModal);
    document.getElementById("auth-backdrop")?.addEventListener("click", (e) => {
      if (e.target.id === "auth-backdrop") closeModal();
    });

    document.getElementById("btn-google-oauth")?.addEventListener("click", () => {
      if (!googleEnabled) {
        showToast("Google OAuth is not configured in .env yet (GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET).", "error", 5000);
        return;
      }
      window.location.href = `${apiUrl("/api/auth/google/login")}?next_route=${encodeURIComponent("/#dashboard")}&frontend_origin=${encodeURIComponent(window.location.origin)}`;
    });

    document.getElementById("link-forgot")?.addEventListener("click", (e) => {
      e.preventDefault();
      currentMode = "forgot";
      render();
    });
    document.getElementById("link-to-register")?.addEventListener("click", (e) => {
      e.preventDefault();
      currentMode = "register";
      render();
    });
    document.getElementById("link-to-login")?.addEventListener("click", (e) => {
      e.preventDefault();
      currentMode = "login";
      render();
    });

    document.getElementById("auth-form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const errBox = document.getElementById("auth-error-box");
      const btn = document.getElementById("auth-submit-btn");
      errBox.style.display = "none";
      btn.disabled = true;
      const origText = btn.textContent;
      btn.innerHTML = `<span class="spinner-sm"></span> Please wait...`;

      try {
        if (currentMode === "login") {
          const res = await api.post("/api/auth/login", {
            email: document.getElementById("auth-email").value,
            password: document.getElementById("auth-password").value,
          });
          if (res.access_token) setAuthToken(res.access_token);
          closeModal();
          showToast(`Welcome back, ${res.user.full_name || res.user.email}!`, "success");
          await onAuthSuccess?.(res.user);
        } else if (currentMode === "register") {
          const res = await api.post("/api/auth/register", {
            full_name: document.getElementById("auth-name").value,
            company: document.getElementById("auth-company").value,
            email: document.getElementById("auth-email").value,
            password: document.getElementById("auth-password").value,
          });
          if (res.access_token) setAuthToken(res.access_token);
          closeModal();
          showToast(res.message, "success", 5500);
          if (res.dev_verification_hint) {
            showToast(`Local Dev Verification Link ready: ${res.dev_verification_hint}`, "info", 8000);
          }
          await onAuthSuccess?.(res.user);
        } else if (currentMode === "forgot") {
          const res = await api.post("/api/auth/forgot-password", {
            email: document.getElementById("auth-email").value,
          });
          showToast(res.message, "success", 5500);
          if (res.dev_reset_hint) {
            closeModal();
            window.location.hash = res.dev_reset_hint.replace("/#", "#");
          } else {
            currentMode = "login";
            render();
          }
        } else if (currentMode === "reset") {
          const res = await api.post("/api/auth/reset-password", {
            token: document.getElementById("auth-reset-token").value,
            new_password: document.getElementById("auth-new-password").value,
          });
          showToast(res.message, "success");
          currentMode = "login";
          render();
        }
      } catch (err) {
        errBox.textContent = err.message;
        errBox.style.display = "block";
        btn.disabled = false;
        btn.textContent = origText;
      }
    });
  };

  render();
}

export function openCreateKeyModal(onCreate) {
  const root = document.getElementById("modal-root");
  if (!root) return;

  root.innerHTML = `
    <div class="modal-backdrop" id="key-backdrop">
      <div class="modal-card">
        <div class="modal-header">
          <div>
            <h3 style="margin:0 0 6px;">Create New API Key</h3>
            <p style="margin:0;font-size:13.5px;color:var(--text-muted);">Linked directly to your active subscription quotas and Master Gateway.</p>
          </div>
          <button class="modal-close" id="key-close">×</button>
        </div>
        <form id="create-key-form">
          <div class="field">
            <label>Key Label</label>
            <input class="input" type="text" id="new-key-name" required minlength="2" maxlength="80" placeholder="e.g. Production Backend Server" />
          </div>
          <div style="display:flex;justify-content:flex-end;gap:10px;">
            <button type="button" class="btn btn-secondary" id="key-cancel">Cancel</button>
            <button type="submit" class="btn btn-primary" id="key-submit">Generate Key</button>
          </div>
        </form>
      </div>
    </div>
  `;

  document.getElementById("key-close")?.addEventListener("click", closeModal);
  document.getElementById("key-cancel")?.addEventListener("click", closeModal);
  document.getElementById("key-backdrop")?.addEventListener("click", (e) => {
    if (e.target.id === "key-backdrop") closeModal();
  });
  document.getElementById("create-key-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("key-submit");
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner-sm"></span> Creating...`;
    try {
      await onCreate(document.getElementById("new-key-name").value);
      closeModal();
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
      btn.textContent = "Generate Key";
    }
  });
}

export function openPlanEditorModal(plan, onSaved) {
  const root = document.getElementById("modal-root");
  if (!root) return;
  const isEdit = Boolean(plan);

  root.innerHTML = `
    <div class="modal-backdrop" id="plan-backdrop">
      <div class="modal-card wide">
        <div class="modal-header">
          <div>
            <h3 style="margin:0 0 4px;">${isEdit ? `Edit Plan: ${esc(plan.name)}` : "Create Subscription Plan"}</h3>
            <p style="margin:0;font-size:13px;color:var(--text-muted);">Configure quotas, rate limits, HTTP method permissions, and Razorpay pricing.</p>
          </div>
          <button class="modal-close" id="plan-close">×</button>
        </div>
        <form id="plan-editor-form">
          <div class="two-col">
            <div class="field"><label>Plan Name</label><input class="input" id="p-name" required value="${esc(plan?.name || "")}" placeholder="Scale Turbo" /></div>
            <div class="field"><label>Slug (lowercase, hyphens)</label><input class="input mono" id="p-slug" required ${isEdit ? "disabled" : ""} value="${esc(plan?.slug || "")}" placeholder="scale-turbo" /></div>
          </div>
          <div class="field"><label>Tagline</label><input class="input" id="p-tagline" value="${esc(plan?.tagline || "")}" placeholder="Built for production SaaS workloads" /></div>
          <div class="two-col">
            <div class="field"><label>Price (INR Rupees)</label><input class="input" type="number" step="1" min="0" id="p-price-inr" required value="${plan ? Math.round(plan.price_paise / 100) : 999}" /></div>
            <div class="field"><label>Billing Cycle (Days)</label><input class="input" type="number" min="1" id="p-days" required value="${plan?.billing_cycle_days ?? 30}" /></div>
          </div>
          <div class="two-col">
            <div class="field"><label>Daily Request Limit</label><input class="input" type="number" min="1" id="p-daily" required value="${plan?.daily_request_limit ?? 10000}" /></div>
            <div class="field"><label>Monthly / Cycle Limit</label><input class="input" type="number" min="1" id="p-monthly" required value="${plan?.monthly_request_limit ?? 250000}" /></div>
          </div>
          <div class="two-col">
            <div class="field"><label>Rate Limit (Req / Min)</label><input class="input" type="number" min="1" id="p-rate" required value="${plan?.rate_limit_per_minute ?? 120}" /></div>
            <div class="field"><label>Max Active API Keys</label><input class="input" type="number" min="1" max="100" id="p-keys" required value="${plan?.max_api_keys ?? 5}" /></div>
          </div>
          <div class="two-col">
            <div class="field"><label>Allowed HTTP Methods</label><input class="input mono" id="p-methods" required value="${esc(plan?.allowed_methods || "GET,POST,PUT,PATCH,DELETE")}" /></div>
            <div class="field"><label>Allowed Endpoints Pattern</label><input class="input mono" id="p-endpoints" required value="${esc(plan?.allowed_endpoints || "*")}" /></div>
          </div>
          <div class="two-col">
            <div class="field"><label>Badge (Optional)</label><input class="input" id="p-badge" value="${esc(plan?.badge || "")}" placeholder="Most Popular" /></div>
            <div class="field"><label>Sort Order</label><input class="input" type="number" id="p-sort" value="${plan?.sort_order ?? 10}" /></div>
          </div>
          <div class="field">
            <label>Features (One per line)</label>
            <textarea class="textarea" id="p-features">${esc((plan?.features_json || []).join("\n"))}</textarea>
          </div>
          <div style="display:flex;gap:20px;margin-bottom:16px;font-size:13.5px;">
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
              <input type="checkbox" id="p-active" ${plan?.is_active !== false ? "checked" : ""} /> Active on Pricing Page
            </label>
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
              <input type="checkbox" id="p-featured" ${plan?.is_featured ? "checked" : ""} /> Highlight as Featured
            </label>
          </div>
          <div style="display:flex;justify-content:flex-end;gap:10px;">
            <button type="button" class="btn btn-secondary" id="plan-cancel">Cancel</button>
            <button type="submit" class="btn btn-primary" id="plan-submit">${isEdit ? "Save Changes" : "Create Plan"}</button>
          </div>
        </form>
      </div>
    </div>
  `;

  document.getElementById("plan-close")?.addEventListener("click", closeModal);
  document.getElementById("plan-cancel")?.addEventListener("click", closeModal);
  document.getElementById("plan-backdrop")?.addEventListener("click", (e) => {
    if (e.target.id === "plan-backdrop") closeModal();
  });

  document.getElementById("plan-editor-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("plan-submit");
    btn.disabled = true;
    const payload = {
      name: document.getElementById("p-name").value.trim(),
      tagline: document.getElementById("p-tagline").value.trim(),
      description: document.getElementById("p-tagline").value.trim(),
      price_paise: Math.round(Number(document.getElementById("p-price-inr").value) * 100),
      currency: "INR",
      billing_cycle_days: Number(document.getElementById("p-days").value),
      daily_request_limit: Number(document.getElementById("p-daily").value),
      monthly_request_limit: Number(document.getElementById("p-monthly").value),
      rate_limit_per_minute: Number(document.getElementById("p-rate").value),
      max_api_keys: Number(document.getElementById("p-keys").value),
      allowed_methods: document.getElementById("p-methods").value.trim(),
      allowed_endpoints: document.getElementById("p-endpoints").value.trim(),
      badge: document.getElementById("p-badge").value.trim() || null,
      sort_order: Number(document.getElementById("p-sort").value || 0),
      features_json: document
        .getElementById("p-features")
        .value.split("\n")
        .map((s) => s.trim())
        .filter(Boolean),
      is_active: document.getElementById("p-active").checked,
      is_featured: document.getElementById("p-featured").checked,
    };

    try {
      if (isEdit) {
        await api.patch(`/api/admin/plans/${plan.id}`, payload);
        showToast("Plan updated successfully.", "success");
      } else {
        payload.slug = document.getElementById("p-slug").value.trim();
        await api.post("/api/admin/plans", payload);
        showToast("Plan created successfully.", "success");
      }
      closeModal();
      await onSaved?.();
    } catch (err) {
      showToast(err.message, "error");
      btn.disabled = false;
    }
  });
}

