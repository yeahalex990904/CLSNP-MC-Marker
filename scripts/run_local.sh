#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -r api/requirements.txt
fi
cd api
exec ../.venv/bin/uvicorn main:app --host 0.0.0.0 --port "${PORT:-8080}" --reload
