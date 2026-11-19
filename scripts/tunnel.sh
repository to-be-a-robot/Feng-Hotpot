#!/usr/bin/env bash
# Give the API running on this Mac a temporary public https address, so a
# hosted frontend (Tyler's Enter preview) can call it before it's deployed.
# The address lasts while this script and the API keep running.
#
#   1. In .env set DEV_ACCESS_KEY (anyone with the URL could otherwise act as admin)
#      and add the preview's address to CORS_ORIGINS (or a CORS_ORIGIN_REGEX).
#   2. Start the API:  cd workers && uvicorn feng_workers.api:app --port 8000
#   3. Run:            ./scripts/tunnel.sh
#   4. Give Tyler the https://....trycloudflare.com address and the DEV_ACCESS_KEY.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v cloudflared >/dev/null; then
  echo "cloudflared isn't installed. Install it with:  brew install cloudflared"
  exit 1
fi
if ! grep -qE '^DEV_ACCESS_KEY=.+' .env 2>/dev/null; then
  echo "Set DEV_ACCESS_KEY in .env first (and restart the API), or the public URL is open to anyone."
  exit 1
fi
if ! curl -fsS -m 3 http://localhost:8000/health >/dev/null; then
  echo "The API isn't answering on http://localhost:8000. Start it first:"
  echo "  cd workers && source .venv/bin/activate && uvicorn feng_workers.api:app --port 8000"
  exit 1
fi
echo "Opening a tunnel to http://localhost:8000 (Ctrl+C to close)..."
exec cloudflared tunnel --url http://localhost:8000
