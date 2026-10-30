#!/usr/bin/env bash
# Chạy mọi kiểm tra giống CI trước khi commit. Dừng ngay khi có bước lỗi.
set -euo pipefail
cd "$(dirname "$0")/.."
unset VIRTUAL_ENV

echo "== backend"
(
  cd backend
  uv run ruff check .
  uv run ruff format --check .
  uv run mypy app
  uv run pytest -q
  uv run python -m app.cli export-import-docs ../docs/IMPORT_TEMPLATES.md >/dev/null
)
git diff --exit-code docs/IMPORT_TEMPLATES.md

echo "== frontend"
pnpm api:generate >/dev/null
git diff --exit-code packages/api-client
pnpm typecheck
pnpm lint
pnpm --filter web build >/dev/null
echo "OK - tất cả kiểm tra đều qua"
