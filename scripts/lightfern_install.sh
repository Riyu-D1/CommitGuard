#!/usr/bin/env bash
# Install the CommitGuard Brain app into a Lightfern library.
#
#   scripts/lightfern_install.sh <path-to-Lightfern-library>
#
# Copies the app folder in (idempotent), creates the runtime dirs, then
# prints the LIGHTFERN_APP_DIR line to add to backend/.env — it does NOT
# edit .env itself.
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "usage: $0 <path-to-Lightfern-library>" >&2
  exit 2
fi

LIB="$1"
if [ ! -d "$LIB" ]; then
  echo "error: '$LIB' is not a directory — pass your Lightfern library root" >&2
  exit 1
fi

APP_NAME="CommitGuard Brain"
SRC="$(cd "$(dirname "$0")/../lightfern/$APP_NAME" && pwd)"
DEST="$LIB/$APP_NAME"

mkdir -p "$DEST"
# Everything except runtime state; .gitkeep files are harmless to copy.
rsync -a --delete \
  --exclude 'inbox/*.json' --exclude 'inbox/done/' \
  --exclude 'live/answers/*.json' --exclude 'live/feed.json' \
  --exclude 'live/status.json' \
  "$SRC/" "$DEST/"

mkdir -p "$DEST/inbox/done" "$DEST/live/answers"

cat <<EOF

Installed: $DEST

Add this line to backend/.env, then restart the backend:

  LIGHTFERN_APP_DIR=$DEST

Verify with: curl 127.0.0.1:8000/lightfern/status
EOF
