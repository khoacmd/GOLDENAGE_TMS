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
  uv run mypy app optimization worker
  uv run pytest -q
)

# File sinh tự động phải khớp code: sinh lại rồi so với bản hiện có trên đĩa.
unchanged() {
  local before
  before=$(cat "$@" | sha256sum)
  "${GENERATE[@]}" >/dev/null
  [[ $(cat "$@" | sha256sum) == "$before" ]] || { echo "Chưa cập nhật: $* (đã sinh lại, hãy commit)"; exit 1; }
}
GENERATE=(bash -c "cd backend && uv run python -m app.cli export-import-docs ../docs/IMPORT_TEMPLATES.md")
unchanged docs/IMPORT_TEMPLATES.md

echo "== frontend"
GENERATE=(pnpm api:generate)
unchanged packages/api-client/openapi.json packages/api-client/src/schema.d.ts
pnpm typecheck
pnpm lint
pnpm --filter web build >/dev/null
echo "OK - tất cả kiểm tra đều qua"
