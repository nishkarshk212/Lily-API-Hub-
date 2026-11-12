#!/bin/sh
set -eu

# Injects API_BASE_URL env variable into config.js at static deploy build time (Vercel / Cloudflare Pages / Netlify).
CLEAN_URL=$(printf '%s' "${API_BASE_URL:-}" | sed 's:/*$::')
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

cat > "${SCRIPT_DIR}/config.js" <<EOF
window.__APP_CONFIG__ = Object.assign(
  {
    API_BASE_URL: "${CLEAN_URL}",
  },
  window.__APP_CONFIG__ || {}
);
EOF

echo "Configured frontend API_BASE_URL=${CLEAN_URL:-<same-origin>}"
