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

# Honour LIGHTFERN_APP_DIR from backend/.env so this script alone wires the
# Lightfern file bridge (the app also loads .env itself; exporting here makes
# it explicit and shows up in the banner). Real env always wins.
if [ -z "${LIGHTFERN_APP_DIR:-}" ] && [ -f .env ]; then
  _lf=$(sed -n 's/^[[:space:]]*\(export[[:space:]]*\)\?LIGHTFERN_APP_DIR[[:space:]]*=[[:space:]]*//p' .env | tail -1 | sed 's/^["'"'"']//; s/["'"'"'][[:space:]]*$//; s/[[:space:]]*$//')
  if [ -n "$_lf" ]; then
    export LIGHTFERN_APP_DIR="$_lf"
  fi
fi

if [ -n "${LIGHTFERN_APP_DIR:-}" ]; then
  LF_LINE="   lightfern    →  $LIGHTFERN_APP_DIR"
else
  LF_LINE="   lightfern    →  off (set LIGHTFERN_APP_DIR in backend/.env)"
fi

cat <<EOF
  CommitGuard
  ──────────────────────────────────────────────────
   demo UI      →  http://127.0.0.1:8000/
   inspector    →  http://127.0.0.1:8000/inspector.html
   slack status →  http://127.0.0.1:8000/slack/status
$LF_LINE
  ──────────────────────────────────────────────────
EOF

exec uv run uvicorn main:app --host 127.0.0.1 --port 8000
