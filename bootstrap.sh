#!/usr/bin/env bash
# Optional first-time helper: install deps and create .env from .env.example.
# From repo root: ./bootstrap.sh  (or: bash bootstrap.sh)
set -euo pipefail

if ! command -v uv &>/dev/null; then
  echo "uv is not on PATH. Install it: https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi

uv sync

if [[ -f .env ]]; then
  echo ".env already exists; not overwriting."
else
  cp .env.example .env
  echo "Created .env from .env.example — set PIPEFY_OAUTH_CLIENT, PIPEFY_OAUTH_SECRET, and any optional keys."
fi
