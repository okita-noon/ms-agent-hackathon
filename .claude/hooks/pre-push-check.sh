#!/usr/bin/env bash
set -euo pipefail

# Only gate "git push" commands
if ! echo "$TOOL_INPUT" | grep -q "git push"; then
  exit 0
fi

BRANCH=$(git branch --show-current)

# Skip check for main
if [ "$BRANCH" = "main" ]; then
  exit 0
fi

# Check if a PR exists for this branch and is already merged
PR_STATE=$(gh pr view "$BRANCH" --json state --jq '.state' 2>/dev/null || echo "NONE")

if [ "$PR_STATE" = "MERGED" ]; then
  echo "❌ ブランチ '$BRANCH' の PR は既にマージ済みです。"
  echo "   新しいブランチを切って、新規 PR として作成してください。"
  exit 1
fi

exit 0
