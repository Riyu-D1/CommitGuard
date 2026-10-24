#!/usr/bin/env bash
# CommitGuard demo launcher — serves the API + demo UI on 127.0.0.1:8000.
# backend/.env (if present) is loaded by the app itself; see backend/.env.example.
set -euo pipefail
cd "$(dirname "$0")/../backend"

if [ ! -f .env ]; then
  echo "hint: no backend/.env — feed will run in SIMULATED mode."
  echo "      cp .env.example .env and fill in SLACK_BOT_TOKEN + SLACK_CHANNEL_ID to go live."
  echo ""
fi

cat <<'EOF'
  CommitGuard
  ──────────────────────────────────────────────────
   demo UI      →  http://127.0.0.1:8000/
   inspector    →  http://127.0.0.1:8000/inspector.html
   slack status →  http://127.0.0.1:8000/slack/status
  ──────────────────────────────────────────────────
EOF

exec uv run uvicorn main:app --host 127.0.0.1 --port 8000
