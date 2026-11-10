# Razorpay Integration Guide — Test Mode & Live Mode

Lily API Hub integrates the official Razorpay Orders API, Checkout SDK (`checkout.js`), HMAC-SHA256 server-side payment verification, idempotent webhooks, and payment reconciliation.

---

## 1. Security Guarantees Built Into the Backend

- **Authoritative Pricing**: `POST /api/payments/create-order` ignores any client-submitted amount and reads `price_paise` directly from the `subscription_plans` table before calling `POST https://api.razorpay.com/v1/orders`.
- **HMAC-SHA256 Verification**: `POST /api/payments/verify` computes `HMAC_SHA256(RAZORPAY_KEY_SECRET, f"{razorpay_order_id}|{razorpay_payment_id}")` with constant-time comparison (`hmac.compare_digest`) AND verifies payment capture & amount directly against `GET https://api.razorpay.com/v1/payments/{id}`.
- **Idempotent Webhooks**: `POST /api/payments/webhook/razorpay` verifies the `X-Razorpay-Signature` header using `RAZORPAY_WEBHOOK_SECRET` against the raw request body bytes and records `event_id` in `webhook_events` so duplicate deliveries never generate duplicate subscriptions or duplicate API keys.
- **Zero Secret Leakage**: Only `RAZORPAY_KEY_ID` (public key) is passed to the frontend. `RAZORPAY_KEY_SECRET` and `RAZORPAY_WEBHOOK_SECRET` stay strictly on the backend.

---

## 2. Test Mode Setup (Local & Staging)

1. Log in to the [Razorpay Dashboard](https://dashboard.razorpay.com/) and toggle **Test Mode** ON (top bar).
2. Navigate to **Account & Settings → API Keys → Generate Test Key**.
3. Copy `Key Id` (`rzp_test_...`) and `Key Secret` into `.env`:
   ```env
   RAZORPAY_KEY_ID="rzp_test_xxxxxxxxxxxxxx"
   RAZORPAY_KEY_SECRET="your_test_key_secret"
   RAZORPAY_WEBHOOK_SECRET="your_chosen_webhook_secret"
   ```
4. Restart Uvicorn so the updated `.env` is loaded.
5. For local webhook testing, expose port `8000` with ngrok or Cloudflare Tunnel:
   ```bash
   ngrok http 8000
   ```
   Then configure Razorpay Webhook URL to `https://<your-ngrok-domain>/api/payments/webhook/razorpay`.
6. Subscribe to these webhook events in Razorpay:
   - `payment.captured`
   - `order.paid`
   - `payment.failed`
   - `refund.created`
   - `payment.refunded`
7. Test UPI (`success@razorpay`), Test Cards, and Netbanking methods from Razorpay's official test credentials page.

---

## 3. Live Mode Setup (Production)

1. Complete KYC & business activation inside Razorpay Dashboard.
2. Switch the dashboard toggle to **Live Mode**.
3. Generate **Live API Keys** (`rzp_live_...`) and update `.env`:
   ```env
   RAZORPAY_KEY_ID="rzp_live_xxxxxxxxxxxxxx"
   RAZORPAY_KEY_SECRET="your_live_key_secret"
   RAZORPAY_WEBHOOK_SECRET="your_live_webhook_secret"
   ```
4. Create a Live Webhook pointing to:
   `https://api.yourdomain.com/api/payments/webhook/razorpay`
   Enable `payment.captured`, `order.paid`, `payment.failed`, `refund.created`, and `payment.refunded`.
5. Run one real ₹1 test plan or starter transaction and verify:
   - `PaymentOrder` transitions `pending` → `successful`
   - Unique `lily_live_*` key is provisioned in Dashboard
   - Printable Receipt opens cleanly
   - Webhook event appears in **Admin Portal → Payments & Webhooks**

---

## 4. Handling Pending Payments & Reconciliation

If a customer completes UPI or Netbanking payment on a mobile redirect and closes the browser before `checkout.js` invokes `/verify`:
- The **Webhook** (`payment.captured` / `order.paid`) activates the plan and provisions the API key automatically.
- Customers and Administrators can also click **Check Status / Reconcile** (`POST /api/payments/reconcile/{order_id}`) to query Razorpay's `/v1/orders/{id}/payments` API and sync status immediately.

