#!/bin/bash
# CommitGuard one-command startup
cd "$(dirname "$0")/backend"
if [ ! -d .venv ]; then
  uv venv --python 3.12
  uv pip install -q -r requirements.txt
fi
echo "CommitGuard running:"
echo "  Demo UI      -> http://127.0.0.1:8000"
echo "  Inspector    -> http://127.0.0.1:8000/inspector.html"
echo "  Simulator    -> open plugin/simulator.html in a browser"
uv run uvicorn main:app --port 8000
