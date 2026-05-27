#!/usr/bin/env bash
set -euo pipefail

# Only gate "gh pr create" commands
if ! echo "$TOOL_INPUT" | grep -q "gh pr create"; then
  exit 0
fi

echo "PR作成前チェックを実行中..."
FAILED=0

# 1. ruff check
if ! ruff check src/ tests/ 2>&1; then
  echo "❌ ruff check 失敗。修正してから PR を作成してください。"
  FAILED=1
fi

# 2. ruff format
if ! ruff format --check src/ tests/ 2>&1; then
  echo "❌ ruff format 失敗。ruff format src/ tests/ を実行してください。"
  FAILED=1
fi

# 3. Frontend type check (if frontend files changed)
if git diff origin/main --name-only | grep -q "^frontend/"; then
  if [ -f frontend/tsconfig.app.json ]; then
    if ! npx --prefix frontend tsc --project tsconfig.app.json --noEmit 2>&1; then
      echo "❌ フロントエンドの型チェック失敗。TypeScript エラーを修正してください。"
      FAILED=1
    fi
  fi
fi

# 4. Conflict check
git fetch origin main --quiet 2>/dev/null || true
if ! git merge origin/main --no-commit --no-ff 2>&1; then
  git merge --abort 2>/dev/null || true
  echo "❌ main とコンフリクトがあります。解消してから PR を作成してください。"
  FAILED=1
else
  git merge --abort 2>/dev/null || true
fi

if [ "$FAILED" -eq 1 ]; then
  exit 1
fi

echo "✅ すべてのチェックに通過しました。"
